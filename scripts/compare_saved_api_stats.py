"""Compare replay-verified native stats or level with an existing RRECollector JSON export.

Offline only. The RRE saved-snapshot adapter is the producer-side parser; this
includes a progression-only projection of saved API experience values. This
tool never executes Lua, contacts a game process, or claims live API parity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compare_physical_player_context_pair import load
from scripts.replay_physical_player_state import verified_state

# Historical Inspect.Stat documentation, as also used by the SC628 comparison:
# https://github-wiki-see.page/m/chrisbecke/Igor/wiki/RIFT-API-Documents
# Request exact case-sensitive ordinary names; append Unbuffed for the other
# variant. The native reader already checks the selector/index contract.
STAT_NAMES = (
    "armor", "powerAttack", "powerSpell", "critAttack", "critSpell",
    "strength", "dexterity", "intelligence", "wisdom", "endurance",
    "resistLife", "resistDeath", "resistFire", "resistWater", "resistEarth",
    "resistAir", "hit", "critPower", "block", "dodge",
)
MAX_SAFE_INTEGER = 2**53 - 1


def require(ok, reason):
    if not ok:
        raise ValueError("saved-api-stats-" + reason)


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def reference_context(native, reference):
    """Check the common saved-export contract and exact player ID."""
    key = native.get("selfKeyCandidate")
    require(isinstance(key, str) and key.isdecimal() and 0 < int(key) < 2**64,
            "invalid-native-player")
    player_id = "u" + format(int(key), "016X")
    require(reference.get("adapterContract") == "rre-saved-snapshot/1"
            and valid_hash(reference.get("sourceSha256"))
            and type(reference.get("sourceBytes")) is int
            and 0 < reference["sourceBytes"] <= 8_000_000
            and isinstance(reference.get("addonVersion"), str)
            and type(reference.get("sequence")) is int and reference["sequence"] > 0,
            "invalid-reference-contract")
    ctx = reference.get("context")
    require(isinstance(ctx, dict), "missing-context")
    player, capabilities = (ctx.get(k) for k in ("player", "capabilities"))
    require(isinstance(player, dict) and player.get("id") == player_id
            and isinstance(capabilities, dict) and capabilities.get("player") is True,
            "player-mismatch-or-unavailable")
    return player_id, ctx


# RRE saved-snapshot adapter's supported Experience producers (SC629 and later).
# Source: rre/tools/rre-reader-saved-snapshot.mjs, exportSavedSnapshot.
EXPERIENCE_VERSIONS = frozenset(f"0.4.{version}" for version in range(14, 24))
EXPERIENCE_FIELDS = ("accumulated", "needed", "rested")


def compare_progression(native, reference):
    """Project historical API experience; native XP is intentionally unavailable.

    Inspect.Experience's needed value describes the next-level requirement.
    A successful empty map does not establish a level cap. Never infer missing
    or failed API results from the current native player's level.
    """
    player_id, ctx = reference_context(native, reference)
    capabilities = ctx["capabilities"]
    has_flag, has_map = "experience" in capabilities, "experience" in ctx
    if reference["addonVersion"] in EXPERIENCE_VERSIONS:
        require(has_flag and type(capabilities["experience"]) is bool,
                "experience-capability-invalid")
        require(capabilities["experience"] == has_map, "experience-capability-map-contradiction")
    else:
        require(not has_flag and not has_map, "experience-version-unqualified")
    values = ctx.get("experience", {})
    require(isinstance(values, dict) and set(values) <= set(EXPERIENCE_FIELDS)
            and all(type(value) in (int, float)
                    and -sys.float_info.max <= value <= sys.float_info.max
                    for value in values.values()), "experience-fields-invalid")
    # A numeric zero is an observation; an absent field is unknown.
    fields = {name: {"status": "reported-candidate" if name in values else "unavailable",
                     "value": values.get(name)} for name in EXPERIENCE_FIELDS}
    if not has_flag:
        status = "not-captured"
    elif not has_map:
        status = "api-unavailable"
    elif not values:
        status = "api-empty"
    elif len(values) < len(EXPERIENCE_FIELDS):
        status = "api-partial"
    else:
        status = "api-values-candidate"
    accumulated, needed = values.get("accumulated"), values.get("needed")
    # Only derive a within-level fraction in the documented normal domain.
    # A zero, negative or anomalous requirement remains a raw value, not a cap.
    fraction = (accumulated / needed
                if accumulated is not None and needed is not None
                and 0 <= accumulated <= needed <= MAX_SAFE_INTEGER and needed > 0
                else None)
    level = native.get("candidateValues", {}).get("player-context", {}).get("level", {})
    native_level = level.get("rawCandidate") if level.get("status") in (
        "numeric-getter-and-presentation-candidate",
        "numeric-getter-candidate-presentation-unqualified") else None
    api_level = ctx["player"].get("level")
    native_level = native_level if type(native_level) is int and 0 < native_level < 2**31 else None
    api_level = api_level if type(api_level) is int and 0 < api_level < 2**31 else None
    level_status = ("not-comparable" if native_level is None or api_level is None
                    else "matching-candidates" if native_level == api_level else "different-candidates")
    return {
        "schemaVersion": 1, "evidenceKind": "rr2-saved-api-progression/1",
        "status": "historical-progression-candidate", "playerIdCandidate": player_id,
        "nativeTarget": native["target"], "nativeSummarySha256": native["summarySha256"],
        "nativePlayerContextSourceSha256": native["sources"]["player-context"]["sha256"],
        "referenceOriginalSha256Claim": reference["sourceSha256"].upper(),
        "referenceAddonVersion": reference["addonVersion"], "referenceSequence": reference["sequence"],
        "levelComparison": {"status": level_status, "nativeLevelCandidate": native_level,
                            "savedApiLevelCandidate": api_level},
        "experienceStatus": status, "experienceFields": fields,
        "savedProgressFractionCandidate": fraction,
        "nativeExperienceStatus": "not-captured",
        "qualification": "Historical API export only. The native XP reader is not qualified "
                         "for build 1179; no XP parity, level-cap inference, current freshness "
                         "or level-up event is established. Export digest checked, original "
                         "SavedVariables bytes and capture epoch not independently verified.",
    }


def compare_values(native, reference):
    """Compare exact named values only; absence and zero are distinct."""
    stats = native.get("candidateValues", {}).get("stats")
    require(isinstance(stats, dict) and stats.get("status") == "candidate-only"
            and stats.get("selectorCount") == 20 and isinstance(stats.get("stats"), list)
            and len(stats["stats"]) == 20, "native-stats-required")
    player_id, ctx = reference_context(native, reference)
    capabilities, api = ctx["capabilities"], ctx.get("stats")
    require(isinstance(api, dict) and capabilities.get("stats") is True
            and type(ctx.get("statsTruncated")) is int and ctx["statsTruncated"] == 0
            and len(api) <= 256, "api-stats-unavailable-or-truncated")
    require(all(isinstance(row, dict) and isinstance(row.get("name"), str)
                for row in stats["stats"]), "invalid-native-rows")
    by_name = {row["name"]: row for row in stats["stats"]}
    require(set(by_name) == set(STAT_NAMES), "native-name-set-mismatch")

    rows = []
    for name in STAT_NAMES:
        for variant, suffix in (("ordinary", ""), ("unbuffed", "Unbuffed")):
            field = name + suffix
            item = by_name[name].get(variant)
            value = item.get("rawSigned64") if isinstance(item, dict) else None
            present = field in api
            other = api.get(field)
            native_ok = (isinstance(item, dict) and item.get("status") == "raw-candidate"
                         and type(value) is int and -(2**63) <= value < 2**63)
            api_ok = present and type(other) in (int, float) and (
                -MAX_SAFE_INTEGER <= other <= MAX_SAFE_INTEGER)
            # Do not coerce missing, boolean or nonfinite data to numeric zero.
            # Values outside Lua's exact-integer range cannot be compared safely.
            if not native_ok:
                status = "native-unavailable"
            elif not present:
                status = "api-missing"
            elif not api_ok or abs(value) > MAX_SAFE_INTEGER:
                status = "not-comparable"
            else:
                status = "equal" if value == other else "different"
            rows.append({"name": name, "variant": variant, "apiField": field,
                         "nativeRaw": value if native_ok else None,
                         "apiValue": other if api_ok else None, "status": status})
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("equal", "different", "native-unavailable",
                             "api-missing", "not-comparable")}
    return {
        "schemaVersion": 1, "evidenceKind": "rr2-saved-api-stat-comparison/1",
        "status": "historical-comparison-candidate", "playerIdCandidate": player_id,
        "nativeTarget": native["target"], "nativeSummarySha256": native["summarySha256"],
        "nativeStatsSourceSha256": native["sources"]["stats"]["sha256"],
        "referenceOriginalSha256Claim": reference["sourceSha256"].upper(),
        "referenceAddonVersion": reference["addonVersion"],
        "referenceSequence": reference["sequence"], "counts": counts, "rows": rows,
        "qualification": "Saved API export does not bind native build, process epoch or capture "
                         "time. Exact-name numeric agreement is historical candidate evidence only. "
                         "The export digest is checked, not the original SavedVariables bytes. "
                         "No live, changed-state, freshness or restart qualification.",
    }


def compare(state_summary, reference_path, reference_sha, *, progression_only=False):
    require(valid_hash(reference_sha), "reference-sha-required")
    reference, digest = load(reference_path, reference_sha)
    native = verified_state(state_summary)
    result = compare_progression(native, reference) if progression_only else compare_values(native, reference)
    return dict(result, referenceExportSha256=digest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-summary", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True,
                        help="Existing JSON output of RRE's saved-snapshot adapter")
    parser.add_argument("--reference-sha256", required=True,
                        help="Independently retained SHA-256 of that JSON export")
    parser.add_argument("--progression-only", action="store_true",
                        help="read saved experience and compare player level without requiring stats")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(), "output-exists")
        result = compare(args.state_summary, args.reference, args.reference_sha256,
                         progression_only=args.progression_only)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:200]}))
        return 2
    brief = {"status": result["status"], "output": str(args.output)}
    if args.progression_only:
        brief.update(experienceStatus=result["experienceStatus"],
                     experienceFields=result["experienceFields"],
                     levelComparison=result["levelComparison"],
                     savedProgressFractionCandidate=result["savedProgressFractionCandidate"],
                     nativeExperienceStatus=result["nativeExperienceStatus"])
    else:
        brief["counts"] = result["counts"]
    print(json.dumps(brief, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
