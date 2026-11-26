"""Offline legacy XP report fixtures; no process or VM access."""
from copy import deepcopy
import unittest

from scripts import sample_current_native_experience_seed as seed
from scripts import sample_current_native_experience_values as values


def fixture():
    identity = {"processId": 123, "processStartUtcTicks": 456,
                "executableSha256": values.GAME_SHA}
    seed_report = {
        "identity": identity.copy(), "qualification": seed.QUALIFICATION,
        "startedAtUtc": "2026-11-07T12:00:01Z",
        "completedAtUtc": "2026-11-07T12:00:02Z",
        "unitKey": 1234, "entity": 0x100000, "component": 0x200000,
        "owner": 0x300000, "index": 0, "rawDword160": 0, "rawByte24F": 0,
        "vectorBegin": 0x400000, "vectorEnd": 0x400008,
        "references": [0x500000], "branch": "indexed-raw-candidate",
        "selected": {"address": 0x500000, "rawInt64_18": 1000,
                     "rawDword24": 45, "rawFloat20Bits": 0, "rawFloat20": 0.0},
    }
    observation = {
        "identity": identity, "qualification": values.QUALIFICATION,
        "startedAtUtc": "2026-11-07T12:00:00Z",
        "completedAtUtc": "2026-11-07T12:00:03Z", "seed": seed_report,
        "valueStatus": "raw-values-candidate", "level": 45, "limit": 65,
        "mode": 2, "baseline": 1200, "needed": 500, "accumulatedCandidate": 300,
        "restedStatus": "raw-rested-candidate", "restedFlag": 1,
        "restedRawBits": 0, "restedCandidate": 0,
    }
    return {"schemaVersion": 1, "contractVersion": "native-current-experience-values-candidate/1",
            "status": "complete", "observation": observation}


class ExperienceValidationTests(unittest.TestCase):
    def validate(self, report):
        return values.validate_report(report, pid=123, ticks=456)

    def test_valid_normal_domain_and_zero_rested(self):
        self.assertEqual(self.validate(fixture())["accumulatedCandidate"], 300)

    def test_producer_owner_type_refusal_is_valid_missing_evidence(self):
        report = fixture()
        o = report["observation"]
        o.update(valueStatus="owner-type-unavailable", level=None, limit=None,
                 mode=None, baseline=None, needed=None, accumulatedCandidate=None,
                 restedStatus="unavailable", restedFlag=None, restedRawBits=None,
                 restedCandidate=None)
        self.assertEqual(self.validate(report)["valueStatus"], "owner-type-unavailable")
        o["restedCandidate"] = 0
        with self.assertRaises(ValueError):
            self.validate(report)

    def test_refused_type_cannot_publish_rested_fields(self):
        for status in ("owner-type-unavailable", "progress-type-unavailable"):
            with self.subTest(status=status):
                report = fixture()
                report["observation"].update(valueStatus=status, level=None, limit=None,
                                             mode=None, baseline=None, needed=None,
                                             accumulatedCandidate=None)
                with self.assertRaises(ValueError):
                    self.validate(report)

    def test_limit_refusal_must_agree_with_level(self):
        report = fixture()
        o = report["observation"]
        o.update(valueStatus="native-minus-one-level-cap", mode=None, baseline=None,
                 needed=None, accumulatedCandidate=None)
        with self.assertRaises(ValueError):
            self.validate(report)
        o["limit"] = 45
        self.assertEqual(self.validate(report)["valueStatus"], "native-minus-one-level-cap")
        bad = fixture()
        bad["observation"]["limit"] = 45
        with self.assertRaises(ValueError):
            self.validate(bad)

    def test_intermediate_checked_overflow_is_not_valid_accumulation(self):
        report = fixture()
        o = report["observation"]
        # First subtraction overflows int64, even though the final sum fits.
        o["seed"]["selected"]["rawInt64_18"] = 2**63 - 1
        o.update(baseline=-1, needed=-2, accumulatedCandidate=2**63 - 2)
        with self.assertRaises(ValueError):
            self.validate(report)
        o.update(valueStatus="arithmetic-overflow", accumulatedCandidate=None)
        self.assertEqual(self.validate(report)["valueStatus"], "arithmetic-overflow")

    def test_overflow_status_requires_an_overflow(self):
        report = fixture()
        report["observation"].update(valueStatus="arithmetic-overflow",
                                     accumulatedCandidate=None)
        with self.assertRaises(ValueError):
            self.validate(report)

    def test_wrong_build_still_rejected(self):
        report = deepcopy(fixture())
        for o in (report["observation"], report["observation"]["seed"]):
            o["identity"]["executableSha256"] = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
        with self.assertRaises(ValueError):
            self.validate(report)


