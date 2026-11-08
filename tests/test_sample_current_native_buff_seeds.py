"""Offline contract checks for the signed native buff grouping input."""
import unittest

from scripts.sample_current_native_buff_seeds import GAME_SHA, QUALIFICATION, validate_report


def report(value=-1, status='raw-candidate', state=0x40000):
    context = 0x20000
    return {
        'schemaVersion': 1, 'contractVersion': 'native-current-buff-seeds-candidate/1',
        'status': 'complete',
        'observation': {
            'qualification': QUALIFICATION,
            'identity': {'processId': 123, 'processStartUtcTicks': 456, 'executableSha256': GAME_SHA},
            'startedAtUtc': '2026-11-08T00:20:00+00:00',
            'completedAtUtc': '2026-11-08T00:20:01+00:00',
            'unitKey': 1, 'context': context, 'sentinel': context + 0x310,
            'nodes': [{
                'address': 0x30000, 'next': context + 0x310, 'object': 0x50000, 'control': 0,
                'rawObject': {
                    'status': 'raw-candidate', 'dword08': 1, 'qword10': 0, 'qword20': state,
                    'qword28': 0, 'dword3C': 0, 'qword48': 0,
                    'descriptorStatus': 'null', 'stateStatus': 'unavailable',
                    'clockStatus': 'unavailable',
                    'stateDword80': value, 'stateDword80Status': status,
                },
            }],
        },
    }


class BuffGroupingInputContractTests(unittest.TestCase):
    def check(self, value):
        return validate_report(value, pid=123, ticks=456)

    def test_signed_boundaries_and_zero(self):
        for number in (-(2**31), -1, 0, 1, 2**31 - 1):
            with self.subTest(number=number):
                self.assertEqual(
                    self.check(report(number))['nodes'][0]['rawObject']['stateDword80'],
                    number,
                )

    def test_explicit_null_unavailable_and_historical_absence(self):
        self.check(report(None, 'null', 0))
        self.check(report(None, 'unavailable', 0x40000))
        old = report()
        del old['observation']['nodes'][0]['rawObject']['stateDword80']
        del old['observation']['nodes'][0]['rawObject']['stateDword80Status']
        self.check(old)
        absent = report()
        absent['observation']['nodes'][0]['rawObject'] = {
            'status': 'unavailable', 'stateDword80': None, 'stateDword80Status': 'unavailable',
        }
        self.check(absent)

    def test_rejects_fabricated_group_values_or_status(self):
        for value, status, state in (
            (2**31, 'raw-candidate', 0x40000),
            (-(2**31)-1, 'raw-candidate', 0x40000),
            (True, 'raw-candidate', 0x40000),
            (0, 'unavailable', 0x40000),
            (0, 'raw-candidate', 0),
            (None, 'null', 0x40000),
            (None, 'invalid', 0x40000),
        ):
            with self.subTest(value=value, status=status, state=state):
                with self.assertRaises(ValueError):
                    self.check(report(value, status, state))
        bad = report()
        del bad['observation']['nodes'][0]['rawObject']['stateDword80Status']
        with self.assertRaises(ValueError):
            self.check(bad)


if __name__ == '__main__':
    unittest.main()
