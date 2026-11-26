"""Offline tests; reference snapshots are synthetic, not live RRE captures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import compare_saved_api_stats as compare


class SavedApiStatTests(unittest.TestCase):
    def setUp(self):
        self.key = "239816685251645959"
        self.player = "u035400012FA2D207"
        rows = []
        api = {}
        for i, name in enumerate(compare.STAT_NAMES):
            rows.append({
                "name": name,
                "ordinary": {"status": "raw-candidate", "rawSigned64": i},
                "unbuffed": {"status": "raw-candidate", "rawSigned64": i + 1},
            })
            api[name] = i
            api[name + "Unbuffed"] = i + 1
        self.native = {
            "target": {"processId": 123}, "selfKeyCandidate": self.key,
            "summarySha256": "A" * 64, "sources": {"stats": {"sha256": "B" * 64}},
            "candidateValues": {"stats": {"status": "candidate-only",
                                         "selectorCount": 20, "stats": rows}},
        }
        self.reference = {
            "adapterContract": "rre-saved-snapshot/1",
            "sourceSha256": "C" * 64, "sourceBytes": 100,
            "addonVersion": "0.4.23", "sequence": 1,
            "context": {"player": {"id": self.player},
                        "capabilities": {"player": True, "stats": True},
                        "statsTruncated": 0, "stats": api},
        }

    def test_all_40_exact_names_and_zero(self):
        result = compare.compare_values(self.native, self.reference)
        self.assertEqual(40, result["counts"]["equal"])
        self.assertEqual(0, result["rows"][0]["nativeRaw"])
        self.assertEqual(0, result["rows"][0]["apiValue"])
        self.assertEqual("historical-comparison-candidate", result["status"])

    def test_missing_boolean_and_different_never_equal(self):
        ctx = self.reference["context"]["stats"]
        ctx.pop("armor")
        ctx["armorUnbuffed"] = True
        ctx["powerAttack"] = 50
        self.native["candidateValues"]["stats"]["stats"][1]["unbuffed"] = {
            "status": "unavailable"}
        result = compare.compare_values(self.native, self.reference)
        self.assertEqual(["api-missing", "not-comparable", "different", "native-unavailable"],
                         [r["status"] for r in result["rows"][:4]])
        self.assertIsNone(result["rows"][0]["apiValue"])

    def test_refuses_wrong_player_or_truncated_export(self):
        for update in ({"player": {"id": "u0000000000000001"}}, {"statsTruncated": 1},
                       {"capabilities": {"player": True, "stats": False}}):
            ref = deepcopy(self.reference)
            ref["context"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                compare.compare_values(self.native, ref)

    def test_large_numbers_and_wrong_stat_name_set(self):
        self.reference["context"]["stats"]["armor"] = 10**500
        self.native["candidateValues"]["stats"]["stats"][0]["unbuffed"]["rawSigned64"] = 2**53
        result = compare.compare_values(self.native, self.reference)
        self.assertEqual(2, result["counts"]["not-comparable"])
        self.native["candidateValues"]["stats"]["stats"][0]["name"] = "strength"
        with self.assertRaisesRegex(ValueError, "native-name-set-mismatch"):
            compare.compare_values(self.native, self.reference)

    def test_pinned_export_digest_checked_before_native_replay(self):
        with TemporaryDirectory() as temp:
            p = Path(temp) / "reference.json"
            raw = json.dumps(self.reference).encode()
            p.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            with patch.object(compare, "verified_state", return_value=self.native) as verify:
                result = compare.compare(Path("native-summary.json"), p, digest)
                self.assertEqual(digest.upper(), result["referenceExportSha256"])
                verify.assert_called_once()
                p.write_bytes(raw + b" ")
                with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                    compare.compare(Path("native-summary.json"), p, digest)
                self.assertEqual(1, verify.call_count)


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.native = {
            "target": {"processId": 123}, "selfKeyCandidate": "239816685251645959",
            "summarySha256": "A" * 64, "sources": {"player-context": {"sha256": "B" * 64}},
            "candidateValues": {"player-context": {
                "level": {"status": "numeric-getter-and-presentation-candidate",
                          "rawCandidate": 45}}},
        }
        self.reference = {
            "adapterContract": "rre-saved-snapshot/1", "sourceSha256": "C" * 64,
            "sourceBytes": 100, "addonVersion": "0.4.23", "sequence": 2,
            "context": {"player": {"id": "u035400012FA2D207", "level": 45},
                        "capabilities": {"player": True, "experience": True},
                        "experience": {"accumulated": 250, "needed": 1000, "rested": 0}},
        }

    def project(self):
        return compare.compare_progression(self.native, self.reference)

    def test_normal_fraction_and_reported_zero(self):
        result = self.project()
        self.assertEqual("matching-candidates", result["levelComparison"]["status"])
        self.assertEqual("api-values-candidate", result["experienceStatus"])
        self.assertEqual(0.25, result["savedProgressFractionCandidate"])
        self.assertEqual({"status": "reported-candidate", "value": 0},
                         result["experienceFields"]["rested"])
        self.assertEqual("not-captured", result["nativeExperienceStatus"])
        self.assertIn("no XP parity", result["qualification"])

    def test_empty_partial_unavailable_and_old_producer_are_distinct(self):
        ctx = self.reference["context"]
        ctx["experience"] = {}
        self.assertEqual("api-empty", self.project()["experienceStatus"])
        ctx["experience"] = {"rested": 0}
        result = self.project()
        self.assertEqual("api-partial", result["experienceStatus"])
        self.assertIsNone(result["savedProgressFractionCandidate"])
        self.assertEqual({"status": "unavailable", "value": None},
                         result["experienceFields"]["needed"])
        ctx.pop("experience")
        ctx["capabilities"]["experience"] = False
        self.assertEqual("api-unavailable", self.project()["experienceStatus"])
        ctx["capabilities"].pop("experience")
        self.reference["addonVersion"] = "0.4.13"
        self.assertEqual("not-captured", self.project()["experienceStatus"])

    def test_no_level_cap_or_ratio_inference_from_anomalous_values(self):
        for accumulated, needed in ((0, 0), (1, -1), (1500, 1000),
                                    (-1, 100), (1, 2**54)):
            with self.subTest(accumulated=accumulated, needed=needed):
                self.reference["context"]["experience"].update(accumulated=accumulated, needed=needed)
                result = self.project()
                self.assertIsNone(result["savedProgressFractionCandidate"])
                self.assertEqual(needed, result["experienceFields"]["needed"]["value"])

    def test_level_difference_is_historical_not_a_level_up_event(self):
        self.reference["context"]["player"]["level"] = 44
        result = self.project()
        self.assertEqual("different-candidates", result["levelComparison"]["status"])
        self.assertEqual(44, result["levelComparison"]["savedApiLevelCandidate"])
        self.assertEqual("historical-progression-candidate", result["status"])

    def test_rejects_wrong_player_and_producer_contract_contradictions(self):
        ctx = self.reference["context"]
        ctx["player"]["id"] = "u0000000000000001"
        with self.assertRaisesRegex(ValueError, "player-mismatch"):
            self.project()
        ctx["player"]["id"] = "u035400012FA2D207"
        ctx["capabilities"]["experience"] = False
        with self.assertRaisesRegex(ValueError, "capability-map-contradiction"):
            self.project()
        ctx["capabilities"].pop("experience")
        with self.assertRaisesRegex(ValueError, "capability-invalid"):
            self.project()
        ctx["capabilities"]["experience"] = True
        self.reference["addonVersion"] = "0.4.13"
        with self.assertRaisesRegex(ValueError, "version-unqualified"):
            self.project()

    def test_invalid_experience_values_and_unknown_fields_rejected(self):
        for bad in ([], {"needed": True}, {"rested": float("inf")},
                    {"accumulated": float("nan")}, {"needed": 10**500}, {"bonus": 1}):
            with self.subTest(value=bad):
                self.reference["context"]["experience"] = bad
                with self.assertRaisesRegex(ValueError, "experience-fields-invalid"):
                    self.project()

    def test_progression_only_cli_requires_no_stats_and_checks_export_digest(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            ref = folder / "reference.json"
            output = folder / "report.json"
            ref.write_text(json.dumps(self.reference), encoding="utf-8")
            digest = hashlib.sha256(ref.read_bytes()).hexdigest()
            with patch.object(compare, "verified_state", return_value=self.native) as verify:
                args = ["--state-summary", "native.json", "--reference", str(ref),
                        "--reference-sha256", digest, "--output", str(output), "--progression-only"]
                self.assertEqual(0, compare.main(args))
                result = json.loads(output.read_text())
                self.assertEqual(digest.upper(), result["referenceExportSha256"])
                self.assertEqual(0.25, result["savedProgressFractionCandidate"])
                verify.assert_called_once()
                ref.write_bytes(ref.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                    compare.compare("native.json", ref, digest, progression_only=True)
                self.assertEqual(1, verify.call_count)


if __name__ == "__main__":
    unittest.main()
