import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.waypoint_navigation_candidate import (MAX_CANDIDATE_BYTES, MAX_POINTS,
                                                   inspect_candidate, read_candidate)


def sign(c):
    keys = ("schema", "patchId", "status", "world", "coordinates", "query", "points", "planner", "evidence")
    identity = {k: c[k] for k in keys}
    identity["plannerResult"] = c.get("plannerResult")
    c["candidateId"] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return c


def sample():
    return sign({"schema": "riftworld.candidate-path/1", "patchId": "a" * 64,
        "status": "complete", "world": {"sourceWorld": "world", "authority": "source-map-name", "liveInstance": "unresolved"},
        "coordinates": {"frameId": "rift-source-xyz", "axisOrder": ["x", "y", "z"], "upAxis": "y", "units": "source-world-unit", "transformToRr2Native": {"kind": "identity", "qualification": "landmark-reprojection-candidate"}},
        "query": {"requestedStartXYZ": [0, 1, 2], "requestedGoalXYZ": [2, 1, 2], "snappedStartXYZ": [0, 1, 2], "snappedGoalXYZ": [2, 1, 2]},
        "points": [{"id": "0", "xyz": [0, 1, 2], "flags": 1}, {"id": "1", "xyz": [2, 1, 2], "flags": 2}],
        "planner": {"buildId": "B" * 64, "profile": {"cell_size": .25, "cell_height": .125, "agent_height": 1.8, "agent_radius": .5, "agent_max_climb": .5, "agent_max_slope": 45, "region_min_size": 4}},
        "evidence": {"geometry": "render-mesh-approximation", "walkability": "estimated", "traversal": "unverified", "sourceRequestCoverage": {"navigationEligible": True}}, "sourceRefs": {"navigationBuild": "retained"}})


def cast_evidence(c):
    return {"schema": "riftworld.finite-route-casts/1", "obj": {"sha256": "A" * 64},
            "settings": {"heightsAbovePath": [1], "lateralOffsets": [0], "twoSidedTriangles": True},
            "routes": [{"candidateId": c["candidateId"], "patchId": c["patchId"], "candidateStatus": c["status"],
                        "sha256": "B" * 64, "segments": [{"segment": 0, "casts": [{"castId": 0, "heightAbovePath": 1, "lateralOffset": 0}]}]}],
            "casts": [{"startXYZ": [0, 2, 2], "endXYZ": [2, 2, 2], "hits": [], "clearAtSampledLines": True}]}


