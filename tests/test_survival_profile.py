"""Offline contract checks for bounded survival profiles; no RIFT reads or input."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import survival_profile as profile


class SurvivalProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "survival.json"
        self.valid = {
            "schemaVersion": 1,
            "nonce": "0123456789abcdef0123456789abcdef",
            "abilities": {"damage": "ability.damage"},
            "actions": ["ability.damage"],
            "thresholds": {"healBelowPct":45, "defendBelowPct":65,
                           "retreatBelowPct":25, "recoverHealthPct":80,
                           "recoverResourcePct":35, "maximumLevelDelta":2},
            "retreat": {"maximumSeconds":20, "minimumTrailPoints":1},
            "timing": {"pollMilliseconds":100, "actionDeadlineMilliseconds":3000},
        }

    def load(self, value=None, **kwargs):
        self.path.write_text(json.dumps(self.valid if value is None else value), encoding="utf-8")
        return profile.load_survival_profile(self.path, **kwargs)

    def refused(self, value=None, *, text=None, expected_binding=None):
        if text is None:
            self.path.write_text(json.dumps(self.valid if value is None else value), encoding="utf-8")
        else:
            self.path.write_text(text, encoding="utf-8")
        with self.assertRaises(profile.SurvivalProfileError):
            profile.load_survival_profile(self.path, expected_binding=expected_binding)

    def test_minimum_profile_requires_damage_and_retreat_without_inventing_roles(self):
        loaded = self.load()
        self.assertEqual({"heal":None, "defense":None, "interrupt":None,
                          "damage":"ability.damage"}, loaded["abilities"])
        self.assertEqual(["ability.damage"], loaded["actions"])
        self.assertEqual({"ability.damage": ["ability.damage"]},
                         loaded["outcomeAbilityIds"])
        self.assertEqual(1, loaded["schemaVersion"])
        self.assertFalse(loaded["inputSent"])
        self.assertEqual(str(self.path.resolve()), loaded["source"])

    def test_all_present_roles_are_distinct_exact_allowlisted_ids(self):
        value = deepcopy(self.valid)
        value["abilities"] = {"heal":"ability.heal", "defense":"ability.defense",
                              "interrupt":"ability.interrupt", "damage":"ability.damage"}
        value["actions"] = ["ability.damage", "ability.heal", "ability.defense",
                            "ability.interrupt", "ability.utility"]
        loaded = self.load(value)
        self.assertEqual(value["abilities"], loaded["abilities"])
        self.assertEqual(value["actions"], loaded["actions"])

        for mutate in (
            lambda row: row["abilities"].update(heal=row["abilities"]["damage"]),
            lambda row: row["abilities"].update(damage="/cast arbitrary macro"),
            lambda row: row["actions"].append("ability.damage"),
            lambda row: row["actions"].remove("ability.heal"),
            lambda row: row.update(actions=[f"ability.{i}" for i in range(9)]),
            lambda row: row.update(macroText="cast anything"),
        ):
            invalid = deepcopy(value)
            mutate(invalid)
            with self.subTest(invalid=invalid):
                self.refused(invalid)

    def test_exact_cast_to_effect_ids_supports_distinct_pacify_damage_event(self):
        cast_id = "A661611602A6D2082"
        effect_id = "A70A3925291DD1E14"
        autoattack_id = "A4FDE000000000000"
        value = deepcopy(self.valid)
        value["abilities"] = {"damage": cast_id}
        value["actions"] = [cast_id]
        value["outcomeAbilityIds"] = {cast_id: [effect_id]}
        loaded = self.load(value)
        self.assertEqual({cast_id: [effect_id]}, loaded["outcomeAbilityIds"])
        self.assertNotIn(autoattack_id, loaded["outcomeAbilityIds"][cast_id])

    def test_outcome_effect_ids_are_exact_bounded_distinct_and_action_keyed(self):
        value = deepcopy(self.valid)
        value["abilities"] = {"damage": "cast.damage", "interrupt": "cast.interrupt"}
        value["actions"] = ["cast.damage", "cast.interrupt"]
        value["outcomeAbilityIds"] = {
            "cast.damage": ["effect.damage", "effect.damage.secondary"],
            "cast.interrupt": ["effect.interrupt"]}
        loaded = self.load(value)
        self.assertEqual(value["outcomeAbilityIds"], loaded["outcomeAbilityIds"])

        mutations = (
            lambda row: row["outcomeAbilityIds"].update(
                {"not-an-allowed-cast": ["effect.other"]}),
            lambda row: row["outcomeAbilityIds"].update({"cast.damage": []}),
            lambda row: row["outcomeAbilityIds"].update(
                {"cast.damage": [f"effect.{index}" for index in range(5)]}),
            lambda row: row["outcomeAbilityIds"].update(
                {"cast.damage": ["effect.same", "effect.same"]}),
            lambda row: row["outcomeAbilityIds"].update(
                {"cast.damage": ["effect.same"], "cast.interrupt": ["effect.same"]}),
            lambda row: row["outcomeAbilityIds"].update(
                {"cast.damage": ["/cast by name"]}),
        )
        for mutate in mutations:
            invalid = deepcopy(value)
            mutate(invalid)
            with self.subTest(invalid=invalid):
                self.refused(invalid)

    def test_optional_binding_can_be_pinned_to_any_exact_caller_subset(self):
        value = deepcopy(self.valid)
        value["binding"] = {"hostName":"amd-desktop", "processId":21672,
                            "processStartUtcTicks":639302305454629980,
                            "playerId":"239816685251645959"}
        loaded = self.load(value, expected_binding={"hostName":"AMD-DESKTOP",
                           "processStartUtcTicks":639302305454629980})
        self.assertEqual("AMD-DESKTOP", loaded["binding"]["hostName"])
        self.load(value, expected_binding={"playerId":"239816685251645959"})
        for expected in ({"processId":1}, {"playerId":"other"}, {"hostName":"LEGION"}):
            with self.subTest(expected=expected):
                self.refused(value, expected_binding=expected)
        self.refused(self.valid, expected_binding={"processId":21672})

    def test_binding_and_expected_binding_are_strict(self):
        for binding in (
            {"hostName":"AMD-DESKTOP", "processId":0, "processStartUtcTicks":1},
            {"hostName":"AMD DESKTOP", "processId":1, "processStartUtcTicks":1},
            {"hostName":"AMD-DESKTOP", "processId":1, "processStartUtcTicks":0},
            {"hostName":"AMD-DESKTOP", "processId":1, "processStartUtcTicks":1,
             "playerId":"/target self"},
            {"hostName":"AMD-DESKTOP", "processId":1, "processStartUtcTicks":1,
             "windowHandle":123},
        ):
            value = deepcopy(self.valid)
            value["binding"] = binding
            with self.subTest(binding=binding):
                self.refused(value)
        with self.assertRaises(TypeError):
            self.load(expected_binding={})
        self.refused(expected_binding={"unitKey":"player"})

    def test_nonce_schema_unknown_and_duplicate_fields_are_refused(self):
        for key, value in (("schemaVersion", 2), ("schemaVersion", True),
                           ("nonce", "A" * 32), ("nonce", "a" * 31)):
            invalid = deepcopy(self.valid)
            invalid[key] = value
            with self.subTest(key=key, value=value):
                self.refused(invalid)
        self.refused(text='{"schemaVersion":1,"schemaVersion":1}')
        self.refused(text="[]")
        self.refused(text="{")

    def test_thresholds_are_finite_bounded_and_ordered(self):
        for field, value in (("healBelowPct", -1), ("defendBelowPct", 101),
                             ("recoverResourcePct", float("inf")),
                             ("maximumLevelDelta", 21), ("maximumLevelDelta", 1.5),
                             ("maximumLevelDelta", True)):
            invalid = deepcopy(self.valid)
            invalid["thresholds"][field] = value
            with self.subTest(field=field, value=value):
                self.refused(invalid)
        invalid = deepcopy(self.valid)
        invalid["thresholds"]["retreatBelowPct"] = 50
        self.refused(invalid)
        self.refused(text=json.dumps(self.valid).replace('"healBelowPct": 45',
                                                         '"healBelowPct": NaN'))

    def test_explicit_absolute_resource_and_qualified_coordinate_basis(self):
        value = deepcopy(self.valid)
        value["resourceKind"] = "absolute-power"
        value["thresholds"]["recoverResourceAbsolute"] = 18
        value["coordinateBasis"] = {
            "qualified": True, "space": "UIParent-to-client-pixels",
            "viewportWidth": 1965.336, "viewportHeight": 1024,
            "clientWidth": 1888, "clientHeight": 992,
            "scaleX": 0.96065, "scaleY": 0.96875,
            "offsetX": 0, "offsetY": 0,
        }
        loaded = self.load(value)
        self.assertEqual(18, loaded["thresholds"]["recoverResourceAbsolute"])
        self.assertEqual("absolute-power", loaded["resourceKind"])
        self.assertTrue(loaded["coordinateBasis"]["qualified"])
        self.assertEqual(1888, loaded["coordinateBasis"]["clientWidth"])

        for section, field, invalid_value in (
            ("thresholds", "recoverResourceAbsolute", -1),
            ("coordinateBasis", "qualified", False),
            ("coordinateBasis", "space", "guessed-scale"),
            ("coordinateBasis", "scaleX", 0),
            ("coordinateBasis", "clientWidth", 63),
        ):
            invalid = deepcopy(value)
            invalid[section][field] = invalid_value
            with self.subTest(section=section, field=field):
                self.refused(invalid)

    def test_retreat_and_timing_have_meaningful_bounds(self):
        cases = (("retreat", "maximumSeconds", 0),
                 ("retreat", "maximumSeconds", 301),
                 ("retreat", "minimumTrailPoints", 0),
                 ("timing", "pollMilliseconds", 24),
                 ("timing", "pollMilliseconds", 5001),
                 ("timing", "actionDeadlineMilliseconds", 60001))
        for section, field, value in cases:
            invalid = deepcopy(self.valid)
            invalid[section][field] = value
            with self.subTest(section=section, field=field, value=value):
                self.refused(invalid)
        invalid = deepcopy(self.valid)
        invalid["timing"] = {"pollMilliseconds":500,
                             "actionDeadlineMilliseconds":400}
        self.refused(invalid)

    def test_file_size_is_bounded_before_json_parsing(self):
        self.path.write_bytes(b" " * (profile.MAX_PROFILE_BYTES + 1))
        with self.assertRaisesRegex(profile.SurvivalProfileError, "exceeds"):
            profile.load_survival_profile(self.path)
        with self.assertRaisesRegex(profile.SurvivalProfileError, "unreadable"):
            profile.load_survival_profile(Path(self.temp.name) / "missing.json")


if __name__ == "__main__":
    unittest.main()
