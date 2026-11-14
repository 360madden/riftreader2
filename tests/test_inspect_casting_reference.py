from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts import inspect_casting_reference as inspect

try:
    from tests.test_casting_ability_reference import CastingAbilityReferenceTests
except ModuleNotFoundError:
    CastingAbilityReferenceTests = None


def typed(kind, value=None, *, status="ok", reason=None):
    result = {"status": status, "kind": kind}
    if status == "ok":
        result["value"] = value
    else:
        result["reason"] = reason or ("missing" if status == "unavailable" else "wrong-type")
    return result


def snapshot(sequence=1, clock=100.25):
    return {
        "schemaVersion": 1,
        "producer": "RiftReader2CastingAbilityReference",
        "producerVersion": "0.1.0",
        "addonVersion": "0.4.1",
        "loadToken": "frame-100.000000",
        "loadedAtFrame": typed("number", 100.0),
        "sequence": sequence,
        "frameClock": typed("number", clock),
        "source": "rift-api",
        "lineage": dict(inspect.LINEAGE),
        "referenceAbility": {"lookupId": inspect.ABILITY_ID,
                             "expectedName": inspect.ABILITY_NAME},
        "playerId": typed("unit-id", "uPLAYER"),
        "targetId": typed("unit-id", "uPLAYER"),
        "player": {"health": typed("number", 9000), "mana": typed("number", 3980),
                   "combat": typed("boolean", False)},
        "ability": {
            "lookupId": inspect.ABILITY_ID,
            "id": typed("ability-id", inspect.ABILITY_ID),
            "idNew": typed("ability-id", inspect.ABILITY_ID),
            "name": typed("string", inspect.ABILITY_NAME),
            "costMana": typed("number", 15),
            "target": typed("unit-id", "uPLAYER"),
            "currentCooldownRemaining": typed("number", 0),
            "currentCooldownPaused": typed("boolean", False),
            "unusable": typed("boolean", False),
            "outOfRange": typed("boolean", False),
            "passive": typed("boolean", False),
            "positioned": typed("boolean", False),
            "autoattack": typed("boolean", False),
        },
        "castbar": {"ability": typed("ability-id", status="unavailable"),
                    "abilityName": typed("string", status="unavailable"),
                    "remaining": typed("number", status="unavailable"),
                    "channeled": typed("boolean", status="unavailable")},
        "readiness": {"status": "ready", "reason": "observed-ready",
                      "modelStatus": "ready", "modelReason": "observed-ready"},
        "facingAndLineOfSight": "unverified",
        "actionAllowed": False,
    }


def wire(value) -> bytes:
    return (inspect.PREFIX + json.dumps(value, sort_keys=True, separators=(",", ":"),
                                        allow_nan=False).encode("utf-8") + inspect.SUFFIX)


