"""Offline fail-closed tests for the optional physical native zone bracket."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import collect_physical_player_state as state
from tests import test_collect_physical_player_state as baseline

SELF_KEY = "239816685251645959"
ZONE_ID = "z487C9102D2EA79BE"
UPDATED_SHA = next(sha for sha in state.SUPPORTED_BUILDS if sha != state.BUILD_SHA)


class ZoneBracketTests(unittest.TestCase):
    def setUp(self):
        # Keep fake acquisitions independent of the host reader registration.
        self.enterContext(patch.dict("os.environ", {
            "RR2_PHYSICAL_TOOLS_ROOT": "debug", "RR2_NATIVE_READER": "",
        }))
        self.selection = deepcopy(baseline.SELECTION)
        self.selection["target"]["executableSha256"] = UPDATED_SHA
        self.fault = None
        self.kinds = []

    def read(self, selection, kind, path, **options):
        self.kinds.append(kind)
        if kind != "zone-context":
            return baseline.StateTests().fake_read(selection, kind, path, **options)
        self.assertEqual(options, {})
        before = path.name == "zone-before.json"
        zone_key = 1216123138
        zone_id = ZONE_ID
        status = "available-candidate"
        start, end = (("2026-11-18T21:00:00Z", "2026-11-18T21:00:01Z") if before
                      else ("2026-11-18T21:00:08Z", "2026-11-18T21:00:09Z"))
        if not before:
            if self.fault == "changed-zone":
                zone_key, zone_id = 12, "z0000000CB7B53FD7"
            if self.fault == "wrong-time":
                start = end = "2026-11-18T20:59:59Z"
            if self.fault == "unavailable-zone":
                status, zone_id = "unavailable", None
        identity = {
            "processId": selection["target"]["processId"],
            "processStartUtcTicks": int(selection["target"]["processStartUtcTicks"]),
            "executablePath": selection["target"]["executablePath"],
            "executableSha256": selection["target"]["executableSha256"].upper(),
            "moduleBaseAddress": 123456, "moduleSize": 1234567,
        }
        if not before and self.fault == "wrong-epoch":
            identity["processStartUtcTicks"] += 1
        observation = {"identity": identity, "selfKey": int(SELF_KEY),
                       "rawZoneKey": zone_key, "zoneIdCandidate": zone_id,
                       "startedAtUtc": start, "completedAtUtc": end}
        report = {"status": "complete", "contractVersion": "native-current-zone-seed-candidate/1",
                  "observation": observation}
        path.write_text(json.dumps(report), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not before and self.fault == "wrong-digest":
            digest = "0" * 64
        values = {"status": status, "selfKey": SELF_KEY, "rawZoneKey": zone_key,
                  "zoneIdCandidate": zone_id, "startedAtUtc": start, "sampledAtUtc": end,
                  "childStatus": "type-1e17-raw-candidate", "childKey": 650763347,
                  "worldInstanceStatus": "unavailable"}
        if not before and self.fault == "changed-child":
            values["childKey"] = 650763348
        if not before and self.fault == "wrong-projection":
            values["rawZoneKey"] += 1
        return {"status": "complete", "nativeRead": kind, "target": selection["target"],
                "nativeOutput": str(path), "nativeSourceSha256": digest,
                "nativeValues": values}

    def collect(self, fault=None, **options):
        self.fault = fault
        with TemporaryDirectory() as temp:
            output = Path(temp) / "sample"
            with patch.object(state, "pin", return_value=self.selection), \
                 patch.object(state.physical_rift, "read_native", side_effect=self.read):
                try:
                    result = state.collect(123, output, samples=2, interval_ms=10,
                                           include_zone=True, **options)
                except ValueError:
                    self.assertFalse((output / "summary.json").exists())
                    raise
                return result

    def test_read_only_zone_endpoints_and_hashes_wrap_existing_three_sources(self):
        path, report = self.collect()
        self.assertEqual(report["status"], "complete-candidate")
        self.assertEqual(self.kinds,
                         ["zone-context", "player-context", "position", "vitals", "zone-context"])
        self.assertEqual(report["selfKeyCandidate"], SELF_KEY)
        self.assertEqual(report["zoneBracketCandidate"]["status"], "matching-candidates")
        self.assertEqual(report["zoneBracketCandidate"]["zoneIdCandidate"], ZONE_ID)
        self.assertEqual(report["zoneBracketCandidate"]["worldInstanceStatus"], "unavailable")
        self.assertIn("transient change", report["zoneBracketCandidate"]["qualification"])
        self.assertEqual(report["zoneBracketCandidate"]["beforeSourceSha256"],
                         report["sources"]["zone-before"]["sourceSha256"])
        self.assertEqual(report["sources"]["zone-before"]["samples"], 1)
        self.assertEqual(report["sources"]["zone-after"]["samples"], 1)

    def test_changed_zone_during_collection_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-changed-during-collection"):
            self.collect("changed-zone")

    def test_changed_child_key_blocks_publication_even_with_matching_zone_id(self):
        with self.assertRaisesRegex(ValueError, "zone-changed-during-collection"):
            self.collect("changed-child")

    def test_missing_zone_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-candidate-unavailable"):
            self.collect("unavailable-zone")

    def test_wrong_zone_digest_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-after-source-identity-invalid"):
            self.collect("wrong-digest")

    def test_changed_process_epoch_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-after-source-identity-invalid"):
            self.collect("wrong-epoch")

    def test_zone_projection_mismatch_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-after-native-zone-values-mismatch"):
            self.collect("wrong-projection")

    def test_backward_time_bracket_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "zone-bracket-time-invalid"):
            self.collect("wrong-time")

    def test_invalid_zone_flag_is_refused_without_probe(self):
        with patch.object(state, "pin") as pin:
            with self.assertRaisesRegex(ValueError, "invalid-sampling-bounds"):
                state.collect(123, Path("unused"), include_zone=1)
            pin.assert_not_called()

    def test_cli_forwards_opt_in_and_displays_bracket(self):
        example = {"status": "complete-candidate",
                   "target": self.selection["target"],
                   "selfKeyCandidate": SELF_KEY,
                   "qualification": "candidate-only",
                   "zoneBracketCandidate": {"status": "matching-candidates",
                                            "zoneIdCandidate": ZONE_ID},
                   "sources": {
                       "player-context": {"candidateValues": {}, "sourceSha256": "a" * 64},
                       "position": {"candidateValues": {}, "sourceSha256": "b" * 64},
                       "vitals": {"candidateValues": {}, "sourceSha256": "c" * 64},
                   }}
        out = StringIO()
        with patch.object(state, "collect", return_value=(Path("sample/summary.json"), example)) as collect, \
             redirect_stdout(out):
            self.assertEqual(state.main(["--physical-pid", "123", "--include-zone"]), 0)
        self.assertTrue(collect.call_args.kwargs["include_zone"])
        self.assertEqual(json.loads(out.getvalue())["zoneBracketCandidate"]["zoneIdCandidate"], ZONE_ID)


if __name__ == "__main__":
    unittest.main()
