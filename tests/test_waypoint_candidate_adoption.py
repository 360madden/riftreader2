import copy
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.waypoint_candidate_adoption import (_compare_candidate, _adoption_digest, validate_adopted_route,
    _full_native_route, corroborate_reverse)
from tests.test_waypoint_navigation_candidate import sample, sign

CTX = {"version": 1, "zoneIdCandidate": "z1234567800000000", "rawZoneKey": 0x12345678,
       "source": "native-zone-receipt", "observedAtUtc": "2026-11-14T00:00:00Z",
       "playerKey": "player", "target": {"hostName": "AMD-DESKTOP", "executableSha256": "a" * 64}}


def native():
    return {"waypoints": [["start", 0, 2], ["stop", 1, 2], ["end", 2, 2]],
            "heights": [1, 1, 1], "pointKinds": ["pass", "pass", "pass"],
            "routeContext": copy.deepcopy(CTX), "recording": {"version": 1, "complete": True,
             "identity": {"runtimeIdentity": {"machine": "AMD-DESKTOP", "gameBuildSha256": "a"*64,
                                               "unitKey": "player"}}, "sources": ["physical-native-report"]}}


def run(c=None, n=None, context=None, direction="forward"):
    return _compare_candidate(c or sample(), n or native(), context or CTX, candidate_start=0,
                           candidate_end=1, native_start=0, native_end=2, direction=direction)


class AdoptionTests(unittest.TestCase):
    def test_different_vertex_densities_and_reverse_preserve_stops(self):
        result = run()
        self.assertEqual(["pass", "pass"], result["pointKinds"])
        self.assertEqual("scoped correspondence only; no global transform, clearance or live authority",
                         result["candidateAdoption"]["qualification"])
        with self.assertRaisesRegex(ValueError, "independent-evidence"):
            run(direction="reverse")

    def test_stop_inserted_and_preserved(self):
        n = native()
        n["pointKinds"][1] = "stop"
        result = run(n=n)
        self.assertEqual(["pass", "stop", "pass"], result["pointKinds"])
        self.assertEqual(["stop", 1, 2], result["waypoints"][1])

    def test_execution_gate_context_owner_direction_and_integrity(self):
        result = run()
        result["candidateAdoption"]["integritySha256"] = _adoption_digest(result)
        identity = result["candidateAdoption"]["owner"]
        validate_adopted_route(result, identity, CTX, "forward")
        gui_roundtrip = copy.deepcopy(result)
        gui_roundtrip.pop("pointKinds")
        gui_roundtrip["waypoints"] = [[name, round(x, 6), round(z, 6)] for name, x, z in gui_roundtrip["waypoints"]]
        validate_adopted_route(gui_roundtrip, identity, CTX, "forward")
        with self.assertRaisesRegex(ValueError, "direction"):
            validate_adopted_route(result, identity, CTX, "reverse")
        with self.assertRaisesRegex(ValueError, "owner"):
            validate_adopted_route(result, {**identity, "unitKey": "other"}, CTX, "forward")
        with self.assertRaisesRegex(ValueError, "context"):
            validate_adopted_route(result, identity, None, "forward")
        result["waypoints"][0][1] += 1
        with self.assertRaisesRegex(ValueError, "integrity"):
            validate_adopted_route(result, identity, CTX, "forward")
        validate_adopted_route(native(), identity, None, "forward")

    def test_reverse_requires_corresponding_return_and_refuses_reseal(self):
        route = run()
        route["candidateAdoption"]["integritySha256"] = _adoption_digest(route)
        c = sample()
        c["points"].reverse()
        c["query"] = {"requestedStartXYZ": [2, 1, 2], "snappedStartXYZ": [2, 1, 2],
                      "requestedGoalXYZ": [0, 1, 2], "snappedGoalXYZ": [0, 1, 2]}
        sign(c)
        n = native()
        for key in ("waypoints", "heights", "pointKinds"):
            n[key].reverse()
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "receipt.json"
            receipt.write_text("{}")
            with patch("scripts.waypoint_candidate_adoption._full_native_route", return_value=n):
                bidirectional = corroborate_reverse(route, c, [receipt], receipt, candidate_start=0,
                                                   candidate_end=1, native_start=0, native_end=2)
                validate_adopted_route(bidirectional, route["candidateAdoption"]["owner"], CTX, "reverse")
                route["waypoints"][0][1] += 1
                with self.assertRaisesRegex(ValueError, "integrity"):
                    corroborate_reverse(route, c, [receipt], receipt, candidate_start=0,
                                        candidate_end=1, native_start=0, native_end=2)

    def test_sparse_receipt_cannot_bridge_unknown_distance(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt, zone = Path(folder) / "receipt.json", Path(folder) / "zone.json"
            receipt.write_text(json.dumps({"status": "arrived", "inputSent": True,
                "releaseSucceeded": True, "desktopInputsDown": [], "path": [
                    {"x": 0, "y": 1, "z": 2, "bearing": 0, "observedAtUtc": "2026-11-14T00:00:00Z"},
                    {"x": 10, "y": 1, "z": 2, "bearing": 0, "observedAtUtc": "2026-11-14T00:00:01Z"}]}))
            zone.write_text("{}")
            with patch("scripts.export_continuous_route.export_route", return_value=native()):
                with self.assertRaisesRegex(ValueError, "discontinuity"):
                    _full_native_route([receipt], zone)

    def test_bend_and_other_floor_rejected(self):
        for axis, value in (("heights", 3), ("waypoints", 3)):
            n = native()
            if axis == "heights": n[axis][1] = value
            else: n[axis][1][2] = value
            with self.subTest(axis=axis), self.assertRaisesRegex(ValueError, "outside-bound"):
                run(n=n)

    def test_context_owner_and_partial_fail_closed(self):
        n = native()
        n["routeContext"]["playerKey"] = "someone-else"
        with self.assertRaisesRegex(ValueError, "owner-mismatch"): run(n=n)
        n = native()
        del n["routeContext"]
        with self.assertRaisesRegex(ValueError, "matching-zone"): run(n=n)
        c = sample(); c["status"] = "partial"; sign(c)
        with self.assertRaisesRegex(ValueError, "complete-candidate"): run(c=c)

    def test_unbounded_snap_and_unknown_transform_fail(self):
        c = sample(); c["query"]["snappedGoalXYZ"] = [3, 1, 2]; sign(c)
        with self.assertRaisesRegex(ValueError, "snap-outside"): run(c=c)
        c = sample(); c["coordinates"]["transformToRr2Native"]["kind"] = "unknown"; sign(c)
        with self.assertRaisesRegex(ValueError, "identity-frame"): run(c=c)


if __name__ == "__main__": unittest.main()
