import importlib.util
from pathlib import Path
import struct
import unittest


SPEC = importlib.util.spec_from_file_location(
    "native_mana_candidate", Path(__file__).parents[1] / "scripts/native_mana_candidate.py")
mana = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mana)


def fixture(*, baseline=3980, maximum=3980, rate=0, revision=7,
            cached_revision=7, cached_clock=100.0):
    record, wrapper = bytearray(64), bytearray(48)
    struct.pack_into("<i", record, 0x18, rate)
    struct.pack_into("<i", record, 0x1C, baseline)
    struct.pack_into("<i", record, 0x20, revision)
    struct.pack_into("<i", record, 0x24, maximum)
    struct.pack_into("<i", wrapper, 0x1C, cached_revision)
    struct.pack_into("<f", wrapper, 0x24, cached_clock)
    return bytes(record), bytes(wrapper)


class ManaCandidateTests(unittest.TestCase):
    def calculate(self, record=None, wrapper=None, clock=101.0, **kwargs):
        if record is None or wrapper is None:
            record, wrapper = fixture()
        return mana.calculate_mana_candidate(
            record, wrapper, clock, build_sha=kwargs.get("build_sha", mana.BUILD_SHA),
            resource_kind=kwargs.get("resource_kind", 3),
            verified_type_code=kwargs.get("verified_type_code", mana.MANA_TYPE))

    def test_ordinary_static_and_regeneration_paths(self):
        result = self.calculate()
        self.assertEqual(("calculated-candidate", 3980, 3980),
                         (result["status"], result["current"], result["maximum"]))
        record, wrapper = fixture(baseline=50, maximum=100, rate=2000)
        result = self.calculate(record, wrapper)
        self.assertEqual((70, -20), (result["current"], result["truncatedRateAdjustment"]))
        record, wrapper = fixture(baseline=50, maximum=100, rate=-2000)
        self.assertEqual(30, self.calculate(record, wrapper)["current"])

    def test_requires_distinct_kind_three_type_proof(self):
        for code in (None, False, True, 0x072B, 0, 0x072A + 0x10000):
            with self.subTest(code=code):
                result = self.calculate(verified_type_code=code)
                self.assertEqual("mana-type-fingerprint-unverified", result["reason"])
                self.assertIsNone(result["current"])
        self.assertEqual("not-mana-kind-three", self.calculate(resource_kind=4)["reason"])

    def test_wrong_build_and_revision_fail_closed(self):
        self.assertEqual("unsupported-build", self.calculate(build_sha="0" * 64)["reason"])
        record, wrapper = fixture(revision=8, cached_revision=7)
        self.assertEqual("revision-mismatch-needs-native-cache-write",
                         self.calculate(record, wrapper)["reason"])

    def test_clamps_and_rejects_unsafe_domains(self):
        cases = [
            (fixture(maximum=0), 101.0, "outside-normal-integer-domain"),
            (fixture(baseline=-1), 101.0, "outside-normal-integer-domain"),
            (fixture(cached_clock=float("nan")), 101.0, "invalid-float-input"),
            (fixture(), float("inf"), "invalid-float-input"),
            (fixture(), 10 ** 10000, "invalid-float-input"),
            (fixture(), 99.0, "clock-delta-outside-normal-domain"),
            (fixture(baseline=(1 << 31) - 1, rate=(1 << 31) - 1), 101.0,
             "signed32-subtraction-overflow"),
        ]
        for (record, wrapper), clock, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(reason, self.calculate(record, wrapper, clock)["reason"])

    def test_preserves_float32_rate_rounding_and_input_bytes(self):
        record, wrapper = fixture(baseline=100, maximum=200000000, rate=16777217,
                                  cached_clock=100.0)
        before = (record, wrapper)
        result = self.calculate(record, wrapper, 1100.0)
        self.assertEqual(-167772160, result["truncatedRateAdjustment"])
        self.assertEqual(167772260, result["current"])
        self.assertEqual(before, (record, wrapper))

    def test_exact_input_lengths_are_required(self):
        record, wrapper = fixture()
        self.assertEqual("mana-input-size", self.calculate(record[:-1], wrapper)["reason"])
        self.assertEqual("mana-input-size", self.calculate(record, wrapper[:-1])["reason"])


if __name__ == "__main__":
    unittest.main()