class CastingReferenceInspectionTests(unittest.TestCase):
    def test_compact_addon_version_preserves_observation_only_contract(self):
        value = snapshot()
        value["addonVersion"] = "0.5.0"
        result = inspect.decode_wire(wire(value))
        self.assertFalse(result["snapshot"]["actionAllowed"])
        value["actionAllowed"] = True
        with self.assertRaises(inspect.CastingReferenceError):
            inspect.decode_wire(wire(value))

    def test_current_ready_wire_decodes_without_action_claim(self):
        result = inspect.decode_wire(wire(snapshot()))
        self.assertTrue(result["referenceIdentityMatched"])
        self.assertTrue(result["effectiveTargetMatched"])
        self.assertTrue(result["readyInputsCoherent"])
        self.assertFalse(result["snapshot"]["actionAllowed"])

    def test_framing_size_json_duplicates_and_nonfinite_fail_closed(self):
        with self.assertRaisesRegex(inspect.CastingReferenceError, "framing"):
            inspect.decode_wire(b"{}")
        with self.assertRaisesRegex(inspect.CastingReferenceError, "json-size"):
            inspect.decode_wire(inspect.PREFIX + b"x" * 8193 + inspect.SUFFIX)
        duplicate = b'{"schemaVersion":1,"schemaVersion":1}'
        with self.assertRaisesRegex(inspect.CastingReferenceError, "duplicate-json-key"):
            inspect.decode_wire(inspect.PREFIX + duplicate + inspect.SUFFIX)
        invalid = wire(snapshot()).replace(b'"value":100.25', b'"value":NaN')
        with self.assertRaisesRegex(inspect.CastingReferenceError, "json-nonfinite"):
            inspect.decode_wire(invalid)

    def test_exact_schema_typed_values_and_identity_are_required(self):
        mutations = []
        extra = snapshot(); extra["unexpected"] = True; mutations.append(extra)
        wrong = snapshot(); wrong["producerVersion"] = "0.2.0"; mutations.append(wrong)
        action = snapshot(); action["actionAllowed"] = True; mutations.append(action)
        kind = snapshot(); kind["player"]["mana"]["kind"] = "string"; mutations.append(kind)
        malformed = snapshot(); malformed["ability"]["costMana"]["value"] = True; mutations.append(malformed)
        unit = snapshot(); unit["playerId"]["value"] = "not-a-unit"; mutations.append(unit)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(inspect.CastingReferenceError):
                inspect.decode_wire(wire(value))

    def test_blocked_unavailable_shape_is_preserved(self):
        value = snapshot()
        value["playerId"] = typed("unit-id", status="unavailable")
        value["targetId"] = typed("unit-id", status="unavailable")
        value["player"] = {"health": typed("number", status="unavailable"),
                           "mana": typed("number", status="unavailable"),
                           "combat": typed("boolean", status="unavailable")}
        value["ability"] = {
            "lookupId": inspect.ABILITY_ID,
            "id": typed("ability-id", status="unavailable"),
            "idNew": typed("ability-id", status="unavailable"),
            "name": typed("string", status="unavailable"),
            "costMana": typed("number", status="unavailable"),
            "target": typed("unit-id", status="unavailable"),
        }
        value["castbar"] = {"ability": typed("ability-id", status="unavailable"),
                            "abilityName": typed("string", status="unavailable")}
        value["readiness"] = {"status": "blocked", "reason": "model-read-unavailable"}
        decoded = inspect.decode_wire(wire(value))
        self.assertFalse(decoded["readyInputsCoherent"])
        self.assertIsNone(decoded["playerId"])

        value["readiness"]["reason"] = "frame-clock-invalid"
        value["frameClock"] = typed("number", status="unavailable")
        self.assertFalse(inspect.decode_wire(wire(value))["readyInputsCoherent"])

    def test_load_token_sequence_clock_and_cross_frame_identity_are_strict(self):
        bad_token = snapshot(); bad_token["loadToken"] = "frame-99.000000"
        with self.assertRaisesRegex(inspect.CastingReferenceError, "load-token-clock-mismatch"):
            inspect.decode_wire(wire(bad_token))
        reversed_clock = snapshot(); reversed_clock["frameClock"] = typed("number", 99.0)
        with self.assertRaisesRegex(inspect.CastingReferenceError, "precedes-load"):
            inspect.decode_wire(wire(reversed_clock))

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "one.wire", root / "two.wire"
            first.write_bytes(wire(snapshot(10, 101.0)))
            second.write_bytes(wire(snapshot(11, 101.3)))
            result = inspect.inspect([first, second])
            self.assertTrue(result["continuityChecked"])
            self.assertEqual("observed-ready", result["status"])
            self.assertTrue(result["observedReady"])
            self.assertTrue(any("not independent arithmetic" in item
                                for item in result["limitations"]))
            for mutation, reason in ((lambda value: value.update(sequence=10), "sequence"),
                                     (lambda value: value.update(frameClock=typed("number", 100.9)), "clock"),
                                     (lambda value: value.update(targetId=typed("unit-id", "uOTHER")), "identity")):
                changed = snapshot(11, 101.3)
                mutation(changed)
                second.write_bytes(wire(changed))
                with self.subTest(reason=reason), self.assertRaisesRegex(
                        inspect.CastingReferenceError, reason):
                    inspect.inspect([first, second])

    def test_semantic_mismatch_is_retained_but_never_upgraded_to_ready(self):
        value = snapshot()
        value["ability"]["idNew"] = typed("ability-id", "AOTHER")
        value["readiness"]["status"] = "blocked"
        value["readiness"]["reason"] = "ability-id-mismatch"
        decoded = inspect.decode_wire(wire(value))
        self.assertFalse(decoded["referenceIdentityMatched"])
        self.assertFalse(decoded["readyInputsCoherent"])
        value["readiness"]["reason"] = "ability-detail-inconsistent"
        self.assertFalse(inspect.decode_wire(wire(value))["readyInputsCoherent"])

    def test_multiple_frames_require_available_advancing_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "one.wire", root / "two.wire"
            one, two = snapshot(1, 100.25), snapshot(2, 100.5)
            one["frameClock"] = typed("number", status="unavailable")
            two["frameClock"] = typed("number", status="unavailable")
            first.write_bytes(wire(one)); second.write_bytes(wire(two))
            with self.assertRaisesRegex(inspect.CastingReferenceError,
                                        "unavailable-for-continuity"):
                inspect.inspect([first, second])

    def test_single_ready_frame_does_not_claim_observed_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.wire"
            path.write_bytes(wire(snapshot()))
            result = inspect.inspect([path])
            self.assertTrue(result["frames"][0]["readyInputsCoherent"])
            self.assertFalse(result["observedReady"])
            self.assertEqual("continuity-unproven", result["status"])

    def test_ready_claim_recomputes_all_serialized_blocking_inputs(self):
        mutations = (
            lambda value: value["ability"].update(costMana=typed("number", 0)),
            lambda value: value["player"].update(mana=typed("number", 14)),
            lambda value: value["player"].update(health=typed("number", 0)),
            lambda value: value["ability"].update(currentCooldownRemaining=typed("number", 1)),
            lambda value: value["ability"].update(unusable=typed("boolean", True)),
            lambda value: value["ability"].update(outOfRange=typed("boolean", True)),
            lambda value: value["ability"].update(currentCooldownPaused=typed("boolean", True)),
            lambda value: value["ability"].update(passive=typed("boolean", True)),
            lambda value: value["ability"].update(positioned=typed("boolean", True)),
            lambda value: value["ability"].update(autoattack=typed("boolean", True)),
            lambda value: value["castbar"].update(ability=typed("ability-id", inspect.ABILITY_ID)),
            lambda value: value["castbar"].update(abilityName=typed("string", inspect.ABILITY_NAME)),
            lambda value: value["castbar"].update(remaining=typed("number", 0)),
            lambda value: value["castbar"].update(channeled=typed("boolean", False)),
            lambda value: value["readiness"].update(
                modelStatus="blocked", modelReason="ability-unusable"),
        )
        for mutate in mutations:
            value = snapshot()
            mutate(value)
            with self.subTest(mutate=mutate):
                self.assertFalse(inspect.decode_wire(wire(value))["readyInputsCoherent"])

    def test_file_size_is_rejected_before_unbounded_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large.wire"
            path.write_bytes(b"x" * (len(inspect.PREFIX) + inspect.MAX_JSON_BYTES
                                     + len(inspect.SUFFIX) + 1))
            with self.assertRaisesRegex(inspect.CastingReferenceError, "file-size"):
                inspect.inspect([path])


