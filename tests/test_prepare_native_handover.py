"""Offline checks for a guarded, versioned native-host ownership handover."""
from pathlib import Path
from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest

from scripts.nav_access_queue import APPLICATION_ID, SCHEMA_VERSION
from scripts.prepare_native_host_handover import (
    render_launcher, require_quarantined_authority,
)


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

    def test_quarantine_preflight_is_readonly_and_refuses_active_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.execute("CREATE TABLE resources (name TEXT,blocked INTEGER,holder TEXT,cleanup_receipt TEXT)")
                conn.execute("CREATE TABLE requests (state TEXT)")
                conn.execute(
                    "INSERT INTO resources VALUES ('vm:rift-lab-1',1,NULL,NULL)"
                )
                conn.commit()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            require_quarantined_authority(path, "vm:rift-lab-1")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("INSERT INTO requests VALUES ('active')")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "outstanding queue work"):
                require_quarantined_authority(path, "vm:rift-lab-1")
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("DELETE FROM requests")
                conn.execute("UPDATE resources SET blocked=0")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "not exclusively quarantined"):
                require_quarantined_authority(path, "vm:rift-lab-1")

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
