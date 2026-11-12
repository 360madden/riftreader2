"""Retained-source admission only; no processes, capture, selection or route writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import physical_rift as physical
from scripts.saved_nearby_waypoints import load_saved_nearby_waypoints
from scripts.waypoint_measurements import document_measurements, parse_projection_route
from tests.test_physical_only_selection import IDENTITY
from tests.test_physical_unit_positions import report as positions_report, bits
from tests.test_physical_unit_names import report as names_report


class SavedNearbyWaypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = positions_report()
        self.native = self.root / "positions.json"
        self.native.write_text(json.dumps(self.raw))
        self.wrapper = dict(status="complete", workflow="physical", nativeRead="unit-positions",
            ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY), nativeOutput=str(self.native),
            nativeSourceSha256=hashlib.sha256(self.native.read_bytes()).hexdigest())
        self.path = self.root / "sample.json"
        self.path.write_text(json.dumps(self.wrapper))
        self.current = dict(machine="AMD-DESKTOP", gameBuildSha256=IDENTITY["executableSha256"],
                            unitKey="42", processId=999, processStartUtcTicks="638999999999999999")

    def names(self, text="3rd Guard Soldier", *, wrong_entity=False):
        row = self.raw["observation"]["rows"][1]
        raw = names_report(keys=[row["unitKey"]])
        raw["observation"]["rows"][0].update(entityAddressDecimal=row["entityAddressDecimal"], fallbackText=text)
        if wrong_entity:
            raw["observation"]["rows"][0]["entityAddressDecimal"] = str(int(row["entityAddressDecimal"]) + 8)
        native = self.root / "names.json"
        native.write_text(json.dumps(raw))
        digest = hashlib.sha256(native.read_bytes()).hexdigest()
        wrapper = dict(status="complete", workflow="physical", nativeRead="unit-names", ownerHost="AMD-DESKTOP",
            target=deepcopy(IDENTITY), nativeOutput=str(native), nativeSourceSha256=digest,
            nativeValues=physical._native_values("unit-names", raw))
        path = self.root / "names-wrapper.json"
        path.write_text(json.dumps(wrapper))
        self.wrapper["nameSample"] = dict(status="saved", path=str(path), source=str(native), sha256=digest)
        self.path.write_text(json.dumps(self.wrapper))
        return raw, native

    def test_static_waypoint_preserves_original_epoch_owner_key_time_and_roundtrip(self):
        original = self.native.read_bytes()
        rows = load_saved_nearby_waypoints(self.path, dict(runtimeIdentity=self.current))
        self.assertEqual(len(rows), 1)
        point = rows[0]
        self.assertEqual(point["number"], 1)
        self.assertEqual(point["unitKey"], "18446744073709551615")
        self.assertEqual(point["label"], "Loaded unit 551615")
        receipt = point["measurement"]
        self.assertEqual(receipt["identity"]["processId"], IDENTITY["processId"])
        self.assertEqual(receipt["identity"]["processStartUtcTicks"], IDENTITY["processStartUtcTicks"])
        self.assertEqual(receipt["sourceSha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(point["observedAtUtc"], self.raw["observation"]["rows"][1]["completedAtUtc"])
        self.assertEqual(point["distance"], 5.)
        document = dict(waypoints=[[point["label"], point["position"]["x"], point["position"]["z"]]],
                        heights=[point["position"]["y"]], pointMeasurements=[receipt])
        self.assertEqual(parse_projection_route(document)["points"][0]["xyz"], point["position"])
        self.assertEqual(document_measurements(document), [receipt])
        self.assertNotIn("recording", document)
        self.assertNotIn("targetKey", receipt)
        point["position"]["x"] = 0
        self.assertEqual(receipt["position"]["x"], 7430)
        self.assertEqual(self.native.read_bytes(), original)

    def test_independent_name_metadata_is_preserved_and_label_bounded(self):
        name_raw, _ = self.names("Guard " + "A" * 95)
        point = load_saved_nearby_waypoints(self.path, self.current)[0]
        self.assertEqual(len(point["label"]), 80)
        name = point["measurement"]["nameCandidate"]
        self.assertEqual(name["baseNameCandidate"], "Guard " + "A" * 95)
        self.assertEqual(name["unitKey"], point["unitKey"])
        self.assertEqual(name["observerKey"], "42")
        self.assertEqual(name["sampledAtUtc"], name_raw["observation"]["rows"][0]["completedAtUtc"])
        self.assertNotEqual(name["sampledAtUtc"], point["observedAtUtc"])
        self.assertEqual(len(name["sourceSha256"]), 64)

    def test_unavailable_or_bad_optional_names_keep_fixed_generic_position(self):
        for fault in ("absent", "entity", "hash"):
            with self.subTest(fault=fault):
                if fault != "absent":
                    _, source = self.names(wrong_entity=fault == "entity")
                    if fault == "hash": source.write_bytes(source.read_bytes() + b" ")
                point = load_saved_nearby_waypoints(self.path, self.current)[0]
                self.assertEqual(point["label"], "Loaded unit 551615")
                self.assertNotIn("nameCandidate", point["measurement"])

    def test_observer_host_build_player_mismatch_refuses(self):
        for field, value in (("machine", "OTHER"), ("gameBuildSha256", "b" * 64), ("unitKey", "43")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_saved_nearby_waypoints(self.path, dict(self.current, **{field: value}))

    def test_position_source_hash_owner_and_key_tamper_refuse(self):
        original = self.native.read_bytes()
        for fault in ("hash", "owner", "key"):
            raw = deepcopy(self.raw)
            if fault == "owner": raw["observation"]["rows"][1]["entityAddressDecimal"] = "123"
            if fault == "key": raw["observation"]["rows"][1]["unitKey"] = "42"
            self.native.write_bytes(original + b" " if fault == "hash" else json.dumps(raw).encode())
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                load_saved_nearby_waypoints(self.path, self.current)
        with self.assertRaises(ValueError):
            load_saved_nearby_waypoints(self.root / "absent.json", self.current)

    def test_empty_nearby_subset_returns_empty_without_writing_a_route(self):
        unit = self.raw["observation"]["rows"][1]
        unit.update(positionCandidate=dict(x=7467, y=871, z=2946), horizontalDistanceCandidate=40)
        unit["rawBits"] = bits(unit["positionCandidate"])
        self.native.write_text(json.dumps(self.raw))
        self.wrapper["nativeSourceSha256"] = hashlib.sha256(self.native.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(self.wrapper))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(load_saved_nearby_waypoints(self.path, self.current), [])
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
