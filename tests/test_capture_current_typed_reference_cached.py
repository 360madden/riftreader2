import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "capture_current_typed_reference_cached",
    Path(__file__).parents[1] / "scripts/capture_current_typed_reference_cached.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class CachedTypedReferenceTests(unittest.TestCase):
    def workflow(self, folder: str, reader_sha: str = capture.EXPECTED_READER_SHA,
                 guest_directory: str = r"C:\managed\reader") -> Path:
        path = Path(folder) / "workflow.json"
        path.write_text(json.dumps({"schemaVersion": 1, "guestDirectory": guest_directory,
                                    "readerSha256": reader_sha}), encoding="utf-8")
        return path

    def test_workflow_resolves_exact_managed_reader_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.workflow(folder)
            value, workflow_sha, reader, reader_sha = capture.load_workflow(path)
            self.assertEqual(capture.EXPECTED_READER_SHA, reader_sha)
            self.assertEqual(r"C:\managed\reader\RiftReader2.Live.exe", reader)
            self.assertEqual(capture.sha(path.read_bytes()), workflow_sha)
            self.assertEqual(reader_sha, value["readerSha256"])

    def test_workflow_rejects_bad_reader_pin_and_symlink_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            for bad in ("A" * 64, "a" * 64, "A" * 63, True, None):
                path = self.workflow(folder, bad)
                with self.subTest(bad=bad), self.assertRaisesRegex(
                        ValueError, "managed-reader-pin-invalid"):
                    capture.load_workflow(path)

    def test_workflow_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "workflow.json"
            path.write_text('{"guestDirectory":"C:/one","guestDirectory":"C:/two",'
                            '"readerSha256":"' + capture.EXPECTED_READER_SHA + '",'
                            '"schemaVersion":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
                capture.load_workflow(path)

    def test_workflow_and_source_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.workflow(folder)
            _, workflow_sha, _, _ = capture.load_workflow(path)
            pins = capture.source_pins()
            capture.require_pins(pins, workflow_sha, path)
            path.write_text(json.dumps({"schemaVersion": 1, "guestDirectory": r"C:\other",
                                        "readerSha256": capture.EXPECTED_READER_SHA}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "workflow-changed"):
                capture.require_pins(pins, workflow_sha, path)
            bad_pins = dict(pins)
            bad_pins[str(Path(capture.__file__).resolve())] = "0" * 64
            with self.assertRaisesRegex(ValueError, "source-changed"):
                capture.require_pins(bad_pins, capture.sha(path.read_bytes()), path)

    def test_workflow_requires_schema_absolute_path_and_accepted_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            for schema, directory in ((2, r"C:\managed\reader"), (1, "relative"),
                                      (1, r"C:\managed\..\reader")):
                path = self.workflow(folder, guest_directory=directory)
                value = json.loads(path.read_text(encoding="utf-8"))
                value["schemaVersion"] = schema
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(schema=schema, directory=directory), self.assertRaises(ValueError):
                    capture.load_workflow(path)

    def test_identity_is_strict_and_duplicate_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "identity.json"
            value = {"schemaVersion": 1, "evidenceKind": "cached-reader-game-identity/1",
                     "pid": 7, "ticks": 9, "sha": capture.GAME_SHA,
                     "readerSha": capture.EXPECTED_READER_SHA}
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(7, capture.load_identity(
                path, game_sha=capture.GAME_SHA,
                reader_sha=capture.EXPECTED_READER_SHA)["pid"])
            path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
                capture.load_identity(path, game_sha=capture.GAME_SHA,
                                      reader_sha=capture.EXPECTED_READER_SHA)

    def test_exclusive_writes_and_transfer_publication_refuse_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "final.json"
            capture.write_new_text(destination, "one")
            with self.assertRaises(FileExistsError):
                capture.write_new_text(destination, "two")
            transfer = root / "transfer.json"
            transfer.write_text("new", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "destination-exists"):
                capture.publish_transfer(transfer, destination)
            self.assertEqual("one", destination.read_text(encoding="utf-8"))

    def test_artifact_receipt_is_self_locating_and_content_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "proof.json"
            path.write_bytes(b"proof")
            receipt = capture.artifact_receipt({"archiveProof": path})["archiveProof"]
            self.assertEqual(str(path.resolve()), receipt["path"])
            self.assertEqual(5, receipt["byteLength"])
            self.assertEqual(capture.sha(b"proof"), receipt["sha256"])

    def test_source_pins_are_absolute_and_include_strict_verifier(self):
        pins = capture.source_pins()
        scripts = Path(capture.__file__).parents[1] / "scripts"
        for name in ("verify_typed_inline_archive.py", "vm_console_native.py",
                     "vmware_guest_session.py"):
            with self.subTest(name=name):
                self.assertIn(str((scripts / name).resolve()), pins)
        self.assertTrue(all(Path(path).is_absolute() for path in pins))
        self.assertTrue(all(capture.SHA_PATTERN.fullmatch(value) for value in pins.values()))

    def test_both_recovered_runs_must_bind_exact_host_request(self):
        request_sha = "A" * 64
        proof = {"runs": [{"inputRequestSha256": request_sha},
                          {"inputRequestSha256": request_sha}]}
        capture.require_proof_request(proof, request_sha)
        for bad in (
                {"runs": [{"inputRequestSha256": request_sha},
                           {"inputRequestSha256": "B" * 64}]},
                {"runs": [{"inputRequestSha256": request_sha}]},
                {"runs": [{"inputRequestSha256": request_sha}, {}]},
                None):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, "host-request-mismatch"):
                capture.require_proof_request(bad, request_sha)

    def test_source_contains_no_reader_bundle_upload(self):
        source = Path(capture.__file__).read_text(encoding="utf-8")
        self.assertNotIn('copyFileFromHostToGuest", str(reader)', source)
        self.assertIn('readerTransferredToGuest": False', source)
        self.assertIn("managed-reader-sha-mismatch-before", source)
        self.assertIn("managed-reader-sha-mismatch-after", source)
        self.assertIn("postflight-game-build-changed", source)
        self.assertIn('"sourcePins"', source)

    def test_non_lab1_fails_before_live_configuration(self):
        with self.assertRaisesRegex(ValueError, "session-id-required"):
            capture.capture("lab2")


class RR2CaptureRoutingTests(unittest.TestCase):
    def test_legacy_cached_reader_never_used_for_current_reference(self):
        with self.assertRaisesRegex(ValueError, "reviewed-reader"):
            capture.capture(session_id="a" * 32)

    def test_reviewed_reader_path_and_nonce_are_forwarded(self):
        from unittest.mock import patch
        with patch("scripts.capture_current_typed_reference.capture", return_value={"status": "fixture"}) as staged:
            result = capture.capture("lab2", session_id="a" * 32,
                                     reader=Path("reviewed.exe"), reader_sha256="A" * 64)
        staged.assert_called_once_with("lab2", Path("reviewed.exe"), "A" * 64, "a" * 32)
        self.assertEqual(result["status"], "fixture")


if __name__ == "__main__":
    unittest.main()
