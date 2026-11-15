"""Destination routes use the existing worker without replacing the user's route."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.physical_waypoints import external_candidate_payload, validate_route_document, admit_candidate_route
from scripts.waypoint_candidate_adoption import _compare_candidate, _adoption_digest, validate_adopted_route
from scripts.waypoints_cli import build_parser
from tests.test_waypoint_candidate_adoption import native
from tests.test_waypoint_navigation_candidate import sample
from tests import test_waypoint_cli_gui as gui_harness


def adopted():
    evidence = native()
    context = evidence["routeContext"]
    context.update(zoneIdCandidate="z00000001ABCDEF00", rawZoneKey=1, playerKey="1")
    evidence["recording"]["identity"]["runtimeIdentity"]["unitKey"] = "1"
    route = _compare_candidate(sample(), evidence, context, candidate_start=0, candidate_end=1,
                               native_start=0, native_end=2, direction="forward")
    route["candidateAdoption"]["integritySha256"] = _adoption_digest(route)
    return route


def save(path, document):
    raw = (json.dumps(document, allow_nan=False) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class PayloadTests(unittest.TestCase):
    def test_exact_snapshot_and_order_preserve_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            route = adopted()
            original = copy.deepcopy(route)
            digest = save(path, route)
            payload = external_candidate_payload(path, digest)
            self.assertEqual(payload["sourceIndices"], [0, 1])
            self.assertEqual(payload["admissionDocument"], route)
            self.assertEqual(payload["externalRouteSha256"].lower(), digest)
            self.assertEqual(route, original)
            path.write_text("{}")
            self.assertEqual(payload["admissionDocument"], original)
            with self.assertRaisesRegex(ValueError, "changed after planning"):
                external_candidate_payload(path, digest)

    def test_raw_review_is_rejected_at_import_and_admission(self):
        route = {"waypoints": [["A", 0, 0]], "riftWorldCandidate": {"status": "review-candidate"}}
        for function, args in ((validate_route_document, (route,)),
                               (admit_candidate_route, (None, route)),
                               (validate_adopted_route, (route, None, None, "forward"))):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError, "scoped-adoption"):
                function(*args)

    def test_external_route_requires_real_adoption_and_supported_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            digest = save(path, {"waypoints": [["A", 0, 0]]})
            with self.assertRaisesRegex(ValueError, "scoped candidate adoption"):
                external_candidate_payload(path, digest)
            digest = save(path, adopted())
            with self.assertRaisesRegex(ValueError, "direction-unsupported"):
                external_candidate_payload(path, digest, direction="reverse")
            with self.assertRaisesRegex(ValueError, "starting point"):
                external_candidate_payload(path, digest, from_point=0)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                external_candidate_payload(path, "bad")

    def test_cli_exposes_external_identity_and_stop_token(self):
        args = build_parser().parse_args(["route", "run", "--file", "route.json",
            "--route-sha256", "a" * 64, "--stop-epoch", "123.25", "--execute"])
        self.assertEqual(args.file, Path("route.json"))
        self.assertEqual(args.stop_epoch, 123.25)


EXTERNAL_CHILD = gui_harness.CHILD.replace("class Position:\n    x: float = 12.0\n    y: float = 3.0\n    z: float = 24.0",
                               "class Position:\n    x: float = 0.0\n    y: float = 1.0\n    z: float = 2.0")
EXTERNAL_CHILD = EXTERNAL_CHILD.replace("app.run_route = route", """
app.run_route = route
import scripts.continuous_move as continuous
def external_runner(adapter, points, stop, emit, **kw):
    kw['entry_check'](Position())
    (root / 'external-points.json').write_text(__import__('json').dumps(points))
    return route(adapter, points, stop, emit, **kw)
continuous.run_continuous_route = external_runner
""")


class ExternalMailboxTests(unittest.TestCase):
    """Real hidden Tk/mailbox path with fake adapter and movement; no game access."""
    cleanup_child = gui_harness.GuiBridgeTests.cleanup_child
    call = gui_harness.GuiBridgeTests.call

    def setUp(self):
        # Reuse the mature offline session harness with only our worker adapter.
        with patch("tests.test_waypoint_cli_gui.CHILD", EXTERNAL_CHILD):
            gui_harness.GuiBridgeTests.setUp(self)

    def test_external_route_preserves_dirty_loaded_route_and_checkpoint(self):
        self.assertTrue(self.call("route.add", {"name": "Unsaved", "x": 10, "z": 20})["ok"])
        before = self.call("route.list")["data"]
        checkpoint = self.root / "artifacts" / "preserve-checkpoint.json"
        checkpoint.write_bytes(b"preserve")
        self.assertTrue(self.call("move.mode", {"engine": "continuous"})["ok"])
        digest = save(self.root / "adopted.json", adopted())
        controls = self.call("status")["data"]["controls"]
        response = self.call("route.run", {"file": str(self.root / "adopted.json"),
            "route_sha256": digest, "stop_epoch": controls["stopEpoch"], "execute": True})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["data"]["executedRouteSha256"].lower(), digest)
        receipt = json.loads(Path(response["data"]["receipt"]).read_text())
        self.assertEqual(receipt["externalRouteSha256"].lower(), digest)
        self.assertTrue(receipt["requestId"])
        self.assertEqual(receipt["requestId"], response["requestId"])
        self.assertTrue((self.root / "movement-called").exists())
        after = self.call("route.list")["data"]
        for key in ("document", "revision", "dirty", "selected", "file"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(checkpoint.read_bytes(), b"preserve")

    def test_stop_invalidates_destination_before_worker_start(self):
        digest = save(self.root / "adopted.json", adopted())
        old = self.call("status")["data"]["controls"]["stopEpoch"]
        self.assertTrue(self.call("stop")["ok"])
        response = self.call("route.run", {"file": str(self.root / "adopted.json"),
            "route_sha256": digest, "stop_epoch": old, "execute": True})
        self.assertFalse(response["ok"], response)
        self.assertEqual(response["error"]["code"], "cancelled-by-stop")
        self.assertFalse((self.root / "movement-called").exists())
        self.assertTrue(self.call("status")["data"]["controls"]["stopLatched"])


if __name__ == "__main__":
    unittest.main()
