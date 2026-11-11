#!/usr/bin/env python3
"""Derive a candidate physical movement vector from two retained native position bursts.

Offline only: a declared key/hold is not proof of delivery or game response.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import movement_controller as movement
from scripts import physical_route_preview as physical


class PhysicalCalibrationError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PhysicalCalibrationError(reason)


def calibrate(before_path: Path, after_path: Path, key: str, hold_ms: int) -> dict:
    before, before_sha = physical._read_native(before_path)
    after, after_sha = physical._read_native(after_path)
    require(before_sha != after_sha, 'before and after evidence must be independent')
    for field in ('processId', 'processStartUtcTicks', 'executableSha256'):
        require(before['identity'].get(field) == after['identity'].get(field),
                'native position process/build epoch changed')
    require(before['unitKey'] == after['unitKey'], 'native position player changed')
    require('firstSampleUtc' in after, 'native after-sample start unavailable')
    try:
        before_end = datetime.fromisoformat(before['lastSampleUtc'].replace('Z', '+00:00'))
        after_start = datetime.fromisoformat(after['firstSampleUtc'].replace('Z', '+00:00'))
    except (TypeError, ValueError, AttributeError) as error:
        raise PhysicalCalibrationError('native sample time invalid') from error
    require(before_end < after_start, 'before/after position captures overlap or reorder')
    try:
        measured = movement.calibrate_displacement(
            key, before['positions'][-1], after['positions'][0], hold_ms)
    except movement.MovementError as error:
        raise PhysicalCalibrationError(str(error)) from error
    identity = before['identity']
    return {
        'schemaVersion': 1,
        'status': 'offline-physical-calibration-candidate',
        'movementEligible': False,
        'actionVerified': False,
        'qualification': 'nominal-key-hold-and-two-native-position-candidates-only',
        'key': measured.key,
        'dx_per_ms': measured.dx_per_ms,
        'dz_per_ms': measured.dz_per_ms,
        'calibration_hold_ms': measured.calibration_hold_ms,
        'horizontal_displacement': measured.horizontal_displacement,
        'vertical_displacement': measured.vertical_displacement,
        'processId': identity['processId'],
        'processStartUtcTicks': str(identity['processStartUtcTicks']),
        'gameBuildSha256': identity['executableSha256'].upper(),
        'unitKey': before['unitKey'],
        'beforeReportSha256': before_sha,
        'afterReportSha256': after_sha,
        'beforeSampleUtc': before['lastSampleUtc'],
        'afterSampleUtc': after['firstSampleUtc'],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--key', choices=tuple(sorted(movement.MOVEMENT_KEYS)), required=True)
    parser.add_argument('--hold-ms', type=int, required=True)
    parser.add_argument('--out', type=Path, help='optional new JSON record; never overwrites')
    args = parser.parse_args(argv)
    try:
        result = calibrate(args.before, args.after, args.key, args.hold_ms)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if args.out is not None:
            with args.out.open('x', encoding='utf-8') as destination:
                destination.write(rendered + '\n')
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'blocked', 'reason': str(error)}))
        return 2
    print(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
