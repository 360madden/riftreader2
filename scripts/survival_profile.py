"""Strict bounded loader for explicit, verified survival integration profiles."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re


MAX_PROFILE_BYTES = 64 * 1024
ABILITY_ROLES = ("heal", "defense", "interrupt", "damage")
_NONCE = re.compile(r"[0-9a-f]{32}")
_EXACT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_BINDING_FIELDS = ("hostName", "processId", "processStartUtcTicks", "playerId")
_BASIS_FIELDS = ("qualified", "space", "viewportWidth", "viewportHeight",
                 "clientWidth", "clientHeight", "scaleX", "scaleY",
                 "offsetX", "offsetY")


class SurvivalProfileError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SurvivalProfileError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _constant(value):
    raise SurvivalProfileError(f"non-finite JSON number: {value}")


def _object(value, label, *, required=(), allowed=()):
    if not isinstance(value, dict):
        raise SurvivalProfileError(f"{label} must be an object")
    missing, unknown = set(required) - set(value), set(value) - set(allowed)
    if missing:
        raise SurvivalProfileError(f"{label} missing: {', '.join(sorted(missing))}")
    if unknown:
        raise SurvivalProfileError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    return value


def _number(value, label, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise SurvivalProfileError(f"{label} must be finite and between {low} and {high}")
    return float(value)


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise SurvivalProfileError(f"{label} must be an integer between {low} and {high}")
    return value


def _exact_id(value, label):
    if not isinstance(value, str) or _EXACT_ID.fullmatch(value) is None:
        raise SurvivalProfileError(f"{label} must be one exact ID")
    return value


def _binding(value):
    value = _object(value, "binding",
                    required=("hostName", "processId", "processStartUtcTicks"),
                    allowed=_BINDING_FIELDS)
    host = value["hostName"]
    if not isinstance(host, str) or _HOST.fullmatch(host) is None:
        raise SurvivalProfileError("binding.hostName is invalid")
    result = {"hostName": host.upper(),
              "processId": _integer(value["processId"], "binding.processId", 1, 2_147_483_647),
              "processStartUtcTicks": _integer(value["processStartUtcTicks"],
                                                "binding.processStartUtcTicks", 1, 10**19)}
    if "playerId" in value:
        result["playerId"] = _exact_id(value["playerId"], "binding.playerId")
    return result


def _coordinate_basis(value):
    value = _object(value, "coordinateBasis", required=_BASIS_FIELDS,
                    allowed=_BASIS_FIELDS)
    if value["qualified"] is not True:
        raise SurvivalProfileError("coordinateBasis must be explicitly qualified")
    if value["space"] != "UIParent-to-client-pixels":
        raise SurvivalProfileError("coordinateBasis.space is unsupported")
    return {
        "qualified": True,
        "space": "UIParent-to-client-pixels",
        "viewportWidth": _number(value["viewportWidth"],
                                   "coordinateBasis.viewportWidth", 64, 8192),
        "viewportHeight": _number(value["viewportHeight"],
                                    "coordinateBasis.viewportHeight", 64, 8192),
        "clientWidth": _integer(value["clientWidth"],
                                  "coordinateBasis.clientWidth", 64, 8192),
        "clientHeight": _integer(value["clientHeight"],
                                   "coordinateBasis.clientHeight", 64, 8192),
        "scaleX": _number(value["scaleX"], "coordinateBasis.scaleX", 0.01, 10),
        "scaleY": _number(value["scaleY"], "coordinateBasis.scaleY", 0.01, 10),
        "offsetX": _number(value["offsetX"], "coordinateBasis.offsetX", -32768, 32767),
        "offsetY": _number(value["offsetY"], "coordinateBasis.offsetY", -32768, 32767),
    }


def _outcome_ability_ids(value, actions):
    """Normalize exact cast-ID to exact observed-effect-ID allowlists."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise SurvivalProfileError("outcomeAbilityIds must be an object")
    unknown = set(value) - set(actions)
    if unknown:
        raise SurvivalProfileError(
            "outcomeAbilityIds keys must be allowlisted actions: "
            + ", ".join(sorted(unknown)))
    result = {}
    observed = []
    for cast_id in actions:
        effect_ids = value.get(cast_id, [cast_id])
        if not isinstance(effect_ids, list) or not 1 <= len(effect_ids) <= 4:
            raise SurvivalProfileError(
                f"outcomeAbilityIds.{cast_id} must contain 1 to 4 exact IDs")
        normalized = [_exact_id(effect_id,
                                f"outcomeAbilityIds.{cast_id}[{index}]")
                      for index, effect_id in enumerate(effect_ids)]
        if len(normalized) != len(set(normalized)):
            raise SurvivalProfileError(
                f"outcomeAbilityIds.{cast_id} contains a duplicate effect ID")
        result[cast_id] = normalized
        observed.extend(normalized)
    if len(observed) > 32:
        raise SurvivalProfileError("outcomeAbilityIds contains more than 32 effect IDs")
    if len(observed) != len(set(observed)):
        raise SurvivalProfileError(
            "outcomeAbilityIds effect IDs must be distinct across cast actions")
    return result


