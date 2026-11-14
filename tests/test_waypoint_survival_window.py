"""Withdrawn Tk/mailbox checks for shared survival controls; no game input."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import unittest

from scripts import waypoint_cli_protocol as protocol
from tests import test_waypoint_cli_gui as gui_fixture


SURVIVAL_PATCH = r'''
import scripts.waypoint_survival_runtime as survival_module
class FakeSurvivalRuntime:
    def __init__(self):
        self.profile = None
        self.preflights = 0
    def status(self):
        return {'configured': self.profile is not None,
                'profileSource': self.profile,
                'coordinateBasisQualified': self.profile is not None,
                'preflightReady': self.preflights > 0,
                'inputSent': False}
    def configure(self, path, adapter):
        self.profile = str(Path(path).absolute())
        return self.status()
    def preflight(self, adapter, stop):
        if stop.is_set():
            raise app.WaypointError('survival-stopped-before-preflight')
        self.preflights += 1
        (root / 'survival-preflight-called').write_text(str(self.preflights), encoding='ascii')
        return {'status':'ready', 'telemetryReady':True,
                'coordinateBasisQualified':True, 'playerId':'u0000000000000001',
                'targetId':None, 'sequence':2, 'inputSent':False}
    def route_runner(self, *args, **kwargs):
        return route(*args, **kwargs)
survival_module.WaypointSurvivalRuntime = FakeSurvivalRuntime
'''


SERVER_PATCH = r'''
        if (root / 'gui-toggle-survival').exists():
            def toggle(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'TCheckbutton' and child.cget('text') == 'Fight / retreat / recover on routes':
                        child.invoke(); return True
                    if toggle(child): return True
                return False
            toggle(tk._default_root)
            (root / 'gui-toggle-survival').unlink()
            (root / 'gui-toggle-survival-complete').touch()
        if (root / 'dump-survival-layout').exists():
            import json
            card = None
            def find_card(widget):
                nonlocal card
                for child in widget.winfo_children():
                    if child.winfo_class() == 'TLabelframe' and child.cget('text') == 'DIRECT MOVEMENT':
                        card = child; return
                    find_card(child)
            find_card(tk._default_root)
            tk._default_root.update_idletasks()
            rows = []
            def collect(widget):
                for child in widget.winfo_children():
                    if child.winfo_manager():
                        rows.append({'class':child.winfo_class(),
                                     'text':str(child.cget('text')) if 'text' in child.keys() else '',
                                     'requestedHeight':child.winfo_reqheight(),
                                     'top':child.winfo_rooty()-card.winfo_rooty(),
                                     'bottom':child.winfo_rooty()-card.winfo_rooty()+child.winfo_height()})
                    collect(child)
            collect(card)
            (root / 'survival-layout.json').write_text(json.dumps({
                'cardHeight':card.winfo_height(), 'requestedHeight':card.winfo_reqheight(),
                'children':rows}), encoding='utf-8')
            (root / 'dump-survival-layout').unlink()
'''


def child_source():
    value = gui_fixture.CHILD.replace(
        "app.ROOT = root\n", "app.ROOT = root\n" + SURVIVAL_PATCH)
    value = value.replace(
        "        return super().poll(dispatch)\n",
        SERVER_PATCH + "        return super().poll(dispatch)\n")
    value = value.replace(
        "    markers.running = lambda: ((root / 'force-no-pose-reader').exists()\n"
        "                               or original_running())\n",
        "    markers.running = lambda: ((root / 'force-no-pose-reader').exists()\n"
        "                               or original_running())\n"
        "    original_stop = markers.stop\n"
        "    def test_stop():\n"
        "        (root / 'overlay-paused').touch()\n"
        "        (root / 'force-no-pose-reader').unlink(missing_ok=True)\n"
        "        return original_stop()\n"
        "    markers.stop = test_stop\n")
    return value


class SurvivalWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile.json"
        self.profile.write_text("{}", encoding="utf-8")
        self.child = subprocess.Popen(
            [sys.executable, "-c", child_source(), str(self.root)],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.addCleanup(self.cleanup_child)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            sessions = protocol.discover_sessions(root=self.root / "sessions")
            if sessions:
                self.session = sessions[0]
                break
            if self.child.poll() is not None:
                self.fail(self.child.stderr.read().decode(errors="replace"))
            time.sleep(.02)
        else:
            self.fail("GUI session did not start")
        self.wait_idle()

    def cleanup_child(self):
        if self.child.poll() is None:
            try:
                if hasattr(self, "session"):
                    self.call("app.close", {"discard": True})
                else:
                    self.child.kill()
                self.child.wait(timeout=5)
            except Exception:
                self.child.kill(); self.child.wait(timeout=5)
        self.child.communicate()
        self.temp.cleanup()

    def call(self, operation, values=None):
        return protocol.request(self.session, operation, values or {}, timeout=5)

    def wait_idle(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = self.call("status")
            if value["ok"] and not value["data"]["app"]["busy"]:
                return value["data"]
            time.sleep(.03)
        self.fail("GUI did not become idle")

    def wait_file(self, name):
        path = self.root / name
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if path.exists(): return
            time.sleep(.02)
        self.fail(f"missing fixture signal: {name}")

    def test_cli_and_gui_share_enabled_profile_and_actual_preflight_result(self):
        initial = self.call("survival.status")
        self.assertTrue(initial["ok"], initial)
        self.assertFalse(initial["data"]["enabled"])
        configured = self.call("survival.configure", {"profile": str(self.profile)})
        self.assertTrue(configured["ok"], configured)
        self.assertEqual(str(self.profile), configured["data"]["profileSource"])
        enabled = self.call("survival.set", {"enabled": "on"})
        self.assertTrue(enabled["data"]["enabled"])
        self.assertTrue(self.call("status")["data"]["survival"]["enabled"])

        (self.root / "gui-toggle-survival").touch()
        self.wait_file("gui-toggle-survival-complete")
        self.assertFalse(self.call("survival.status")["data"]["enabled"])

        result = self.call("survival.preflight")
        self.assertTrue(result["ok"], result)
        self.assertEqual("ready", result["data"]["result"]["status"])
        self.assertEqual(result["data"]["result"], result["data"]["survival"])
        status = self.wait_idle()
        self.assertIn("Survival ready", status["app"]["state"])
        self.assertEqual("1", (self.root / "survival-preflight-called").read_text())

    def test_preflight_pauses_owned_overlay_and_never_clears_stop(self):
        self.call("survival.configure", {"profile": str(self.profile)})
        (self.root / "force-no-pose-reader").touch()
        result = self.call("survival.preflight")
        self.assertTrue(result["ok"], result)
        self.assertTrue((self.root / "overlay-paused").exists())

        stopped = self.call("stop")
        self.assertTrue(stopped["ok"], stopped)
        self.assertTrue(self.call("status")["data"]["controls"]["stopLatched"])
        refused = self.call("survival.preflight")
        self.assertFalse(refused["ok"], refused)
        self.assertIn("survival-stopped-before-preflight", refused["error"]["message"])
        self.assertTrue(self.call("status")["data"]["controls"]["stopLatched"])

    def test_default_replay_layout_keeps_survival_controls_inside_card(self):
        (self.root / "dump-survival-layout").touch()
        self.wait_file("survival-layout.json")
        value = json.loads((self.root / "survival-layout.json").read_text(encoding="utf-8"))
        self.assertLessEqual(value["requestedHeight"], 205)
        visible = [row for row in value["children"] if row["class"] in
                   ("TButton", "TCheckbutton", "TLabel")]
        self.assertTrue(any(row["text"] == "Ability profile…" for row in visible))
        self.assertTrue(any(row["text"] == "Check survival" for row in visible))
        self.assertTrue(any(row["class"] == "TLabel" for row in visible))
        self.assertLessEqual(max(row["requestedHeight"] for row in visible), 25)


if __name__ == "__main__":
    unittest.main()
