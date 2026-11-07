import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from scripts.inspect_typed_resource import ResourceInspectionError, inspect, main


FIELDS = {
    "coordX": {"status": "ok", "value": 1}, "coordY": {"status": "ok", "value": 2},
    "coordZ": {"status": "ok", "value": 3}, "health": {"status": "ok", "value": 4},
    "healthMax": {"status": "ok", "value": 5}, "mana": {"status": "ok", "value": 3980},
    "manaMax": {"status": "ok", "value": 4000}, "combat": {"status": "unavailable"},
    "dead": {"status": "unavailable"}, "mounted": {"status": "unavailable"},
    "zone": {"status": "unavailable"}, "power": {"status": "unavailable"},
    "combo": {"status": "ok", "value": 0}, "planar": {"status": "ok", "value": 3},
    "planarMax": {"status": "ok", "value": 3},
}


def wire(sequence=7, mana=None):
    fields = json.loads(json.dumps(FIELDS))
    if mana is not None:
        fields["mana"] = mana
    value = {
        "schemaVersion": 2, "addon": "RiftReaderApiProbe", "addonVersion": "0.6.0",
        "source": "rift-api", "sequence": sequence,
        "clock": {"status": "ok", "domain": "Inspect.Time.Frame", "value": 12.5 + sequence},
        "player": {"status": "ok", "unitId": "u035400012FA2D678", "fields": fields},
        "target": {"status": "absent", "fields": {name: {"status": "unavailable"} for name in FIELDS}},
        "nativeTextEntryState": "unknown", "autonomousInputReady": False,
    }
    return b"RRAPIVAL2|" + json.dumps(value, separators=(",", ":"), sort_keys=True).encode() + b"|RRAPIVALEND"


def snapshot(path: Path, payload: bytes, *, corrupt=False):
    data = b"x" * 19 + payload + b"y" * 11
    sha = hashlib.sha256(data).hexdigest().upper()
    value = {
        "schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1", "status": "complete",
        "identity": {"processId": 7164, "processStartUtcTicks": 123, "executableSha256": "A" * 64},
        "startedAtUtc": "2026-11-06T12:00:00Z", "completedAtUtc": "2026-11-06T12:00:01Z",
        "chunks": [{"address": "0x1000", "requestedByteLength": len(data), "status": "success",
                    "bytesRead": len(data), "bytesBase64": base64.b64encode(data).decode(),
                    "bytesSha256": "0" * 64 if corrupt else sha}],
    }
    path.write_text(json.dumps(value), encoding="utf-8")


class TypedResourceInspectionTests(unittest.TestCase):
    def test_cli_requires_explicit_current_or_historical_source(self):
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["--snapshot", "missing.json", "--resource", "mana"])
        self.assertEqual(2, raised.exception.code)
        self.assertIn("one of the arguments --session-id --historical-rrapival2 is required",
                      stderr.getvalue())

    def test_cli_allows_explicit_historical_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire())
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["--snapshot", str(path), "--resource", "mana",
                               "--historical-rrapival2"])
        self.assertEqual(0, result)
        report = json.loads(stdout.getvalue())
        self.assertEqual(3980, report["selected"]["current"]["value"])

    def test_extracts_mana_and_maximum(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire())
            result = inspect(path, "mana")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["selected"]["playerUnitId"], "u035400012FA2D678")
        self.assertEqual(result["selected"]["current"]["value"], 3980)
        self.assertEqual(result["selected"]["maximum"]["value"], 4000)

    def test_selects_latest_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire(7) + b"padding" + wire(9))
            result = inspect(path, "mana")
        self.assertEqual(result["selected"]["sequence"], 9)

    def test_unavailable_mana_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire(mana={"status": "unavailable"}))
            result = inspect(path, "mana")
        self.assertEqual(result["status"], "unavailable")

    def test_corrupt_chunk_hash_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire(), corrupt=True)
            with self.assertRaisesRegex(ResourceInspectionError, "chunk-sha256"):
                inspect(path, "mana")

    def test_duplicate_wire_key_fails_closed(self):
        bad = wire().replace(b'"sequence":7', b'"sequence":8,"sequence":7')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, bad)
            with self.assertRaisesRegex(ResourceInspectionError, "malformed-or-incomplete"):
                inspect(path, "mana")


