"""Offline checks for a guarded, versioned native-host ownership handover."""
from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import unittest

from scripts.nav_access_queue import APPLICATION_ID, SCHEMA_VERSION
from scripts.prepare_native_host_handover import (
    render_launcher, require_epoch_relation, require_idle_authority,
    require_quarantined_authority, successor_plan,
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

    def test_same_epoch_preflight_needs_free_cleaned_queue_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.execute("CREATE TABLE resources (name TEXT,blocked INTEGER,holder TEXT,cleanup_receipt TEXT)")
                conn.execute("CREATE TABLE requests (state TEXT)")
                conn.execute(
                    "INSERT INTO resources VALUES ('vm:rift-lab-1',0,NULL,'verified-cleanup')"
                )
                conn.commit()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            require_idle_authority(path, "vm:rift-lab-1")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("UPDATE resources SET holder='other-owner'")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "free and unheld"):
                require_idle_authority(path, "vm:rift-lab-1")
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("UPDATE resources SET holder=NULL,cleanup_receipt=NULL")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "cleanup receipt"):
                require_idle_authority(path, "vm:rift-lab-1")
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("UPDATE resources SET blocked=1,cleanup_receipt='old-receipt'")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "free and unheld"):
                require_idle_authority(path, "vm:rift-lab-1")
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("UPDATE resources SET blocked=0")
                conn.execute("INSERT INTO requests VALUES ('cleanup')")
                conn.commit()
            with self.assertRaisesRegex(ValueError, "outstanding queue work"):
                require_idle_authority(path, "vm:rift-lab-1")

    def test_vm_epoch_modes_refuse_wrong_relation_and_resource_drift(self):
        previous = {
            "vmx": r"c:\\rift modding\\vms\\rift-lab\\rift-lab.vmx",
            "port": 5905,
            "pid": 38044,
            "startTicks": 134372941117887852,
            "logEpoch": "2026-10-24T05:41:51.833Z",
        }
        require_epoch_relation(previous, dict(previous), same_epoch=True)
        with self.assertRaisesRegex(ValueError, "has not changed"):
            require_epoch_relation(previous, dict(previous), same_epoch=False)
        changed = dict(previous, pid=40000, startTicks=134372941117887853)
        require_epoch_relation(previous, changed, same_epoch=False)
        with self.assertRaisesRegex(ValueError, "epoch changed"):
            require_epoch_relation(previous, changed, same_epoch=True)
        with self.assertRaisesRegex(ValueError, "resource identity changed"):
            require_epoch_relation(previous, dict(changed, port=5906), same_epoch=False)

    def test_successor_plan_preserves_full_64bit_vm_ticks_and_original(self):
        start_ticks = 134372941117887852
        identity = {
            "vmx": r"c:\\rift modding\\vms\\rift-lab\\rift-lab.vmx",
            "port": 5905,
            "startTicks": start_ticks,
            "pid": 38044,
        }
        prior = {
            "vmIdentity": dict(identity),
            "shutdownFile": "previous-stop",
            "schemaVersion": 1,
        }
        result = successor_plan(prior, identity, Path("successor-stop"))
        restored = json.loads(json.dumps(result, indent=2))
        self.assertEqual(restored["vmIdentity"]["startTicks"], start_ticks)
        self.assertNotEqual(start_ticks, int(float(start_ticks)))
        self.assertEqual(restored["shutdownFile"], "successor-stop")
        self.assertEqual(prior["shutdownFile"], "previous-stop")
        self.assertNotIn("createdUtc", prior)

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
