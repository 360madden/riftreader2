"""Offline selected-target report compatibility and negative checks."""
import copy
import json
import unittest
from scripts import sample_current_native_selected_target as module

PID, TICKS, KEY = 123, 639296903905448486, 0x80000002CD0034D1
START, END = '2026-11-08T01:00:00+00:00', '2026-11-08T01:00:01+00:00'

def report(healthless=False):
    identity = dict(processId=PID, processStartUtcTicks=TICKS, executableSha256=module.GAME_SHA)
    field = dict(status='unavailable', current=None, maximum=None, unavailableReason='not-present')
    vitals = dict(identity=identity.copy(), unitKey=KEY, startedAtUtc=START, completedAtUtc=END,
                  qualification='candidate-only; semantics/passive-freshness/restart-unverified',
                  health=field.copy(), energy=field.copy(), mana=field.copy())
    context = dict(qualification='typed owner raw inputs; target level presentation, combat semantics and freshness unverified',
                   status='owner-unavailable', owner=None, rawLevel=None, rawCombat=None, combatCandidate=None,
                   levelStatus=None, levelBranch=None, numericLevelCandidate=None)
    position = dict(status='candidate', unitKey=KEY, componentAddress=0x20070000, startedAtUtc=START,
                    completedAtUtc=END, position=dict(x=1.5, y=2.0, z=3.0),
                    qualification='cached position candidate; freshness and target semantics unverified')
    observation = dict(identity=identity, startedAtUtc=START, completedAtUtc=END, selfKey=321,
                       status='candidate', beforeGuardStatus='fallback-key-candidate', afterGuardStatus='fallback-key-candidate',
                       targetKey=KEY, targetUnitId=f'u{KEY:016X}', targetEntity=0x20040000,
                       targetVitals=None if healthless else vitals, nameSeed={}, targetContext=context,
                       targetPosition=position, qualification=module.QUALIFICATION)
    return dict(schemaVersion=1, contractVersion='native-current-selected-target-candidate-sample/1',
                status='complete', qualification=module.QUALIFICATION, observation=observation)

