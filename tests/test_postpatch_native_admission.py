"""Offline admission checks for physical RIFT build 1179 native reads.

No game process, window, controller, or real native reader is contacted.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_rift


BUILD_1179 = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
HISTORICAL_BUILD = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


def selection(sha=BUILD_1179):
    return {
        "status": "ready",
        "ownerHost": "AMD-DESKTOP",
        "target": {
            "hostName": "AMD-DESKTOP",
            "processId": 12345,
            "processStartUtcTicks": "638000000000000001",
            "executableSha256": sha,
        },
    }


class PostpatchNativeAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        executable = self.folder / "offline-native-reader.exe"
        executable.write_bytes(b"MZ")
        for obj, name, value in (
            (physical_rift, "NATIVE_EXE", executable),
            (physical_rift.socket, "gethostname", lambda: "AMD-DESKTOP"),
        ):
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_unqualified_fields_are_refused_before_native_launch(self):
        # Old-build research is not an implicit qualification for build 1179.
        for kind in (
            "smoothed-scalar",
            "selected-target", "zone-context",
            "target-name", "unit-names",
        ):
            with self.subTest(kind=kind), patch.object(physical_rift.subprocess, "run") as run:
                result = physical_rift.read_native(
                    selection(), kind, self.folder / (kind + ".json"),
                    unit_keys=["1"] if kind == "unit-names" else None,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "postpatch-native-read-unqualified")
                run.assert_not_called()

    def test_target_projection_is_not_admitted_by_facing_requalification(self):
        with patch.object(physical_rift.subprocess, "run") as run:
            result = physical_rift.read_native(
                selection(), "facing", self.folder / "target.json", include_target=True,
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "postpatch-target-projection-unqualified")
            run.assert_not_called()

    def test_admitted_kinds_pass_the_exact_sha_to_native_reader(self):
        # A synthetic nonzero native exit proves command assembly, not live semantics.
        for kind in ("position", "facing", "actor-pose", "orientation", "unit-positions", "selected-position", "vitals", "player-context", "stats"):
            with self.subTest(kind=kind), patch.object(
                physical_rift.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 3, "", "offline-refusal"),
            ) as run:
                result = physical_rift.read_native(
                    selection(BUILD_1179.lower()), kind, self.folder / (kind + ".json"),
                )
                self.assertEqual(result["reason"], "native-reader-failed")
                args = run.call_args.args[0]
                self.assertEqual(args[1], physical_rift.NATIVE_READS[kind])
                self.assertEqual(args[2:6], [
                    "--pid", "12345", "--start-ticks", "638000000000000001",
                ])
                self.assertEqual(args.count("--sha256"), 1)
                self.assertEqual(args[args.index("--sha256") + 1], BUILD_1179)

    def test_historical_build_does_not_inherit_new_build_admission(self):
        # Historical invocation may still be attempted, but is independently
        # subject to the native reader's own exact-build checks.
        with patch.object(
            physical_rift.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 3, "", "offline-refusal"),
        ) as run:
            result = physical_rift.read_native(
                selection(HISTORICAL_BUILD), "vitals", self.folder / "historical.json",
            )
            self.assertEqual(result["reason"], "native-reader-failed")
            self.assertNotIn("--sha256", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
