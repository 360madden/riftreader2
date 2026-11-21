"""Offline independent replay of one four-source native selected-target profile.

Reopens original selected-target, selected-position and keyed-name sources,
checks retained SHA256 against the saved profile, and reproduces the comparison.
The report remains a native candidate, never independent game UI/API evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts import physical_selected_target_profile as profile

SOURCE_NAMES = {
    "selectedBefore": ("selected-before.json", "selected-target"),
    "selectedPosition": ("selected-position.json", "selected-position"),
    "unitName": ("unit-name.json", "unit-names"),
    "selectedAfter": ("selected-after.json", "selected-target"),
}
SHA = re.compile(r"[0-9A-Fa-f]{64}\Z")


def require(test, reason):
    if not test:
        raise ValueError("selected-target-profile-replay-" + reason)


def _read_json(path, *, max_size):
    require(path.is_file() and not path.is_symlink(),
            "source-file-unavailable")
    raw = path.read_bytes()
    require(0 < len(raw) <= max_size, "source-size-unqualified")
    doc = physical_rift._strict_native_json(raw.decode("utf-8-sig"))
    require(type(doc) is dict, "source-not-object")
    return doc, hashlib.sha256(raw).hexdigest().upper()


def replay(path):
    path = Path(path).absolute()
    report, profile_sha = _read_json(path, max_size=1024*1024)
    require(report.get("schema") == profile.SCHEMA
            and report.get("status") in (
                "no-target-baseline-candidate", "selected-target-candidate")
            and report.get("gameplayInputSent") is False
            and report.get("selectedIdentityAtEndpointsMatched") is True
            and report.get("intermediateSelectionHistory") == "unavailable"
            and report.get("hostilityStatus") == "unqualified"
            and report.get("combatSuitabilityStatus") == "unqualified",
            "profile-unqualified")
    identity = report.get("process")
    require(type(identity) is dict and set(identity) == {
        "processId", "processStartUtcTicks", "executableSha256"}
        and type(identity["processId"]) is int and identity["processId"] > 0
        and type(identity["processStartUtcTicks"]) is str
        and identity["processStartUtcTicks"].isdecimal()
        and identity["executableSha256"] == profile.BUILD_1179,
        "profile-owner-unqualified")
    expected_keys = (("selectedBefore", "selectedAfter")
                     if report["status"] == "no-target-baseline-candidate"
                     else tuple(SOURCE_NAMES))
    shas, paths = report.get("nativeSourcesSha256"), report.get("sourcePaths")
    require(type(shas) is dict and type(paths) is dict
            and set(shas) == set(expected_keys)
            and set(paths) == set(expected_keys), "source-inventory-mismatch")
    original, projected = {}, {}
    for key in expected_keys:
        filename, kind = SOURCE_NAMES[key]
        source = path.parent / filename
        require(paths[key] == str(source) and type(shas[key]) is str
                and SHA.fullmatch(shas[key]) is not None,
                "source-path-or-sha-invalid")
        raw, sha = _read_json(source, max_size=8*1024*1024)
        require(sha == shas[key].upper(), "source-sha-mismatch")
        observation = raw.get("observation")
        owner = observation.get("identity") if type(observation) is dict else None
        require(type(owner) is dict and owner.get("processId") == identity["processId"]
                and str(owner.get("processStartUtcTicks")) ==
                    identity["processStartUtcTicks"]
                and owner.get("executableSha256") == identity["executableSha256"],
                "source-owner-changed")
        original[key] = raw
        projected[key] = physical_rift._native_values(kind, raw)
        require(projected[key] is not None, "source-projection-unavailable")
    before, after = original["selectedBefore"], original["selectedAfter"]
    start, finish = projected["selectedBefore"], projected["selectedAfter"]
    position = original.get("selectedPosition")
    name = projected.get("unitName")
    checked_positions = None
    if position is not None:
        samples = position.get("observations")
        require(type(samples) is list and len(samples) == 2
                and position.get("observation") == samples[-1]
                and position.get("identity") == samples[-1].get("identity")
                and position.get("completedSamples") == 2
                and position.get("requestedSamples") == 2,
                "position-burst-unqualified")
        t = physical_rift._utc_tick_order_key
        require(
            all(t(row["startedAtUtc"]) <= t(row["completedAtUtc"])
                for row in samples)
            and t(before["observation"]["completedAtUtc"]) <=
                t(samples[0]["startedAtUtc"])
            and t(samples[0]["completedAtUtc"]) <= t(samples[1]["startedAtUtc"]),
            "position-burst-chronology-invalid")
        checked_positions = []
        for sample in samples:
            require(type(sample) is dict
                    and sample.get("identity") == position["identity"],
                    "position-burst-owner-changed")
            checked_positions.append(physical_rift._native_values(
                "selected-position", {
                    "schemaVersion": 1,
                    "contractVersion": "native-current-selected-position-candidate-sample/1",
                    "status": "complete", "observation": sample}))
        require(checked_positions[-1] == projected["selectedPosition"],
                "position-burst-last-projection-mismatch")
    endpoints = [
        (before["observation"]["startedAtUtc"],
         before["observation"]["completedAtUtc"])
    ]
    if position is not None:
        endpoints += [
            (position["observation"]["startedAtUtc"],
             position["observation"]["completedAtUtc"]),
            (original["unitName"]["observation"]["startedAtUtc"],
             original["unitName"]["observation"]["completedAtUtc"])]
    endpoints += [(after["observation"]["startedAtUtc"],
                   after["observation"]["completedAtUtc"])]
    t = physical_rift._utc_tick_order_key
    require(all(t(a) <= t(b) for a, b in endpoints)
            and all(t(first[1]) <= t(second[0])
                    for first, second in zip(endpoints, endpoints[1:])),
            "source-chronology-invalid")
    elapsed = (t(endpoints[-1][1])[0] - t(endpoints[0][0])[0]).total_seconds()
    require(0 <= elapsed <= 30 and report.get("capturedSpanSeconds") == elapsed,
            "source-span-unqualified")
    result = profile.compare(before, dict(after, nativeValues=finish), start,
                             name["rows"][0] if name is not None
                             and type(name.get("rows")) is list
                             and len(name["rows"]) == 1 else None,
                             checked_positions, position)
    for key, value in result.items():
        require(report.get(key) == value, "summary-field-conflict-" + key)
    require(report.get("selfUnitKey") == start.get("selfUnitKey"),
            "self-key-conflict")
    require(report.get("qualification") ==
            ("Each source was separately acquired and pinned to "
             "the identical physical game process and on-disk build, "
             "then reopened against its native SHA receipt. Selected "
             "key, entity, self key and temporal order were checked. "
             "Intermediate selected-target changes (including A-B-A) "
             "are unobserved. Sequential matching native values do "
             "not independently verify RIFT UI/API meaning, world "
             "instance, hostility, attackability, LOS, movement, "
             "or combat outcomes."),
            "profile-qualification-conflict")
    return {
        "status": "source-replayed-candidate", "profileStatus": report["status"],
        "sourceCount": len(expected_keys),
        "selectedUnitIdCandidate": result["selectedUnitIdCandidate"],
        "baseNameCandidate": result["baseNameCandidate"],
        "targetLevelCandidate": result["targetLevelCandidate"],
        "healthCandidate": result["healthCandidate"],
        "profileSha256": profile_sha,
        "inputSent": False, "qualification": (
            "Original native source bytes and bounded process/time/target "
            "relationships independently replayed; no live API/UI validation, "
            "gameplay causality, hostility or combat authority.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = replay(args.profile)
    except (OSError, ValueError, TypeError, KeyError,
            UnicodeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240],
                          "inputSent": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
