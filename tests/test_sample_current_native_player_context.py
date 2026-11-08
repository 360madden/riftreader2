"""Focused offline checks for the player-context CLI value projection."""
import json
import unittest

from scripts.sample_current_native_player_context import project_values


class PlayerContextProjectionTests(unittest.TestCase):
    def test_raw_candidates_and_lossless_target_id(self):
        source = {
            'rawLevel': 41, 'levelStatus': 'numeric-getter-and-presentation-candidate',
            'rawCombat': 0, 'combatStatus': 'raw-byte-candidate', 'combatCandidate': False,
            'targetStatus': 'fallback-key-candidate',
            'targetUnitIdCandidate': 'u80000002CD0034D1',
            'entity': 0x7FFF00000000,
        }
        values = project_values(source)
        self.assertEqual(values, {
            'level': {'status': 'numeric-getter-and-presentation-candidate', 'rawCandidate': 41},
            'combat': {'status': 'raw-byte-candidate', 'rawByte': 0, 'candidate': False},
            'target': {'status': 'fallback-key-candidate', 'unitIdCandidate': 'u80000002CD0034D1'},
        })
        self.assertEqual(json.loads(json.dumps(values))['target']['unitIdCandidate'], 'u80000002CD0034D1')
        self.assertNotIn('entity', values)

    def test_unavailable_target_remains_null_and_level_unqualified(self):
        source = {
            'rawLevel': 43, 'levelStatus': 'alternate-component-unavailable',
            'rawCombat': 1, 'combatStatus': 'raw-byte-candidate', 'combatCandidate': True,
            'targetStatus': 'override-unavailable', 'targetUnitIdCandidate': None,
        }
        values = project_values(source)
        self.assertEqual(values['level']['status'], 'alternate-component-unavailable')
        self.assertEqual(values['level']['rawCandidate'], 43)
        self.assertEqual(values['combat']['candidate'], True)
        self.assertEqual(values['target'], {'status': 'override-unavailable', 'unitIdCandidate': None})
        self.assertIsNone(json.loads(json.dumps(values))['target']['unitIdCandidate'])


if __name__ == '__main__':
    unittest.main()