class SelectedTargetReportTests(unittest.TestCase):
    def validate(self, value):
        return module.validate_report(value, pid=PID, ticks=TICKS)

    def test_legacy_and_healthless_position(self):
        for healthless in (False, True):
            with self.subTest(healthless=healthless):
                result = self.validate(report(healthless))
                self.assertEqual(KEY, result['targetPosition']['unitKey'])
                self.assertEqual(healthless, result['targetVitals'] is None)
                self.assertEqual(module.QUALIFICATION, result['qualification'])

    def test_legacy_missing_position_retained(self):
        value = report()
        value['observation']['targetPosition'].update(status='component-unavailable', componentAddress=None,
                                                     startedAtUtc=None, completedAtUtc=None, position=None)
        self.assertEqual('component-unavailable', self.validate(value)['targetPosition']['status'])

    def test_healthless_requires_position_and_explicit_vitals_null(self):
        for position in (None, {}, dict(status='unknown'), dict(status='component-unavailable')):
            value = report(True)
            value['observation']['targetPosition'] = position
            with self.subTest(position=position), self.assertRaises(ValueError): self.validate(value)
        value = report(True)
        del value['observation']['targetVitals']
        with self.assertRaises(ValueError): self.validate(value)

    def test_healthless_context_requires_absent_owner(self):
        for status in ('raw-typed-candidate', 'owner-or-fields-unavailable', 'unverified-type', 'unknown'):
            value = report(True)
            value['observation']['targetContext']['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError): self.validate(value)

    def test_identity_binding_and_timestamp_mutations(self):
        changes = [
            lambda o: o['identity'].update(processId=PID+1),
            lambda o: o['identity'].update(processStartUtcTicks=TICKS+1),
            lambda o: o['identity'].update(executableSha256='0'*64),
            lambda o: o.update(selfKey=0),
            lambda o: o.update(targetKey=KEY+1),
            lambda o: o.update(targetEntity=None),
            lambda o: o.update(beforeGuardStatus='override-unavailable'),
            lambda o: o.update(afterGuardStatus='override-unavailable'),
            lambda o: o['targetPosition'].update(unitKey=KEY+1),
            lambda o: o['targetPosition'].update(componentAddress=0),
            lambda o: o['targetPosition'].update(startedAtUtc='2026-11-08T00:59:59+00:00'),
            lambda o: o['targetPosition'].update(completedAtUtc='2026-11-08T01:00:02+00:00'),
            lambda o: o['targetPosition'].update(completedAtUtc='2026-11-08T00:59:59+00:00'),
            lambda o: o['targetPosition']['position'].update(x=float('nan')),
        ]
        for healthless in (False, True):
            for index, change in enumerate(changes):
                with self.subTest(healthless=healthless, change=index):
                    value = report(healthless)
                    change(value['observation'])
                    with self.assertRaises(ValueError): self.validate(value)

    def test_present_vitals_guards_remain(self):
        changes = [
            lambda v: v.update(unitKey=KEY+1),
            lambda v: v['identity'].update(processId=PID+1),
            lambda v: v.update(completedAtUtc='2026-11-08T01:00:02+00:00'),
            lambda v: v.update(qualification='fresh'),
            lambda v: v['health'].update(status='unknown'),
            lambda v: v['health'].update(current=0),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                value = report()
                change(value['observation']['targetVitals'])
                with self.assertRaises(ValueError): self.validate(value)

    def test_unavailable_target_rejects_position(self):
        value = report(True)
        value['observation'].update(status='unavailable', beforeGuardStatus='raw-getter-zero-candidate')
        with self.assertRaises(ValueError): self.validate(value)

class SelectedTargetValuesTests(unittest.TestCase):
    def values(self, value):
        return module.selected_target_values(value, pid=PID, ticks=TICKS)

    def test_target_vitals_and_lossless_identity_are_exposed(self):
        value = report()
        value['observation']['targetVitals']['health'].update(
            status='calculated-candidate', current=321, maximum=654, unavailableReason=None)
        original = copy.deepcopy(value)
        result = self.values(value)
        self.assertEqual(str(KEY), result['unitKey'])
        self.assertEqual('321', result['selfUnitKey'])
        self.assertEqual(f'u{KEY:016X}', result['unitId'])
        self.assertEqual(str(KEY), json.loads(json.dumps(result))['unitKey'])
        self.assertEqual(321, result['health']['current'])
        self.assertEqual(654, result['health']['maximum'])
        self.assertEqual('calculated-candidate', result['health']['status'])
        self.assertEqual(module.QUALIFICATION, result['qualification'])
        self.assertEqual(original, value)

    def test_unavailable_fields_stay_null_not_zero(self):
        result = self.values(report())
        for field in ('health', 'energy', 'mana'):
            self.assertIsNone(result[field]['current'])
            self.assertIsNone(result[field]['maximum'])
            self.assertEqual('unavailable', result[field]['status'])
            self.assertEqual('not-present', result[field]['unavailableReason'])
        self.assertIsNone(result['numericLevelCandidate'])
        self.assertIsNone(result['combatCandidate'])

    def test_healthless_target_retains_position_without_fabricated_vitals(self):
        result = self.values(report(True))
        self.assertEqual(dict(x=1.5, y=2.0, z=3.0), result['positionCandidate'])
        for field in ('health', 'energy', 'mana'):
            self.assertIsNone(result[field]['current'])
            self.assertEqual('target-vitals-unavailable', result[field]['unavailableReason'])

    def test_missing_position_is_null(self):
        value = report()
        value['observation']['targetPosition'].update(
            status='component-unavailable', componentAddress=None,
            startedAtUtc=None, completedAtUtc=None, position=None)
        self.assertIsNone(self.values(value)['positionCandidate'])

    def test_unavailable_target_preserves_guard_reason(self):
        for reason in ('raw-getter-zero-candidate', 'override-unavailable', 'guard-unreadable-or-invalid'):
            with self.subTest(reason=reason):
                value = report()
                value['observation'].update(status='unavailable', beforeGuardStatus=reason,
                    afterGuardStatus=None, targetKey=None, targetUnitId=None, targetEntity=None,
                    targetVitals=None, targetContext=None, targetPosition=None)
                result = self.values(value)
                self.assertEqual('unavailable', result['status'])
                self.assertEqual(reason, result['unavailableReason'])
                self.assertIsNone(result['unitKey'])
                self.assertIsNone(result['positionCandidate'])
                self.assertIsNone(result['combatCandidate'])
                self.assertIsNone(result['health']['current'])
                self.assertEqual(reason, result['health']['unavailableReason'])

    def test_real_zero_and_false_are_preserved(self):
        value = report()
        observation = value['observation']
        observation['targetVitals']['health'].update(
            status='calculated-candidate', current=0, maximum=100, unavailableReason=None)
        observation['targetContext'].update(status='raw-typed-candidate', owner=0x20080000,
            rawLevel=0, rawCombat=0, combatCandidate=False, levelStatus='numeric-getter-candidate',
            levelBranch='owner', numericLevelCandidate=0)
        result = self.values(value)
        self.assertEqual(0, result['health']['current'])
        self.assertEqual(0, result['numericLevelCandidate'])
        self.assertIs(result['combatCandidate'], False)

    def test_source_timestamps_are_not_replaced(self):
        value = report()
        value['observation']['completedAtUtc'] = '2026-11-08T01:00:01.1234567Z'
        result = self.values(value)
        self.assertEqual(START, result['startedAtUtc'])
        self.assertEqual('2026-11-08T01:00:01.1234567Z', result['completedAtUtc'])

    def test_invalid_identity_is_rejected_before_values_are_returned(self):
        value = report()
        value['observation']['identity']['processStartUtcTicks'] += 1
        with self.assertRaises(ValueError):
            self.values(value)

    def test_values_do_not_share_mutable_position_or_vitals(self):
        value = report()
        original = copy.deepcopy(value)
        result = self.values(value)
        result['positionCandidate']['x'] = 999
        result['health']['current'] = 999
        self.assertEqual(original, value)


if __name__ == '__main__':
    unittest.main()
