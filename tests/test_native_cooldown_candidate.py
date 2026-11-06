import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "native_cooldown_candidate",
    Path(__file__).parents[1] / "scripts/native_cooldown_candidate.py")
cooldown = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cooldown)


class CooldownCandidateTests(unittest.TestCase):
    def reconstruct(self, **overrides):
        values = dict(timer=112.0, duration=12.0, game_clock=107.5,
                      remaining_floor=0.0, build_sha=cooldown.BUILD_SHA)
        values.update(overrides)
        return cooldown.reconstruct_cooldown_fields(**values)

    def test_active_candidate_reconstructs_only_verified_fields(self):
        result = self.reconstruct()
        self.assertEqual(result["status"], "candidate-arithmetic")
        self.assertEqual(result["currentCooldownBegin"], 100.0)
        self.assertEqual(result["currentCooldownDuration"], 12.0)
        self.assertEqual(result["currentCooldownRemaining"], 4.5)
        self.assertIsNone(result["currentCooldownExpired"])
        self.assertIsNone(result["currentCooldownPaused"])

    def test_negative_delta_exposes_only_verified_expired_branch(self):
        result = self.reconstruct(game_clock=114.25, remaining_floor=0.0)
        self.assertEqual(result["clockDelta"], -2.25)
        self.assertEqual(result["currentCooldownExpired"], 2.25)
        self.assertEqual(result["currentCooldownRemaining"], 0.0)

    def test_floor_is_an_input_not_an_assumed_zero(self):
        result = self.reconstruct(game_clock=111.75, remaining_floor=0.5)
        self.assertEqual(result["clockDelta"], 0.25)
        self.assertEqual(result["currentCooldownRemaining"], 0.5)

    def test_float32_rounding_is_explicit(self):
        result = self.reconstruct(timer=16_777_217.0, duration=1.0,
                                  game_clock=16_777_216.0)
        self.assertEqual(result["inputs"]["timer"], 16_777_216.0)
        self.assertEqual(result["currentCooldownBegin"], 16_777_215.0)
        self.assertEqual(result["clockDelta"], 0.0)

    def test_unsupported_build_returns_before_input_validation(self):
        result = self.reconstruct(build_sha="other", timer=float("nan"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "unsupported-build")
        self.assertNotIn("inputs", result)

    def test_invalid_inputs_fail_explicitly_without_partial_fields(self):
        for field, value, reason in (
            ("timer", float("nan"), "timer-not-finite"),
            ("duration", "12", "duration-not-numeric"),
            ("game_clock", float("inf"), "game-clock-not-finite"),
            ("remaining_floor", 1e100, "remaining-floor-outside-float32"),
            ("timer", 10 ** 10000, "timer-outside-float32"),
        ):
            with self.subTest(field=field):
                result = self.reconstruct(**{field: value})
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["reason"], reason)
                self.assertIsNone(result["currentCooldownBegin"])

    def test_derived_float32_overflow_is_rejected(self):
        result = self.reconstruct(timer=3.4e38, duration=-3.4e38)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "begin-outside-float32")
        self.assertIsNone(result["currentCooldownBegin"])


if __name__ == "__main__":
    unittest.main()