def _validate_binding(profile_binding, expected):
    if expected is None:
        return
    if not isinstance(expected, dict) or not expected:
        raise TypeError("expected_binding must be a nonempty target identity object")
    unknown = set(expected) - set(_BINDING_FIELDS)
    if unknown:
        raise SurvivalProfileError("expected binding has unknown fields: " + ", ".join(sorted(unknown)))
    if profile_binding is None:
        raise SurvivalProfileError("profile has no binding for caller-pinned validation")
    normalized = {}
    for key, value in expected.items():
        if key == "hostName":
            if not isinstance(value, str) or _HOST.fullmatch(value) is None:
                raise SurvivalProfileError("expected binding hostName is invalid")
            normalized[key] = value.upper()
        elif key == "playerId":
            normalized[key] = _exact_id(value, "expected binding.playerId")
        elif key == "processId":
            normalized[key] = _integer(value, "expected binding.processId", 1, 2_147_483_647)
        else:
            normalized[key] = _integer(value, "expected binding.processStartUtcTicks", 1, 10**19)
    if any(profile_binding.get(key) != value for key, value in normalized.items()):
        raise SurvivalProfileError("profile binding does not match the caller-pinned identity")


def load_survival_profile(path, *, expected_binding=None):
    """Load and normalize one profile without reading RIFT or sending input."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SurvivalProfileError(f"survival profile is unreadable: {exc}") from None
    if len(raw) > MAX_PROFILE_BYTES:
        raise SurvivalProfileError(f"survival profile exceeds {MAX_PROFILE_BYTES} bytes")
    try:
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SurvivalProfileError(f"survival profile is invalid JSON: {exc}") from None
    document = _object(document, "profile",
                       required=("schemaVersion", "nonce", "abilities", "actions",
                                 "thresholds", "retreat", "timing"),
                       allowed=("schemaVersion", "nonce", "binding", "coordinateBasis",
                                "resourceKind",
                                "abilities", "actions", "outcomeAbilityIds",
                                "thresholds", "retreat", "timing"))
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise SurvivalProfileError("schemaVersion must be 1")
    nonce = document["nonce"]
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        raise SurvivalProfileError("nonce must be exactly 32 lowercase hexadecimal characters")
    resource_kind = document.get("resourceKind", "percent")
    if resource_kind == "percentage":
        resource_kind = "percent"
    if resource_kind not in ("percent", "absolute-power"):
        raise SurvivalProfileError("resourceKind must be percent or absolute-power")

    abilities = _object(document["abilities"], "abilities",
                        required=("damage",), allowed=ABILITY_ROLES)
    normalized_abilities = {}
    for role in ABILITY_ROLES:
        value = abilities.get(role)
        normalized_abilities[role] = (None if value is None and role != "damage"
                                      else _exact_id(value, f"abilities.{role}"))
    present = [value for value in normalized_abilities.values() if value is not None]
    if len(present) != len(set(present)):
        raise SurvivalProfileError("present ability roles must use distinct exact IDs")

    actions = document["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 8:
        raise SurvivalProfileError("actions must contain 1 to 8 exact allowlisted ability IDs")
    actions = [_exact_id(value, f"actions[{index}]") for index, value in enumerate(actions)]
    if len(actions) != len(set(actions)):
        raise SurvivalProfileError("actions contains a duplicate ability ID")
    if set(present) - set(actions):
        raise SurvivalProfileError("all role ability IDs must appear in the actions allowlist")
    outcome_ability_ids = _outcome_ability_ids(
        document.get("outcomeAbilityIds"), actions)

    thresholds = _object(document["thresholds"], "thresholds",
                         required=("healBelowPct", "defendBelowPct", "retreatBelowPct",
                                   "recoverHealthPct", "recoverResourcePct", "maximumLevelDelta"),
                         allowed=("healBelowPct", "defendBelowPct", "retreatBelowPct",
                                  "recoverHealthPct", "recoverResourcePct",
                                  "recoverResourceAbsolute", "maximumLevelDelta"))
    thresholds = {
        "healBelowPct": _number(thresholds["healBelowPct"], "thresholds.healBelowPct", 0, 100),
        "defendBelowPct": _number(thresholds["defendBelowPct"], "thresholds.defendBelowPct", 0, 100),
        "retreatBelowPct": _number(thresholds["retreatBelowPct"], "thresholds.retreatBelowPct", 0, 100),
        "recoverHealthPct": _number(thresholds["recoverHealthPct"], "thresholds.recoverHealthPct", 0, 100),
        "recoverResourcePct": _number(thresholds["recoverResourcePct"], "thresholds.recoverResourcePct", 0, 100),
        "maximumLevelDelta": _integer(thresholds["maximumLevelDelta"],
                                      "thresholds.maximumLevelDelta", 0, 20),
    }
    if "recoverResourceAbsolute" in document["thresholds"]:
        thresholds["recoverResourceAbsolute"] = _number(
            document["thresholds"]["recoverResourceAbsolute"],
            "thresholds.recoverResourceAbsolute", 0, 1_000_000_000)
    if not (thresholds["retreatBelowPct"] <= thresholds["healBelowPct"]
            <= thresholds["defendBelowPct"] <= thresholds["recoverHealthPct"]):
        raise SurvivalProfileError("health thresholds must satisfy retreat <= heal <= defense <= recovery")

    retreat = _object(document["retreat"], "retreat",
                      required=("maximumSeconds", "minimumTrailPoints"),
                      allowed=("maximumSeconds", "minimumTrailPoints"))
    retreat = {"maximumSeconds": _number(retreat["maximumSeconds"],
                                          "retreat.maximumSeconds", 1, 300),
               "minimumTrailPoints": _integer(retreat["minimumTrailPoints"],
                                               "retreat.minimumTrailPoints", 1, 256)}

    timing = _object(document["timing"], "timing",
                     required=("pollMilliseconds", "actionDeadlineMilliseconds"),
                     allowed=("pollMilliseconds", "actionDeadlineMilliseconds"))
    timing = {"pollMilliseconds": _integer(timing["pollMilliseconds"],
                                             "timing.pollMilliseconds", 25, 5000),
              "actionDeadlineMilliseconds": _integer(timing["actionDeadlineMilliseconds"],
                                                        "timing.actionDeadlineMilliseconds", 100, 60000)}
    if timing["actionDeadlineMilliseconds"] < timing["pollMilliseconds"]:
        raise SurvivalProfileError("action deadline must be at least one polling interval")

    binding = _binding(document["binding"]) if "binding" in document else None
    coordinate_basis = (_coordinate_basis(document["coordinateBasis"])
                        if "coordinateBasis" in document else None)
    _validate_binding(binding, expected_binding)
    return {"schemaVersion": 1, "nonce": nonce, "binding": binding,
            "coordinateBasis": coordinate_basis,
            "resourceKind": resource_kind,
            "abilities": normalized_abilities, "actions": actions,
            "outcomeAbilityIds": outcome_ability_ids,
            "thresholds": thresholds, "retreat": retreat, "timing": timing,
            "source": str(source.resolve()), "inputSent": False}
