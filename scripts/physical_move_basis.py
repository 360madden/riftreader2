#!/usr/bin/env python3
"""Build offline W/S/Q/E movement vectors and optional A/D turn candidates.

Uses retained move-key receipts and native observations. The output preserves
source provenance and the qualification limits of the recorded measurements.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.physical_move_key_calibration import from_helper_receipt

KEYS = ("w", "s", "q", "e")
BUNDLE_SCHEMA = "rr2-physical-movement-calibration-bundle/1"
BUNDLE_REPORT = "movement-basis.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _utc(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("basis-time-invalid") from exc
    require(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
            "basis-time-invalid")
    return result


def vector(report):
    return (report["dxPerMillisecondCandidate"],
            report["dzPerMillisecondCandidate"])


def geometry(first, second):
    x, z = first
    a, b = second
    norm1, norm2 = math.hypot(x, z), math.hypot(a, b)
    require(all(math.isfinite(v) for v in (x, z, a, b, norm1, norm2))
            and norm1 > 0 and norm2 > 0, "basis-velocity-invalid")
    dot = (x * a + z * b) / (norm1 * norm2)
    cross = (x * b - z * a) / (norm1 * norm2)
    dot = max(-1.0, min(1.0, dot))
    cross = max(-1.0, min(1.0, cross))
    return {
        "unsignedAngleDegreesCandidate": math.degrees(math.acos(dot)),
        "signedAngleDegreesCandidate": math.degrees(math.atan2(cross, dot)),
        "normalizedDotCandidate": dot,
        "normalizedCrossCandidate": cross,
        "firstSpeedOverSecondCandidate": norm1 / norm2,
    }


def analyze(paths, *, later_forward=None, turn_sources=None, target_preflight=None):
    require(type(paths) is dict and set(paths) == set(KEYS), "basis-keys-required")
    inputs = {key: from_helper_receipt(Path(paths[key])) for key in KEYS}
    require(all(inputs[key]["key"] == key for key in KEYS), "basis-key-mismatch")
    if later_forward is not None:
        after = from_helper_receipt(Path(later_forward))
        require(after["key"] == "w", "basis-later-forward-key-invalid")
        inputs["laterW"] = after

    values = tuple(inputs.values())
    identifiers = ("machine", "processId", "processStartUtcTicks",
                   "gameBuildSha256", "unitKey")
    require(all(all(r[field] == values[0][field] for field in identifiers)
                for r in values), "basis-player-process-build-mismatch")
    source_hashes = [v["sourceReceiptSha256"] for v in values]
    require(len(set(source_hashes)) == len(source_hashes), "basis-duplicate-source")

    ordered_keys = [*KEYS]
    if "laterW" in inputs:
        ordered_keys.append("laterW")
    starts = [_utc(inputs[k]["beforeSampleUtc"]) for k in ordered_keys]
    ends = [_utc(inputs[k]["afterSampleUtc"]) for k in ordered_keys]
    require(all(starts[i] < ends[i] for i in range(len(starts))), "basis-sample-time-invalid")
    require(all(ends[i] < starts[i + 1] for i in range(len(starts) - 1)),
            "basis-chronology-invalid")
    gaps = {f"{ordered_keys[i]}_to_{ordered_keys[i+1]}":
            (starts[i+1] - ends[i]).total_seconds()
            for i in range(len(starts) - 1)}

    matrix = {
        "forwardVsBackward": geometry(vector(inputs["w"]), vector(inputs["s"])),
        "forwardVsLeftStrafe": geometry(vector(inputs["w"]), vector(inputs["q"])),
        "leftVsRightStrafe": geometry(vector(inputs["q"]), vector(inputs["e"])),
        "backwardVsLeftStrafe": geometry(vector(inputs["s"]), vector(inputs["q"])),
    }
    if "laterW" in inputs:
        matrix["earlyVsLaterForward"] = geometry(
            vector(inputs["w"]), vector(inputs["laterW"]))
    cardinal = (
        abs(matrix["forwardVsBackward"]["unsignedAngleDegreesCandidate"] - 180) <= 10
        and abs(matrix["forwardVsLeftStrafe"]["unsignedAngleDegreesCandidate"] - 90) <= 10
        and abs(matrix["leftVsRightStrafe"]["unsignedAngleDegreesCandidate"] - 180) <= 10
        and abs(matrix["backwardVsLeftStrafe"]["unsignedAngleDegreesCandidate"] - 90) <= 10
    )

    reprojected = None
    if "laterW" in inputs and cardinal:
        # A *model*, not measured current strafe. Relative angular rotation
        # follows observed forward direction; speed scale assumes proportional
        # movement response across keys and is unverified for changed facing.
        signed = matrix["earlyVsLaterForward"]["signedAngleDegreesCandidate"]
        forward_scale = math.hypot(*vector(inputs["laterW"])) / math.hypot(*vector(inputs["w"]))
        if abs(signed) <= 45 and 0.8 <= forward_scale <= 1.2:
            radians = math.radians(signed)
            c, s = math.cos(radians), math.sin(radians)
            reprojected = {}
            for key in ("s", "q", "e"):
                x, z = vector(inputs[key])
                reprojected[key] = {
                    "vxPerMillisecondCandidate": (x*c - z*s) * forward_scale,
                    "vzPerMillisecondCandidate": (x*s + z*c) * forward_scale,
                }
            reprojected = {
                "status": "unverified-rigid-rotation-model",
                "relativeDirectionChangeDegreesCandidate": signed,
                "speedScaleFromForwardCandidate": forward_scale,
                "modeledVectors": reprojected,
                "sameFacingConfirmed": False,
                "navigationEligible": False,
                "qualification": "Rotated earlier key vectors to later forward; no later strafe measurements.",
            }

    basis = {
        "schemaVersion": 1,
        "status": "offline-physical-key-basis-candidate",
        "movementEligible": False,
        "navigationEligible": False,
        "headingQualified": False,
        "sameFacingConfirmed": False,
        "gameResponseVerified": False,
        "cardinalGeometryCandidate": cardinal,
        "sourceKind": "same-epoch-distinct-helper-receipts",
        "identity": {field: values[0][field] for field in identifiers},
        "sourceReceiptsSha256": {key: inputs[key]["sourceReceiptSha256"] for key in ordered_keys},
        "samples": {key: {
            "observedHoldMilliseconds": inputs[key]["observedHoldMilliseconds"],
            "horizontalSpeedPerMillisecondCandidate": math.hypot(*vector(inputs[key])),
            "vxCandidate": vector(inputs[key])[0],
            "vzCandidate": vector(inputs[key])[1],
            "beforeSampleUtc": inputs[key]["beforeSampleUtc"],
            "afterSampleUtc": inputs[key]["afterSampleUtc"],
        } for key in ordered_keys},
        "timeBetweenSamplesSeconds": gaps,
        "geometry": matrix,
        "laterFacingReprojectionCandidate": reprojected,
        "limitations": [
            "Same process/player/build does not prove unchanged facing, zone or world instance.",
            "Observed XYZ vectors are native-memory candidates; game consumption is unverified.",
            "This geometry comparison does not establish actor-facing continuity between receipts.",
            "A matching cardinal pattern is not approval to execute navigation.",
            "Long key holds are observations, not a validated linear model for short pulses.",
            "Optional later-facing reprojection assumes rigid rotation and proportional speeds; not observed.",
        ],
    }
    calibration_start = None
    if target_preflight is not None:
        from scripts.physical_rift import _utc_tick_order_key
        from scripts.prepare_physical_move_calibration import verify_preflight

        target, baseline, preflight_digest = verify_preflight(target_preflight)
        identity = basis["identity"]
        require(identity["machine"].casefold() == target["hostName"].casefold()
                and identity["processId"] == target["processId"]
                and identity["processStartUtcTicks"] == target["processStartUtcTicks"]
                and identity["gameBuildSha256"].casefold() == target["executableSha256"].casefold()
                and identity["unitKey"] == baseline["unitKey"], "basis-calibration-preflight-target-mismatch")
        calibration_start = _utc_tick_order_key(baseline["completedAtUtc"])
        require(calibration_start <= _utc_tick_order_key(inputs["w"]["beforeSampleUtc"]),
                "basis-measurement-predates-preflight")
        basis["preflightSummarySha256"] = preflight_digest
    if turn_sources is not None:
        from scripts.physical_turn_calibration_receipts import turn_calibration
        require(cardinal, "basis-cardinal-geometry-required-for-turns")
        basis["turnCalibrationCandidate"] = turn_calibration(basis["identity"], turn_sources, not_before=calibration_start)
    return basis


def _same_basis(a, b):
    """Compare saved and recomputed values with room for floating-point rounding."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same_basis(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same_basis(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def _write_report(path, report):
    rendered = json.dumps(report, sort_keys=True, allow_nan=False)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(rendered + "\n")


