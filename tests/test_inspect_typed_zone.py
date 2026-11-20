"""Bounded offline RR2R1 zone-field extraction, never a live-game assertion."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.inspect_typed_resource import ResourceInspectionError, inspect, main
from tests.test_inspect_typed_resource import snapshot, wire

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/addon/fixtures/reference-v1.json"
SOURCE = json.loads(FIXTURE.read_text(encoding="utf-8"))
NONCE = SOURCE["nonce"]


def reference(*, zone="z487C9102D2EA79BE", seq=None):
    payload = json.loads(json.dumps(SOURCE["before"]))
    payload["fields"]["zone"] = zone if isinstance(zone, dict) else {"status": "ok", "value": zone}
    if seq is not None:
        payload["sequence"] = seq
    return b"RR2R1|" + json.dumps(payload, separators=(",", ":")).encode("ascii") + b"|ENDRR2R1"


class ZoneSourceTests(unittest.TestCase):
    def read(self, raw, session=NONCE):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, raw)
            return inspect(path, "zone", session)

    def test_extract_statused_zone_with_exact_nonce_and_preserve_identity(self):
        value = self.read(reference())
        self.assertEqual(value["status"], "available")
        self.assertEqual(value["selected"]["protocol"], "RR2R1")
        self.assertEqual(value["selected"]["sessionId"], NONCE)
        self.assertEqual(value["selected"]["resource"], "zone")
        self.assertIsNone(value["selected"]["maximum"])
        self.assertEqual(value["selected"]["current"], {"status": "ok", "value": "z487C9102D2EA79BE"})
        self.assertEqual(value["identity"]["processId"], 7164)
        self.assertEqual(value["completedAtUtc"], "2026-11-06T12:00:01Z")

    def test_absent_or_invalid_zone_does_not_invent_id(self):
        unavailable = self.read(reference(zone={"status": "unavailable"}))
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["selected"]["current"], {"status": "unavailable"})
        invalid = self.read(reference(zone={"status": "invalid"}))
        self.assertEqual(invalid["status"], "unavailable")
        self.assertEqual(invalid["selected"]["current"], {"status": "invalid"})

    def test_newest_frame_wins_without_borrowing_stale_zone(self):
        old = reference(seq=1)
        new = reference(zone={"status": "unavailable"}, seq=2)
        result = self.read(old + b"between" + new)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["selected"]["sequence"], 2)

    def test_wrong_nonce_or_wrong_zone_value_type_refused(self):
        with self.assertRaisesRegex(ResourceInspectionError, "session-mismatch"):
            self.read(reference(), session="a" * 32)
        payload = reference(zone=123)
        with self.assertRaisesRegex(ResourceInspectionError, "malformed-or-incomplete"):
            self.read(payload)

    def test_current_zone_cannot_use_historical_resource_mode(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, wire())
            with self.assertRaisesRegex(ResourceInspectionError, "zone-requires-rr2r1-session-id"):
                inspect(path, "zone", None)
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["--snapshot", str(path), "--resource", "zone", "--historical-rrapival2"])
            self.assertEqual(code, 2)
            self.assertIn("zone-requires-rr2r1-session-id", err.getvalue())

    def test_cli_current_zone_source_decodes(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            snapshot(path, reference())
            out = StringIO()
            with redirect_stdout(out):
                code = main(["--snapshot", str(path), "--resource", "zone", "--session-id", NONCE])
            self.assertEqual(code, 0)
            value = json.loads(out.getvalue())
            self.assertEqual(value["selected"]["current"]["value"], "z487C9102D2EA79BE")


if __name__ == "__main__":
    unittest.main()
