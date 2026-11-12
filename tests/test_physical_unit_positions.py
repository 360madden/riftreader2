"""Bounded loaded-unit projection retains ownership, timing and coverage limits."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_rift as p
from tests.test_physical_facing import optical_camera
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY


def bits(xyz):
    return [struct.unpack('<I', struct.pack('<f', xyz[axis]))[0] for axis in ('x', 'y', 'z')]


def report():
    origin = {'x': 7427, 'y': 871, 'z': 2946}
    rows = []
    for i, (key, point, distance) in enumerate((('42', origin, 0),
            (str(2**64 - 1), {'x': 7430, 'y': 871, 'z': 2950}, 5))):
        rows.append({'unitKey': key, 'unitIdCandidate': f'u{int(key):016X}',
                     'entityAddressDecimal': str(0x20004000 + i * 0x1000),
                     'positionCandidate': point, 'rawBits': bits(point),
                     'startedAtUtc': f'2026-11-12T04:00:00.0{i * 2 + 1}00000Z',
                     'completedAtUtc': f'2026-11-12T04:00:00.0{i * 2 + 2}00000Z',
                     'horizontalDistanceCandidate': distance})
    observation = {'identity': REPORT_IDENTITY, 'startedAtUtc': '2026-11-12T04:00:00Z',
                   'completedAtUtc': '2026-11-12T04:00:00.1000000Z', 'selfKey': '42',
                   'selfPositionCandidate': origin, 'selfPositionRawBits': bits(origin),
                   'unitLimit': 512, 'examined': 3, 'noPosition': 1, 'unavailable': 0,
                   'unavailableChains': 0, 'bucketsExamined': 1, 'startBucket': 0,
                   'bucketCount': 1, 'unitLimitReached': False, 'readBytes': 4096,
                   'opticalCameraCandidate': optical_camera(), 'opticalCameraAfterCandidate': optical_camera(),
                   'cameraStableCandidate': True, 'worldIdentityStatus': 'unavailable', 'rows': rows}
    return {'schemaVersion': 1, 'contractVersion': 'native-current-unit-positions-candidate-sample/1',
            'status': 'complete', 'observation': observation}


class PhysicalUnitPositionsTests(unittest.TestCase):
    def test_lossless_keys_exact_geometry_and_partial_coverage(self):
        value = p._native_values('unit-positions', report())
        self.assertEqual(2, value['positionsFound'])
        self.assertEqual(1, value['unitsWithoutPosition'])
        self.assertEqual(str(2**64 - 1), value['units'][1]['unitKey'])
        self.assertEqual(5, value['units'][1]['horizontalDistanceCandidate'])
        self.assertAlmostEqual((1 - 3/14)/2, value['units'][1]['screenPointCandidate']['normalizedX'])
        self.assertEqual('bounded-unit-manager-subset', value['worldCoverage'])

    def test_forged_bits_distance_owner_and_coverage_fail(self):
        for fault in ('bits', 'distance', 'owner', 'coverage', 'camera', 'time'):
            with self.subTest(fault=fault):
                source = report()
                row = source['observation']['rows'][1]
                if fault == 'bits': row['rawBits'] = [0, 0, 0]
                if fault == 'distance': row['horizontalDistanceCandidate'] = 10
                if fault == 'owner': row['unitKey'] = '42'
                if fault == 'coverage': source['observation']['examined'] = 5
                if fault == 'camera': source['observation']['cameraStableCandidate'] = False
                if fault == 'time': row['startedAtUtc'] = '2026-11-12T03:00:00Z'
                with self.assertRaises(ValueError):
                    p._native_values('unit-positions', source)

    def test_camera_change_retains_positions_and_withholds_screen_points(self):
        source = report()
        source['observation']['opticalCameraAfterCandidate']['cameraAddressDecimal'] = '2096815868168'
        source['observation']['cameraStableCandidate'] = False
        value = p._native_values('unit-positions', source)
        self.assertEqual(2, value['positionsFound'])
        self.assertTrue(all(unit['screenPointCandidate']['status'] == 'unavailable' for unit in value['units']))

    def test_main_routes_scan_options_and_rejects_them_for_other_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            exe, output = Path(directory) / 'reader.exe', Path(directory) / 'units.json'
            exe.write_bytes(b'MZ')
            def run(command, **kwargs):
                self.assertEqual('sample-current-unit-positions', command[1])
                self.assertEqual(['--unit-limit', '512', '--start-bucket', '7'], command[-4:])
                output.write_text(json.dumps(report()))
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    'recordType': 'native-current-unit-positions-summary/1', 'status': 'complete',
                    'positions': 2, 'output': str(output)}), '')
            with patch.object(p.socket, 'gethostname', return_value='AMD-DESKTOP'), \
                 patch.object(p.observe_physical, '_identity', return_value=IDENTITY), \
                 patch.object(p, 'NATIVE_EXE', exe), patch.object(p.subprocess, 'run', side_effect=run), \
                 redirect_stdout(io.StringIO()) as text:
                self.assertEqual(0, p.main(['--expected-host', 'AMD-DESKTOP', '--physical-pid', '123',
                    '--read-native', 'unit-positions', '--unit-limit', '512', '--start-bucket', '7', '--output', str(output)]))
            self.assertEqual(2, json.loads(text.getvalue())['nativeValues']['positionsFound'])
        with patch.object(p, 'select_physical') as select, redirect_stdout(io.StringIO()):
            self.assertEqual(2, p.main(['--expected-host', 'AMD-DESKTOP', '--read-native', 'facing', '--unit-limit', '10']))
            select.assert_not_called()