def updated_fixture():
    """Synthetic partial build-1179 evidence; never a live XP result."""
    report = fixture()
    o = report["observation"]
    for value in (o, o["seed"]):
        value["identity"].update(executableSha256=values.UPDATED_GAME_SHA,
                                 moduleSize=0x4000000, moduleBaseAddress=0x140000000)
    o["seed"].update(ownerVtableRva=0x2A31740, ownerGetterRva=0x1C503E0)
    o["seed"]["selected"].update(vtableRva=0x2BDF520, getterRva=0x201A040)
    o.update(valueStatus="needed-recipe-unqualified", mode=None, needed=None,
             accumulatedCandidate=None)
    return report


class UpdatedExperienceValidationTests(unittest.TestCase):
    def validate(self, report):
        return values.validate_report(report, pid=123, ticks=456,
                                      expected_sha=values.UPDATED_GAME_SHA)

    def test_partial_values_preserve_baseline_and_unknown_needed(self):
        report = updated_fixture()
        result = values.project_values(report)
        self.assertEqual("needed-recipe-unqualified", result["valueStatus"])
        self.assertEqual(1200, result["baselineCandidate"])
        self.assertEqual(45, result["levelCandidate"])
        self.assertEqual(65, result["limitCandidate"])
        self.assertIsNone(result["neededCandidate"])
        self.assertIsNone(result["accumulatedCandidate"])
        self.assertEqual(0, result["rawRestedCandidate"])
        with self.assertRaises(ValueError):
            values.validate_report(report, pid=123, ticks=456)

    def test_partial_reader_cannot_claim_calculated_experience(self):
        for change in ({"needed": 100}, {"mode": 2}, {"accumulatedCandidate": 100},
                       {"valueStatus": "raw-values-candidate"}, {"baseline": None}):
            with self.subTest(change=change):
                report = updated_fixture()
                report["observation"].update(change)
                with self.assertRaises(ValueError):
                    self.validate(report)

    def test_full_current_build_values_are_rederived_from_seed(self):
        report = updated_fixture()
        report["observation"].update(valueStatus="raw-values-candidate", mode=2,
                                     needed=500, accumulatedCandidate=300)
        result = values.project_values(report)
        self.assertEqual(500, result["neededCandidate"])
        self.assertEqual(300, result["accumulatedCandidate"])
        self.assertEqual(0.6, result["progressFractionCandidate"])
        report["observation"]["accumulatedCandidate"] = 301
        with self.assertRaises(ValueError):
            self.validate(report)

    def test_fraction_is_unavailable_for_sentinel_or_outside_level(self):
        report = updated_fixture()
        o = report["observation"]
        o.update(valueStatus="native-minus-one-needed", mode=2, needed=-1)
        self.assertIsNone(values.project_values(report)["progressFractionCandidate"])
        o.update(valueStatus="raw-values-candidate", needed=100, accumulatedCandidate=-100)
        self.assertIsNone(values.project_values(report)["progressFractionCandidate"])
        o.update(needed=200, accumulatedCandidate=0)
        self.assertEqual(0.0, values.project_values(report)["progressFractionCandidate"])

    def test_uninitialized_cap_provider_preserves_explicit_absence(self):
        report = updated_fixture()
        o = report["observation"]
        o.update(valueStatus="cap-provider-uninitialized", limit=None, baseline=None)
        self.assertEqual("cap-provider-uninitialized", self.validate(report)["valueStatus"])
        o["baseline"] = 0
        with self.assertRaises(ValueError):
            self.validate(report)


if __name__ == "__main__":
    unittest.main()