class CandidateTests(unittest.TestCase):
    def test_preserves_context_and_never_authorizes(self):
        c = sample()
        result = inspect_candidate(c)
        self.assertEqual(result["candidate"], c)
        self.assertFalse(result["executionEligible"])
        self.assertFalse(result["autoRejoinAvailable"])
        self.assertFalse(result["inputSent"])
        self.assertEqual(result["segmentClearance"], "unknown")
        self.assertTrue(any("transform" in b for b in result["executionBlockers"]))
        result["candidate"]["points"].clear()
        self.assertTrue(c["points"])

    def test_partial_and_unknown_transform_stay_review_only(self):
        c = sample()
        c["status"] = "partial"
        c["coordinates"]["transformToRr2Native"] = {"kind": "unknown", "qualification": "unqualified"}
        result = inspect_candidate(sign(c))
        self.assertFalse(result["executionEligible"])
        self.assertTrue(any("partial" in b for b in result["executionBlockers"]))

    def test_tamper_and_malformed_are_rejected(self):
        c = sample()
        c["points"][0]["xyz"][0] = 9
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            inspect_candidate(c)
        c = sample()
        c["planner"]["profile"]["agent_radius"] = -1
        with self.assertRaisesRegex(ValueError, "profile"):
            inspect_candidate(sign(c))
        c = sample()
        c["patchId"] = "unknown"
        with self.assertRaisesRegex(ValueError, "patch identity"):
            inspect_candidate(sign(c))

    def test_planner_disagreement_rejected_even_when_resigned(self):
        c = sample()
        c["plannerResult"] = {"waypoints": [{"pos": [0, 1, 2], "flags": 1}], "status": "complete", "cacheKey": c["planner"]["buildId"], **c["query"]}
        with self.assertRaisesRegex(ValueError, "disagrees"):
            inspect_candidate(sign(c))

    def test_cli_refuses_missing_file(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "waypoint_navigation_candidate.py"
        run = subprocess.run([sys.executable, str(script), "inspect", "missing-candidate.json"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertFalse(json.loads(run.stderr)["executionEligible"])

    def test_bounded_json_read_rejects_duplicates_nonfinite_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            for payload in (b'{"a":1,"a":2}', b'{"a":{"x":1,"x":2}}',
                            b'{"x":NaN}', b'{"x":Infinity}'):
                path.write_bytes(payload)
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    read_candidate(path)
            path.write_bytes(b" " * (MAX_CANDIDATE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                read_candidate(path)

    def test_limits_and_nonfinite_rejected_before_review(self):
        c = sample()
        c["points"] = [c["points"][0]] * (MAX_POINTS + 1)
        with self.assertRaisesRegex(ValueError, "points"):
            inspect_candidate(c)
        for value in (True, float("inf"), 10 ** 400):
            c = sample()
            c["points"][0]["xyz"][0] = value
            if value is not True and value != float("inf"):
                sign(c)
            elif value is True:
                sign(c)
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                inspect_candidate(c)
        c = sample()
        c["sourceRefs"]["anything"] = float("inf")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            inspect_candidate(c)

    def test_source_references_are_data_only(self):
        c = sample()
        c["sourceRefs"] = {"navigationBuild": "Z:/definitely-missing/not-a-command"}
        self.assertEqual(inspect_candidate(c)["candidate"]["sourceRefs"], c["sourceRefs"])

    def test_attach_sampled_evidence_and_keep_qualifications(self):
        c = sample()
        result = inspect_candidate(c, casts=cast_evidence(c), candidate_sha256="B" * 64)
        evidence = result["clearanceEvidence"]
        self.assertEqual(evidence["candidateFileHashStatus"], "matched")
        self.assertEqual(evidence["sourceIdentityStatus"], "reported-only")
        self.assertEqual(evidence["segments"][0]["state"], "clear-at-sampled-lines")
        self.assertEqual(evidence["usableWidth"], "unknown")
        self.assertEqual(evidence["navmeshWalkability"], "estimated")
        self.assertEqual(evidence["liveTraversal"], "unverified")
        self.assertFalse(result["executionEligible"])

    def test_mismatched_and_incomplete_evidence_refused(self):
        c = sample()
        for mutation in ("candidate", "coordinates", "duplicate", "missing", "geometry", "hash"):
            d = cast_evidence(c)
            kwargs = {"candidate_sha256": "B" * 64}
            if mutation == "candidate":
                d["routes"][0]["candidateId"] = "f" * 64
            elif mutation == "coordinates":
                d["casts"][0]["endXYZ"][0] = 3
            elif mutation == "duplicate":
                d["routes"].append(copy.deepcopy(d["routes"][0]))
            elif mutation == "missing":
                d["routes"][0]["segments"][0]["casts"] = []
            elif mutation == "geometry":
                kwargs["geometry_sha256"] = "C" * 64
            else:
                kwargs["candidate_sha256"] = "C" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                inspect_candidate(c, casts=d, **kwargs)

    def test_cast_dimensions_are_bounded_before_expansion(self):
        c = sample()
        d = cast_evidence(c)
        d["settings"]["heightsAbovePath"] = [1] * 129
        with self.assertRaisesRegex(ValueError, "settings exceed"):
            inspect_candidate(c, casts=d)
        d = cast_evidence(c)
        d["settings"]["lateralOffsets"] = [0, 0, 0]
        self.assertEqual(inspect_candidate(c, casts=d)["clearanceEvidence"]["segments"][0]["state"], "clear-at-sampled-lines")

    def test_hits_and_zero_length_remain_distinct(self):
        c = sample()
        d = cast_evidence(c)
        d["casts"][0].update({"clearAtSampledLines": False, "hits": [{"group": "wall", "objTriangleIndex": 3, "segmentFraction": .5, "pointXYZ": [1, 2, 2]}]})
        e = inspect_candidate(c, casts=d)["clearanceEvidence"]
        self.assertEqual(e["segments"][0]["state"], "hits-at-sampled-lines")
        c["points"][1]["xyz"] = c["points"][0]["xyz"][:]
        sign(c)
        d = cast_evidence(c)
        d["routes"][0]["segments"][0] = {"segment": 0, "casts": [], "assessment": "not-assessed-zero-length-segment"}
        self.assertEqual(inspect_candidate(c, casts=d)["clearanceEvidence"]["segments"][0]["state"], "not-assessed-zero-length")


if __name__ == "__main__":
    unittest.main()
