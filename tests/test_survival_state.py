"""Source-bound offline survival assessment, including decoded RR2R1 zero/false values."""
import base64
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import survival_state as survival


ROOT = Path(__file__).resolve().parents[1]
BUILD = "A" * 64
SELF = "u0000000000000007"
UTC = "2026-11-14T05:57:"


class SurvivalTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.summary = self.folder / "summary.json"
        fields = {"player-context": {"sampledAtUtc": UTC + "01Z",
                  "combat": {"status": "raw-byte-candidate", "candidate": False, "rawByte": 0},
                  "level": {"status": "alternate-component-unavailable", "rawCandidate": 40},
                  "target": {"status": "raw-getter-zero-candidate", "unitIdCandidate": None}},
                  "vitals": {"sampledAtUtc": UTC + "03Z",
                  "health": {"status": "calculated-candidate", "current": 0, "maximum": 150}}}
        for key in ("energy", "mana"):
            fields["vitals"][key] = {"status": "unavailable", "current": None,
                                     "maximum": None, "unavailableReason": "wrong-kind"}
        self.identity = {"processId": 27, "processStartUtcTicks": 123, "executableSha256": BUILD}
        self.replayed = {"target": dict(self.identity, processStartUtcTicks="123"),
                         "selfKeyCandidate": "7", "summarySha256": "C" * 64,
                         "candidateValues": fields, "sources": {}}
        for kind, values in fields.items():
            data = json.dumps({"observations": [{"startedAtUtc": values["sampledAtUtc"],
                               "completedAtUtc": values["sampledAtUtc"]}]}).encode()
            (self.folder / (kind + ".json")).write_bytes(data)
            self.replayed["sources"][kind] = {"sha256": hashlib.sha256(data).hexdigest().upper()}
        mock = patch.object(survival, "verified_state", return_value=self.replayed)
        mock.start()
        self.addCleanup(mock.stop)
        fixture = json.loads((ROOT / "contracts/addon/fixtures/reference-v1.json").read_text())
        self.frame = fixture["before"]
        self.frame["player"] = {"status": "ok", "value": SELF}
        self.nonce = fixture["nonce"]

    def snapshot(self, second, seq, *, update=None, identity=None):
        frame = deepcopy(self.frame)
        frame.update(sequence=seq, clock={"status": "ok", "value": seq + 1.5})
        frame["fields"].update(health={"status": "ok", "value": 0},
                               healthMax={"status": "ok", "value": 150},
                               combat={"status": "ok", "value": False}, dead={"status": "ok", "value": True})
        if update:
            update(frame)
        wire = b"RR2R1|" + json.dumps(frame).encode("ascii") + b"|ENDRR2R1"
        size = len(wire)
        summary = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1", "status": "complete",
                   "identity": identity or self.identity, "startedAtUtc": UTC + f"{second:02}.00Z",
                   "completedAtUtc": UTC + f"{second:02}.05Z",
                   "chunks": [{"address": "0x1000", "status": "success", "bytesRead": size,
                   "requestedByteLength": size, "bytesBase64": base64.b64encode(wire).decode(),
                   "bytesSha256": hashlib.sha256(wire).hexdigest().upper()}]}
        path = self.folder / f"ref-{second}.json"
        path.write_text(json.dumps(summary))
        return path

    def compare(self, before, after, **kwargs):
        return survival.assess(self.summary, before=before, after=after, session_id=self.nonce, **kwargs)

    def test_candidates_are_never_live_engagement_readiness(self):
        result = survival.assess(self.summary)
        fields = result["fields"]
        self.assertFalse(result["engagement"]["ready"])
        self.assertIsNone(fields["dead"]["value"])
        self.assertEqual(fields["health"]["value"], {"current": 0, "maximum": 150})
        self.assertIs(fields["combat"]["value"], False)
        self.assertIsNone(fields["playerLevel"]["value"])
        self.assertEqual(fields["playerLevel"]["rawCandidate"], 40)
        for key in ("mana", "hostility", "selectedTarget", "targetLevel", "abilityReadiness"):
            self.assertEqual(fields[key]["availability"], "unavailable")

    def test_reference_decodes_actual_bytes_and_compares_capture_intervals_per_field(self):
        result = self.compare(self.snapshot(0, 1), self.snapshot(3, 2))
        self.assertEqual(result["fields"]["dead"]["value"], True)
        comparisons = result["reference"]["comparisons"]
        self.assertEqual(comparisons["health"]["status"], "agree")
        self.assertEqual(comparisons["healthMax"]["status"], "agree")
        self.assertEqual(comparisons["combat"]["status"], "outside-comparison-window")
        self.assertAlmostEqual(comparisons["combat"]["captureSpanSeconds"], 2.05)
        self.assertFalse(result["engagement"]["ready"])

    def test_disagreement_and_unavailable_are_independent(self):
        def change(frame):
            frame["fields"]["health"] = {"status": "ok", "value": 10}
            frame["fields"]["healthMax"] = {"status": "unavailable"}
        comparisons = self.compare(self.snapshot(0, 1), self.snapshot(2, 2, update=change))["reference"]["comparisons"]
        self.assertEqual(comparisons["health"]["status"], "disagree")
        self.assertEqual(comparisons["healthMax"]["status"], "unavailable")
        self.assertEqual(comparisons["combat"]["status"], "agree")

    def test_wrong_identity_player_nonce_or_epoch_fails_closed(self):
        before = self.snapshot(0, 1)
        for after in (
            lambda: self.snapshot(2, 2, identity=dict(self.identity, processStartUtcTicks=124)),
            lambda: self.snapshot(2, 2, update=lambda f: f["player"].update(value="other")),
            lambda: self.snapshot(2, 2, update=lambda f: f.update(sessionId="1"*32)),
            lambda: self.snapshot(2, 2, update=lambda f: f.update(epoch=f["epoch"]+1)),
            lambda: self.snapshot(2, 1),
        ):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.compare(before, after())

    def test_comparison_refuses_changed_native_source_or_corrupt_reference(self):
        before, after = self.snapshot(0, 1), self.snapshot(2, 2)
        source = self.folder / "vitals.json"
        source.write_text(source.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            self.compare(before, after)
        raw = json.loads(after.read_text())
        raw["chunks"][0]["bytesSha256"] = "0"*64
        after.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, "chunk-sha256"):
            self.compare(before, after)

    def test_incomplete_reference_arguments_return_json_error(self):
        output = StringIO()
        with redirect_stdout(output):
            code = survival.main(["--summary", str(self.summary), "--session-id", self.nonce])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["engagement"]["ready"])


class RetainedEvidenceTests(unittest.TestCase):
    def test_actual_physical_source_and_cli(self):
        path = ROOT / "artifacts/physical-state-20261114-0058-21672/summary.json"
        if not path.is_file():
            self.skipTest("Retained AMD-DESKTOP composite unavailable")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(survival.main(["--summary", str(path)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["fields"]["health"]["value"], {"current": 18208, "maximum": 18208})
        self.assertEqual(result["fields"]["combat"]["rawByte"], 0)
        self.assertIsNone(result["fields"]["selectedTarget"]["value"])
        self.assertFalse(result["engagement"]["ready"])


if __name__ == "__main__":
    unittest.main()