@unittest.skipIf(CastingAbilityReferenceTests is None, "bundled Lua 5.1 runtime unavailable")
class LuaProducerToDecoderTests(unittest.TestCase):
    def setUp(self):
        self.producer = CastingAbilityReferenceTests(
            "test_ready_self_target_is_typed_observation_only")
        self.producer.setUp()

    def decode(self):
        raw = self.producer.lua.globals().RiftReader2CastingAbilityReferenceWire
        return inspect.decode_wire(raw.encode("utf-8"))

    def test_actual_ready_wire_recomputes_coherent_inputs(self):
        self.assertTrue(self.decode()["readyInputsCoherent"])

    def test_actual_two_ready_wires_are_required_for_observed_ready(self):
        first = self.producer.lua.globals().RiftReader2CastingAbilityReferenceWire
        self.producer.state_value.clock = 100.3
        self.producer.reference.Refresh(True)
        second = self.producer.lua.globals().RiftReader2CastingAbilityReferenceWire
        with tempfile.TemporaryDirectory() as folder:
            one, two = Path(folder) / "one.wire", Path(folder) / "two.wire"
            one.write_bytes(first.encode("utf-8")); two.write_bytes(second.encode("utf-8"))
            result = inspect.inspect([one, two])
        self.assertTrue(result["observedReady"])
        self.assertEqual("observed-ready", result["status"])

    def test_actual_blocked_and_invalid_wires_never_upgrade(self):
        ability = self.producer.state_value.abilities[inspect.ABILITY_ID]
        ability.costMana = 4000
        self.producer.state_value.clock = 100.3
        self.producer.reference.Refresh(True)
        self.assertFalse(self.decode()["readyInputsCoherent"])
        ability.costMana = "15"
        self.producer.state_value.clock = 100.6
        self.producer.reference.Refresh(True)
        decoded = self.decode()
        self.assertEqual("invalid", decoded["snapshot"]["ability"]["costMana"]["status"])
        self.assertFalse(decoded["readyInputsCoherent"])

    def test_actual_inconsistent_second_detail_never_upgrades(self):
        self.producer.state_value.changeAbilityAfter = self.producer.counts.abilityScalar + 2
        self.producer.state_value.changedCooldown = 9
        self.producer.state_value.clock = 100.3
        self.producer.reference.Refresh(True)
        decoded = self.decode()
        self.assertEqual("ability-detail-inconsistent",
                         decoded["snapshot"]["readiness"]["reason"])
        self.assertFalse(decoded["readyInputsCoherent"])


if __name__ == "__main__":
    unittest.main()
