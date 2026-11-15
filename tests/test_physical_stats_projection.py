"""Offline projection checks for the existing physical native stats reader."""
import unittest

from scripts import physical_rift


EXPECTED = [
    ("armor", 37), ("powerAttack", 24), ("powerSpell", 32),
    ("critAttack", 26), ("critSpell", 33)
]


def report():
    rows = []
    for name, selector in EXPECTED:
        rows.append({
            "name": name, "selector": selector, "mappedIndex": selector,
            "ordinary": {"status": "raw-candidate", "rawSigned64": 100 + selector,
                         "doubleCandidate": float(100 + selector), "precision": "exact-integer-range"},
            "unbuffed": {"status": "raw-candidate", "rawSigned64": 90 + selector,
                         "doubleCandidate": float(90 + selector), "precision": "exact-integer-range"},
        })
    selector_map = [-1] * 84
    for row in rows:
        selector_map[row["selector"]] = row["mappedIndex"]
    return {
        "schemaVersion": 1, "contractVersion": "native-current-stats-candidate/1",
        "status": "complete",
        "observation": {
            "qualification": "raw typed stat candidates; API availability, units, freshness and restart unverified",
            "identity": {
                "processId": 123, "processStartUtcTicks": 639300936028818696,
                "executableSha256": "1935a05c9db6d468e34e0055014a4a99c1b5afceb1695884e24600f5c20a4be8"},
            "unitKey": 239816685251645959,
            "startedAtUtc": "2026-11-15T18:00:00Z",
            "completedAtUtc": "2026-11-15T18:00:01Z",
            "selectorMapCandidate": selector_map, "stats": rows,
        },
    }


class PhysicalStatsProjectionTests(unittest.TestCase):
    def test_existing_physical_stats_read_exposes_candidate_values(self):
        result = physical_rift._native_values("stats", report())
        self.assertEqual(result["unitKey"], "239816685251645959")
        self.assertEqual(result["selectorCount"], 5)
        self.assertEqual(result["stats"][0]["ordinary"]["rawSigned64"], 137)
        self.assertEqual(result["stats"][0]["unbuffed"]["rawSigned64"], 127)
        self.assertIn("unverified", result["qualification"])

    def test_inconsistent_selector_map_is_refused(self):
        source = report()
        source["observation"]["selectorMapCandidate"][37] = 999
        with self.assertRaises(ValueError):
            physical_rift._native_values("stats", source)

    def test_nonfinite_or_inconsistent_stat_is_refused(self):
        source = report()
        source["observation"]["stats"][0]["ordinary"]["doubleCandidate"] = float("nan")
        with self.assertRaises(ValueError):
            physical_rift._native_values("stats", source)
        source = report()
        source["observation"]["stats"][0]["ordinary"]["status"] = "index-unavailable"
        with self.assertRaises(ValueError):
            physical_rift._native_values("stats", source)


if __name__ == "__main__":
    unittest.main()
