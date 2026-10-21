"""Offline acceptance for durable access scheduling; no game/VM calls."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "nav_access_queue.py"
SPEC = importlib.util.spec_from_file_location("nav_access_queue", SCRIPT)
nav = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = nav
SPEC.loader.exec_module(nav)


class Clock:
    def __init__(self):
        self.now = 1_000_000

    def __call__(self):
        return self.now


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "queue.sqlite3"
        self.clock = Clock()
        self.queue = nav.AccessQueue(self.path, create=True, clock=self.clock)
        self.queue.register("vm:lab-1", "epoch-1")
        self.clean("vm:lab-1")

    def resource(self, name):
        return next(row for row in self.queue.status()["resources"] if row["name"] == name)

    def clean(self, name, **overrides):
        row = self.resource(name)
        arguments = {"resource": name, "epoch": row["epoch"], "generation": row["generation"],
                     "observed_ms": self.clock.now, "receipt": "synthetic-release-evidence",
                     "stopped": True, "released": True, "in_flight": False}
        arguments.update(overrides)
        return self.queue.cleanup(**arguments)

    def submit(self, name, track="A", resources=None, **options):
        if resources is None:
            resources = {"vm:lab-1": "epoch-1"}
        return self.queue.submit(name, "worker-" + track, track, resources, **options)

    def state(self, name):
        return next(row for row in self.queue.status()["requests"] if row["request_id"] == name)

    def complete(self, grant, outcome="succeeded"):
        self.queue.finish(grant["request_id"], grant["token"], outcome, ["synthetic-run-result"])
        for resource in grant["lease"]:
            self.clean(resource)

    def test_missing_database_is_not_recreated(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            nav.AccessQueue(missing)
        self.assertFalse(missing.exists())

    def test_existing_database_cannot_be_initialized_again(self):
        self.submit("a")
        with self.assertRaises(FileExistsError):
            nav.AccessQueue(self.path, create=True)
        self.assertEqual(self.state("a")["state"], "queued")

    def test_relative_database_path_rejected(self):
        with self.assertRaises(nav.QueueError):
            nav.AccessQueue("relative.sqlite3", create=True)

    def test_unknown_schema_fails_closed(self):
        with closing(sqlite3.connect(self.path)) as database:
            database.execute("PRAGMA user_version=999")
        with self.assertRaises(nav.QueueError):
            self.queue.dispatch()

    def test_deleted_database_not_recreated_by_existing_instance(self):
        self.path.unlink()
        with self.assertRaises(sqlite3.OperationalError):
            self.queue.status()
        self.assertFalse(self.path.exists())

    def test_registration_starts_blocked_until_cleanup(self):
        self.queue.register("vm:lab-2", "epoch-2")
        self.submit("b", "B", {"vm:lab-2": "epoch-2"})
        self.assertIsNone(self.queue.dispatch())
        self.clean("vm:lab-2")
        self.assertEqual(self.queue.dispatch()["request_id"], "b")

    def test_same_epoch_registration_does_not_reset_owner(self):
        self.submit("a")
        grant = self.queue.dispatch()
        before = self.resource("vm:lab-1")
        self.queue.register("vm:lab-1", "epoch-1")
        self.assertEqual(self.resource("vm:lab-1"), before)
        self.assertEqual(self.queue.check("a", grant["token"])["state"], "active")

    def test_exact_request_idempotency_and_changed_specification_refused(self):
        original = self.submit("a")
        self.assertEqual(self.submit("a"), original)
        with self.assertRaises(nav.QueueError):
            self.submit("a", priority=1)
        self.assertEqual(len(self.queue.status()["requests"]), 1)

    def test_three_tracks_queue_and_transfer_only_after_cleanup(self):
        for track in "ABC":
            self.submit(track, track)
        for track in "ABC":
            grant = self.queue.dispatch()
            self.assertEqual(grant["track"], track)
            self.assertIsNone(self.queue.dispatch())
            self.queue.finish(track, grant["token"], "succeeded", ["synthetic-" + track])
            self.assertIsNone(self.queue.dispatch())
            self.clean("vm:lab-1")
        self.assertEqual([r["state"] for r in self.queue.status()["requests"]], ["succeeded"] * 3)

    def test_independent_vm_resources_can_be_granted_together(self):
        self.queue.register("vm:lab-2", "epoch-2")
        self.clean("vm:lab-2")
        self.submit("a")
        self.submit("b", "B", {"vm:lab-2": "epoch-2"})
        self.assertEqual({self.queue.dispatch()["request_id"], self.queue.dispatch()["request_id"]}, {"a", "b"})

    def test_shared_host_input_resource_prevents_parallel_vm_conflict(self):
        self.queue.register("host:desktop-input", "host-1")
        self.clean("host:desktop-input")
        self.queue.register("vm:lab-2", "epoch-2")
        self.clean("vm:lab-2")
        self.submit("a", resources={"vm:lab-1": "epoch-1", "host:desktop-input": "host-1"})
        self.submit("b", "B", {"vm:lab-2": "epoch-2", "host:desktop-input": "host-1"})
        self.queue.dispatch()
        self.assertIsNone(self.queue.dispatch())
        self.assertIsNone(self.resource("vm:lab-2")["holder"])

    def test_atomic_all_or_none_allows_unrelated_work(self):
        self.queue.register("host:desktop-input", "host-1")
        self.submit("blocked", resources={"vm:lab-1": "epoch-1", "host:desktop-input": "host-1"}, priority=10)
        self.submit("ready", "C")
        self.assertEqual(self.queue.dispatch()["request_id"], "ready")
        self.assertIsNone(self.resource("host:desktop-input")["holder"])

    def test_priority_then_shared_benefit_then_duration_then_fifo(self):
        self.submit("ordinary", priority=1)
        self.submit("shorter", "B", priority=1, benefit=3, estimated_ms=100)
        self.submit("longer", "C", priority=1, benefit=3, estimated_ms=200)
        self.submit("urgent", priority=2)
        order = []
        for _ in range(4):
            grant = self.queue.dispatch()
            order.append(grant["request_id"])
            self.complete(grant)
        self.assertEqual(order, ["urgent", "shorter", "longer", "ordinary"])

    def test_aging_allows_old_low_priority_to_beat_new_high_priority(self):
        self.submit("older", priority=0)
        self.clock.now += 11 * nav.AGING_MS
        self.submit("newer", "B", priority=10)
        self.assertEqual(self.queue.dispatch()["request_id"], "older")

    def test_failed_dependency_propagates_without_running(self):
        self.submit("a")
        self.submit("b", "B", dependencies=["a"])
        self.submit("c", "C", dependencies=["b"])
        self.complete(self.queue.dispatch(), "failed")
        self.assertIsNone(self.queue.dispatch())
        self.assertEqual(self.state("b")["state"], "dependency_failed")
        self.assertEqual(self.state("c")["state"], "dependency_failed")

    def test_successful_dependency_waits_for_final_cleanup_and_keeps_evidence(self):
        self.submit("a")
        self.submit("b", "B", dependencies=["a"], priority=10)
        grant = self.queue.dispatch()
        self.queue.finish("a", grant["token"], "succeeded", ["shared-capture", "shared-telemetry"])
        self.assertIsNone(self.queue.dispatch())
        self.clean("vm:lab-1")
        self.assertEqual(self.queue.dispatch()["request_id"], "b")
        self.assertEqual(self.state("a")["evidence"], ["shared-capture", "shared-telemetry"])

    def test_future_self_and_duplicate_dependencies_rejected(self):
        self.submit("a")
        for dependencies in (["missing"], ["b"], ["a", "a"]):
            with self.subTest(dependencies=dependencies), self.assertRaises(nav.QueueError):
                self.submit("b", dependencies=dependencies)

    def test_wrong_token_rejected_without_losing_valid_owner(self):
        self.submit("a")
        grant = self.queue.dispatch()
        with self.assertRaises(nav.QueueError):
            self.queue.heartbeat("a", "0" * 64)
        self.assertEqual(self.queue.check("a", grant["token"])["state"], "active")

    def test_expiration_persists_even_when_late_heartbeat_is_rejected(self):
        self.submit("a")
        self.submit("b", "B")
        grant = self.queue.dispatch()
        self.clock.now = grant["expires_ms"]
        with self.assertRaises(nav.QueueError):
            self.queue.heartbeat("a", grant["token"])
        self.assertEqual(self.state("a")["state"], "cleanup")
        self.assertIsNone(self.queue.dispatch())
        self.clean("vm:lab-1")
        self.assertEqual(self.state("a")["state"], "expired")
        self.assertEqual(self.queue.dispatch()["request_id"], "b")

    def test_heartbeat_never_extends_hard_deadline(self):
        self.submit("a", ttl_ms=2000, max_ms=5000)
        grant = self.queue.dispatch()
        for _ in range(4):
            self.clock.now += 1000
            result = self.queue.heartbeat("a", grant["token"])
        self.assertEqual(result["expires_ms"], grant["deadline_ms"])
        self.clock.now = grant["deadline_ms"]
        with self.assertRaises(nav.QueueError):
            self.queue.check("a", grant["token"])
        self.assertEqual(self.state("a")["state"], "cleanup")

    def test_restart_preserves_active_owner_and_recovers_expired_owner(self):
        self.submit("a")
        grant = self.queue.dispatch()
        reopened = nav.AccessQueue(self.path, clock=self.clock)
        self.assertIsNone(reopened.dispatch())
        self.assertEqual(reopened.check("a", grant["token"])["state"], "active")
        self.clock.now = grant["expires_ms"] + 1
        self.assertEqual(reopened.status()["requests"][0]["state"], "cleanup")

    def test_cancel_queued_idempotent_and_wrong_owner_refused(self):
        self.submit("a")
        with self.assertRaises(nav.QueueError):
            self.queue.cancel("a", "worker-B")
        self.queue.cancel("a", "worker-A")
        self.assertEqual(self.queue.cancel("a", "worker-A")["state"], "cancelled")
        self.assertIsNone(self.queue.dispatch())

    def test_active_cancellation_revokes_token_and_blocks_next_owner(self):
        self.submit("a")
        self.submit("b", "B")
        grant = self.queue.dispatch()
        self.queue.cancel("a", "worker-A")
        with self.assertRaises(nav.QueueError):
            self.queue.check("a", grant["token"])
        self.assertIsNone(self.queue.dispatch())
        self.clean("vm:lab-1")
        next_grant = self.queue.dispatch()
        self.assertEqual(next_grant["request_id"], "b")
        self.assertGreater(next_grant["lease"]["vm:lab-1"]["generation"], grant["lease"]["vm:lab-1"]["generation"])

    def test_negative_or_nonboolean_cleanup_flags_cannot_release(self):
        self.submit("a")
        self.queue.dispatch()
        self.queue.cancel("a", "worker-A")
        for flags in ({"stopped": False}, {"released": False}, {"in_flight": True}, {"released": 1}):
            with self.subTest(flags=flags), self.assertRaises(nav.QueueError):
                self.clean("vm:lab-1", **flags)
        self.assertEqual(self.resource("vm:lab-1")["holder"], "a")

    def test_active_resource_cannot_be_cleared_by_cleanup(self):
        self.submit("a")
        self.queue.dispatch()
        with self.assertRaises(nav.QueueError):
            self.clean("vm:lab-1")
        self.assertEqual(self.resource("vm:lab-1")["holder"], "a")

    def test_stale_epoch_generation_time_and_future_cleanup_refused(self):
        self.submit("a")
        grant = self.queue.dispatch()
        self.clock.now += 100
        self.queue.cancel("a", "worker-A")
        for override in ({"epoch": "old-epoch"}, {"generation": grant["lease"]["vm:lab-1"]["generation"]},
                         {"observed_ms": self.clock.now - 1}, {"observed_ms": self.clock.now + 1}):
            with self.subTest(override=override), self.assertRaises(nav.QueueError):
                self.clean("vm:lab-1", **override)
        self.assertEqual(self.resource("vm:lab-1")["blocked"], 1)

    def test_cleanup_older_than_five_seconds_refused(self):
        self.queue.register("vm:lab-2", "epoch-2")
        observed = self.clock.now
        self.clock.now += 5001
        with self.assertRaises(nav.QueueError):
            self.clean("vm:lab-2", observed_ms=observed)

    def test_partial_multiresource_cleanup_does_not_finalize_request(self):
        self.queue.register("host:desktop-input", "host-1")
        self.clean("host:desktop-input")
        self.submit("a", resources={"host:desktop-input": "host-1", "vm:lab-1": "epoch-1"})
        grant = self.queue.dispatch()
        self.queue.finish("a", grant["token"], "succeeded", ["synthetic-result"])
        self.clean("vm:lab-1")
        self.assertEqual(self.state("a")["state"], "cleanup")
        self.assertEqual(self.resource("host:desktop-input")["holder"], "a")
        self.clean("host:desktop-input")
        self.assertEqual(self.state("a")["state"], "succeeded")

    def test_epoch_change_revokes_active_and_invalidates_queued(self):
        self.submit("a")
        self.submit("b", "B")
        grant = self.queue.dispatch()
        self.queue.register("vm:lab-1", "epoch-NEW")
        with self.assertRaises(nav.QueueError):
            self.queue.check("a", grant["token"])
        self.assertIsNone(self.queue.dispatch())
        self.assertEqual(self.state("b")["state"], "stale")
        self.clean("vm:lab-1")
        self.assertEqual(self.state("a")["state"], "stale")

    def test_clock_rollback_quarantines_owner_and_blocks_dispatch(self):
        self.submit("a")
        self.queue.dispatch()
        previous = self.clock.now
        self.clock.now -= 1
        with self.assertRaises(nav.QueueError):
            self.queue.dispatch()
        self.clock.now = previous
        self.assertEqual(self.state("a")["state"], "cleanup")
        self.assertIsNone(self.queue.dispatch())

    def test_status_pagination_and_no_token_disclosure(self):
        for name in ("a", "b", "c"):
            self.submit(name)
        grant = self.queue.dispatch()
        first = self.queue.status(limit=2)
        second = self.queue.status(after_sequence=first["next_sequence"], limit=2)
        self.assertEqual([r["request_id"] for r in first["requests"] + second["requests"]], ["a", "b", "c"])
        self.assertIsNone(second["next_sequence"])
        self.assertNotIn(grant["token"], json.dumps(first))
        self.assertNotIn("token_hash", json.dumps(first))
        self.assertFalse(first["live_enforcement"])

    def test_invalid_types_bounds_names_and_missing_resources_refused(self):
        for options in ({"priority": True}, {"priority": 11}, {"benefit": 0}, {"ttl_ms": 999},
                        {"ttl_ms": 6000, "max_ms": 5000}, {"estimated_ms": 5001, "max_ms": 5000},
                        {"resources": {}}, {"resources": {"VM:LAB-1": "epoch-1"}},
                        {"resources": {"vm:missing": "epoch-1"}}, {"resources": {"vm:lab-1": "wrong"}}):
            with self.subTest(options=options), self.assertRaises(nav.QueueError):
                self.submit("invalid", **options)

    def test_queue_and_resource_capacity_limits(self):
        with patch.object(nav, "MAX_PENDING", 1):
            self.submit("a")
            with self.assertRaises(nav.QueueError):
                self.submit("b")
        with patch.object(nav, "MAX_RESOURCES", 1):
            with self.assertRaises(nav.QueueError):
                self.queue.register("vm:extra", "extra-epoch")

    def test_eight_competing_threads_receive_exactly_one_grant(self):
        for index in range(8):
            self.submit("request-" + str(index))
        barrier = threading.Barrier(8)
        def compete(_):
            queue = nav.AccessQueue(self.path, clock=self.clock)
            barrier.wait(timeout=10)
            return queue.dispatch()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(compete, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(sum(row["state"] == "active" for row in self.queue.status()["requests"]), 1)

    def test_six_independent_processes_receive_exactly_one_grant(self):
        for index in range(6):
            self.submit("request-" + str(index))
        start = self.root / "start"
        code = (
            "import sys,time,json; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); from nav_access_queue import AccessQueue; "
            "q=AccessQueue(sys.argv[2],clock=lambda:1000000); "
            "Path(sys.argv[4]).touch(); deadline=time.monotonic()+10\n"
            "while not Path(sys.argv[3]).exists():\n"
            " if time.monotonic()>deadline: raise RuntimeError('barrier timeout')\n"
            " time.sleep(.01)\n"
            "print(json.dumps(q.dispatch() is not None))\n"
        )
        processes = []
        try:
            for index in range(6):
                ready = self.root / ("ready-" + str(index))
                processes.append(subprocess.Popen(
                    [sys.executable, "-c", code, str(SCRIPT.parent), str(self.path), str(start), str(ready)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            deadline = time.monotonic() + 10
            while len(list(self.root.glob("ready-*"))) != 6:
                if time.monotonic() > deadline:
                    self.fail("child process readiness deadline")
                time.sleep(.01)
            start.touch()
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                results.append(json.loads(stdout))
            self.assertEqual(sum(results), 1)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_failed_grant_transaction_leaves_no_partial_resource_ownership(self):
        self.queue.register("host:desktop-input", "host-1")
        self.clean("host:desktop-input")
        self.submit("a", resources={"host:desktop-input": "host-1", "vm:lab-1": "epoch-1"})
        with closing(sqlite3.connect(self.path)) as database:
            database.execute("""CREATE TRIGGER reject_grant BEFORE INSERT ON events
                                WHEN NEW.kind='granted' BEGIN
                                SELECT RAISE(ABORT, 'injected grant failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.queue.dispatch()
        self.assertEqual(self.state("a")["state"], "queued")
        self.assertTrue(all(row["holder"] is None for row in self.queue.status()["resources"]))

    def test_worker_process_exit_keeps_lease_until_expiry_and_cleanup(self):
        self.submit("a")
        self.submit("b", "B")
        code = (
            "import sys,os; sys.path.insert(0,sys.argv[1]); "
            "from nav_access_queue import AccessQueue; "
            "q=AccessQueue(sys.argv[2],clock=lambda:1000000); "
            "assert q.dispatch()['request_id']=='a'; os._exit(23)"
        )
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPT.parent), str(self.path)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(self.state("a")["state"], "active")
        self.assertIsNone(self.queue.dispatch())
        self.clock.now += 5000
        self.assertIsNone(self.queue.dispatch())
        self.assertEqual(self.state("a")["state"], "cleanup")
        self.clean("vm:lab-1")
        self.assertEqual(self.queue.dispatch()["request_id"], "b")

    def test_process_exit_mid_transaction_rolls_back_partial_grant(self):
        self.submit("a")
        code = (
            "import sys,os,sqlite3; c=sqlite3.connect(sys.argv[1],isolation_level=None); "
            "c.execute('BEGIN IMMEDIATE'); "
            "c.execute(\"UPDATE resources SET holder='a',generation=generation+1 WHERE name='vm:lab-1'\"); "
            "os._exit(23)"
        )
        result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIsNone(self.resource("vm:lab-1")["holder"])
        self.assertEqual(self.queue.dispatch()["request_id"], "a")

    def test_epoch_change_quarantines_all_resources_of_active_experiment(self):
        self.queue.register("host:desktop-input", "host-1")
        self.clean("host:desktop-input")
        self.submit("a", resources={"host:desktop-input": "host-1", "vm:lab-1": "epoch-1"})
        self.queue.dispatch()
        self.queue.register("vm:lab-1", "epoch-2")
        resources = self.queue.status()["resources"]
        self.assertTrue(all(row["blocked"] and row["holder"] == "a" for row in resources))
        self.clean("vm:lab-1")
        self.assertEqual(self.state("a")["state"], "cleanup")
        self.clean("host:desktop-input")
        self.assertEqual(self.state("a")["state"], "stale")

    def test_finish_requires_explicit_evidence_and_valid_outcome(self):
        self.submit("a")
        grant = self.queue.dispatch()
        for outcome, evidence in (("succeeded", []), ("expired", ["evidence"]), ("succeeded", [" "])):
            with self.subTest(outcome=outcome, evidence=evidence), self.assertRaises(nav.QueueError):
                self.queue.finish("a", grant["token"], outcome, evidence)
        self.assertEqual(self.state("a")["state"], "active")

    def test_cli_rejects_invalid_encoding_and_oversized_request(self):
        request = self.root / "invalid.json"
        for raw in (b'\xff\xfe\xff', b' ' * 65537):
            request.write_bytes(raw)
            output = io.StringIO()
            with redirect_stdout(output):
                code = nav.main(["--database", str(self.path), "--request", str(request)])
            self.assertEqual(code, 2)
            self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_cli_operation_and_duplicate_json_rejection(self):
        # Use a separate real-clock database; no live control operations exist.
        path = self.root / "cli.sqlite3"
        output = io.StringIO()
        with redirect_stdout(output):
            code = nav.main(["--database", str(path), "--initialize"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        request = self.root / "request.json"
        request.write_text('{"operation":"status","arguments":{}}', encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            code = nav.main(["--database", str(path), "--request", str(request)])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["result"]["live_enforcement"])
        request.write_text('{"operation":"status","operation":"dispatch","arguments":{}}', encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            code = nav.main(["--database", str(path), "--request", str(request)])
        self.assertEqual(code, 2)
        self.assertIn("duplicate", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