class RR2ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(__file__).parents[1] / "contracts/addon/fixtures/reference-v1.json").read_text())
        cls.nonce = cls.fixture["nonce"]

    def inspect_root(self, root=None, payload=None):
        if payload is None:
            payload = b"RR2R1|" + json.dumps(root, separators=(",", ":")).encode("ascii") + b"|ENDRR2R1"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, payload)
            return inspect(path, "mana", self.nonce)

    def test_cli_current_path_requires_and_accepts_exact_session_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, self.fixture["beforeFrame"].encode("ascii"))
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["--snapshot", str(path), "--resource", "mana",
                               "--session-id", self.nonce])
        self.assertEqual(0, result)
        self.assertEqual("RR2R1", json.loads(stdout.getvalue())["selected"]["protocol"])

    def test_shared_fixture_rr2_only_and_zero_false(self):
        result = self.inspect_root(payload=self.fixture["beforeFrame"].encode("ascii"))
        self.assertEqual(result["selected"]["sessionId"], self.nonce)
        self.assertEqual(result["selected"]["protocol"], "RR2R1")
        root = json.loads(json.dumps(self.fixture["before"]))
        root["fields"]["mana"] = {"status": "ok", "value": 0}
        root["fields"]["combat"] = {"status": "ok", "value": False}
        selected = self.inspect_root(root)["selected"]
        self.assertEqual(selected["current"]["value"], 0)
        self.assertIs(selected["fields"]["combat"]["value"], False)

    def test_foreign_nonce_and_legacy_never_satisfy_binding(self):
        root = dict(self.fixture["before"], sessionId="a" * 32)
        with self.assertRaisesRegex(ResourceInspectionError, "session-mismatch"):
            self.inspect_root(root)
        with self.assertRaisesRegex(ResourceInspectionError, "no-complete"):
            self.inspect_root(payload=wire())

    def test_epoch_conflict_and_same_sequence_conflict_fail(self):
        before = self.fixture["beforeFrame"].encode("ascii")
        for changes in ({"epoch": 2, "sequence": 2}, {"clock": {"status": "ok", "value": 999}}):
            root = dict(self.fixture["before"], **changes)
            payload = before + b"RR2R1|" + json.dumps(root).encode() + b"|ENDRR2R1"
            with self.subTest(changes=changes), self.assertRaises(ResourceInspectionError):
                self.inspect_root(payload=payload)

    def test_matching_frame_cannot_mask_foreign_nonce(self):
        foreign = dict(self.fixture["after"], sessionId="a" * 32)
        payload = (self.fixture["beforeFrame"].encode("ascii") + b"RR2R1|"
                   + json.dumps(foreign).encode("ascii") + b"|ENDRR2R1")
        with self.assertRaisesRegex(ResourceInspectionError, "session-mismatch"):
            self.inspect_root(payload=payload)

    def test_static_non_json_marker_is_not_a_frame(self):
        payload = b"RR2R1|\x00static marker" + self.fixture["beforeFrame"].encode("ascii")
        self.assertEqual(self.inspect_root(payload=payload)["status"], "available")

    def test_status_propagation_and_types_fail_closed(self):
        for change in ("clock", "player", "bool", "zone", "integer"):
            root = json.loads(json.dumps(self.fixture["before"]))
            if change in ("clock", "player"):
                root[change] = {"status": "invalid"}
            elif change == "bool":
                root["fields"]["dead"] = {"status": "ok", "value": 0}
            elif change == "zone":
                root["fields"]["zone"] = {"status": "ok", "value": "a\x00b"}
            else:
                root["sequence"] = True
            with self.subTest(change=change), self.assertRaises(ResourceInspectionError):
                self.inspect_root(root)

    def test_latest_unavailable_clears_previous_value(self):
        root = json.loads(json.dumps(self.fixture["after"]))
        root["clock"] = {"status": "unavailable"}
        root["player"] = {"status": "unavailable"}
        root["fields"] = {name: {"status": "unavailable"} for name in FIELDS}
        payload = self.fixture["beforeFrame"].encode() + b"RR2R1|" + json.dumps(root).encode() + b"|ENDRR2R1"
        result = self.inspect_root(payload=payload)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["selected"]["sequence"], root["sequence"])

    def test_suffix_literal_in_zone_does_not_truncate(self):
        root = json.loads(json.dumps(self.fixture["before"]))
        root["fields"]["zone"] = {"status": "ok", "value": "prefix|ENDRR2R1suffix"}
        self.assertEqual(self.inspect_root(root)["status"], "available")


if __name__ == "__main__":
    unittest.main()
