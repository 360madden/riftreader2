"""Synthetic-only safety tests for screenshot without game input."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import capture_lab_hp_screenshot as cap
from tests.test_nav_control_watchdog import VM, TARGET


class FakeQueue:
    def __init__(self, epoch, *, blocked=False, wrong_grant=False, missing_token=False):
        self.epoch = epoch
        self.blocked = blocked
        self.wrong_grant = wrong_grant
        self.missing_token = missing_token
        self.cancelled = False
        self.request = None
        self.grant = None
        self.outcome = None
        self.finished = False
        self.stop_seen = False

    def dispatch_fence(self):
        return nullcontext()

    def status(self, *, after_sequence=0, limit=100):
        row = dict(name="vm:rift-lab-2", epoch=self.epoch,
                   blocked=int(self.blocked and not self.finished),
                   holder=None if self.request is None or self.finished else self.request,
                   cleanup_receipt="watchdog-attested" if self.finished else None)
        requests = [] if self.request is None else [
            dict(request_id=self.request, state=self.outcome if self.finished else "active",
                 sequence=1)]
        return dict(resources=[row], requests=requests, next_sequence=None)

    def submit(self, request_id, owner, track, resources, **kwargs):
        self.request = request_id

    def dispatch(self):
        self.grant = dict(request_id="other-request" if self.wrong_grant else self.request,
                          lease={"vm:rift-lab-2": {"epoch": self.epoch, "generation": 1}})
        if not self.missing_token:
            self.grant["token"] = "a" * 64
        return self.grant

    def cancel(self, request_id, owner):
        assert request_id == self.request and owner == "hp-screenshot"
        self.cancelled = True
        if self.grant is not None and self.grant["request_id"] == request_id:
            self.finished = True
            self.outcome = "cancelled"

    def heartbeat(self, request_id, token):
        if request_id != self.request or token != "a" * 64:
            raise AssertionError("wrong lease")

    def finish(self, request_id, token, outcome, evidence):
        assert self.stop_seen, "STOP must precede finish"
        assert request_id == self.request and token == "a" * 64
        assert outcome in ("succeeded", "failed") and evidence
        self.outcome = outcome
        self.finished = True


class ScreenshotSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture_attempts = 0
        self.now = datetime.now(timezone.utc)
        self.review = dict(
            observedAtUtc=self.now.isoformat(),
            processId=TARGET["processId"],
            processStartUtcTicks=TARGET["processStartUtcTicks"],
            executableSha256=TARGET["executableSha256"],
            hpCandidate={"current": 14830, "maximum": 14830},
            review="synthetic",
        )
        self.status = self.bound_status()
        self.epoch = self.status["host"]["coordination"]["supervisor"]["epoch"]

    def bound_status(self):
        host = dict(connected=True, instanceId="guest-one",
                    machineName=TARGET["machineName"], vmIdentity=dict(VM),
                    consoleReservation=dict(held=True, required=True, faulted=False, closing=False),
                    coordination=dict(state="ready", shutdownRequested=False,
                                      safeToClose=False, resource="vm:rift-lab-2"))
        guest = dict(instanceId="guest-one", target=dict(TARGET), armed=False,
                     busy=False, recoveryRequired=False, desktopInputsDown=[])
        host["coordination"]["supervisor"] = dict(
            state="running", threadAlive=True, initialCleanupVerified=True,
            resource="vm:rift-lab-2",
            epoch=cap.resource_epoch(cap.bind_identity(host, guest)))
        return dict(host=host, guest=guest)

    def make_review_file(self, *, age=0, sha=None, type_code="0x2C2"):
        base = self.root / "artifacts/native-unit-manager/lab2/fixture"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "review.json"
        data = {
            "lab": "lab2", "status": "complete",
            "identity": dict(processId=7012, processStartUtcTicks=123456789,
                             executableSha256=sha or cap.BUILD_SHA),
            "healthRecordCandidate": dict(
                status="type-checked-record-candidate", typeCode=type_code,
                inputsStable=True,
                observedAtUtc=(self.now - timedelta(seconds=age)).isoformat(),
                calculatedHealth={"status": "calculated-candidate",
                                  "current": 10635, "maximum": 10635}),
        }
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_review_requires_exact_type_build_and_recent_observation(self):
        with patch.object(cap, "ROOT", self.root):
            good = self.make_review_file()
            self.assertEqual(7012, cap.native_review("lab2", good, self.now)["processId"])
            stale = self.make_review_file(age=301)
            with self.assertRaisesRegex(cap.CaptureBlocked, "too old"):
                cap.native_review("lab2", stale, self.now)
            wrong = self.make_review_file(type_code="0x072B")
            with self.assertRaisesRegex(cap.CaptureBlocked, "not type-checked"):
                cap.native_review("lab2", wrong, self.now)
            wrong_sha = self.make_review_file(sha="F" * 64)
            with self.assertRaisesRegex(cap.CaptureBlocked, "unsupported native"):
                cap.native_review("lab2", wrong_sha, self.now)

    def test_recent_review_boundaries(self):
        observation = {"observedAtUtc": self.now.isoformat()}
        cap.require_recent_review(observation, self.now + timedelta(seconds=300))
        with self.assertRaisesRegex(cap.CaptureBlocked, "too old"):
            cap.require_recent_review(observation, self.now + timedelta(seconds=301))
        with self.assertRaisesRegex(cap.CaptureBlocked, "future-dated"):
            cap.require_recent_review(observation, self.now - timedelta(seconds=16))
        with self.assertRaisesRegex(cap.CaptureBlocked, "timestamp invalid"):
            cap.require_recent_review({"observedAtUtc": "not-a-date"}, self.now)

    def test_status_pins_native_target_supervisor_epoch_and_idle_input(self):
        self.assertEqual(self.epoch, cap.ready_epoch(self.status, self.review, "vm:rift-lab-2"))
        self.status["guest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(cap.CaptureBlocked, "identity changed"):
            cap.ready_epoch(self.status, self.review, "vm:rift-lab-2")
        self.status["guest"]["target"]["processId"] -= 1
        self.status["host"]["coordination"]["supervisor"]["epoch"] = "nav-wrong"
        with self.assertRaisesRegex(cap.CaptureBlocked, "epoch differs"):
            cap.ready_epoch(self.status, self.review, "vm:rift-lab-2")
        self.status["host"]["coordination"]["supervisor"]["epoch"] = self.epoch
        self.status["guest"]["desktopInputsDown"] = ["W"]
        with self.assertRaisesRegex(cap.CaptureBlocked, "not idle"):
            cap.ready_epoch(self.status, self.review, "vm:rift-lab-2")

    def test_blocked_resource_prevents_grant(self):
        with self.assertRaisesRegex(cap.CaptureBlocked, "held, blocked"):
            cap.idle_queue(FakeQueue(self.epoch, blocked=True),
                           "vm:rift-lab-2", self.epoch)

    def test_only_same_lab_pending_work_blocks_queue(self):
        class PendingQueue(FakeQueue):
            def __init__(self, epoch, pending):
                super().__init__(epoch)
                self.pending = pending

            def status(self, **kwargs):
                snapshot = super().status(**kwargs)
                snapshot["requests"] = [self.pending]
                return snapshot

        for state in ("queued", "active", "cleanup"):
            with self.subTest(state=state):
                other_lab = {
                    "state": state,
                    "specification": {"resources": {"vm:rift-lab-1": "other-epoch"}},
                }
                available = cap.idle_queue(PendingQueue(self.epoch, other_lab),
                                           "vm:rift-lab-2", self.epoch)
                self.assertEqual(self.epoch, available["epoch"])
                this_lab = {
                    "state": state,
                    "specification": {"resources": {"vm:rift-lab-2": self.epoch}},
                }
                with self.assertRaisesRegex(cap.CaptureBlocked, "competing work"):
                    cap.idle_queue(PendingQueue(self.epoch, this_lab),
                                   "vm:rift-lab-2", self.epoch)

    def test_release_needs_watchdog_terminal_and_receipt(self):
        class Stuck:
            def status(self, **_kwargs):
                return dict(resources=[dict(name="vm:rift-lab-2", epoch=self.epoch,
                                            blocked=1, holder="own", cleanup_receipt=None)],
                            requests=[dict(request_id="own", state="cleanup")],
                            next_sequence=None)
        stuck = Stuck()
        stuck.epoch = self.epoch
        with self.assertRaisesRegex(cap.CaptureBlocked, "release not verified"):
            cap.await_release(stuck, "own", "vm:rift-lab-2", self.epoch,
                              wait_seconds=0)

    def exercise_capture(self, fail_capture=False, stop_response=None):
        self.capture_attempts += 1
        output = self.root / f"capture-{self.capture_attempts}"
        queue = FakeQueue(self.epoch)
        calls = []
        status = self.status

        class FakeClient:
            def __init__(self, _config, access=None):
                self.access = access

            def request(self, path, *, method, payload=None):
                calls.append((path, self.access is not None))
                if path == "/api/status":
                    return status
                if path == "/api/stop":
                    queue.stop_seen = True
                    return ({"stopped": True, "recoveryRequired": False}
                            if stop_response is None else stop_response)
                raise AssertionError("Unexpected guest request: " + path)

        def fake_capture(client, path):
            assert client.access == {"request_id": queue.request, "token": "a" * 64}
            if fail_capture:
                raise RuntimeError("mock capture unavailable")
            path.mkdir()
            (path / "capture.json").write_text(
                json.dumps({"target": dict(TARGET)}), encoding="utf-8")
            return dict(captureId="fixture", capture=str(path / "capture.json"),
                        image=str(path / "image.bmp"))

        with (patch("scripts.ensure_guest_agent.ensure"),
              patch.object(cap.HostConfig, "load", return_value=object()),
              patch.object(cap, "ControlClient", FakeClient),
              patch.object(cap, "AccessQueue", return_value=queue),
              patch.object(cap, "_capture", side_effect=fake_capture)):
            stop_rejected = stop_response is not None and (
                not isinstance(stop_response, dict)
                or stop_response.get("stopped") is not True
                or stop_response.get("recoveryRequired") is not False)
            if fail_capture:
                with self.assertRaisesRegex(cap.CaptureBlocked, "capture failed closed: RuntimeError"):
                    cap.capture_once("lab2", self.review, output)
            elif stop_rejected:
                with self.assertRaisesRegex(cap.CaptureBlocked, "guest STOP did not verify release"):
                    cap.capture_once("lab2", self.review, output)
            else:
                result = cap.capture_once("lab2", self.review, output)
                self.assertEqual("captured-after-watchdog-release", result["status"])
        self.assertEqual("failed" if fail_capture or stop_rejected else "succeeded", queue.outcome)
        self.assertTrue(queue.finished and queue.stop_seen)
        self.assertEqual(1, len([c for c in calls if c[0] == "/api/stop"]))
        self.assertFalse(any(c[0] in ("/api/arm", "/api/action") for c in calls))

    def test_wrong_grant_cancels_only_own_request_before_capture(self):
        queue = FakeQueue(self.epoch, wrong_grant=True)

        class FakeClient:
            def __init__(self, _config, access=None):
                assert access is None

            def request(self, path, *, method, payload=None):
                assert path == "/api/status"
                return self_status

        self_status = self.status
        with (patch("scripts.ensure_guest_agent.ensure"),
              patch.object(cap.HostConfig, "load", return_value=object()),
              patch.object(cap, "ControlClient", FakeClient),
              patch.object(cap, "AccessQueue", return_value=queue),
              patch.object(cap, "_capture", side_effect=AssertionError("no capture authorized"))):
            with self.assertRaisesRegex(cap.CaptureBlocked, "own request cancelled"):
                cap.capture_once("lab2", self.review, self.root / "capture")
        self.assertTrue(queue.cancelled and not queue.finished)

    def test_malformed_own_grant_still_stops_and_quarantines(self):
        queue = FakeQueue(self.epoch, missing_token=True)
        calls = []
        current_status = self.status

        class FakeClient:
            def __init__(self, _config, access=None):
                assert access is None

            def request(self, path, *, method, payload=None):
                calls.append(path)
                if path == "/api/status":
                    return current_status
                if path == "/api/stop":
                    queue.stop_seen = True
                    return {"stopped": True, "recoveryRequired": False}
                raise AssertionError("unexpected guest request")

        with (patch("scripts.ensure_guest_agent.ensure"),
              patch.object(cap.HostConfig, "load", return_value=object()),
              patch.object(cap, "ControlClient", FakeClient),
              patch.object(cap, "AccessQueue", return_value=queue),
              patch.object(cap, "_capture", side_effect=AssertionError("no capture authorized"))):
            with self.assertRaisesRegex(cap.CaptureBlocked, "issued grant token invalid"):
                cap.capture_once("lab2", self.review, self.root / "capture")
        self.assertTrue(queue.stop_seen and queue.cancelled and queue.finished)
        self.assertEqual(1, calls.count("/api/stop"))

    def test_capture_only_leased_and_stopped(self):
        self.exercise_capture()

    def test_capture_failure_still_stop_and_finish(self):
        self.exercise_capture(fail_capture=True)

    def test_stop_response_must_attest_release(self):
        for response in (
            {"stopped": False, "recoveryRequired": False},
            {"stopped": True, "recoveryRequired": True},
            {"stopped": True},
            {},
        ):
            with self.subTest(response=response):
                self.exercise_capture(stop_response=response)


if __name__ == "__main__":
    unittest.main()