def local_calibration_folder(root, host):
    return root / ".local" / "waypoints-calibration" / host.lower()


def _bundle_sources(directory):
    from scripts.prepare_physical_move_calibration import FACING, SUMMARY

    translations = {key: directory / f"{key}.json" for key in KEYS}
    turns = {key: tuple(directory / f"{key}-{part}.json" for part in ("before", "pulse", "after"))
             for key in ("a", "d")}
    preflight = directory / SUMMARY
    required = (preflight, directory / FACING, *translations.values(), *turns["a"], *turns["d"])
    return translations, turns, preflight, required


def calibration_bundle(directory, *, verify=False):
    """Build or independently replay a complete calibration kept in one directory."""
    from scripts.physical_move_basis_waypoint import read_basis
    directory = Path(directory)
    require(directory.is_dir(), "calibration-bundle-directory-unavailable")
    destination = directory / BUNDLE_REPORT
    if verify:
        saved, saved_sha = read_basis(destination)
        require(saved.get("bundleSchema") == BUNDLE_SCHEMA, "invalid-calibration-bundle-schema")
    else:
        require(not destination.exists() and not destination.is_symlink(), "calibration-bundle-output-exists")

    translations, turns, preflight, required = _bundle_sources(directory)
    missing = [path.name for path in required if not path.is_file()]
    require(not missing, "calibration-bundle-missing: " + ", ".join(missing))
    report = analyze(translations, turn_sources=turns, target_preflight=preflight)
    report["bundleSchema"] = BUNDLE_SCHEMA
    if verify:
        require(_same_basis(saved, report), "calibration-bundle-basis-mismatch")
        return {"status": "verified-calibration-bundle", "identity": report["identity"],
                "basisSha256": saved_sha, "sourceCount": len(required), "movementEligible": False}
    _write_report(destination, report)
    return report


