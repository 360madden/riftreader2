#!/usr/bin/env python3
"""Acquire advancing nonce-bound survival API frames from physical RIFT.

This command only reads a bounded, previously admitted heap span. Telemetry
readiness is deliberately separate from engagement authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.capture_readerbridge_v3 import (
    CaptureError, _read_json, _run_native, _same_target, _target,
    _validate_scout, _validate_seed, _write_json,
)
from scripts.physical_waypoints import DEFAULT_BASIS, PhysicalAdapter

MARKER = b"RR2SURV1|"
SUFFIX = b"|ENDRR2SURV1"
MARKER_INT32 = str(int.from_bytes(MARKER[:4], "little"))
MAX_FRAME_BYTES = 8192
NONCE = re.compile(r"[0-9a-f]{32}\Z")
UNIT = re.compile(r"u[0-9a-fA-F]{16}\Z")
ROOT_OBJECTS = ("player", "target", "ability", "cast", "readiness",
                "catalog", "controls", "trial")
UNSUPPORTED = [
    "optical-facing-and-generic-hostile-line-of-sight",
    "desktop-pixel-binding-for-addon-ui-coordinates",
    "automatic-protected-cast-or-stop-click",
    "multi-target-threat-elite-and-add-count-classification",
    "independent-native-qualification-of-api-field-semantics",
]


def autodiscover_seed(target, artifact_root=ROOT / "artifacts",
                      minimum_span_bytes=16 * 1024 * 1024):
    """Choose the newest bounded scout index for the exact process epoch."""
    artifact_root = Path(artifact_root)
    patterns = ("survival-*/*/index.json", "readerbridge-*/*/index.json",
                "*survival*/*/index.json")
    candidates = []
    for pattern in patterns:
        candidates.extend(artifact_root.glob(pattern))
    unique = sorted(set(candidates), key=lambda path: path.stat().st_mtime
                    if path.is_file() and not path.is_symlink() else -1,
                    reverse=True)[:128]
    for path in unique:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            if path.parent.name.startswith("attempt-"):
                continue
            value = _read_json(path)
            spans = value.get("coveredSpans")
            if (value.get("evidenceKind") == "native-value-scout/1"
                    and _same_target(value.get("identity", {}), target)
                    and isinstance(spans, list) and spans):
                int(spans[0]["baseAddress"], 16)
                _require(type(spans[0].get("byteLength")) is int
                         and spans[0]["byteLength"] >= minimum_span_bytes,
                         "invalid-autodiscovered-survival-seed")
                return path
        except (OSError, ValueError, TypeError, KeyError, CaptureError,
                SurvivalLiveError):
            continue
    raise SurvivalLiveError("current-survival-seed-not-found")


class SurvivalLiveError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise SurvivalLiveError(reason)


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SurvivalLiveError("duplicate-survival-frame-key")
        value[key] = item
    return value


def _finite(value, reason):
    _require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def _positive_int(value, reason):
    _require(type(value) is int and 0 < value <= 9_007_199_254_740_991, reason)
    return value


def _validate_catalog(catalog):
    status = catalog.get("status")
    _require(status in (None, "observed", "available", "unavailable"),
             "invalid-survival-catalog-status")
    if status not in ("observed", "available"):
        return
    count, page, pages = (catalog.get("count"), catalog.get("page"),
                          catalog.get("pages"))
    _require(type(count) is int and 0 <= count <= 10000
             and type(page) is int and type(pages) is int
             and 1 <= page <= pages <= 1250,
             "invalid-survival-catalog-page")
    entries = catalog.get("entries")
    _require(isinstance(entries, dict) and len(entries) <= 8,
             "invalid-survival-catalog-entries")
    for ability_id, name in entries.items():
        _require(isinstance(ability_id, str) and 0 < len(ability_id) <= 128
                 and isinstance(name, str) and 0 < len(name) <= 512,
                 "invalid-survival-catalog-entry")
    sampled = catalog.get("sampledAt")
    if sampled is not None:
        _require(_finite(sampled, "invalid-survival-catalog-clock") >= 0,
                 "invalid-survival-catalog-clock")


def _validate_rect(value, reason):
    _require(isinstance(value, dict), reason)
    for name in ("left", "top", "width", "height"):
        _finite(value.get(name), reason)
    _require(value["width"] > 0 and value["height"] > 0, reason)


def _validate_controls(controls):
    space = controls.get("space")
    _require(space in (None, "UIParent"), "invalid-survival-control-space")
    actions = controls.get("actions", {})
    _require(isinstance(actions, dict) and len(actions) <= 8,
             "invalid-survival-control-actions")
    slots = set()
    for ability_id, action in actions.items():
        _require(isinstance(ability_id, str) and 0 < len(ability_id) <= 128
                 and isinstance(action, dict)
                 and action.get("abilityId") == ability_id,
                 "invalid-survival-control-action")
        slot = action.get("slot")
        _require(type(slot) is int and 1 <= slot <= 8 and slot not in slots,
                 "invalid-survival-control-slot")
        slots.add(slot)
        _require(type(action.get("mapped")) is bool
                 and type(action.get("visible")) is bool
                 and isinstance(action.get("readiness"), dict)
                 and isinstance(action.get("ability"), dict),
                 "invalid-survival-control-action")
        if action["mapped"]:
            _validate_rect(action, "invalid-survival-control-rect")
    for name in ("cast", "stop", "cancel"):
        value = controls.get(name)
        if value is not None:
            _require(isinstance(value, dict), "invalid-survival-control")
            if value.get("mapped") is True:
                _validate_rect(value, "invalid-survival-control-rect")


def _validate_last_event(event, frame, *, incoming=False, positive=False):
    if event is None:
        return
    _require(isinstance(event, dict), "invalid-survival-last-event")
    _positive_int(event.get("sequence"), "invalid-survival-last-event")
    _require(_finite(event.get("clock"), "invalid-survival-last-event") >= 0,
             "invalid-survival-last-event")
    _require(isinstance(event.get("kind"), str) and 0 < len(event["kind"]) <= 64,
             "invalid-survival-last-event")
    for name in ("caster", "target"):
        value = event.get(name)
        _require(value is None or isinstance(value, str) and UNIT.fullmatch(value),
                 "invalid-survival-last-event")
    selected = event.get("selectedTargetId")
    if frame.get("eventScope") == "selected-or-self/1":
        _require(isinstance(selected, str) and UNIT.fullmatch(selected)
                 and isinstance(frame.get("targetId"), str)
                 and selected.casefold() == frame["targetId"].casefold(),
                 "invalid-survival-event-selection")
    else:
        _require(selected is None, "invalid-survival-event-selection")
    for name in ("damage", "heal", "overheal"):
        if event.get(name) is not None:
            _require(_finite(event[name], "invalid-survival-last-event") >= 0,
                     "invalid-survival-last-event")
    _require(event.get("crit") is None or type(event["crit"]) is bool,
             "invalid-survival-last-event")
    _require(event.get("abilityName") is None
             or isinstance(event["abilityName"], str)
             and 0 < len(event["abilityName"]) <= 512,
             "invalid-survival-event-ability-name")
    frame_time = frame["frameTime"]
    _require(0 <= frame_time - event["clock"] <= (5 if positive else 2),
             "stale-or-future-survival-event")
    if incoming:
        _require(frame.get("eventScope") == "selected-or-self/1"
                 and event.get("kind") == "damage"
                 and type(event.get("damage")) in (int, float)
                 and math.isfinite(event["damage"]) and event["damage"] > 0
                 and isinstance(event.get("caster"), str)
                 and isinstance(event.get("target"), str)
                 and event["caster"].casefold() == frame["targetId"].casefold()
                 and event["target"].casefold() == frame["playerId"].casefold(),
                 "invalid-survival-incoming-event")
    if positive:
        damage, healing = event.get("damage"), event.get("heal")
        _require(frame.get("positiveEventScope") == "last-effective-damage-or-heal/1"
                 and isinstance(event.get("caster"), str)
                 and event["caster"].casefold() == frame["playerId"].casefold()
                 and isinstance(event.get("target"), str)
                 and event["target"].casefold() in {
                     frame["playerId"].casefold(), frame["targetId"].casefold()}
                 and ((type(damage) in (int, float) and math.isfinite(damage)
                       and damage > 0)
                      or (type(healing) in (int, float) and math.isfinite(healing)
                          and healing > 0)),
                 "invalid-survival-positive-event")


def _validate_positive_events(frame):
    events = frame.get("positiveEvents")
    if events is None:
        return
    _require(frame.get("positiveEventsScope") == "per-ability/1"
             and isinstance(events, dict) and len(events) <= 8,
             "invalid-survival-positive-events")
    for ability_id, event in events.items():
        _require(isinstance(ability_id, str) and 0 < len(ability_id) <= 128
                 and isinstance(event, dict)
                 and (event.get("normalizedAbilityId") or event.get("abilityNew"))
                 == ability_id,
                 "invalid-survival-positive-event-key")
        _validate_last_event(event, frame, positive=True)


def _validate_last_death(frame):
    event = frame.get("lastDeath")
    scope = frame.get("deathScope")
    _require(scope in (None, "exact-unit-death/1"),
             "unexpected-survival-death-scope")
    if event is None:
        return
    _require(scope == "exact-unit-death/1" and isinstance(event, dict),
             "invalid-survival-last-death")
    _positive_int(event.get("sequence"), "invalid-survival-last-death")
    clock = _finite(event.get("clock"), "invalid-survival-last-death")
    _require(0 <= frame["frameTime"] - clock <= 5,
             "stale-or-future-survival-death")
    target = event.get("target")
    _require(isinstance(target, str) and UNIT.fullmatch(target),
             "invalid-survival-last-death")
    caster = event.get("caster")
    _require(caster is None or isinstance(caster, str) and UNIT.fullmatch(caster),
             "invalid-survival-last-death")
    for name in ("targetName", "casterName"):
        value = event.get(name)
        _require(value is None or isinstance(value, str)
                 and 0 < len(value) <= 128,
                 "invalid-survival-last-death")


def _validate_death_progression(previous, current):
    """Reject a retained death receipt that rewinds or mutates in one epoch."""
    if not isinstance(current, dict):
        return
    if not isinstance(previous, dict):
        return
    prior_generation = (previous["sequence"], previous["clock"])
    generation = (current["sequence"], current["clock"])
    _require(generation >= prior_generation,
             "survival-death-generation-regressed")
    if current["sequence"] == previous["sequence"]:
        _require(current == previous, "conflicting-survival-death-generation")


def decode_frame(data: bytes, expected_nonce: str, expected_player: str) -> dict:
    _require(isinstance(data, bytes), "invalid-survival-frame-bytes")
    _require(data.startswith(MARKER), "survival-frame-marker-missing")
    end = data.find(SUFFIX, len(MARKER))
    _require(end >= len(MARKER), "survival-frame-terminator-missing")
    total = end + len(SUFFIX)
    _require(total <= MAX_FRAME_BYTES, "survival-frame-oversized")
    raw = data[len(MARKER):end]
    _require(raw, "survival-frame-json-empty-or-oversized")
    try:
        frame = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_strict_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                SurvivalLiveError("nonfinite-survival-frame")))
    except UnicodeError as exc:
        raise SurvivalLiveError("invalid-survival-frame-utf8") from exc
    except json.JSONDecodeError as exc:
        raise SurvivalLiveError("invalid-survival-frame-json") from exc
    _require(isinstance(frame, dict), "invalid-survival-frame-object")
    _require(frame.get("schemaVersion") == 1
             and frame.get("addon") == "RiftReader2Casting"
             and frame.get("addonVersion") in ("0.4.2", "0.5.0", "0.5.1")
             and frame.get("source") == "rift-api",
             "unexpected-survival-frame-contract")
    _require(frame.get("eventScope") in (None, "selected-or-self/1"),
             "unexpected-survival-event-scope")
    _require(frame.get("positiveEventScope") in
             (None, "last-effective-damage-or-heal/1"),
             "unexpected-survival-positive-event-scope")
    _require(frame.get("positiveEventsScope") in (None, "per-ability/1"),
             "unexpected-survival-positive-events-scope")
    _require(frame.get("sessionId") == expected_nonce,
             "survival-frame-nonce-mismatch")
    _positive_int(frame.get("epoch"), "invalid-survival-frame-epoch")
    _positive_int(frame.get("sequence"), "invalid-survival-frame-sequence")
    _require(_finite(frame.get("frameTime"), "invalid-survival-frame-clock") >= 0,
             "invalid-survival-frame-clock")
    _require(frame.get("status") in ("observed", "unavailable"),
             "invalid-survival-frame-status")
    player = frame.get("playerId")
    _require(isinstance(player, str) and UNIT.fullmatch(player),
             "invalid-survival-frame-player")
    _require(player.casefold() == expected_player.casefold(),
             "survival-frame-player-mismatch")
    target = frame.get("targetId")
    _require(target is None or isinstance(target, str) and UNIT.fullmatch(target),
             "invalid-survival-frame-target")
    for name in ROOT_OBJECTS:
        _require(isinstance(frame.get(name), dict),
                 "invalid-survival-frame-section")
    readiness = frame["readiness"]
    _require(readiness.get("status") in
             (None, "ready", "waiting", "blocked", "unavailable"),
             "invalid-survival-readiness-status")
    _require(readiness.get("reason") is None
             or isinstance(readiness["reason"], str)
             and len(readiness["reason"]) <= 256,
             "invalid-survival-readiness-reason")
    _validate_catalog(frame["catalog"])
    _validate_controls(frame["controls"])
    _validate_last_event(frame.get("lastEvent"), frame)
    _validate_last_event(frame.get("lastIncoming"), frame, incoming=True)
    _validate_last_event(frame.get("lastPositiveEvent"), frame, positive=True)
    _validate_positive_events(frame)
    _validate_last_death(frame)
    canonical = json.dumps(frame, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return {"frame": frame, "frameBytes": total,
            "frameSha256": hashlib.sha256(canonical).hexdigest().upper()}


def _scout_request(target, base, length, max_milliseconds):
    return {
        "schemaVersion": 1, "evidenceKind": "native-value-scout-request/1",
        "target": target, "startAddress": f"0x{base:X}",
        "references": [{"name": "rr2-survival-prefix", "type": "int32",
                        "value": MARKER_INT32}],
        "contextBeforeBytes": 0, "contextAfterBytes": 2044,
        "maxScanBytes": length, "maxDurationMilliseconds": max_milliseconds,
        "maxRegionCount": 32768, "maxMatchCount": 64,
    }


def _capture_request(target, addresses):
    ranges = []
    for index, address in enumerate(addresses):
        for part in range(2):
            ranges.append({
                "id": f"frame-{index}-{part}",
                "addressKind": "absolute-session-address",
                "address": f"0x{address + part * 4096:X}",
                "byteLength": 4096,
            })
    return {
        "schemaVersion": 1, "evidenceKind": "native-memory-read-request/1",
        "target": target,
        "sampling": {"sampleCount": 1, "intervalMilliseconds": 0,
                     "maxDurationMilliseconds": 1000},
        "ranges": ranges,
    }


def _captured_frames(report, target, request, addresses):
    capture = report.get("capture", {})
    samples = capture.get("samples")
    _require(report.get("evidenceKind") == "native-memory-semantic-unqualified"
             and report.get("request") == request
             and capture.get("status") == "complete"
             and _same_target(capture.get("identity", {}), target)
             and isinstance(samples, list) and len(samples) == 1,
             "invalid-survival-capture-owner-or-status")
    observed = samples[0].get("ranges")
    _require(isinstance(observed, list) and len(observed) == len(addresses) * 2,
             "invalid-survival-capture-ranges")
    by_id = {item.get("rangeId"): item for item in observed}
    chunks = []
    for expected in request["ranges"]:
        item = by_id.get(expected["id"])
        try:
            data = base64.b64decode(item["bytesBase64"], validate=True)
        except Exception as exc:
            raise SurvivalLiveError("invalid-survival-capture-bytes") from exc
        _require(item.get("status") == "success"
                 and item.get("requestedAddress") == expected["address"]
                 and item.get("resolvedAddress") == expected["address"]
                 and item.get("requestedByteLength") == expected["byteLength"]
                 and item.get("bytesRead") == len(data) == expected["byteLength"]
                 and hashlib.sha256(data).hexdigest().upper() == item.get("bytesSha256"),
                 "invalid-survival-capture-range")
        chunks.append(data)
    return [b"".join(chunks[index * 2:index * 2 + 2])
            for index in range(len(addresses))]


def _capture_known(target, addresses, artifact_prefix, runner=subprocess.run):
    addresses = list(dict.fromkeys(addresses))[:16]
    if not addresses:
        return []
    request = _capture_request(target, addresses)
    request_path = Path(str(artifact_prefix) + ".request.json")
    report_path = Path(str(artifact_prefix) + ".json")
    _write_json(request_path, request)
    _run_native("capture-native", request_path, report_path, runner)
    frames = _captured_frames(_read_json(report_path), target, request, addresses)
    return [({"address": f"0x{address:X}"}, data)
            for address, data in zip(addresses, frames)]


def _scout_once(target, base, length, max_milliseconds, attempt_dir,
                runner=subprocess.run):
    request = _scout_request(target, base, length, max_milliseconds)
    request_path = Path(str(attempt_dir) + ".request.json")
    _write_json(request_path, request)
    _run_native("scout-values-native", request_path, attempt_dir, runner)
    candidates = _validate_scout(_read_json(attempt_dir / "index.json"),
                                 target, attempt_dir)
    matching = [candidate for candidate, _ in candidates
                if "rr2-survival-prefix" in candidate.get("referenceNames", [])]
    # The scout contract caps context at 2048 bytes. Read the complete bounded
    # frame from each exact marker address under the same process identity.
    addresses = [int(candidate["address"], 16) for candidate in matching[:64]]
    result = []
    for offset in range(0, len(addresses), 16):
        batch = addresses[offset:offset + 16]
        result.extend(_capture_known(
            target, batch,
            Path(str(attempt_dir) + f".frames-{offset // 16 + 1:02d}"), runner))
    return result


def _canonical_unit_key(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SurvivalLiveError("invalid-current-player-key") from exc
    _require(0 < number <= 0xFFFFFFFFFFFFFFFF, "invalid-current-player-key")
    return f"u{number:016X}"


def _catalog_summary(catalog):
    if catalog.get("status") not in ("observed", "available"):
        return {"availability": "unavailable", "complete": False,
                "reason": catalog.get("reason", "catalog-unavailable")}
    entries = catalog["entries"]
    complete = catalog["pages"] == 1 and len(entries) == catalog["count"]
    return {
        "availability": "observed-page", "complete": complete,
        "count": catalog["count"], "page": catalog["page"],
        "pages": catalog["pages"], "sampledAt": catalog.get("sampledAt"),
        "entries": entries,
        "qualification": ("complete-current-catalog" if complete else
                          "partial-current-page; other pages require explicit addon selection"),
    }


def outcome_baseline(snapshot):
    """Pin the greatest outgoing generation/clock visible before submission."""
    if not isinstance(snapshot, dict):
        return None
    named = [(name, snapshot.get(name))
             for name in ("lastEvent", "lastPositiveEvent")]
    positives = snapshot.get("positiveEvents")
    if isinstance(positives, dict):
        named.extend(("positiveEvents." + ability_id, event)
                     for ability_id, event in positives.items())
    named = [(name, event) for name, event in named if isinstance(event, dict)]
    events = [event for _, event in named]
    if not events:
        return None
    sequences = [event.get("sequence") for event in events]
    clocks = [event.get("clock") for event in events]
    if (not all(type(value) is int and value > 0 for value in sequences)
            or not all(type(value) in (int, float) and math.isfinite(value)
                       for value in clocks)):
        return None
    return {"sequence": max(sequences), "clock": max(clocks),
            "sources": [name for name, _ in named]}


def assess_outcome(baseline_event, snapshot, *, player_id, ability_id,
                   encounter_target_id=None, effect_target_id=None,
                   submission_frame_time=None, outcome_deadline_frame_time=None,
                   target_id=None, effect_ability_ids=None):
    """Match one newer exact-context effect; selected encounter may differ from target."""
    # ``target_id`` retains the original offensive-call spelling while forcing
    # callers of self effects to pin encounter and effect targets separately.
    if target_id is not None:
        encounter_target_id = encounter_target_id or target_id
        effect_target_id = effect_target_id or target_id
    if effect_ability_ids is None:
        effect_ability_ids = (ability_id,)
    elif (not isinstance(effect_ability_ids, (list, tuple))
          or not 1 <= len(effect_ability_ids) <= 4
          or any(not isinstance(value, str) or not value
                 for value in effect_ability_ids)
          or len(set(effect_ability_ids)) != len(effect_ability_ids)):
        return {"status": "unavailable", "reason": "invalid-effect-ability-ids",
                "castAbilityId": ability_id}
    else:
        effect_ability_ids = tuple(effect_ability_ids)
    if (not isinstance(ability_id, str) or not ability_id
            or not isinstance(encounter_target_id, str)
            or not isinstance(effect_target_id, str)
            or type(submission_frame_time) not in (int, float)
            or not math.isfinite(submission_frame_time)
            or type(outcome_deadline_frame_time) not in (int, float)
            or not math.isfinite(outcome_deadline_frame_time)
            or not 0 < outcome_deadline_frame_time - submission_frame_time <= 5):
        return {"status": "unavailable", "reason": "outcome-context-incomplete"}
    positive_events = snapshot.get("positiveEvents") if isinstance(snapshot, dict) else None
    mapped = []
    if isinstance(positive_events, dict):
        mapped = [(effect_id, positive_events.get(effect_id))
                  for effect_id in effect_ability_ids]
        mapped = [(effect_id, event) for effect_id, event in mapped
                  if isinstance(event, dict)]
    if mapped:
        effect_id, positive = max(
            mapped, key=lambda item: (item[1].get("sequence", 0),
                                      item[1].get("clock", -1)))
        event_source = "positiveEvents." + effect_id
    else:
        positive = None
        event_source = None
    if not isinstance(positive, dict):
        positive = snapshot.get("lastPositiveEvent") if isinstance(snapshot, dict) else None
        event_source = "lastPositiveEvent"
    if not isinstance(positive, dict):
        positive = snapshot.get("lastEvent") if isinstance(snapshot, dict) else None
        event_source = "lastEvent"
    event = positive
    if not isinstance(event, dict):
        return {"status": "unavailable", "reason": "no-positive-post-action-event",
                "latestDiagnosticEvent": (snapshot.get("lastEvent")
                                          if isinstance(snapshot, dict) else None)}
    if isinstance(baseline_event, dict):
        if (event.get("sequence", 0) <= baseline_event.get("sequence", 0)
                or event.get("clock", -1) <= baseline_event.get("clock", -1)):
            return {"status": "unavailable", "reason": "event-not-newer-than-baseline"}
    frame_time = snapshot.get("frameTime")
    event_clock = event.get("clock")
    if (type(frame_time) not in (int, float) or not math.isfinite(frame_time)
            or type(event_clock) not in (int, float) or not math.isfinite(event_clock)
            or event_clock < submission_frame_time
            or event_clock > outcome_deadline_frame_time
            or event_clock > frame_time or frame_time - event_clock > 5):
        return {"status": "unavailable", "reason": "post-action-event-outside-window"}
    event_ability = event.get("normalizedAbilityId") or event.get("abilityNew")
    exact = (str(event.get("caster", "")).casefold() == player_id.casefold()
             and str(snapshot.get("targetId", "")).casefold()
             == encounter_target_id.casefold()
             and str(event.get("selectedTargetId", "")).casefold()
             == encounter_target_id.casefold()
             and str(event.get("target", "")).casefold()
             == effect_target_id.casefold()
             and event_ability in effect_ability_ids)
    if not exact:
        return {"status": "unavailable", "reason": "post-action-event-id-mismatch",
                "castAbilityId": ability_id,
                "effectAbilityId": event_ability}
    damage = event.get("damage")
    healing = event.get("heal")
    if type(damage) in (int, float) and math.isfinite(damage) and damage > 0:
        return {"status": "intended-hit-confirmed", "event": event,
                "eventSource": event_source,
                "castAbilityId": ability_id,
                "effectAbilityId": event_ability,
                "latestDiagnosticEvent": snapshot.get("lastEvent")}
    if type(healing) in (int, float) and math.isfinite(healing) and healing > 0:
        return {"status": "intended-heal-confirmed", "event": event,
                "eventSource": event_source,
                "castAbilityId": ability_id,
                "effectAbilityId": event_ability,
                "latestDiagnosticEvent": snapshot.get("lastEvent")}
    return {"status": "unavailable", "reason": "no-positive-matching-damage-or-heal",
            "event": event}


def assess_incoming(snapshot, *, player_id, encounter_target_id):
    """Return one current exact selected-hostile→player damage receipt."""
    event = snapshot.get("lastIncoming") if isinstance(snapshot, dict) else None
    if not isinstance(event, dict):
        return {"status": "unavailable", "reason": "no-current-incoming-event"}
    frame_time, clock = snapshot.get("frameTime"), event.get("clock")
    exact = (type(frame_time) in (int, float) and math.isfinite(frame_time)
             and type(clock) in (int, float) and math.isfinite(clock)
             and 0 <= frame_time - clock <= 2
             and event.get("kind") == "damage"
             and type(event.get("damage")) in (int, float)
             and math.isfinite(event["damage"]) and event["damage"] > 0
             and str(snapshot.get("targetId", "")).casefold()
             == encounter_target_id.casefold()
             and str(event.get("selectedTargetId", "")).casefold()
             == encounter_target_id.casefold()
             and str(event.get("caster", "")).casefold()
             == encounter_target_id.casefold()
             and str(event.get("target", "")).casefold() == player_id.casefold())
    return ({"status": "incoming-damage-observed", "event": event} if exact else
            {"status": "unavailable", "reason": "incoming-event-context-mismatch"})


class SurvivalLiveConsumer:
    """Stateful exact-identity consumer; each snapshot performs a new native read.

    The first accepted frame is a baseline. ``telemetryReady`` becomes true only
    after a later scan observes a strictly advancing sequence and source clock.
    """

    def __init__(self, expected_host, physical_pid, session_id,
                 seed_index=None, output=None,
                 *, scan_mib=16, scan_milliseconds=450, pool_mib=2,
                 snapshot_milliseconds=3000,
                 relative_lag_seconds=2.0,
                 runner=subprocess.run, selector=physical_rift.select_physical,
                 adapter_factory=PhysicalAdapter, scout_once=_scout_once,
                 capture_known=_capture_known,
                 monotonic=time.monotonic):
        _require(isinstance(session_id, str) and NONCE.fullmatch(session_id),
                 "invalid-survival-session-id")
        _require(type(scan_mib) is int and 1 <= scan_mib <= 32,
                 "survival-scan-mib-out-of-range")
        _require(type(pool_mib) is int and 1 <= pool_mib <= scan_mib,
                 "survival-pool-mib-out-of-range")
        _require(type(scan_milliseconds) is int and 100 <= scan_milliseconds <= 2000,
                 "survival-scan-time-out-of-range")
        _require(type(snapshot_milliseconds) is int
                 and 500 <= snapshot_milliseconds <= 5000,
                 "survival-snapshot-time-out-of-range")
        _require(type(relative_lag_seconds) in (int, float)
                 and math.isfinite(relative_lag_seconds)
                 and 0.2 <= relative_lag_seconds <= 10,
                 "survival-relative-lag-out-of-range")
        _require(output is not None, "survival-output-required")
        self.output = Path(output)
        _require(not self.output.exists(), "survival-output-already-exists")
        selection = selector(expected_host=expected_host, physical_pid=physical_pid)
        _require(selection.get("status") == "ready", "physical-selection-not-ready")
        self.target = _target(selection.get("target", {}))
        seed_index = (autodiscover_seed(self.target) if seed_index is None
                      else Path(seed_index))
        base, length = _validate_seed(_read_json(seed_index), self.target, scan_mib)
        adapter = adapter_factory(expected_host, physical_pid, DEFAULT_BASIS)
        _require(_same_target(adapter.target, self.target),
                 "adapter-process-identity-mismatch")
        self.player_id = _canonical_unit_key(adapter.unit_key)
        self.session_id = session_id
        self.seed_index = seed_index
        self.base, self.length = base, length
        self.seed_base, self.seed_length = base, length
        self.pool_bytes = pool_mib * 1024 * 1024
        self.scan_milliseconds = scan_milliseconds
        self.snapshot_milliseconds = snapshot_milliseconds
        self.relative_lag_seconds = float(relative_lag_seconds)
        self.runner, self.scout_once = runner, scout_once
        self.capture_known, self.monotonic = capture_known, monotonic
        self.output.mkdir(parents=True, exist_ok=False)
        self.attempt = 0
        self.accepted = []
        self.attempts = []
        self.seen = {}
        self.known_addresses = []
        self.latest_reference = None
        self.latest_death_reference = None

    def _decode_candidates(self, candidates):
        decoded, failures = [], []
        for candidate, data in candidates:
            try:
                item = decode_frame(data, self.session_id, self.player_id)
                if item["frame"]["status"] != "observed":
                    raise SurvivalLiveError("survival-frame-status-unavailable")
                key = (item["frame"]["epoch"], item["frame"]["sequence"])
                prior = self.seen.get(key)
                if prior is not None and prior != item["frameSha256"]:
                    raise SurvivalLiveError("conflicting-survival-generation")
                self.seen[key] = item["frameSha256"]
                item["address"] = candidate.get("address")
                decoded.append(item)
            except SurvivalLiveError as exc:
                if str(exc) == "conflicting-survival-generation":
                    raise
                failures.append(str(exc))
        decoded.sort(key=lambda item: (item["frame"]["epoch"],
                                       item["frame"]["sequence"]))
        return decoded, failures

    def _newest_usable(self, decoded):
        if not self.accepted:
            return decoded[-1] if decoded else None
        previous = self.accepted[-1]["frame"]
        usable = [item for item in decoded
                  if item["frame"]["epoch"] == previous["epoch"]
                  and item["frame"]["sequence"] > previous["sequence"]
                  and item["frame"]["frameTime"] > previous["frameTime"]]
        return usable[-1] if usable else None

    def snapshot(self):
        self.attempt += 1
        started = self.monotonic()
        phases = []
        cached = []
        if self.known_addresses:
            try:
                cached = self.capture_known(
                    self.target, self.known_addresses,
                    self.output / f"attempt-{self.attempt}.cached", self.runner)
                phases.append({"kind": "cached-address-batch",
                               "candidateCount": len(cached), "status": "complete"})
            except (CaptureError, OSError, subprocess.SubprocessError,
                    SurvivalLiveError) as exc:
                # A stale/unreadable immutable string is not a terminal state and
                # never supplies data. Fall through to a fresh bounded scout.
                phases.append({"kind": "cached-address-batch", "candidateCount": 0,
                               "status": "unavailable", "reason": str(exc)})
        decoded, failures = self._decode_candidates(cached)
        selected = self._newest_usable(decoded)
        scouted = selected is None
        candidates = cached
        full_fallback = False
        if scouted:
            try:
                candidates = self.scout_once(
                    self.target, self.base, self.length, self.scan_milliseconds,
                    self.output / f"attempt-{self.attempt}.scout", self.runner)
                decoded, scout_failures = self._decode_candidates(candidates)
                failures.extend(scout_failures)
                selected = self._newest_usable(decoded)
                phases.append({"kind": "bounded-pool-scout",
                               "candidateCount": len(candidates), "status": "complete"})
            except (CaptureError, OSError, subprocess.SubprocessError,
                    SurvivalLiveError) as exc:
                if self.base == self.seed_base and self.length == self.seed_length:
                    raise
                candidates, decoded = [], []
                phases.append({"kind": "bounded-pool-scout", "candidateCount": 0,
                               "status": "unavailable", "reason": str(exc)})
            if (selected is None
                    and (self.base != self.seed_base or self.length != self.seed_length)):
                elapsed_ms = (self.monotonic() - started) * 1000
                remaining = int(self.snapshot_milliseconds - elapsed_ms)
                _require(remaining >= 100, "survival-snapshot-deadline-exceeded")
                full_fallback = True
                candidates = self.scout_once(
                    self.target, self.seed_base, self.seed_length,
                    min(self.scan_milliseconds, remaining),
                    self.output / f"attempt-{self.attempt}.full-scout", self.runner)
                decoded, full_failures = self._decode_candidates(candidates)
                failures.extend(full_failures)
                selected = self._newest_usable(decoded)
                phases.append({"kind": "full-admitted-span-scout",
                               "candidateCount": len(candidates), "status": "complete"})
        _require((self.monotonic() - started) * 1000 <= self.snapshot_milliseconds,
                 "survival-snapshot-deadline-exceeded")
        receipt = {
            "attempt": self.attempt,
            "elapsedMilliseconds": (self.monotonic() - started) * 1000,
            "scanStartAddress": f"0x{self.base:X}", "scanBytes": self.length,
            "cachedAddressCount": len(self.known_addresses),
            "boundedScoutPerformed": scouted,
            "fullSpanFallbackPerformed": full_fallback,
            "phases": phases,
            "candidateCount": len(candidates),
            "validMatchingFrameCount": len(decoded),
            "candidateFailures": sorted(set(failures)),
            "selectedSequence": (selected["frame"]["sequence"]
                                 if selected is not None else None),
        }
        self.attempts.append(receipt)
        if selected is None:
            raise SurvivalLiveError("survival-frame-not-advanced")
        if self.accepted:
            _require(selected["frame"]["epoch"] == self.accepted[0]["frame"]["epoch"],
                     "survival-frame-epoch-changed")
        death = selected["frame"].get("lastDeath")
        _validate_death_progression(self.latest_death_reference, death)
        if isinstance(death, dict):
            self.latest_death_reference = death
        accepted_at = self.monotonic()
        relative_lag = None
        if self.latest_reference is not None:
            wall_advance = accepted_at - self.latest_reference["acceptedAtMonotonic"]
            source_advance = (selected["frame"]["frameTime"]
                              - self.latest_reference["frame"]["frameTime"])
            relative_lag = max(0.0, wall_advance - source_advance)
            _require(relative_lag <= self.relative_lag_seconds,
                     "survival-source-relative-lag-exceeded")
        self.accepted.append(selected)
        self.latest_reference = {
            "acceptedAtMonotonic": accepted_at, "frame": selected["frame"],
            "frameSha256": selected["frameSha256"], "address": selected.get("address")}
        # New immutable strings usually remain near the retained Lua pool. Narrow
        # later scans around observed addresses, but never escape the admitted span.
        addresses = [int(item["address"], 16) for item in decoded
                     if isinstance(item.get("address"), str)]
        if addresses:
            self.known_addresses = list(dict.fromkeys(addresses))[-8:]
        if addresses and self.seed_length > self.pool_bytes:
            center = max(addresses)
            low = max(self.seed_base, center - self.pool_bytes // 2)
            high = min(self.seed_base + self.seed_length, low + self.pool_bytes)
            self.base, self.length = max(self.seed_base, high - self.pool_bytes), high - max(
                self.seed_base, high - self.pool_bytes)
        return {
            "status": "observed-candidate",
            "telemetryReady": len(self.accepted) >= 2,
            "baseline": len(self.accepted) == 1,
            "target": self.target, "playerId": self.player_id,
            "sessionId": self.session_id, "epoch": selected["frame"]["epoch"],
            "sequence": selected["frame"]["sequence"],
            "frameTime": selected["frame"]["frameTime"],
            "snapshot": selected["frame"],
            "catalog": _catalog_summary(selected["frame"]["catalog"]),
            "actions": selected["frame"]["controls"].get("actions", {}),
            "cancel": selected["frame"]["controls"].get("cancel"),
            "lastEvent": selected["frame"].get("lastEvent"),
            "lastPositiveEvent": selected["frame"].get("lastPositiveEvent"),
            "positiveEvents": selected["frame"].get("positiveEvents", {}),
            "lastIncoming": selected["frame"].get("lastIncoming"),
            "lastDeath": selected["frame"].get("lastDeath"),
            "deathScope": selected["frame"].get("deathScope"),
            "eventScope": selected["frame"]["eventScope"],
            "controlCoordinateSpace": selected["frame"]["controls"].get("space"),
            "engagement": {"ready": False, "reasons": list(UNSUPPORTED)},
            "source": {"address": selected.get("address"),
                       "frameSha256": selected["frameSha256"],
                       "relativeLagSecondsCandidate": relative_lag,
                       "relativeLagLimitSeconds": self.relative_lag_seconds,
                       "freshnessQualification": (
                           "relative-to-last-accepted-source-clock; no absolute age claim")},
            "acquisition": receipt,
        }

    def cancel_reference(self, *, max_age_seconds=5.0):
        """Return a recent verified Cancel rectangle; this performs no native read."""
        _require(type(max_age_seconds) in (int, float)
                 and math.isfinite(max_age_seconds) and 0 < max_age_seconds <= 10,
                 "invalid-cancel-reference-age")
        _require(self.latest_reference is not None,
                 "cancel-reference-unavailable")
        age = self.monotonic() - self.latest_reference["acceptedAtMonotonic"]
        _require(0 <= age <= max_age_seconds, "cancel-reference-expired")
        frame = self.latest_reference["frame"]
        cancel = frame["controls"].get("cancel")
        _require(isinstance(cancel, dict) and cancel.get("mapped") is True
                 and cancel.get("visible") is True
                 and frame["controls"].get("space") == "UIParent"
                 and isinstance(frame.get("targetId"), str),
                 "cancel-reference-unavailable")
        _validate_rect(cancel, "cancel-reference-unavailable")
        return {
            "status": "cached-verified-cancel", "ageSeconds": age,
            "maxAgeSeconds": float(max_age_seconds), "target": self.target,
            "sessionId": self.session_id, "epoch": frame["epoch"],
            "playerId": self.player_id, "selectedTargetId": frame["targetId"],
            "sourceSequence": frame["sequence"],
            "sourceFrameTime": frame["frameTime"],
            "sourceFrameSha256": self.latest_reference["frameSha256"],
            "controlCoordinateSpace": "UIParent", "cancel": cancel,
            "abilityReadinessRequired": False,
            "requiredExecutionChecks": [
                "exact-process-build-window-and-client-geometry",
                "exact-current-selected-target",
                "exclusive-input-owner-and-stop-release",
            ],
            "qualification": (
                "Recent verified cancel geometry only; execution must freshly "
                "recheck native identity, selected target and client geometry."),
        }


def acquire(expected_host, physical_pid, session_id, seed_index=None, output=None, *,
            scan_mib=16, scan_milliseconds=450, interval_milliseconds=250,
            max_attempts=6, runner=subprocess.run, sleep=time.sleep,
            monotonic=time.monotonic, selector=physical_rift.select_physical,
            adapter_factory=PhysicalAdapter, scout_once=_scout_once,
            capture_known=_capture_known):
    _require(type(interval_milliseconds) is int and 0 <= interval_milliseconds <= 2000,
             "survival-interval-out-of-range")
    _require(type(max_attempts) is int and 2 <= max_attempts <= 20,
             "survival-attempts-out-of-range")
    started = monotonic()
    consumer = SurvivalLiveConsumer(
        expected_host, physical_pid, session_id, seed_index, output,
        scan_mib=scan_mib, scan_milliseconds=scan_milliseconds,
        runner=runner, selector=selector, adapter_factory=adapter_factory,
        scout_once=scout_once, capture_known=capture_known, monotonic=monotonic)
    latest = None
    for attempt in range(max_attempts):
        if attempt and interval_milliseconds:
            sleep(interval_milliseconds / 1000)
        try:
            latest = consumer.snapshot()
        except SurvivalLiveError as exc:
            if str(exc) != "survival-frame-not-advanced":
                raise
            continue
        if latest["telemetryReady"]:
            break
    _require(latest is not None and latest["telemetryReady"],
             "advancing-survival-frames-not-observed")
    first = consumer.accepted[0]["frame"]
    frame = latest["snapshot"]
    catalog = latest["catalog"]
    unsupported = list(UNSUPPORTED)
    if not catalog["complete"]:
        unsupported.append("complete-learned-ability-catalog")
    report = {
        "schemaVersion": 1,
        "evidenceKind": "physical-survival-live-candidate/1",
        "status": "observed-candidate", "ready": True,
        "inputSent": False, "target": consumer.target,
        "playerId": consumer.player_id,
        "sessionId": session_id, "epoch": frame["epoch"],
        "sourceWindow": {
            "firstSequence": first["sequence"],
            "lastSequence": frame["sequence"],
            "firstFrameTime": first["frameTime"],
            "lastFrameTime": frame["frameTime"],
            "elapsedMilliseconds": (monotonic() - started) * 1000,
            "initialScanStartAddress": f"0x{consumer.seed_base:X}",
            "initialScanBytes": consumer.seed_length,
            "currentPoolStartAddress": f"0x{consumer.base:X}",
            "currentPoolBytes": consumer.length,
            "relativeLagSecondsCandidate": latest["source"]["relativeLagSecondsCandidate"],
            "relativeLagLimitSeconds": latest["source"]["relativeLagLimitSeconds"],
            "freshnessQualification": latest["source"]["freshnessQualification"],
        },
        "snapshot": frame, "catalog": catalog,
        "telemetry": {
            "ready": True,
            "qualification": "two nonce/epoch/player-bound advancing API frames",
        },
        "engagement": {"ready": False, "reasons": unsupported},
        "unsupportedFields": unsupported, "attempts": consumer.attempts,
        "sources": [{"sequence": item["frame"]["sequence"],
                     "frameTime": item["frame"]["frameTime"],
                     "frameSha256": item["frameSha256"],
                     "address": item.get("address")}
                    for item in consumer.accepted],
        "qualification": (
            "Current nonce-bound RIFT API candidate telemetry; no action, native "
            "field qualification, threat decision, or engagement authority."),
    }
    _write_json(consumer.output / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--session-id", required=True,
                        help="32-lowercase-hex nonce already bound with /rr2surv bind")
    parser.add_argument("--seed-index", type=Path,
                        help="Exact-process scout index; default discovers the newest exact-epoch artifact")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scan-mib", type=int, default=16)
    parser.add_argument("--scan-ms", type=int, default=450)
    parser.add_argument("--interval-ms", type=int, default=250)
    parser.add_argument("--max-attempts", type=int, default=6)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(acquire(
            args.expected_host, args.physical_pid, args.session_id,
            args.seed_index, args.output, scan_mib=args.scan_mib,
            scan_milliseconds=args.scan_ms,
            interval_milliseconds=args.interval_ms,
            max_attempts=args.max_attempts), allow_nan=False, sort_keys=True))
        return 0
    except (SurvivalLiveError, CaptureError, OSError, subprocess.SubprocessError,
            TypeError, KeyError, OverflowError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[a-z0-9:-]{1,160}", reason):
            reason = "survival-live-unavailable"
        print(json.dumps({"status": "blocked", "ready": False,
                          "inputSent": False, "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
