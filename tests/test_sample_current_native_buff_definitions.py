"""Preserve exact source-reader pins for historical and current buff captures."""
import unittest

from scripts.sample_current_native_buff_definitions import (
    CURRENT_SEED_READER, CURRENT_SEED_SHA,
    LEGACY_SEED_READER, LEGACY_SEED_SHA, TIMING_SEED_SHA,
    reader_selection,
)


class BuffDefinitionReaderSelectionTests(unittest.TestCase):
    def test_historical_legacy_seed_uses_original_pins(self):
        plan = reader_selection(LEGACY_SEED_SHA)
        self.assertEqual(plan[3:6], (LEGACY_SEED_READER, LEGACY_SEED_SHA, 117544800))
        self.assertEqual(plan[6:], ('current-variant-restrictions-', 'current-buff-seeds-'))

    def test_current_signed_input_seed_uses_distinct_pins(self):
        plan = reader_selection(CURRENT_SEED_SHA)
        self.assertEqual(plan[3:6], (CURRENT_SEED_READER, CURRENT_SEED_SHA, 117741408))
        self.assertEqual(plan[6:], ('current-variant-restrictions-', 'current-buff-seeds-'))
        self.assertNotEqual(plan[4], reader_selection(LEGACY_SEED_SHA)[4])

    def test_historical_timing_reader_is_unchanged(self):
        plan = reader_selection(TIMING_SEED_SHA)
        self.assertEqual(plan[1:3], (TIMING_SEED_SHA, 117565792))
        self.assertEqual(plan[4:6], (TIMING_SEED_SHA, 117565792))
        self.assertEqual(plan[3], plan[0])
        self.assertEqual(plan[6:], ('current-buff-loaded-field-', 'current-buff-loaded-field-'))

    def test_unknown_reader_fails_closed(self):
        for candidate in (None, '', '0' * 64, LEGACY_SEED_SHA.lower()):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    reader_selection(candidate)


if __name__ == '__main__':
    unittest.main()
