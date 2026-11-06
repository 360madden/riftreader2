"""Real host main() subprocess, private VM identity shim, disposable guests only."""
from copy import deepcopy
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

from scripts.nav_access_queue import AccessQueue
from tests.test_control_lease_access import CallerGuest, ACTION
from tests.test_nav_control_watchdog import VM


@unittest.skipUnless(os.name == "nt", "Windows host composition")
class HostProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.repo = Path(__file__).parents[1]
        self.children = []; self.guests = []
        self.addCleanup(self.cleanup)
        self.vmx = self.root / "lab.vmx"; self.vmx.touch()
        vmrun = self.root / "vmrun.exe"; vmrun.touch()
        ports = []
        for _ in range(2):
            s = socket.socket(); s.bind(("127.0.0.1", 0)); ports.append(s)
        self.agent_port, self.ui_port = [s.getsockname()[1] for s in ports]
        for s in ports: s.close()
        self.config = self.root / "host.json"
        self.config.write_text(json.dumps({"schemaVersion":1,"bindAddress":"192.168.56.1",
            "agentPort":self.agent_port,"uiPort":self.ui_port,"guestAddress":"192.168.56.128",
            "expectedMachineName":"RIFT-LAB-1","token":"guest-token-0123456789",
            "operatorToken":"operator-token-012345","outputDirectory":str(self.root / "evidence"),
            "vmx":str(self.vmx),"vmrun":str(vmrun),"vncPort":5905}))
        self.q = AccessQueue(self.root / "queue.sqlite3", create=True)
        identity = {**deepcopy(VM), "vmx": str(self.vmx).replace("/", "\\").casefold()}
        # The temporary child patches VM identity and loopback binding AFTER configuration validation. Production
        # startup, sockets, mutex, queue, supervisor, HTTP and shutdown remain real.
        self.shim = self.root / "entry.py"
        self.shim.write_text("\n".join([
            "import sys; sys.path.insert(0," + repr(str(self.repo)) + ")",
            "from scripts import control_host as h",
            "from dataclasses import replace",
            "load=h.HostConfig.load",
            "h.HostConfig.load=staticmethod(lambda p:replace(load(p),bind_address='127.0.0.1',guest_address='127.0.0.1'))",
            "original=h.VmEpochGuard.__init__",
            "def initialize(self,config):",
            " original(self,config)",
            " if self.module:",
            "  identity=" + repr(identity),
            "  self.module.collect_identity=lambda _:dict(identity)",
            "  self.module.verify_identity=lambda *_:dict(identity)",
            "h.VmEpochGuard.__init__=initialize",
            "append=h.EvidenceJournal.append",
            "def guarded_append(self,kind,value):",
            " if kind=='nav-host-shutdown-pending/1' and __import__('pathlib').Path(__file__).with_name('fail-journal').exists(): __import__('pathlib').Path(__file__).with_name('journal-failed').touch(); raise OSError('private fixture disk failure')",
            " return append(self,kind,value)",
            "h.EvidenceJournal.append=guarded_append",
            "raise SystemExit(h.main(sys.argv[1:]))"]))

    def cleanup(self):
        # Never leave private child processes after a failed assertion.
        for child, marker in self.children:
            if child.poll() is None:
                marker.touch(exist_ok=True)
                try: child.wait(3)
                except subprocess.TimeoutExpired: child.kill(); child.wait(3)
            child.communicate(timeout=3)
        for guest in self.guests: guest.close()

    def launch(self, reconcile=False, database=None, expect_running=True):
        marker = self.root / ("stop-" + str(len(self.children)))
        args = [sys.executable, str(self.shim), "--config", str(self.config),
                "--coordination-db", str(database or self.q.path), "--coordination-resource", "vm:lab-1",
                "--shutdown-file", str(marker)]
        if reconcile: args.append("--reconcile-existing")
        child = subprocess.Popen(args, cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.children.append((child, marker))
        if expect_running:
            self.wait(lambda: self.http()[0] == 200, child)
        return child, marker

    def http(self, operation="status", body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.ui_port, timeout=.5)
        try:
            c.request("GET" if body is None else "POST", "/api/" + operation,
                      None if body is None else json.dumps(body),
                      {"Authorization":"Bearer operator-token-012345", "Content-Type":"application/json",
                       "Origin":"http://127.0.0.1:" + str(self.ui_port)})
            r = c.getresponse(); return r.status, json.loads(r.read())
        finally: c.close()

    def wait(self, predicate, child, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if child.poll() is not None:
                out, err = child.communicate(); self.fail("private host exited: " + err.decode() + out.decode())
            try:
                if predicate(): return
            except (OSError, http.client.HTTPException): pass
            time.sleep(.02)
        self.fail("private host did not reach observed condition")

    def guest(self):
        g = CallerGuest(SimpleNamespace(port=self.agent_port, local_status=lambda: {"connected":True}))
        self.guests.append(g); return g

    def ready(self, child):
        self.wait(lambda: self.http()[1]["host"]["coordination"]["state"] == "ready", child)

    def grant(self, name):
        row = self.q.status()["resources"][0]
        self.q.submit(name,"fixture","A",{row["name"]:row["epoch"]},ttl_ms=30000,max_ms=30000)
        g = self.q.dispatch(); return {"request_id":g["request_id"],"token":g["token"]}

    def shutdown(self, child, marker):
        marker.write_text("stop")
        out, err = child.communicate(timeout=8)
        self.assertEqual(child.returncode, 0, err.decode())
        self.assertNotIn('"status": "shutdown-blocked"', out.decode())
        self.assertTrue(self.q.status()["resources"][0]["blocked"])

    def test_actual_host_entrypoint_serves_leased_capture_then_verified_shutdown(self):
        child, marker = self.launch(); g = self.guest(); self.ready(child)
        self.assertEqual(self.http("capture", {})[0], 409)
        access = self.grant("first")
        status, result = self.http("capture", {"access":access,"payload":{}})
        self.assertEqual(status, 200, result); self.assertEqual(result["imageFormat"], "bmp")
        self.shutdown(child, marker)
        self.assertFalse(any(c["operation"] in ("arm","action") for c in g.commands))

    def test_automatic_reconnect_uses_new_supervisor_and_rejects_old_grant(self):
        child, marker = self.launch(); first = self.guest(); self.ready(child)
        access = self.grant("first"); first.close(); self.guests.remove(first)
        self.wait(lambda: not self.http()[1]["host"]["connected"], child)
        second = self.guest(); self.ready(child)
        self.assertEqual(self.http("action", {"access":access,"payload":ACTION})[0], 409)
        fresh = self.grant("second")
        self.assertEqual(self.http("capture", {"access":fresh,"payload":{}})[0], 200)
        self.shutdown(child, marker)
        self.assertFalse(any(c["operation"] in ("arm","action") for c in second.commands))
        self.assertEqual(self.q.status()["requests"][0]["state"], "stale")

    def test_process_restart_requires_explicit_existing_reconciliation_and_keeps_history(self):
        child, marker = self.launch(); first = self.guest(); self.ready(child)
        access = self.grant("before-restart"); self.shutdown(child, marker)
        first.close(); self.guests.remove(first)
        second, marker2 = self.launch(reconcile=True); self.guest(); self.ready(second)
        self.assertEqual(self.http("action", {"access":access,"payload":ACTION})[0], 409)
        self.assertEqual(self.q.status()["requests"][0]["request_id"], "before-restart")
        self.shutdown(second, marker2)

    def test_unverified_shutdown_keeps_process_and_console_reserved(self):
        child, marker = self.launch(); guest = self.guest(); self.ready(child)
        guest.close(); self.guests.remove(guest)
        self.wait(lambda: not self.http()[1]["host"]["connected"], child)
        marker.write_text("stop")
        self.wait(lambda: self.http()[1]["host"]["coordination"]["shutdownRequested"], child)
        view = self.http()[1]["host"]
        self.assertFalse(view["coordination"]["safeToClose"])
        self.assertTrue(view["consoleReservation"]["held"])
        self.assertIsNone(child.poll())
        self.assertTrue(self.q.status()["resources"][0]["blocked"])
        # End only this deliberately failed disposable process, not a live service.
        child.kill(); child.communicate(timeout=3)

    def test_blocked_shutdown_journal_failure_does_not_abandon_reservation(self):
        (self.root / "fail-journal").touch()
        child, marker = self.launch(); guest = self.guest(); self.ready(child)
        guest.close(); self.guests.remove(guest)
        self.wait(lambda: not self.http()[1]["host"]["connected"], child)
        marker.write_text("stop")
        self.wait(lambda: self.http()[1]["host"]["coordination"]["shutdownRequested"], child)
        self.wait(lambda: (self.root / "journal-failed").exists(), child)
        time.sleep(.1)  # Confirm survival after the instrumented failure actually occurred.
        self.assertIsNone(child.poll(), "journal failure terminated blocked host")
        view = self.http()[1]["host"]
        self.assertFalse(view["coordination"]["safeToClose"])
        self.assertTrue(view["consoleReservation"]["held"])
        child.kill(); child.communicate(timeout=3)

    def test_missing_database_is_not_created_and_opens_no_service(self):
        missing = self.root / "not-created.sqlite3"
        child, _ = self.launch(database=missing, expect_running=False)
        out, err = child.communicate(timeout=5)
        self.assertNotIn(b"RFC 1918", out + err)
        self.assertEqual(child.returncode, 2); self.assertFalse(missing.exists())
        with self.assertRaises(OSError): self.http()


if __name__ == "__main__":
    unittest.main()
