"""Strict projection of bounded native keyed unit-level report into candidate rows."""
from __future__ import annotations

import re

QUALIFICATION = (
    "candidate-only; exact keyed native level source, no UI/API meaning, "
    "hostility, attackability, proximity freshness or world-instance proof"
)
CONTRACT = "native-current-unit-levels-candidate/1"
DECIMAL = re.compile(r"[1-9][0-9]{0,19}\Z")
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")


def _require(condition, reason):
    if not condition:
        raise ValueError("invalid-native-unit-levels-" + reason)


def _key(value):
    return (type(value) is str and DECIMAL.fullmatch(value) is not None
            and 0 < int(value) < 2**64
            and str(int(value)) == value)


def values(document):
    """All rows are candidates even when typed owner and numeric level agree."""
    from scripts import physical_rift

    _require(type(document) is dict
             and document.get("schemaVersion") == 1
             and document.get("contractVersion") == CONTRACT
             and document.get("status") == "complete",
             "source-contract")
    row = document.get("observation")
    _require(type(row) is dict and row.get("qualification") == QUALIFICATION,
             "observation-qualification")
    identity = row.get("identity")
    _require(type(identity) is dict
             and type(identity.get("processId")) is int
             and 0 < identity["processId"] < 2**31
             and type(identity.get("processStartUtcTicks")) is int
             and identity["processStartUtcTicks"] > 0
             and type(identity.get("executableSha256")) is str
             and SHA.fullmatch(identity["executableSha256"]) is not None,
             "process-identity")
    _require(_key(row.get("selfKey")), "self-key")
    start, end = (physical_rift._utc_tick_order_key(row.get(k))
                  for k in ("startedAtUtc", "completedAtUtc"))
    _require(start <= end, "observation-chronology")
    rows = row.get("rows")
    _require(type(rows) is list and 1 <= len(rows) <= 12,
             "unit-row-count")
    seen, projected = set(), []
    for item in rows:
        _require(type(item) is dict and _key(item.get("unitKey"))
                 and item["unitKey"] not in seen
                 and item.get("unitIdCandidate") ==
                     f'u{int(item["unitKey"]):016X}',
                 "unit-id")
        seen.add(item["unitKey"])
        begin, finished = (physical_rift._utc_tick_order_key(item.get(k))
                           for k in ("startedAtUtc", "completedAtUtc"))
        _require(start <= begin <= finished <= end, "unit-row-chronology")
        entity = item.get("entityAddressDecimal")
        _require(entity is None or (_key(entity)
                 and 0x10000 <= int(entity) <= 0x7FFF_FFFF_FFFF
                 and int(entity) % 8 == 0), "entity-address")
        status = item.get("status")
        level = item.get("numericLevelCandidate")
        branch = item.get("levelBranch")
        reason = item.get("unavailableReason")
        _require(status in ("numeric-level-candidate",
                            "unavailable", "unverified-owner-type"),
                 "row-status")
        if status == "numeric-level-candidate":
            _require(type(level) is int and 1 <= level <= 1000
                     and branch in ("alternate-primary", "alternate-secondary")
                     and entity is not None and reason is None,
                     "numeric-level")
        else:
            _require(level is None and branch is None
                     and type(reason) is str and reason,
                     "unavailable-level")
            if status == "unverified-owner-type":
                _require(entity is not None and
                         reason == "owner-vptr-or-getter-mismatch",
                         "owner-type")
        projected.append({
            "unitKey": item["unitKey"],
            "unitIdCandidate": item["unitIdCandidate"],
            "status": status,
            "numericLevelCandidate": level,
            "levelBranch": branch,
            "entityAddressDecimal": entity,
            "unavailableReason": reason,
        })
    return {
        "selfKey": row["selfKey"],
        "rows": projected,
        "numericLevelCandidateCount": sum(
            item["status"] == "numeric-level-candidate" for item in projected),
        "sampledAtUtc": row["completedAtUtc"],
        "qualification": QUALIFICATION,
        "worldInstanceStatus": "unavailable",
        "hostilityStatus": "unavailable",
        "combatSuitabilityStatus": "unqualified",
    }
