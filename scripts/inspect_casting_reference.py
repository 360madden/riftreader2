"""Strictly decode retained RR2CASTREF1 ability-reference wires.

This is an offline contract inspector.  It accepts only the current v1 producer
shape, preserves typed unavailable/invalid observations, and checks continuity
when more than one wire is supplied.  It does not contact RIFT, establish that
the installed Lua file matches source control, or turn API observations into
independent native-field or casting qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys


PREFIX = b"RR2CASTREF1|"
SUFFIX = b"|RR2CASTREFEND"
MAX_JSON_BYTES = 8192
MAX_WIRES = 64
ABILITY_ID = "A0865F2DE73516486"
ABILITY_NAME = "Lifebound Veil"
TOP_KEYS = {
    "schemaVersion", "producer", "producerVersion", "addonVersion", "loadToken",
    "loadedAtFrame", "sequence", "frameClock", "source", "lineage",
    "referenceAbility", "playerId", "targetId", "player", "ability", "castbar",
    "readiness", "facingAndLineOfSight", "actionAllowed",
}
LINEAGE = {
    "model": "RiftReader2Casting/private.Casting",
    "calls": "Inspect.Ability.New.Detail;Inspect.Unit.Lookup;Inspect.Unit.Detail;Inspect.Unit.Castbar",
    "installedSourceSha256": "external-deployment-receipt-required",
    "sampling": "sequential-non-atomic",
}
ABILITY_BASE = {"lookupId", "id", "idNew", "name", "costMana", "target"}
ABILITY_FULL = ABILITY_BASE | {
    "currentCooldownRemaining", "currentCooldownPaused", "unusable", "outOfRange",
    "passive", "positioned", "autoattack",
}
CASTBAR_BASE = {"ability", "abilityName"}
CASTBAR_FULL = CASTBAR_BASE | {"remaining", "channeled"}
MODEL_REASONS = {
    "unavailable", "player-unavailable", "no-target", "select-ability",
    "identity-changed", "player-not-alive", "target-not-alive",
    "unsupported-ability-type", "ability-target-mismatch", "out-of-range",
    "cast-state-unavailable", "invalid-cooldown", "cooldown-paused",
    "cooldown-ability-or-gcd", "cast-or-channel-active", "ability-unusable",
    "invalid-ability-cost", "insufficient-or-unknown-power",
    "insufficient-or-unknown-mana", "insufficient-or-unknown-energy",
    "insufficient-or-unknown-charge", "insufficient-or-unknown-spirit",
    "insufficient-or-unknown-planar", "observed-ready",
}
REFERENCE_REASONS = MODEL_REASONS | {
    "reference-ability-unavailable", "model-read-unavailable",
    "ability-detail-unavailable", "ability-id-mismatch", "ability-name-mismatch",
    "ability-detail-inconsistent", "identity-changed-after-detail",
    "model-status-invalid", "frame-clock-invalid",
}


class CastingReferenceError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CastingReferenceError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _number(value, label: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CastingReferenceError(f"{label}:finite-number-required")
    return value


def _text(value, label: str, limit: int):
    if (not isinstance(value, str) or not 0 < len(value) <= limit
            or any(ord(character) < 32 for character in value)):
        raise CastingReferenceError(f"{label}:bounded-text-required")
    return value


def _typed(value, label: str, kind: str, *, limit: int = 256) -> dict:
    if not isinstance(value, dict) or value.get("kind") != kind:
        raise CastingReferenceError(f"{label}:typed-{kind}-contract")
    status = value.get("status")
    if status == "ok":
        if set(value) != {"status", "kind", "value"}:
            raise CastingReferenceError(f"{label}:ok-shape")
        observed = value["value"]
        if kind == "number":
            _number(observed, label)
        elif kind == "boolean":
            if type(observed) is not bool:
                raise CastingReferenceError(f"{label}:boolean-value")
        else:
            _text(observed, label, limit)
            if kind == "unit-id" and not observed.startswith("u"):
                raise CastingReferenceError(f"{label}:unit-id-value")
    elif status == "unavailable":
        if set(value) != {"status", "reason", "kind"} or value.get("reason") != "missing":
            raise CastingReferenceError(f"{label}:unavailable-shape")
    elif status == "invalid":
        allowed = ({"wrong-type", "nonfinite"} if kind == "number" else
                   {"wrong-type"} if kind == "boolean" else
                   {"wrong-type", "invalid-string"})
        if set(value) != {"status", "reason", "kind"} or value.get("reason") not in allowed:
            raise CastingReferenceError(f"{label}:invalid-shape")
    else:
        raise CastingReferenceError(f"{label}:typed-status")
    return value


def _value(typed: dict):
    return typed.get("value") if typed.get("status") == "ok" else None


def _ready_inputs_coherent(root: dict) -> bool:
    ability = root["ability"]
    player = root["player"]
    castbar = root["castbar"]
    readiness = root["readiness"]
    player_id = _value(root["playerId"])
    target_id = _value(root["targetId"])
    cost = _value(ability["costMana"])
    mana = _value(player["mana"])
    health = _value(player["health"])
    flags = ("currentCooldownPaused", "unusable", "outOfRange", "passive",
             "positioned", "autoattack")
    return (
        set(ability) == ABILITY_FULL
        and set(castbar) == CASTBAR_FULL
        and readiness == {
            "status": "ready", "reason": "observed-ready",
            "modelStatus": "ready", "modelReason": "observed-ready"}
        and player_id is not None and player_id == target_id
        and _value(ability["target"]) == target_id
        and _value(ability["id"]) == ABILITY_ID
        and _value(ability["idNew"]) == ABILITY_ID
        and _value(ability["name"]) == ABILITY_NAME
        and isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost > 0
        and isinstance(mana, (int, float)) and not isinstance(mana, bool) and mana >= cost
        and isinstance(health, (int, float)) and not isinstance(health, bool) and health > 0
        and _value(ability["currentCooldownRemaining"]) == 0
        and all(_value(ability[name]) is False for name in flags)
        and castbar["ability"]["status"] == "unavailable"
        and castbar["abilityName"]["status"] == "unavailable"
        and castbar["remaining"]["status"] == "unavailable"
        and castbar["channeled"]["status"] == "unavailable"
    )


def decode_wire(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not raw.startswith(PREFIX) or not raw.endswith(SUFFIX):
        raise CastingReferenceError("wire-framing")
    payload = raw[len(PREFIX):-len(SUFFIX)]
    if not 0 < len(payload) <= MAX_JSON_BYTES:
        raise CastingReferenceError("wire-json-size")
    try:
        root = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CastingReferenceError(f"json-nonfinite:{value}")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CastingReferenceError("wire-json-invalid") from exc
    if not isinstance(root, dict) or set(root) != TOP_KEYS:
        raise CastingReferenceError("top-level-contract")
    if (root.get("schemaVersion") != 1
            or root.get("producer") != "RiftReader2CastingAbilityReference"
            or root.get("producerVersion") != "0.1.0"
            or root.get("addonVersion") not in ("0.4.1", "0.4.2", "0.5.0")
            or root.get("source") != "rift-api"
            or root.get("lineage") != LINEAGE
            or root.get("referenceAbility") != {
                "lookupId": ABILITY_ID, "expectedName": ABILITY_NAME}
            or root.get("facingAndLineOfSight") != "unverified"
            or root.get("actionAllowed") is not False):
        raise CastingReferenceError("producer-identity-contract")

    sequence = root.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise CastingReferenceError("sequence-invalid")
    load_token = root.get("loadToken")
    if not isinstance(load_token, str) or not re.fullmatch(r"(?:frame--?\d+\.\d{6}|unavailable)", load_token):
        raise CastingReferenceError("load-token-invalid")
    loaded = _typed(root.get("loadedAtFrame"), "loadedAtFrame", "number")
    clock = _typed(root.get("frameClock"), "frameClock", "number")
    if loaded["status"] == "ok":
        if load_token != f"frame-{loaded['value']:.6f}":
            raise CastingReferenceError("load-token-clock-mismatch")
    elif load_token != "unavailable":
        raise CastingReferenceError("load-token-unavailable-mismatch")
    if (loaded["status"] == "ok" and clock["status"] == "ok"
            and clock["value"] < loaded["value"]):
        raise CastingReferenceError("frame-clock-precedes-load")

    player_id = _typed(root.get("playerId"), "playerId", "unit-id", limit=128)
    target_id = _typed(root.get("targetId"), "targetId", "unit-id", limit=128)
    player = root.get("player")
    if not isinstance(player, dict) or set(player) != {"health", "mana", "combat"}:
        raise CastingReferenceError("player-contract")
    _typed(player["health"], "player.health", "number")
    _typed(player["mana"], "player.mana", "number")
    _typed(player["combat"], "player.combat", "boolean")

    ability = root.get("ability")
    castbar = root.get("castbar")
    if not isinstance(ability, dict) or set(ability) not in (ABILITY_BASE, ABILITY_FULL):
        raise CastingReferenceError("ability-contract")
    if ability.get("lookupId") != ABILITY_ID:
        raise CastingReferenceError("ability-lookup-identity")
    _typed(ability["id"], "ability.id", "ability-id", limit=128)
    _typed(ability["idNew"], "ability.idNew", "ability-id", limit=128)
    _typed(ability["name"], "ability.name", "string", limit=120)
    _typed(ability["costMana"], "ability.costMana", "number")
    _typed(ability["target"], "ability.target", "unit-id", limit=128)
    if set(ability) == ABILITY_FULL:
        _typed(ability["currentCooldownRemaining"], "ability.currentCooldownRemaining", "number")
        for name in ("currentCooldownPaused", "unusable", "outOfRange", "passive",
                     "positioned", "autoattack"):
            _typed(ability[name], f"ability.{name}", "boolean")
    if not isinstance(castbar, dict) or set(castbar) not in (CASTBAR_BASE, CASTBAR_FULL):
        raise CastingReferenceError("castbar-contract")
    _typed(castbar["ability"], "castbar.ability", "ability-id", limit=128)
    _typed(castbar["abilityName"], "castbar.abilityName", "string", limit=120)
    if set(castbar) == CASTBAR_FULL:
        _typed(castbar["remaining"], "castbar.remaining", "number")
        _typed(castbar["channeled"], "castbar.channeled", "boolean")

    readiness = root.get("readiness")
    if not isinstance(readiness, dict) or set(readiness) not in (
            {"status", "reason"}, {"status", "reason", "modelStatus", "modelReason"}):
        raise CastingReferenceError("readiness-contract")
    if readiness.get("status") not in ("ready", "waiting", "blocked"):
        raise CastingReferenceError("readiness-status")
    if readiness.get("reason") not in REFERENCE_REASONS:
        raise CastingReferenceError("readiness-reason")
    if ((readiness["status"] == "ready") != (readiness["reason"] == "observed-ready")
            or (readiness["status"] == "waiting")
            != (readiness["reason"] == "cooldown-ability-or-gcd")):
        raise CastingReferenceError("readiness-status-reason-disagree")
    unavailable_shape = set(ability) == ABILITY_BASE and set(castbar) == CASTBAR_BASE
    if unavailable_shape != (set(readiness) == {"status", "reason"}):
        raise CastingReferenceError("readiness-shape-disagrees")
    if unavailable_shape and readiness["reason"] not in {
            "reference-ability-unavailable", "model-read-unavailable", "frame-clock-invalid"}:
        raise CastingReferenceError("unavailable-readiness-reason")
    if not unavailable_shape:
        if (readiness.get("modelStatus") not in ("ready", "waiting", "blocked")
                or readiness.get("modelReason") not in MODEL_REASONS):
            raise CastingReferenceError("model-readiness-contract")
        if ((readiness["modelStatus"] == "ready")
                != (readiness["modelReason"] == "observed-ready")
                or (readiness["modelStatus"] == "waiting")
                != (readiness["modelReason"] == "cooldown-ability-or-gcd")):
            raise CastingReferenceError("model-status-reason-disagree")

    canonical = _value(ability["idNew"]) or _value(ability["id"])
    identity_matched = (canonical == ABILITY_ID and _value(ability["name"]) == ABILITY_NAME)
    target_matched = (_value(target_id) is not None
                      and _value(ability["target"]) == _value(target_id))
    ready_inputs = _ready_inputs_coherent(root)
    return {
        "wireSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sequence": sequence,
        "frameClock": _value(clock),
        "loadToken": load_token,
        "loadedAtFrame": _value(loaded),
        "playerId": _value(player_id),
        "targetId": _value(target_id),
        "referenceIdentityMatched": identity_matched,
        "effectiveTargetMatched": target_matched,
        "readyInputsCoherent": ready_inputs,
        "snapshot": root,
    }


def _read_wire_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise CastingReferenceError("wire-file-invalid")
    maximum = len(PREFIX) + MAX_JSON_BYTES + len(SUFFIX)
    if not 0 < path.stat().st_size <= maximum:
        raise CastingReferenceError("wire-file-size-invalid")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if not 0 < len(raw) <= maximum:
        raise CastingReferenceError("wire-file-size-invalid")
    return raw


def inspect(paths: list[Path]) -> dict:
    if not paths or len(paths) > MAX_WIRES:
        raise CastingReferenceError("wire-count-invalid")
    frames = []
    for path in paths:
        raw = _read_wire_file(path)
        frame = decode_wire(raw)
        frame["path"] = str(path.resolve(strict=True))
        frames.append(frame)
    return inspect_decoded(frames)


def inspect_decoded(frames: list[dict]) -> dict:
    if not frames or len(frames) > MAX_WIRES:
        raise CastingReferenceError("wire-count-invalid")
    first = frames[0]
    for previous, current in zip(frames, frames[1:]):
        if (current["loadToken"] != first["loadToken"]
                or current["snapshot"]["loadedAtFrame"]
                != first["snapshot"]["loadedAtFrame"]
                or current["snapshot"]["playerId"] != first["snapshot"]["playerId"]
                or current["snapshot"]["targetId"] != first["snapshot"]["targetId"]):
            raise CastingReferenceError("cross-frame-identity-changed")
        if current["sequence"] <= previous["sequence"]:
            raise CastingReferenceError("sequence-not-advancing")
        before, after = previous["frameClock"], current["frameClock"]
        if before is None or after is None:
            raise CastingReferenceError("frame-clock-unavailable-for-continuity")
        if after <= before:
            raise CastingReferenceError("frame-clock-not-advancing")
    observed_ready = (len(frames) > 1 and frames[-2]["readyInputsCoherent"]
                      and frames[-1]["readyInputsCoherent"])
    status = ("observed-ready" if observed_ready else
              "continuity-unproven" if frames[-1]["readyInputsCoherent"] else
              "blocked-or-unavailable")
    return {
        "schemaVersion": 1,
        "evidenceKind": "casting-ability-reference-inspection/1",
        "status": status,
        "observedReady": observed_ready,
        "frameCount": len(frames),
        "continuityChecked": len(frames) > 1,
        "frames": frames,
        "limitations": [
            "The wire is an observation-only RIFT API presentation; actionAllowed is always false.",
            "The installed Lua source hash requires an external deployment receipt.",
            "API/native agreement may share a client getter or cache and is not independent arithmetic proof.",
            "Sequential API calls are not an atomic observation; facing and line of sight remain unverified.",
            "Observed-ready requires two identity-stable frames with coherent serialized inputs and advancing clocks.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wire", action="append", required=True, type=Path,
                        help="exact framed wire file; repeat in chronological order")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.wire)
        encoded = json.dumps(result, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        print(encoded, end="")
        return 0
    except (OSError, CastingReferenceError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
