"""Read-only screenshot/native association must reject drift without losing the frame."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import observe_target as tool, physical_rift
from tests.test_physical_facing import report_with_target
from tests.test_physical_only_selection import IDENTITY


class NativeFacingObservationTests(unittest.TestCase):
    def run_bracket(self, fault=None):
        source = report_with_target()
        row = deepcopy(source['observations'][0])
        source.update(observation=row, observations=[row], requestedSamples=1, completedSamples=1)
        before = source
        after = deepcopy(source)
        def shift(value):
            if isinstance(value, dict):
                return {key: ((datetime.fromisoformat(item.replace('Z', '+00:00')) + timedelta(seconds=2)).isoformat()
                              if key in ('startedAtUtc', 'completedAtUtc') else shift(item))
                        for key, item in value.items()}
            if isinstance(value, list):
                return [shift(item) for item in value]
            return value
        after = shift(after)
        last = after['observation']
        if fault == 'owner':
            last['playerEntityDecimal'] = '2098705793048'
        if fault == 'camera':
            for name in ('opticalCameraCandidate', 'opticalCameraAfterTargetCandidate'):
                last[name]['cameraAddressDecimal'] = '2096815868168'
        if fault == 'target':
            target = last['targetPositionPairCandidate']['target']
            target.update(unitKey='100', unitIdCandidate='u0000000000000064')
        # JSON has one logical last observation, rather than two independently shifted copies.
        after['observations'] = [last]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / 'before.json', root / 'after.json']
            for path, report in zip(paths, (before, after)):
                path.write_text(json.dumps(report))
            receipt = root / 'image.json'
            receipt.write_text(json.dumps({
                'imageSha256': 'A' * 64,
                'capturedStartedAtUtc': '2026-11-12T03:13:22.0000000Z' if fault == 'order' else '2026-11-12T03:13:22.5000000Z',
                'capturedCompletedAtUtc': '2026-11-12T03:13:22.6000000Z'}))
            selection = {'status': 'ready', 'target': IDENTITY}
            snapshots = [{'status': 'complete', 'nativeOutput': str(path)} for path in paths]
            if fault == 'before-failure':
                snapshots[0] = {'status': 'blocked', 'reason': 'reader-busy'}
            if fault == 'after-failure':
                snapshots[1] = {'status': 'blocked', 'reason': 'changed-epoch'}
            frame = {'status': 'verified-awaiting-visual-review', 'workflow': 'physical',
                     'targetId': 'physical-amd-desktop', 'target': dict(IDENTITY),
                     'image': str(root / 'image.png'), 'receipt': str(receipt), 'imageSha256': 'A' * 64}
            if fault == 'identity':
                frame['target']['processStartUtcTicks'] = '999'
            with patch.object(physical_rift, 'select_physical', return_value=selection), \
                 patch.object(physical_rift, 'read_native', side_effect=snapshots) as native, \
                 patch('scripts.observe_gpu.capture_gpu', return_value=frame) as gpu, \
                 patch.object(tool.time, 'perf_counter', side_effect=[0, 6] if fault == 'slow' else [0, 1]):
                result = tool._capture_with_native_facing('AMD-DESKTOP', root / 'frame', 123)
            gpu.assert_called_once_with('AMD-DESKTOP', root / 'frame', physical_pid=123)
            self.assertEqual(1 if fault == 'before-failure' else 2, native.call_count)
            self.assertEqual('verified-awaiting-visual-review', result['status'])
            return result['nativeFacing']

    def test_stable_state_has_values_associated_with_frame(self):
        bracket = self.run_bracket()
        self.assertEqual('stable-bracket-candidate', bracket['status'])
        self.assertEqual('239816685251645959', bracket['values']['playerKey'])
        self.assertEqual('99', bracket['values']['selectedTargetProjectionCandidate']['targetKey'])

    def test_drift_and_bad_order_withhold_values_but_retain_image(self):
        cases = {'owner': 'player-changed', 'camera': 'camera-unavailable-or-changed',
                 'target': 'target-changed', 'identity': 'identity-mismatch',
                 'order': 'acquisition-order-mismatch', 'slow': 'exceeded-five-seconds',
                 'before-failure': 'native-before-unavailable', 'after-failure': 'native-after-unavailable'}
        for fault, reason in cases.items():
            with self.subTest(fault=fault):
                bracket = self.run_bracket(fault)
                self.assertEqual('unavailable', bracket['status'])
                self.assertIn(reason, bracket['reason'])
                self.assertNotIn('values', bracket)

    def test_cli_uses_native_wgc_path_and_rejects_foreground_or_vm_modes(self):
        result = {'status': 'verified-awaiting-visual-review', 'targetId': 'physical-amd-desktop',
                  'workflow': 'physical'}
        with patch.object(tool.socket, 'gethostname', return_value='AMD-DESKTOP'), \
             patch.object(tool, '_capture_with_native_facing', return_value=result) as capture, \
             patch.object(tool, '_capture_physical') as desktop, redirect_stdout(io.StringIO()):
            self.assertEqual(0, tool.main(['--target', 'physical-amd-desktop', '--expected-host',
                                          'AMD-DESKTOP', '--physical-pid', '123', '--native-facing']))
            capture.assert_called_once_with('AMD-DESKTOP', None, 123)
            desktop.assert_not_called()
            for target, kwargs in (('lab1', {}), ('physical-amd-desktop', {'allow_foreground_change': True})):
                with self.assertRaisesRegex(ValueError, 'focus-neutral-physical'):
                    tool.observe(target, 'AMD-DESKTOP', native_facing=True, **kwargs)
