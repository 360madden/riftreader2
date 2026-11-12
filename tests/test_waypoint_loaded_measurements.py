"""Offline admission of historical loaded-unit waypoint positions."""
from copy import deepcopy
import json
import unittest

from scripts.waypoint_measurements import (LOADED_UNIT_POSITION_QUALIFICATION, document_measurements,
                                          loaded_unit_measurement, measurement, parse_projection_route)


class LoadedUnitMeasurementsTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a"*64, "unitKey": "42",
                         "processId": 123, "processStartUtcTicks": "456"}
        self.xyz = {"x": 7421.64013671875, "y": 863.5865478515625, "z": 2941.143310546875}
        self.timestamp = "2026-11-12T17:01:02.1234567Z"
        self.receipt = loaded_unit_measurement(self.xyz, self.identity, "unit-positions.json", self.timestamp,
                                               unit_key=str(2**64-1), entity_address=str(0x20000),
                                               source_sha256="bC"*32)
        self.document = {"waypoints": [["Saved unit", round(self.xyz["x"], 6), round(self.xyz["z"], 6)]],
                         "heights": [self.xyz["y"]], "pointMeasurements": [self.receipt]}

    def test_saved_receipt_roundtrips_full_xyz_subject_observer_epoch_and_source(self):
        document = json.loads(json.dumps(self.document))
        retained, = document_measurements(document)
        self.assertEqual(self.receipt, retained)
        self.assertEqual(self.xyz, retained["position"])
        self.assertEqual(self.identity, retained["identity"])
        self.assertEqual((str(2**64-1), "131072", "bC"*32, self.timestamp, LOADED_UNIT_POSITION_QUALIFICATION),
                         tuple(retained[key] for key in ("subjectKey", "entityAddressDecimal", "sourceSha256",
                                                         "observedAtUtc", "qualification")))
        self.assertEqual(self.receipt, parse_projection_route(document)["recordingIdentity"]["pointMeasurements"][0])
        self.xyz["x"] = 0
        self.identity["unitKey"] = "999"
        self.assertNotEqual(self.xyz, self.receipt["position"])
        self.assertEqual("42", self.receipt["identity"]["unitKey"])

    def test_invalid_subject_entity_hash_qualification_and_source_are_refused(self):
        for field, bad in (("subjectKey", 42), ("subjectKey", "０１"), ("subjectKey", "01"), ("subjectKey", "0"),
                           ("subjectKey", str(2**64)), ("entityAddressDecimal", "065536"),
                           ("entityAddressDecimal", "65537"), ("entityAddressDecimal", str(0xfff8)),
                           ("entityAddressDecimal", str(0x800000000000)), ("entityAddressDecimal", 131072),
                           ("sourceSha256", "a"*63), ("sourceSha256", "z"*64), ("sourceSha256", None),
                           ("qualification", "current location"), ("targetKey", "123"), ("identity", {}),
                           ("observedAtUtc", "2026-11-12T17:01:02"), ("source", "")):
            with self.subTest(field=field, bad=bad):
                doc = deepcopy(self.document)
                doc["pointMeasurements"][0][field] = bad
                with self.assertRaises(ValueError):
                    parse_projection_route(doc)
                self.assertEqual([None], document_measurements(doc))

    def test_changed_xyz_or_other_player_in_mixed_route_is_refused(self):
        doc = deepcopy(self.document)
        doc["heights"][0] += .125
        with self.assertRaisesRegex(ValueError, "coordinate-mismatch"):
            parse_projection_route(doc)
        doc = deepcopy(self.document)
        second = measurement(self.xyz, dict(self.identity, unitKey="43"), "other.json", self.timestamp)
        doc["pointMeasurements"].append(second)
        doc["waypoints"] *= 2
        doc["heights"] *= 2
        with self.assertRaisesRegex(ValueError, "identity-mismatch"):
            parse_projection_route(doc)

    def test_foreign_fields_do_not_reclassify_existing_receipts_or_nested_names(self):
        target = measurement(self.xyz, self.identity, "target.json", self.timestamp,
                             kind="native-selected-target-position", target_key="44")
        target["nameCandidate"] = {"text": "Soldier", "sourceSha256": "d"*64}
        doc = dict(self.document, pointMeasurements=[target])
        self.assertEqual([target], document_measurements(doc))
        for field in ("subjectKey", "entityAddressDecimal", "sourceSha256"):
            with self.subTest(field=field):
                invalid = dict(self.document, pointMeasurements=[{**target, field: self.receipt[field]}])
                with self.assertRaisesRegex(ValueError, "kind-mismatch"):
                    parse_projection_route(invalid)


if __name__ == "__main__":
    unittest.main()
