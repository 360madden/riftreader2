"""Direct-facing projection, raw float32 checks and the public physical command."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_rift as physical
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY
from tests.test_analyze_physical_turn_pair import matrix, sample


def report():
    # Shortest decimal float32 JSON can change an aim-vector subtraction unless
    # projection derives the angle from the preserved bits.
    values = [-.10222641, 7425.006, 861.5069, 2955.1047, 7426.1885, 863.58655, 2946.8757]
    bits = [struct.unpack('<I', struct.pack('<f', value))[0] for value in values]
    exact = [struct.unpack('<f', struct.pack('<I', value))[0] for value in bits]
    rows = []
    for i in range(3):
        orientation = sample('orientation', 1, 5.857142014, identity=REPORT_IDENTITY)
        body = -orientation['secondary']['planarAngleDegreesCandidate']
        system = (math.degrees(exact[0]) + 180) % 360 - 180
        rows.append({
            'identity': REPORT_IDENTITY, 'playerKeyDecimal': '239816685251645959',
            'playerEntityDecimal': '2098705793040', 'playerSystemDecimal': '2096880748192',
            'startedAtUtc': f'2026-11-12T03:13:22.{i}000000Z',
            'completedAtUtc': f'2026-11-12T03:13:22.{i}100000Z',
            'rawBits': bits, 'playerSystemYawRadiansCandidate': values[0],
            'playerSystemBearingDegreesCandidate': system,
            'bodyBearingDegreesCandidate': body,
            'primaryBearingDegreesCandidate': body,
            'playerSystemMinusPrimaryDegreesCandidate': (system - body + 180) % 360 - 180,
            'playerSystemMinusBodyDegreesCandidate': (system - body + 180) % 360 - 180,
            'positionOrientationCandidate': orientation,
            'positionCandidate': dict(zip(('x', 'y', 'z'), values[4:])),
            'cameraAimPointCandidate': dict(zip(('x', 'y', 'z'), values[1:4])),
            'cameraAimBearingDegreesCandidate': math.degrees(math.atan2(exact[1]-exact[4], exact[3]-exact[6])),
            'bearingConvention': 'degrees-from-positive-z-toward-positive-x',
            'headingQualified': False, 'cameraYawQualified': False,
        })
    return {'schemaVersion': 1, 'status': 'complete', 'identity': REPORT_IDENTITY,
            'contractVersion': 'native-current-facing-candidate-samples/1',
            'requestedSamples': 3, 'completedSamples': 3,
            'observation': rows[-1], 'observations': rows}


class PhysicalFacingTests(unittest.TestCase):
    def test_optical_camera_origin_and_angles_are_validated(self):
        values = [0, 0, -1, 0, 1, 0, 1, 0, 0, 3, 39, -8, 7424, 832, 2944]
        camera = {
            'status': 'available-candidate', 'unavailableReason': None,
            'sourceRootRva': '0x3362848', 'selectedModeCameraGetterRva': '0xF88580',
            'cameraYawQualified': False, 'rotationRowMajor': values[:9],
            'rendererEyeXYZ': values[9:12], 'renderOriginXYZ': values[12:],
            'rawBits': [struct.unpack('<I', struct.pack('<f', v))[0] for v in values],
            'bearingDegreesCandidate': 0, 'pitchDegreesCandidate': 0,
            'worldEyeXYZ': [7427, 871, 2936],
        }
        source = report()
        for row in source['observations']:
            row['opticalCameraCandidate'] = camera
        parsed = physical._native_values('facing', source)['opticalCamera']
        self.assertEqual([7427, 871, 2936], parsed['worldEyeXYZ'])
        self.assertFalse(parsed['cameraYawQualified'])
        for field, value in (('rawBits', [0] * 15), ('bearingDegreesCandidate', 10),
                             ('worldEyeXYZ', [7424, 832, 2944])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                physical._optical_camera_values(dict(camera, **{field: value}))
        missing = physical._optical_camera_values({
            'status': 'unavailable', 'unavailableReason': 'unsupported mode',
            'sourceRootRva': '0x3362848', 'selectedModeCameraGetterRva': '0xF88580',
            'cameraYawQualified': False})
        self.assertEqual('unavailable', missing['status'])

    def test_float32_rounded_camera_coordinates_keep_exact_angle(self):
        values = physical._native_values('facing', report())
        self.assertAlmostEqual(values['playerSystemBearingDegreesCandidate'], -5.857141638, places=7)
        self.assertAlmostEqual(values['bodyBearingDegreesCandidate'], -5.857142090, places=7)
        self.assertAlmostEqual(values['cameraAimBearingDegreesCandidate'], -8.178168873, places=7)
        self.assertEqual(3, values['sampleCount'])
        self.assertFalse(values['headingQualified'])
        self.assertFalse(values['cameraYawQualified'])

    def test_divergent_scalar_is_exposed_beside_matrix_bearing(self):
        source = report()
        for row in source['observations']:
            row['playerSystemYawRadiansCandidate'] = .5
            row['rawBits'][0] = 0x3F000000
            row['playerSystemBearingDegreesCandidate'] = math.degrees(.5)
            row['playerSystemMinusBodyDegreesCandidate'] = (
                math.degrees(.5) - row['bodyBearingDegreesCandidate'] + 180) % 360 - 180
            row['playerSystemMinusPrimaryDegreesCandidate'] = row['playerSystemMinusBodyDegreesCandidate']
        values = physical._native_values('facing', source)
        self.assertAlmostEqual(-5.857142090, values['bodyBearingDegreesCandidate'], places=7)
        self.assertGreater(values['playerSystemMinusBodyDegreesCandidate'], 34)

    def test_primary_yaw_remains_distinct_from_smoothed_body(self):
        source = report()
        for row in source['observations']:
            row['positionOrientationCandidate']['primary'] = matrix(30, 0x60)
            row['primaryBearingDegreesCandidate'] = -30
            row['playerSystemMinusPrimaryDegreesCandidate'] = (
                row['playerSystemBearingDegreesCandidate'] + 30 + 180) % 360 - 180
        values = physical._native_values('facing', source)
        self.assertAlmostEqual(-30, values['primaryBearingDegreesCandidate'])
        self.assertAlmostEqual(-5.857142090, values['bodyBearingDegreesCandidate'], places=7)

    def test_changed_owner_replay_forged_angle_and_bits_fail(self):
        for field, value in (('playerSystemDecimal', '123'),
                             ('bodyBearingDegreesCandidate', 90),
                             ('cameraAimBearingDegreesCandidate', 90),
                             ('rawBits', [0] * 7),
                             ('startedAtUtc', '2026-11-12T03:13:22.0000000Z')):
            with self.subTest(field=field):
                source = deepcopy(report())
                source['observations'][1][field] = value
                with self.assertRaises(ValueError):
                    physical._native_values('facing', source)

    def test_main_routes_facing_burst_to_selected_native_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'RiftReader2.Live.exe'
            executable.write_bytes(b'MZ')
            destination = Path(directory) / 'facing.json'
            def run(command, **kwargs):
                self.assertEqual(['sample-current-facing', '--pid', '123', '--start-ticks',
                                  IDENTITY['processStartUtcTicks']], command[1:6])
                self.assertEqual(['--samples', '3', '--interval-ms', '60'], command[-4:])
                destination.write_text(json.dumps(report()), encoding='utf-8')
                receipt = {'recordType': 'native-current-facing-summary/1',
                           'status': 'complete', 'output': str(destination), 'completedSamples': 3}
                return subprocess.CompletedProcess(command, 0, json.dumps(receipt), '')
            with patch.object(physical.socket, 'gethostname', return_value='AMD-DESKTOP'), \
                 patch.object(physical.observe_physical, '_identity', return_value=IDENTITY), \
                 patch.object(physical, 'NATIVE_EXE', executable), \
                 patch.object(physical.subprocess, 'run', side_effect=run), \
                 redirect_stdout(io.StringIO()) as output:
                code = physical.main(['--expected-host', 'AMD-DESKTOP', '--physical-pid', '123',
                                      '--read-native', 'facing', '--samples', '3', '--interval-ms', '60',
                                      '--output', str(destination)])
            self.assertEqual(0, code)
            self.assertEqual('complete', json.loads(output.getvalue())['status'])
