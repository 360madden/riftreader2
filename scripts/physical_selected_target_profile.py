"""One physical RIFT selected-target profile from existing read-only native readers.

The four source acquisitions are sequential. Their source receipts and exact
process identity are retained; no action, game input, UI focus or casting occurs.
A matching name/position is a candidate, not hostility or combat suitability.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.physical_nearby_units import source_from_receipt

SCHEMA = "rr2-physical-selected-target-profile/1"
BUILD_1179 = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
UNIT = re.compile(r"u[0-9A-F]{16}\Z")


def require(ok, reason):
    if not ok:
        raise ValueError("selected-target-profile-" + reason)


def source(selection, kind, path, *, read, **kwargs):
    receipt = read(selection, kind, output=path, **kwargs)
    require(type(receipt) is dict, "native-receipt-invalid")
    raw, values, digest = source_from_receipt(receipt, path, selection, kind)
    require(type(receipt.get("nativeSourceSha256")) is str
            and receipt["nativeSourceSha256"].casefold() == digest.casefold(),
            "native-source-receipt-sha-missing")
    return raw, values, digest, receipt


def compare(first, second, selected, name, pos_values, pos_raw):
    """Require same entity/self and ordered native sources, not one atomic snapshot."""
    one, two = first["observation"], second["observation"]
    require(one["identity"] == two["identity"]
            and one["selfKey"] == two["selfKey"], "self-or-epoch-changed")
    status_one, status_two = selected["status"], second["nativeValues"]["status"]
    require(status_one in ("candidate", "unavailable")
            and status_two == status_one, "selected-state-changed")
    if status_one == "unavailable":
        return {
            "status": "no-target-baseline-candidate",
            "selectedUnitIdCandidate": None, "baseNameCandidate": None,
            "nameStatus": "not-applicable",
            "targetLevelCandidate": None, "healthCandidate": None,
            "resourceCandidate": None, "positionXYZCandidate": None,
            "positionAgreement": "not-applicable",
            "selectedEntityAddressDecimal": None,
        }
    key = selected["unitKey"]
    require(type(key) is str and key.isdecimal() and key == str(int(key))
            and 0 < int(key) < 2**64 and
            selected["unitId"] == f"u{int(key):016X}"
            and UNIT.fullmatch(selected["unitId"]) is not None,
            "selected-unit-id-invalid")
    require(two.get("targetKey") == int(key)
            and two.get("targetUnitId") == selected["unitId"]
            and one.get("targetEntity") == two.get("targetEntity")
            and type(two.get("targetEntity")) is int
            and two["targetEntity"] >= 0x10000,
            "selected-unit-or-entity-changed")
    require(type(name) is dict and name.get("unitKey") == key,
            "name-unit-key-mismatch")
    ent = str(two["targetEntity"])
    consistent_name = (name.get("status") == "available-candidate"
                       and name.get("entityAddressDecimal") == ent
                       and type(name.get("baseNameCandidate")) is str
                       and bool(name["baseNameCandidate"].strip()))
    if name.get("entityAddressDecimal") != ent:
        name_status = "entity-mismatch-unavailable"
    elif consistent_name:
        name_status = "cache-name-candidate"
    else:
        name_status = "cache-name-unavailable"
    require(type(pos_values) is list and len(pos_values) == 2
            and type(pos_raw.get("observations")) is list
            and len(pos_raw["observations"]) == 2,
            "selected-position-burst-invalid")
    for row in pos_values:
        require(type(row) is dict
                and row.get("status") == "position-candidate"
                and row.get("targetKey") == key
                and row.get("selfKey") == str(one["selfKey"])
                and row.get("rawFallbackKey") == key,
                "selected-position-identity-changed")
    require(str(pos_raw["observation"].get("targetEntityDecimal")) == ent
            and all(str(x.get("targetEntityDecimal")) == ent
                    for x in pos_raw["observations"]),
            "selected-position-entity-changed")
    coords = [selected["positionCandidate"],
              *(row.get("targetPositionXYZCandidate") for row in pos_values),
              second["nativeValues"]["positionCandidate"]]
    require(all(type(xyz) is dict
                and all(type(xyz.get(axis)) in (int, float)
                        and math.isfinite(xyz[axis]) for axis in ("x", "y", "z"))
                for xyz in coords), "selected-position-unavailable")
    drift = max(math.dist([a[k] for k in ("x", "y", "z")],
                          [b[k] for k in ("x", "y", "z")])
                for a, b in zip(coords, coords[1:]))
    level_first = selected.get("numericLevelCandidate")
    level_last = second["nativeValues"].get("numericLevelCandidate")
    level = level_last if (type(level_last) is int and level_last > 0
                           and level_last == level_first) else None
    return {
        "status": "selected-target-candidate",
        "selectedUnitIdCandidate": selected["unitId"],
        "selectedEntityAddressDecimal": ent,
        "baseNameCandidate": name.get("baseNameCandidate") if consistent_name else None,
        "nameStatus": name_status,
        "targetLevelCandidate": level,
        "levelAgreement": "unchanged-candidate" if level is not None
                          else "unavailable-or-changed",
        "healthCandidate": second["nativeValues"].get("health"),
        "resourceCandidate": second["nativeValues"].get("energy"),
        "positionXYZCandidate": (coords[-1] if drift <= 0.10 else None),
        "positionAgreement": "within-0.10-native-units" if drift <= 0.10
                             else "moved-or-disagreed",
        "maxSequentialPositionDelta": drift,
    }


def capture(host, pid, destination, *,
            select=physical_rift.select_physical,
            read=physical_rift.read_native):
    require(host in physical_rift.SUPPORTED_HOSTS
            and type(pid) is int and 0 < pid < 2**31,
            "invalid-expected-host-or-pid")
    root = Path(destination)
    if not root.is_absolute():
        root = ROOT / root
    require(root.parent.is_dir() and not root.exists() and not root.is_symlink(),
            "output-directory-must-be-new")
    selection = select(host, pid)
    target = selection.get("target")
    require(selection.get("status") == "ready"
            and type(target) is dict and target.get("processId") == pid
            and str(target.get("executableSha256", "")).upper() == BUILD_1179
            and target.get("hostName") == host,
            "physical-1179-process-unavailable")
    root.mkdir()
    source_hashes = {}
    try:
        before, bvalue, bsha, _ = source(
            selection, "selected-target", root / "selected-before.json", read=read)
        source_hashes["selectedBefore"] = bsha
        require(type(bvalue) is dict
                and bvalue.get("status") in ("candidate", "unavailable"),
                "selected-before-unqualified")
        pos_raw, pos_values, name_value = None, None, None
        if bvalue["status"] == "candidate":
            pos_raw, pos_candidate, psha, receipt = source(
                selection, "selected-position", root / "selected-position.json",
                read=read, samples=2, interval_ms=100)
            source_hashes["selectedPosition"] = psha
            pos_values = receipt.get("nativeBurstValues")
            require(pos_candidate == pos_values[-1] if isinstance(pos_values, list)
                    and pos_values else False,
                    "position-projection-or-burst-mismatch")
            name_doc, names, nsha, _ = source(
                selection, "unit-names", root / "unit-name.json", read=read,
                unit_keys=[bvalue["unitKey"]])
            source_hashes["unitName"] = nsha
            require(type(names) is dict
                    and names.get("selfKey") == bvalue["selfUnitKey"]
                    and type(names.get("rows")) is list and len(names["rows"]) == 1,
                    "name-owner-or-request-mismatch")
            name_value = names["rows"][0]
        after, avalue, asha, _ = source(
            selection, "selected-target", root / "selected-after.json", read=read)
        source_hashes["selectedAfter"] = asha
        require(select(host, pid).get("target") == target,
                "physical-process-changed-after-capture")
        t = physical_rift._utc_tick_order_key
        endpoints = [(before["observation"]["startedAtUtc"],
                      before["observation"]["completedAtUtc"])]
        if pos_raw is not None:
            endpoints.extend([
                (pos_raw["observation"]["startedAtUtc"],
                 pos_raw["observation"]["completedAtUtc"]),
                (name_doc["observation"]["startedAtUtc"],
                 name_doc["observation"]["completedAtUtc"]),
            ])
        endpoints.append((after["observation"]["startedAtUtc"],
                          after["observation"]["completedAtUtc"]))
        require(all(t(a) <= t(b) for a, b in endpoints)
                and all(t(first[1]) <= t(second[0])
                        for first, second in zip(endpoints, endpoints[1:])),
                "nonsequential-native-evidence")
        elapsed = (t(endpoints[-1][1])[0] - t(endpoints[0][0])[0]).total_seconds()
        require(0 <= elapsed <= 30, "capture-span-over-budget")
        # Include the latest projected values without implying API qualification.
        profile = compare(
            before, {**after, "nativeValues": avalue}, bvalue, name_value,
            pos_values, pos_raw)
        result = {
            "schema": SCHEMA, **profile,
            "process": {"processId": pid,
                        "processStartUtcTicks": target["processStartUtcTicks"],
                        "executableSha256": BUILD_1179},
            "selfUnitKey": bvalue["selfUnitKey"],
            "capturedSpanSeconds": elapsed,
            "nativeSourcesSha256": source_hashes,
            "sourcePaths": {
                key: str(root / filename) for key, filename in (
                    ("selectedBefore", "selected-before.json"),
                    ("selectedPosition", "selected-position.json"),
                    ("unitName", "unit-name.json"),
                    ("selectedAfter", "selected-after.json"))
                if key in source_hashes},
            "gameplayInputSent": False,
            "selectedIdentityAtEndpointsMatched": True,
            "intermediateSelectionHistory": "unavailable",
            "hostilityStatus": "unqualified",
            "combatSuitabilityStatus": "unqualified",
            "qualification": ("Each source was separately acquired and pinned to "
                              "the identical physical game process and on-disk build, "
                              "then reopened against its native SHA receipt. Selected "
                              "key, entity, self key and temporal order were checked. "
                              "Intermediate selected-target changes (including A-B-A) "
                              "are unobserved. Sequential matching native values do "
                              "not independently verify RIFT UI/API meaning, world "
                              "instance, hostility, attackability, LOS, movement, "
                              "or combat outcomes.")
        }
        path = root / "profile.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return path, result
    except Exception as exc:
        with (root / "failure.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({"schema": SCHEMA, "status": "unqualified",
                       "reason": str(exc)[:240], "gameplayInputSent": False,
                       "sourceSha256": source_hashes}, stream, indent=2)
            stream.write("\n")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-host", choices=physical_rift.SUPPORTED_HOSTS,
                        required=True)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path, report = capture(args.expected_host, args.physical_pid, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240],
                          "gameplayInputSent": False}))
        return 2
    print(json.dumps({"status": report["status"],
                      "selectedUnitIdCandidate": report["selectedUnitIdCandidate"],
                      "baseNameCandidate": report["baseNameCandidate"],
                      "targetLevelCandidate": report["targetLevelCandidate"],
                      "healthCandidate": report["healthCandidate"],
                      "positionAgreement": report.get("positionAgreement"),
                      "sourceFile": str(path), "gameplayInputSent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
