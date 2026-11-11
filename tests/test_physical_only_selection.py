"""Offline physical-only selection tests; no game input or VMware dependencies."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import physical_rift as physical

IDENTITY = {
    "hostName": "AMD-DESKTOP",
    "processId": 123,
    "hwnd": 456,
    "processStartUtcTicks": "638000000000000001",
    "executableSha256": "a" * 64,
}
REPORT_IDENTITY = {
    "processId": IDENTITY["processId"],
    "processStartUtcTicks": int(IDENTITY["processStartUtcTicks"]),
    "executableSha256": IDENTITY["executableSha256"],
}


class PhysicalOnlySelectionTests(unittest.TestCase):
    def setUp(self):
        # Offline synthetic selections target AMD-DESKTOP on every test runner.
        hostname = patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP")
        hostname.start()
        self.addCleanup(hostname.stop)

    def test_amd_desktop_auto_selects_local_process(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY) as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["workflow"], "physical")
        self.assertEqual(result["targetId"], "physical-amd-desktop")
        self.assertEqual(result["ownerHost"], "AMD-DESKTOP")
        self.assertEqual(result["target"], IDENTITY)
        reader.assert_called_once_with(None, require_window=False)

    def test_legion_auto_selects_its_own_process(self):
        legion = {**IDENTITY, "hostName": "LEGION"}
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical.observe_physical, "_identity", return_value=legion) as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["targetId"], "physical-legion")
        self.assertEqual(result["ownerHost"], "LEGION")
        reader.assert_called_once_with(None, require_window=False)

    def test_explicit_pid_stays_bound_to_local_process(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY) as reader:
            result = physical.select_physical(physical_pid=123)
        self.assertEqual(result["status"], "ready")
        reader.assert_called_once_with(123, require_window=False)

    def test_windowless_identity_is_usable_for_read_only_selection(self):
        # A valid process epoch must not require screenshot eligibility.
        identity = {**IDENTITY, "executablePath": r"C:\Games\RIFT\rift_x64.exe",
                    "hwnd": 0}
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_run",
                          return_value=(0, json.dumps(identity))):
            result = physical.select_physical(expected_host="AMD-DESKTOP",
                                              physical_pid=123)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["target"]["processId"], 123)
        self.assertEqual(result["target"]["processStartUtcTicks"],
                         "638000000000000001")
        self.assertEqual(result["target"]["executableSha256"], "a" * 64)
        self.assertEqual(result["target"]["hwnd"], 0)

    def test_wrong_expected_host_blocks_before_process_probe(self):
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical.observe_physical, "_identity") as reader:
            result = physical.select_physical(expected_host="AMD-DESKTOP")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "host-mismatch")
        reader.assert_not_called()

    def test_unsupported_host_blocks_before_process_probe(self):
        with patch.object(physical.socket, "gethostname", return_value="OTHER-PC"), \
             patch.object(physical.observe_physical, "_identity") as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "unsupported-host")
        reader.assert_not_called()

    def test_invalid_pid_blocks_before_process_probe(self):
        for pid in (True, 0, -1, 4294967296, "123"):
            with self.subTest(pid=pid), \
                 patch.object(physical.socket, "gethostname", return_value="LEGION"), \
                 patch.object(physical.observe_physical, "_identity") as reader:
                result = physical.select_physical(physical_pid=pid)
                self.assertEqual(result["reason"], "invalid-physical-pid")
                reader.assert_not_called()

    def test_missing_or_ambiguous_rift_fails_without_fallback(self):
        for failure in ("not-running", "ambiguous-process"):
            with self.subTest(failure=failure), \
                 patch.object(physical.socket, "gethostname", return_value="LEGION"), \
                 patch.object(physical.observe_physical, "_identity", side_effect=ValueError(failure)):
                result = physical.select_physical()
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], failure)
            self.assertEqual(result["workflow"], "physical")

    def test_cross_host_identity_and_pid_mismatch_are_blocked(self):
        for identity, kwargs, reason in (
            ({**IDENTITY, "hostName": "LEGION"}, {}, "identity-host-mismatch"),
            (IDENTITY, {"physical_pid": 999}, "physical-pid-mismatch"),
        ):
            with self.subTest(reason=reason), \
                 patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(physical.observe_physical, "_identity", return_value=identity):
                result = physical.select_physical(**kwargs)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], reason)

    def test_native_vitals_reads_only_selected_local_pid_and_epoch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "candidate.json"
            def fake_run(command, **kwargs):
                self.assertEqual(command[0], str(executable))
                self.assertEqual(command[1:6], ["sample-current-vitals", "--pid", "123",
                                                 "--start-ticks", IDENTITY["processStartUtcTicks"]])
                self.assertEqual(command[-2:], ["--output", str(destination)])
                self.assertFalse(kwargs.get("shell", False))
                destination.write_text(json.dumps({"status": "complete", "observation": {
                    "identity": REPORT_IDENTITY, "unitKey": 239816685251645959,
                    "health": {"status": "calculated-candidate", "current": 100, "maximum": 150},
                    "energy": {"status": "unavailable", "current": None, "maximum": None},
                    "mana": {"status": "unavailable", "current": None, "maximum": None}}}),
                    encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                                                   json.dumps({"status": "complete", "output": str(destination),
                                                               "recordType": "native-current-vitals-candidate-summary/2"}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "vitals", destination)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeRead"], "vitals")
        self.assertEqual(result["nativeValues"]["health"]["current"], 100)
        self.assertEqual(result["nativeValues"]["unitKey"], "239816685251645959")
        self.assertIn("candidate-only", result["qualification"])

    def test_native_actor_pose_projects_only_candidate_angles(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "pose.json"
            observed = {"identity": REPORT_IDENTITY, "playerKeyDecimal": "239816685251645959",
                        "actorHeadingQualified": False, "renderStatus": "normal-render-pointer-absent",
                        "actorMatrix": {"planarAngleDegreesCandidate": 111.5},
                        "modelMatrix": {"planarAngleDegreesCandidate": 0},
                        "renderMatrix": None, "completedAtUtc": "now"}

            def fake_run(command, **kwargs):
                self.assertEqual(command[1], "sample-current-actor-pose")
                destination.write_text(json.dumps({
                    "status": "complete", "identity": REPORT_IDENTITY,
                    "observation": observed}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": "native-current-actor-pose-summary/1",
                    "status": "complete", "output": str(destination)}), "")

            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "actor-pose", destination)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["playerKey"], "239816685251645959")
        self.assertEqual(result["nativeValues"]["actorPlanarDegreesCandidate"], 111.5)
        self.assertIsNone(result["nativeValues"]["renderPlanarDegreesCandidate"])
        self.assertIs(result["nativeValues"]["actorHeadingQualified"], False)

    def test_actor_pose_rejects_invalid_key_or_qualified_heading(self):
        observation = {"playerKeyDecimal": "239816685251645959",
                       "actorHeadingQualified": False, "renderStatus": "unavailable",
                       "actorMatrix": {"planarAngleDegreesCandidate": 111.5},
                       "modelMatrix": {"planarAngleDegreesCandidate": None},
                       "renderMatrix": None}
        for invalid in ({**observation, "playerKeyDecimal": "0"},
                        {**observation, "actorHeadingQualified": True},
                        {**observation, "actorMatrix": {"planarAngleDegreesCandidate": float("inf")}},
                        {**observation, "actorMatrix": {"planarAngleDegreesCandidate": 180.1}},
                        {**observation, "actorMatrix": {}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                physical._native_values("actor-pose", {"observation": invalid})

    def test_actor_pose_burst_projects_last_angle_and_sample_count(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "pose-burst.json"
            rows = [{"identity": REPORT_IDENTITY, "playerKeyDecimal": "239816685251645959",
                     "actorHeadingQualified": False, "renderStatus": "unavailable",
                     "actorMatrix": {"planarAngleDegreesCandidate": 110 + i},
                     "modelMatrix": {"planarAngleDegreesCandidate": 0},
                     "renderMatrix": None, "completedAtUtc": str(i)} for i in range(3)]

            def fake_run(command, **kwargs):
                self.assertEqual(command[-4:], ["--samples", "3", "--interval-ms", "0"])
                self.assertGreaterEqual(kwargs["timeout"], 30)
                destination.write_text(json.dumps({
                    "status": "complete", "identity": REPORT_IDENTITY,
                    "requestedSamples": 3, "completedSamples": 3,
                    "observation": rows[-1], "observations": rows}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": "native-current-actor-pose-summary/1",
                    "status": "complete", "output": str(destination)}), "")

            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "actor-pose", destination,
                                              samples=3, interval_ms=0)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["sampleCount"], 3)
        self.assertEqual(result["nativeValues"]["actorPlanarDegreesCandidate"], 112)
        self.assertEqual(result["nativeValues"]["playerKey"], "239816685251645959")
        self.assertIs(result["nativeValues"]["actorHeadingQualified"], False)
        self.assertEqual(result["nativeValues"]["planarAngleSeriesDegreesCandidate"],
                         {"actor": [110, 111, 112], "model": [0, 0, 0],
                          "render": [None, None, None]})
        self.assertEqual(result["nativeValues"]["planarSignedTravelDegreesCandidate"],
                         {"actor": 2, "model": 0, "render": None})
        self.assertEqual(result["nativeValues"]["actorMaxAdjacentStepDegreesCandidate"], 1)

    def test_actor_pose_angle_series_unwraps_crossing_180_but_never_qualifies_heading(self):
        angles = (170, 179, -179, -170)
        rows = [{"identity": REPORT_IDENTITY, "playerKeyDecimal": "239816685251645959",
                 "actorHeadingQualified": False, "renderStatus": "unavailable",
                 "actorMatrix": {"planarAngleDegreesCandidate": angle},
                 "modelMatrix": {"planarAngleDegreesCandidate": 0},
                 "renderMatrix": None} for angle in angles]
        report = {"status": "complete", "identity": REPORT_IDENTITY,
                  "requestedSamples": 4, "completedSamples": 4,
                  "observations": rows, "observation": rows[-1]}
        values = physical._native_values("actor-pose", report)
        self.assertEqual(values["planarAngleSeriesDegreesCandidate"]["actor"], list(angles))
        self.assertEqual(values["planarSignedTravelDegreesCandidate"]["actor"], 20)
        self.assertEqual(values["actorMaxAdjacentStepDegreesCandidate"], 9)
        self.assertIs(values["actorHeadingQualified"], False)
        self.assertEqual(physical._candidate_angle_steps([-170, -179, 179, 170]), [-9, -2, -9])
        self.assertIsNone(physical._candidate_angle_steps([0, 180]))
        self.assertIsNone(physical._candidate_angle_steps([0, None, 30]))

    def test_actor_pose_burst_rejects_missing_mixed_or_incomplete_series(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        base = {"identity": REPORT_IDENTITY, "playerKeyDecimal": "239816685251645959",
                "actorHeadingQualified": False, "renderStatus": "unavailable",
                "actorMatrix": {"planarAngleDegreesCandidate": 111.5},
                "modelMatrix": {"planarAngleDegreesCandidate": None},
                "renderMatrix": None}
        for name, changes in (
            ("missing-series", {"observations": None}),
            ("incomplete", {"completedSamples": 1}),
            ("mixed-player", {"observations": [base, {**base, "playerKeyDecimal": "2"}]}),
            ("mixed-epoch", {"observations": [base, {**base, "identity": {**REPORT_IDENTITY, "processStartUtcTicks": 1}}]}),
            ("qualified-intermediate", {"observations": [{**base, "actorHeadingQualified": True}, base]}),
            ("nonfinite-intermediate", {"observations": [{**base, "actorMatrix": {"planarAngleDegreesCandidate": float("nan")}}, base]}),
            ("missing-matrix-intermediate", {"observations": [{**base, "modelMatrix": None}, base]}),
            ("out-of-range-intermediate", {"observations": [{**base, "actorMatrix": {"planarAngleDegreesCandidate": -181}}, base]}),
            ("missing-angle-intermediate", {"observations": [{**base, "actorMatrix": {}}, base]}),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                executable = Path(temporary) / "RiftReader2.Live.exe"
                executable.write_bytes(b"MZ")
                destination = Path(temporary) / "invalid-pose.json"
                rows = changes.get("observations", [base, base])
                report = {"status": "complete", "identity": REPORT_IDENTITY,
                          "requestedSamples": 2, "completedSamples": 2,
                          "observation": rows[-1] if rows else base, "observations": rows}
                report.update(changes)
                def fake_run(command, **kwargs):
                    destination.write_text(json.dumps(report), encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "recordType": "native-current-actor-pose-summary/1",
                        "status": "complete", "output": str(destination)}), "")
                with patch.object(physical, "NATIVE_EXE", executable), \
                     patch.object(physical.subprocess, "run", side_effect=fake_run):
                    result = physical.read_native(selected, "actor-pose", destination,
                                                  samples=2, interval_ms=0)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "invalid-native-reader-report")

    def test_physical_actor_pose_transform_sources_opt_in_passes_native_flag(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        self.assertEqual(physical.read_native(selected, "position", include_transform_sources=True)["reason"],
                         "transform-sources-require-actor-pose")
        self.assertEqual(physical.read_native(selected, "actor-pose", include_transform_sources="true")["reason"],
                         "transform-sources-require-actor-pose")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "sources.json"
            base = {"identity": REPORT_IDENTITY, "playerKeyDecimal": "123",
                    "actorHeadingQualified": False, "renderStatus": "alternate-reference-branch-not-followed",
                    "actorMatrix": {"planarAngleDegreesCandidate": 12},
                    "modelMatrix": {"planarAngleDegreesCandidate": 0}, "renderMatrix": None}
            xyz = {"x": 1, "y": 2, "z": 3}
            sources = {"positionSecondaryXyz": xyz, "actorOffsetAt04F8": xyz,
                       "actorOffsetAt0770": xyz, "reconstructedActorWorldTranslation": xyz,
                       "actorWorldTranslationMaxAbsDelta": 0}
            def fake_run(command, **_):
                self.assertEqual(command[-2:], ["--include-transform-sources", "true"])
                destination.write_text(json.dumps({"status": "complete", "identity": REPORT_IDENTITY,
                                                   "observation": {**base, "translationSourcesCandidate": sources}}),
                                       encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": "native-current-actor-pose-summary/1", "status": "complete",
                    "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "actor-pose", destination,
                                              include_transform_sources=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["translationSourcesCandidate"], sources)

    def test_actor_pose_translation_sources_are_optional_validated_and_owner_scoped(self):
        base = {"playerKeyDecimal": "123", "actorHeadingQualified": False,
                "renderStatus": "alternate-reference-branch-not-followed",
                "actorMatrix": {"planarAngleDegreesCandidate": 42},
                "modelMatrix": {"planarAngleDegreesCandidate": 0},
                "renderMatrix": None}
        xyz = {"x": 11, "y": 20, "z": 33}
        sources = {"positionSecondaryXyz": xyz,
                   "actorOffsetAt04F8": {"x": 0, "y": 1.5, "z": 0},
                   "actorOffsetAt0770": {"x": 0, "y": .5, "z": 0},
                   "reconstructedActorWorldTranslation": {"x": 11, "y": 22, "z": 33},
                   "actorWorldTranslationMaxAbsDelta": 0}
        report = {"observation": {**base, "translationSourcesCandidate": sources}}
        values = physical._native_values("actor-pose", report, expect_translation_sources=True)
        self.assertEqual(values["translationSourcesCandidate"], sources)
        self.assertNotIn("translationSourcesCandidate",
                         physical._native_values("actor-pose", {"observation": base}))
        with self.assertRaisesRegex(ValueError, "missing-native-actor-translation-sources"):
            physical._native_values("actor-pose", {"observation": base},
                                    expect_translation_sources=True)
        for bad in ({**sources, "actorOffsetAt0770": {"x": 0, "y": float("nan"), "z": 0}},
                    {**sources, "positionSecondaryXyz": {"x": 1}},
                    {**sources, "actorWorldTranslationMaxAbsDelta": -1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                physical._native_values("actor-pose",
                                        {"observation": {**base, "translationSourcesCandidate": bad}})
        burst = {"observation": report["observation"],
                 "requestedSamples": 2, "completedSamples": 2,
                 "observations": [base, report["observation"]]}
        with self.assertRaisesRegex(ValueError, "missing-native-actor-translation-sources"):
            physical._native_values("actor-pose", burst, expect_translation_sources=True)

    def test_actor_pose_projects_optional_world_translation_candidates(self):
        base = {"playerKeyDecimal": "123", "actorHeadingQualified": False,
                "renderStatus": "normal-render-matrix-candidate",
                "actorMatrix": {"planarAngleDegreesCandidate": 42},
                "modelMatrix": {"planarAngleDegreesCandidate": 0},
                "renderMatrix": {"planarAngleDegreesCandidate": 42}}
        self.assertNotIn("actorWorldTranslationCandidate",
                         physical._native_values("actor-pose", {"observation": base}))
        xyz = {"x": 7444.156, "y": 863.5272, "z": 2965.9778}
        observation = {**base, "actorWorldTranslationCandidate": xyz,
                       "renderWorldTranslationCandidate": {**xyz, "y": 863.5872},
                       "renderWorldTranslationMaxAbsDeltaCandidate": 0.06}
        values = physical._native_values("actor-pose", {"observation": observation})
        self.assertEqual(values["actorWorldTranslationCandidate"], xyz)
        self.assertEqual(values["renderWorldTranslationCandidate"]["z"], xyz["z"])
        self.assertEqual(values["renderWorldTranslationMaxAbsDeltaCandidate"], 0.06)
        for wrong in (
            {**observation, "actorWorldTranslationCandidate": {**xyz, "x": float("nan")}},
            {**observation, "renderWorldTranslationCandidate": {"x": 1, "y": 2}},
            {**observation, "renderWorldTranslationMaxAbsDeltaCandidate": -1},
            {**observation, "renderWorldTranslationMaxAbsDeltaCandidate": float("inf")},
        ):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                physical._native_values("actor-pose", {"observation": wrong})

    def test_actor_pose_opt_in_position_brackets_project_owner_checked_xyz(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        key = "239816685251645959"
        rows = []
        for index in range(3):
            rows.append({
                "identity": REPORT_IDENTITY, "playerKeyDecimal": key,
                "actorHeadingQualified": False, "renderStatus": "unavailable",
                "actorMatrix": {"planarAngleDegreesCandidate": 110 + index},
                "modelMatrix": {"planarAngleDegreesCandidate": 0},
                "renderMatrix": None,
                "actorWorldTranslationCandidate": {
                    "x": 10 + index + (0.25 if index else 0), "y": 1.94, "z": 20},
                "positionBracketCandidate": {
                    "playerKeyDecimal": key, "elapsedMilliseconds": 7.5,
                    "before": {"x": 10 + index, "y": 2, "z": 20},
                    "after": {"x": 10 + index + (0.5 if index else 0), "y": 2, "z": 20}
                }})
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "pose-xyz.json"
            def fake_run(command, **kwargs):
                self.assertEqual(command[-2:], ["--include-position", "true"])
                destination.write_text(json.dumps({
                    "status": "complete", "identity": REPORT_IDENTITY,
                    "requestedSamples": 3, "completedSamples": 3,
                    "observation": rows[-1], "observations": rows}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": "native-current-actor-pose-summary/1",
                    "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "actor-pose", destination,
                                              samples=3, interval_ms=0,
                                              include_position=True)
        self.assertEqual(result["status"], "complete")
        values = result["nativeValues"]
        self.assertEqual(values["positionNetPlanarDisplacementCandidate"], 2.5)
        self.assertEqual(values["positionMaxWithinSamplePlanarChangeCandidate"], 0.5)
        self.assertEqual(values["positionObservedPlanarPathLengthCandidate"], 2.5)
        self.assertEqual(values["positionMaxAdjacentPlanarStepCandidate"], 1)
        self.assertEqual(len(values["positionBracketSeriesCandidate"]), 3)
        self.assertEqual(values["actorPositionPlanarResidualSeriesCandidate"], [0, 0, 0])
        self.assertEqual(values["actorPositionMaxPlanarResidualCandidate"], 0)
        for vertical in values["actorPositionVerticalOffsetSeriesCandidate"]:
            self.assertAlmostEqual(vertical, -0.06, places=6)
        self.assertEqual(values["planarSignedTravelDegreesCandidate"]["actor"], 2)
        self.assertFalse(values["actorHeadingQualified"])

    def test_actor_pose_bracket_fit_clamps_to_segment_and_rejects_bad_actor_values(self):
        base = {"playerKeyDecimal": "123", "actorHeadingQualified": False,
                "renderStatus": "alternate-reference-branch-not-followed",
                "actorMatrix": {"planarAngleDegreesCandidate": 42},
                "modelMatrix": {"planarAngleDegreesCandidate": 0},
                "renderMatrix": None,
                "positionBracketCandidate": {
                    "playerKeyDecimal": "123", "elapsedMilliseconds": 5,
                    "before": {"x": 0, "y": 2, "z": 0},
                    "after": {"x": 10, "y": 2, "z": 0}}}
        def fit(actor):
            row = {**base, "actorWorldTranslationCandidate": actor}
            return physical._native_values("actor-pose", {"observation": row},
                                           expect_position=True)
        aligned = fit({"x": 5, "y": 1.94, "z": 0})
        self.assertEqual(aligned["actorPositionMaxPlanarResidualCandidate"], 0)
        self.assertAlmostEqual(aligned["actorPositionVerticalOffsetSeriesCandidate"][0],
                               -0.06, places=6)
        self.assertEqual(fit({"x": 5, "y": 1.94, "z": 3})
                         ["actorPositionMaxPlanarResidualCandidate"], 3)
        self.assertEqual(fit({"x": 12, "y": 1.94, "z": 0})
                         ["actorPositionMaxPlanarResidualCandidate"], 2)
        self.assertIsNone(fit(None)["actorPositionMaxPlanarResidualCandidate"])
        for invalid in ({"x": 5, "y": float("nan"), "z": 0},
                        {"x": 5, "y": 0},
                        {"x": 1.7e308, "y": 0, "z": 1.7e308}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                fit(invalid)

    def test_actor_pose_out_and_back_motion_is_visible_despite_zero_net_displacement(self):
        key = "239816685251645959"
        rows = []
        for index, x in enumerate((0, 10, 0)):
            rows.append({
                "identity": REPORT_IDENTITY, "playerKeyDecimal": key,
                "actorHeadingQualified": False, "renderStatus": "unavailable",
                "actorMatrix": {"planarAngleDegreesCandidate": 12},
                "modelMatrix": {"planarAngleDegreesCandidate": 0},
                "renderMatrix": None,
                "positionBracketCandidate": {
                    "playerKeyDecimal": key, "elapsedMilliseconds": 5,
                    "before": {"x": x, "y": 1, "z": 2},
                    "after": {"x": x, "y": 1, "z": 2}
                }})
        values = physical._native_values("actor-pose", {
            "identity": REPORT_IDENTITY, "requestedSamples": 3,
            "completedSamples": 3, "observation": rows[-1], "observations": rows
        }, expect_position=True)
        self.assertEqual(values["positionNetPlanarDisplacementCandidate"], 0)
        self.assertEqual(values["positionMaxWithinSamplePlanarChangeCandidate"], 0)
        self.assertEqual(values["positionObservedPlanarPathLengthCandidate"], 20)
        self.assertEqual(values["positionMaxAdjacentPlanarStepCandidate"], 10)
        self.assertFalse(values["actorHeadingQualified"])

    def test_actor_pose_position_bracket_rejects_missing_mixed_or_nonfinite_source(self):
        key = "239816685251645959"
        base = {"identity": REPORT_IDENTITY, "playerKeyDecimal": key,
                "actorHeadingQualified": False, "renderStatus": "unavailable",
                "actorMatrix": {"planarAngleDegreesCandidate": 12},
                "modelMatrix": {"planarAngleDegreesCandidate": None},
                "renderMatrix": None}
        bracket = {"playerKeyDecimal": key, "elapsedMilliseconds": 8.0,
                   "before": {"x": 1, "y": 2, "z": 3},
                   "after": {"x": 1, "y": 2, "z": 3}}
        report = {"observation": {**base, "positionBracketCandidate": bracket}}
        self.assertEqual(
            physical._native_values("actor-pose", report, expect_position=True)
            ["positionNetPlanarDisplacementCandidate"], 0)
        for malformed in (
            {**base},
            {**base, "positionBracketCandidate": {**bracket, "playerKeyDecimal": "1"}},
            {**base, "positionBracketCandidate": {**bracket, "elapsedMilliseconds": -1}},
            {**base, "positionBracketCandidate": {**bracket, "after": {"x": float("nan"), "y": 2, "z": 3}}},
            {**base, "positionBracketCandidate": {**bracket, "before": {"x": 1, "y": 2}}},
            {**base, "positionBracketCandidate": {**bracket,
                "before": {"x": 1e308, "y": 2, "z": 3},
                "after": {"x": -1e308, "y": 2, "z": 3}}},
        ):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                physical._native_values("actor-pose", {"observation": malformed},
                                        expect_position=True)
        with self.assertRaises(ValueError):
            physical._native_values("actor-pose", report)

    def test_position_bracket_is_refused_for_other_native_kinds_without_launch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with patch.object(physical.subprocess, "run") as reader:
            for kind in ("vitals", "position", "stats"):
                with self.subTest(kind=kind):
                    result = physical.read_native(selected, kind, include_position=True)
                self.assertEqual(result["reason"], "position-bracket-requires-actor-pose")
            reader.assert_not_called()

    def test_vitals_burst_reports_last_hp_from_stable_player(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "vitals-burst.json"
            rows = [{
                "identity": REPORT_IDENTITY, "unitKey": 239816685251645959,
                "health": {"status": "calculated-candidate", "current": 100 + i, "maximum": 150},
                "energy": {"status": "unavailable"},
                "mana": {"status": "unavailable"},
                "completedAtUtc": str(i)} for i in range(3)]

            def fake_run(command, **kwargs):
                self.assertEqual(command[-4:], ["--samples", "3", "--interval-ms", "0"])
                destination.write_text(json.dumps({
                    "status": "complete", "identity": REPORT_IDENTITY,
                    "requestedSamples": 3, "completedSamples": 3,
                    "observation": rows[-1], "observations": rows}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-vitals-candidate-summary/2",
                                "status": "complete", "output": str(destination)}), "")

            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "vitals", destination,
                                              samples=3, interval_ms=0)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["sampleCount"], 3)
        self.assertEqual(result["nativeValues"]["health"]["current"], 102)
        self.assertEqual(result["nativeValues"]["unitKey"], "239816685251645959")

    def test_vitals_burst_rejects_mixed_player_samples(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "vitals-mixed.json"
            original = {"identity": REPORT_IDENTITY, "unitKey": 123,
                        "health": {"status": "calculated-candidate", "current": 100, "maximum": 150},
                        "energy": {"status": "unavailable"}, "mana": {"status": "unavailable"}}
            different = {**original, "unitKey": 124}
            def fake_run(command, **kwargs):
                destination.write_text(json.dumps({
                    "status": "complete", "identity": REPORT_IDENTITY,
                    "requestedSamples": 2, "completedSamples": 2,
                    "observation": different, "observations": [original, different]}),
                    encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-vitals-candidate-summary/2",
                                "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "vitals", destination,
                                              samples=2, interval_ms=0)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "invalid-native-reader-report")

    def test_native_read_rechecks_actual_pc_before_using_cached_selection(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with patch.object(physical.subprocess, "run") as reader:
            for current_host in ("LEGION", "OTHER-PC"):
                with self.subTest(current_host=current_host), \
                     patch.object(physical.socket, "gethostname", return_value=current_host):
                    result = physical.read_native(selected, "vitals")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "host-mismatch")
            reader.assert_not_called()

    def test_native_read_rejects_malformed_cached_target_without_launch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with patch.object(physical.subprocess, "run") as reader:
            for invalid_target in (None, [], {**IDENTITY, "hostName": 123}):
                with self.subTest(target=invalid_target):
                    result = physical.read_native({**selected, "target": invalid_target}, "vitals")
                    self.assertEqual(result["status"], "blocked")
                    self.assertEqual(result["reason"], "invalid-local-process-identity")
            reader.assert_not_called()

    def test_native_read_fails_closed_before_launch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "existing.json"
            destination.write_text("original", encoding="utf-8")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run") as runner:
                result = physical.read_native(selected, "vitals", destination)
                self.assertEqual(result["reason"], "native-output-exists")
                result = physical.read_native({**selected, "target": {**IDENTITY,
                                              "hostName": "LEGION"}}, "vitals")
                self.assertEqual(result["reason"], "invalid-local-process-identity")
                result = physical.read_native({**selected, "status": "blocked"}, "vitals")
                self.assertEqual(result["status"], "blocked")
                runner.assert_not_called()
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")

    def test_native_reader_failure_never_promotes_candidate(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", return_value=subprocess.CompletedProcess(
                     [], 2, "", "wrong-build")):
                result = physical.read_native(selected, "position", Path(temporary) / "new.json")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "native-reader-failed")
        self.assertEqual(result["exitCode"], 2)

    def test_position_stream_uses_final_summary_not_first_sample(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "position.json"
            def fake_run(command, **kwargs):
                self.assertEqual(command[-4:], ["--samples", "2", "--interval-ms", "0"])
                self.assertGreaterEqual(kwargs["timeout"], 30)
                destination.write_text(json.dumps({"status": "complete",
                    "identity": REPORT_IDENTITY, "requestedSamples": 2, "completedSamples": 2,
                    "observations": [{"unitKey": "239816685251645959",
                    "x": 1.0, "y": 2.0, "z": 3.0, "completedAtUtc": "earlier"},
                    {"unitKey": "239816685251645959", "x": 1.5,
                     "y": 2.5, "z": 3.5, "completedAtUtc": "now"}]}), encoding="utf-8")
                samples = [json.dumps({"recordType": "native-current-position-candidate/1",
                                       "observation": {"x": 1}})]
                samples.append(json.dumps({"recordType": "native-current-position-candidate-summary/1",
                                           "status": "complete", "output": str(destination)}))
                return subprocess.CompletedProcess(command, 0, "\n".join(samples) + "\n", "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "position", destination,
                                              samples=2, interval_ms=0)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeSummary"]["recordType"],
                         "native-current-position-candidate-summary/1")
        self.assertEqual(result["nativeValues"]["x"], 1.5)
        self.assertEqual(result["nativeValues"]["sampleCount"], 2)
        self.assertEqual(result["nativeValues"]["unitKey"], "239816685251645959")

    def test_position_burst_rejects_truncated_or_false_sample_counts(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        valid = {"unitKey": "239816685251645959", "x": 1.0, "y": 2.0, "z": 3.0}
        for requested, completed, rows in (
            (2, 1, [valid]),
            (1, 2, [valid, valid]),
            (2, 2, [valid]),
            (True, 2, [valid, valid]),
        ):
            with self.subTest(requested=requested, completed=completed, size=len(rows)), \
                 tempfile.TemporaryDirectory() as temporary:
                executable = Path(temporary) / "RiftReader2.Live.exe"
                executable.write_bytes(b"MZ")
                destination = Path(temporary) / "position.json"

                def fake_run(command, **kwargs):
                    destination.write_text(json.dumps({
                        "status": "complete", "identity": REPORT_IDENTITY,
                        "requestedSamples": requested, "completedSamples": completed,
                        "observations": rows}), encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "recordType": "native-current-position-candidate-summary/1",
                        "status": "complete", "output": str(destination)}), "")

                with patch.object(physical, "NATIVE_EXE", executable), \
                     patch.object(physical.subprocess, "run", side_effect=fake_run):
                    result = physical.read_native(selected, "position", destination,
                                                  samples=2, interval_ms=0)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "invalid-native-reader-report")

    def test_position_burst_rejects_mixed_or_invalid_player_samples(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        valid = {"unitKey": "239816685251645959", "x": 1.0, "y": 2.0, "z": 3.0}
        invalid_cases = (
            [valid, {**valid, "unitKey": "239816685251645960"}],
            [valid, {**valid, "unitKey": None}],
            [valid, {**valid, "unitKey": 239816685251645959}],
            [valid, {**valid, "unitKey": "18446744073709551616"}],
            [valid, {**valid, "x": float("nan")}],
            [valid, {**valid, "y": float("inf")}],
            [valid, {**valid, "z": True}],
            [valid, None],
        )
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "position.json"

            for samples in invalid_cases:
                with self.subTest(samples=samples):
                    def fake_run(command, **kwargs):
                        destination.write_text(json.dumps({
                            "status": "complete", "identity": REPORT_IDENTITY,
                            "observations": samples}), encoding="utf-8")
                        return subprocess.CompletedProcess(command, 0, json.dumps({
                            "recordType": "native-current-position-candidate-summary/1",
                            "status": "complete", "output": str(destination)}), "")

                    with patch.object(physical, "NATIVE_EXE", executable), \
                         patch.object(physical.subprocess, "run", side_effect=fake_run):
                        result = physical.read_native(selected, "position", destination,
                                                      samples=2, interval_ms=0)
                    self.assertEqual(result["status"], "blocked")
                    self.assertEqual(result["reason"], "invalid-native-reader-report")
                    destination.unlink()

    def test_position_burst_preserves_max_uint64_unit_key(self):
        self.assertEqual(physical._native_values("position", {"observations": [{
            "unitKey": "18446744073709551615", "x": 0.5, "y": 1.5, "z": 2.5}]}),
            {"sampleCount": 1, "unitKey": "18446744073709551615",
             "x": 0.5, "y": 1.5, "z": 2.5, "sampledAtUtc": None,
             "refreshGuardStatus": None})

    def test_native_report_rejects_wrong_type_or_process_epoch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "candidate.json"
            def wrong_type(command, **kwargs):
                destination.write_text(json.dumps({"status": "complete", "identity": REPORT_IDENTITY}),
                                       encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-stats-summary/1",
                                "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=wrong_type):
                result = physical.read_native(selected, "position", destination)
            self.assertEqual(result["reason"], "invalid-native-reader-receipt")
            destination.unlink()
            def wrong_epoch(command, **kwargs):
                destination.write_text(json.dumps({"status": "complete", "observation": {
                    "identity": {**REPORT_IDENTITY, "processStartUtcTicks": 1},
                    "unitKey": 123, "health": {"status": "unavailable"},
                    "energy": {"status": "unavailable"}, "mana": {"status": "unavailable"}}}),
                    encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-vitals-candidate-summary/2",
                                "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=wrong_epoch):
                result = physical.read_native(selected, "vitals", destination)
            self.assertEqual(result["reason"], "invalid-native-reader-report")

    def test_position_burst_options_are_bounded_without_launch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with patch.object(physical.subprocess, "run") as runner:
            for kind, samples, interval, expected in (
                ("orientation", 3, None, "sampling-options-require-position-vitals-or-actor-pose"),
                ("position", 0, None, "invalid-position-sampling"),
                ("position", 31, None, "invalid-position-sampling"),
                ("position", None, 2001, "invalid-position-sampling"),
                ("position", True, None, "invalid-position-sampling"),
            ):
                with self.subTest(kind=kind, samples=samples, interval=interval):
                    result = physical.read_native(selected, kind,
                                                  samples=samples, interval_ms=interval)
                    self.assertEqual(result["reason"], expected)
            runner.assert_not_called()

    def test_native_read_requires_explicit_host_before_process_probe(self):
        with patch.object(physical, "select_physical") as selector, \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main(["--read-native", "vitals"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["reason"],
                         "native-read-requires-expected-host")
        selector.assert_not_called()

    def test_native_read_cli_keeps_json_receipt(self):
        with patch.object(physical, "select_physical", return_value={"status": "ready"}), \
             patch.object(physical, "read_native", return_value={"status": "complete", "nativeRead": "stats"}) as reader, \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main(["--expected-host", "AMD-DESKTOP", "--read-native", "stats"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["nativeRead"], "stats")
        reader.assert_called_once_with({"status": "ready"}, "stats", None,
                                       samples=None, interval_ms=None, include_position=False,
                                        include_transform_sources=False)

    def test_cli_default_is_current_physical_host_and_json(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY), \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["targetId"], "physical-amd-desktop")


if __name__ == "__main__":
    unittest.main()
