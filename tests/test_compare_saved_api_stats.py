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


if __name__ == "__main__":
    unittest.main()
