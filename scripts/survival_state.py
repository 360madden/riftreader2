"""Assess retained physical player-state evidence. Reads files only and emits JSON.

Optionally compare the last native HP and combat observations with the later of
two advancing, nonce-bound RR2R1 snapshots. Readiness concerns live engagement.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_physical_player_context_pair as context
from scripts import inspect_typed_resource
from scripts.assess_native_xyz_reference_correlation import utc
from scripts.replay_physical_player_state import verified_state


def observation(value, qualification, sampled_at=None, **details):
    return {"availability": "unavailable" if value is None else "observed",
            "value": value, "qualification": qualification, "sampledAtUtc": sampled_at,
            **details}


def vital(values, name):
    raw = values[name]
    current, maximum = raw["current"], raw["maximum"]
    sampled_at = values["sampledAtUtc"]
    if raw["status"] != "calculated-candidate":
        return observation(None, raw["unavailableReason"] or raw["status"], sampled_at)
    if (type(current) is not int or type(maximum) is not int
            or not 0 <= current <= maximum or maximum <= 0):
        return observation(None, "invalid-native-resource-range", sampled_at)
    return observation({"current": current, "maximum": maximum}, raw["status"], sampled_at)


def reference_pair(before, after, session_id, state):
    rows = []
    for path in (before, after):
        # The existing resource inspector decodes the whole RR2R1 frame,
        # including health, healthMax and combat when mana is unavailable.
        row = inspect_typed_resource.inspect(Path(path), "mana", session_id)
        frame, identity = row["selected"], row["identity"]
        target = state["target"]
        inspect_typed_resource.require_reference_binding(frame, session_id)
        if (type(identity.get("processId")) is not int
                or identity["processId"] != target["processId"]
                or str(identity.get("processStartUtcTicks")) != target["processStartUtcTicks"]
                or str(identity.get("executableSha256")).upper() != target["executableSha256"].upper()
                or frame["playerUnitId"] != f"u{int(state['selfKeyCandidate']):016X}"):
            raise ValueError("reference-process-build-or-self-mismatch")
        for field in ("moduleBaseAddress", "moduleSize"):
            if field in identity and (type(identity[field]) is not int or identity[field] != state[field]):
                raise ValueError("reference-module-mismatch")
        if utc(row["startedAtUtc"]) > utc(row["completedAtUtc"]):
            raise ValueError("reference-capture-time-reversed")
        rows.append(row)
    earlier, later = rows
    a, b = earlier["selected"], later["selected"]
    if (utc(earlier["completedAtUtc"]) >= utc(later["startedAtUtc"])
            or earlier["snapshotSha256"] == later["snapshotSha256"]
            or a["wireSha256"] == b["wireSha256"] or a["epoch"] != b["epoch"]
            or a["sequence"] >= b["sequence"] or a["frameTime"] is None
            or b["frameTime"] is None or a["frameTime"] >= b["frameTime"]
            or utc(later["completedAtUtc"]) - utc(earlier["startedAtUtc"]) > 120 * 10_000_000):
        raise ValueError("reference-pair-must-advance-within-120-seconds")
    return rows


def assess(summary, *, before=None, after=None, session_id=None, max_skew_seconds=2.0):
    if any(v is not None for v in (before, after, session_id)) and not all((before, after, session_id)):
        raise ValueError("supply-both-reference-snapshots-and-the-bound-session-id")
    if not math.isfinite(max_skew_seconds) or not 0 < max_skew_seconds <= 120:
        raise ValueError("max-skew-seconds-must-be-positive-and-at-most-120")
    summary = Path(summary)
    state = verified_state(summary)
    values = state["candidateValues"]
    player, vitals = values["player-context"], values["vitals"]
    stamp = player["sampledAtUtc"]
    level, target = player["level"], player["target"]
    usable_level = (level["status"].startswith("numeric-getter") and level["rawCandidate"] > 0)
    fields = {
        "health": vital(vitals, "health"), "mana": vital(vitals, "mana"), "energy": vital(vitals, "energy"),
        "combat": observation(player["combat"]["candidate"], player["combat"]["status"], stamp,
                              rawByte=player["combat"]["rawByte"]),
        "playerLevel": observation(level["rawCandidate"] if usable_level else None,
                                   level["status"], stamp, rawCandidate=level["rawCandidate"]),
        "selectedTarget": observation(target["unitIdCandidate"], target["status"], stamp),
        "dead": observation(None, "no-native-death-observation"),
        "targetLevel": observation(None, "not-in-player-composite"),
        "hostility": observation(None, "not-in-player-composite"),
        "abilityReadiness": observation(None, "not-in-player-composite"),
    }
    report = {"schemaVersion": 1, "evidenceKind": "physical-survival-state/1",
              "status": "assessed", "summarySha256": state["summarySha256"],
              "target": state["target"], "selfKeyCandidate": state["selfKeyCandidate"],
              "sources": state["sources"], "fields": fields,
              "engagement": {"ready": False, "reasons": [
                  "offline-evidence", "native-health-combat-and-level-semantics-unqualified",
                  "target-threat-and-ability-readiness-unverified"]},
              "reference": {"status": "not-supplied"}}
    if before is None:
        return report

    rows = reference_pair(before, after, session_id, state)
    later = rows[-1]
    ref = later["selected"]
    reference_fields = ref["fields"]
    dead = reference_fields["dead"]
    fields["dead"] = observation(dead.get("value"), "retained-addon-" + dead["status"],
                                 later["completedAtUtc"])
    pairs = {}
    for kind, names in (("player-context", ("combat",)), ("vitals", ("health", "healthMax"))):
        native, _ = context.load(summary.parent / (kind + ".json"), state["sources"][kind]["sha256"])
        last = native["observations"][-1]
        # Bound the full capture intervals, including a potentially slow snapshot.
        spread = (max(utc(last["completedAtUtc"]), utc(later["completedAtUtc"]))
                  - min(utc(last["startedAtUtc"]), utc(later["startedAtUtc"]))) / 10_000_000
        for name in names:
            health = fields["health"]["value"] or {}
            candidate = (fields["combat"]["value"] if name == "combat" else
                         health.get("current" if name == "health" else "maximum"))
            api = reference_fields[name]
            if candidate is None or api["status"] != "ok":
                result = "unavailable"
            elif spread > max_skew_seconds:
                result = "outside-comparison-window"
            else:
                result = "agree" if candidate == api["value"] else "disagree"
            pairs[name] = {"status": result, "nativeCandidate": candidate,
                           "api": api, "captureSpanSeconds": spread}
    report["reference"] = {
        "status": "advancing-retained-reference", "sessionId": session_id, "epoch": ref["epoch"],
        "frames": [{"snapshotSha256": row["snapshotSha256"], "wireSha256": row["selected"]["wireSha256"],
                    "sequence": row["selected"]["sequence"], "frameTime": row["selected"]["frameTime"],
                    "startedAtUtc": row["startedAtUtc"], "completedAtUtc": row["completedAtUtc"]}
                   for row in rows],
        "maxSkewSeconds": max_skew_seconds, "comparisons": pairs,
        "qualification": "Capture-time comparison only; native meaning and passive freshness remain unverified."}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True, help="Composite summary beside its pinned sources")
    parser.add_argument("--reference-before", type=Path, help="Earlier RR2R1 native-memory snapshot")
    parser.add_argument("--reference-after", type=Path, help="Later RR2R1 native-memory snapshot")
    parser.add_argument("--session-id", help="Already-bound RR2R1 nonce")
    parser.add_argument("--max-skew-seconds", type=float, default=2.0,
                        help="Maximum span of native and reference captures for comparison (default 2s)")
    args = parser.parse_args(argv)
    try:
        report = assess(args.summary, before=args.reference_before, after=args.reference_after,
                        session_id=args.session_id, max_skew_seconds=args.max_skew_seconds)
        print(json.dumps(report, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "engagement": {"ready": False}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