def install_calibration_bundle(expected_host, directory):
    """Install one verified same-host bundle as this checkout's Waypoints default."""
    from scripts import observe_physical, physical_rift

    require(sys.platform == "win32", "calibration-install-requires-windows")
    require(physical_rift.is_local_host(expected_host), "calibration-install-host-mismatch")
    source = observe_physical._local_absolute_path(Path(directory).absolute(), "invalid-calibration-source-path")
    _, _, _, measurements = _bundle_sources(source)
    files = (*measurements, source / BUNDLE_REPORT)
    for path in files:
        observe_physical._plain_path(path)
    verified = calibration_bundle(source, verify=True)
    require(verified["identity"]["machine"].casefold() == expected_host.casefold(), "calibration-bundle-host-mismatch")

    destination = local_calibration_folder(ROOT, expected_host)
    observe_physical._plain_path(destination)
    if destination.exists():
        installed = calibration_bundle(destination, verify=True)
        require(installed["basisSha256"] == verified["basisSha256"], "different-default-calibration-already-installed")
        status = "calibration-bundle-already-installed"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="calibration-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "bundle"
            staged.mkdir()
            for path in files:
                shutil.copyfile(path, staged / path.name)
            copied = calibration_bundle(staged, verify=True)
            require(copied["basisSha256"] == verified["basisSha256"], "calibration-bundle-changed-during-install")
            staged.rename(destination)
        status = "calibration-bundle-installed"
    return {**verified, "status": status, "basisPath": str(destination), "inputSent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bundle", type=Path, help="build movement-basis.json in a complete local calibration folder")
    mode.add_argument("--verify-bundle", type=Path, help="recompute and verify the saved basis against its sibling files")
    mode.add_argument("--install-bundle", type=Path, help="verify and copy a same-host bundle into this checkout")
    parser.add_argument("--expected-host", help="required local Windows hostname for --install-bundle")
    for key, long_name in (("w", "--forward"), ("s", "--backward"),
                           ("q", "--left"), ("e", "--right")):
        parser.add_argument(long_name, type=Path, dest=key)
    parser.add_argument("--later-forward", type=Path)
    parser.add_argument("--target-preflight", type=Path,
                        help="match saved measurements to the supplied read-only calibration preflight")
    for key in ("a", "d"):
        parser.add_argument(f"--turn-{key}", type=Path, nargs=3, metavar=("BEFORE", "PULSE", "AFTER"),
                            help=f"settled facing reports bracketing one {key.upper()} move-key receipt")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    translations = {key: getattr(args, key) for key in KEYS}
    turns = {key: paths for key, paths in (("a", args.turn_a), ("d", args.turn_d)) if paths is not None}
    if args.install_bundle is not None and args.expected_host is None:
        parser.error("--install-bundle requires --expected-host")
    if args.expected_host is not None and args.install_bundle is None:
        parser.error("--expected-host applies only to --install-bundle")
    if args.bundle or args.verify_bundle or args.install_bundle:
        if any(translations.values()) or turns or args.later_forward or args.target_preflight or args.out:
            parser.error("Bundle modes use the folder's standard filenames and do not accept individual files.")
    elif not all(translations.values()):
        parser.error("Supply --forward, --backward, --left and --right, or choose a bundle mode.")
    try:
        if args.install_bundle is not None:
            result = install_calibration_bundle(args.expected_host, args.install_bundle)
        elif args.bundle or args.verify_bundle:
            result = calibration_bundle(args.bundle or args.verify_bundle, verify=args.verify_bundle is not None)
        else:
            result = analyze(translations, later_forward=args.later_forward, turn_sources=turns or None,
                             target_preflight=args.target_preflight)
            if args.out:
                _write_report(args.out, result)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
