"""Offline checks for a guarded, versioned native-host ownership handover."""
from pathlib import Path
import unittest

from scripts.prepare_native_host_handover import render_launcher


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "artifacts" / "update-recovery-20261023-01" / "run-coordinated-host-v7.py"


class PrepareHandoverTests(unittest.TestCase):
    @unittest.skipUnless(TEMPLATE.is_file(), "old launch receipt/template not available")
    def test_versioned_launcher_preserves_original_and_changes_only_outputs(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        output = render_launcher(source, "v7", "v8")
        self.assertEqual(
            output.replace("coordinated-host-v8", "coordinated-host-v7")
                  .replace("coordinated-host-plan-v8", "coordinated-host-plan-v7"),
            source,
        )
        self.assertIn('assert VmEpochGuard(HostConfig.load(config)).collect() == plan["vmIdentity"]', output)
        self.assertIn("reconcile-existing", output)
        self.assertIn("expectedWindowsSession", output)
        self.assertNotIn("coordinated-host-v7", output)
        self.assertNotIn("coordinated-host-plan-v7", output)

    def test_rejects_unexpected_launch_template(self):
        with self.assertRaisesRegex(ValueError, "unexpected launcher template"):
            render_launcher("something unrelated", "v7", "v8")

    def test_rejects_unsafe_versions(self):
        for prior, next_version in (
            ("v7", "v7"), ("7", "v8"), ("v7", "../v8"), ("v7", "v0")
        ):
            with self.subTest(prior=prior, next_version=next_version):
                with self.assertRaises(ValueError):
                    render_launcher("not important", prior, next_version)


if __name__ == "__main__":
    unittest.main()
