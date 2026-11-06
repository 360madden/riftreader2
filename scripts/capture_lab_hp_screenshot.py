"""One-shot, queue-leased RIFT HP screenshot. Never arms or sends game input.

This is corroborating visual evidence only. It does not OCR or qualify native HP.
Default is a dry plan; --run requires a recent native type-checked HP review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient, _capture
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS, QUEUE
from scripts.nav_access_queue import AccessQueue, TERMINAL
from scripts.nav_control_watchdog import bind_identity, resource_epoch
from scripts.probe_native_unit_manager import BUILD_SHA

MAX_REVIEW_AGE_SECONDS = 300
CLEANUP_WAIT_SECONDS = 15


class CaptureBlocked(ValueError):
    """Fail closed; a screenshot is never authority for gameplay input."""


def require(condition, message):
    if not condition:
        raise CaptureBlocked(message)


def require_recent_review(review, now=None):
    try:
        observed = datetime.fromisoformat(review["observedAtUtc"].replace("Z", "+00:00"))
        age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        raise CaptureBlocked("native observation timestamp invalid") from exc
    require(-15 <= age <= MAX_REVIEW_AGE_SECONDS,
            "native review too old or future-dated for screenshot comparison")


def native_review(lab, path, now=None):
    path = Path(path).resolve(strict=True)
    allowed = (ROOT / "artifacts" / "native-unit-manager" / lab).resolve()
    require(path.is_relative_to(allowed) and path.name == "review.json",
            "review must be a retained native probe for this lab")
    require(path.stat().st_size <= 1024 * 1024, "oversized native review")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    hp = data.get("healthRecordCandidate")
    identity = data.get("identity")
    require(data.get("lab") == lab and data.get("status") == "complete"
            and isinstance(hp, dict) and isinstance(identity, dict),
            "missing complete same-lab native review")
    require(hp.get("status") == "type-checked-record-candidate"
            and hp.get("typeCode") == "0x2C2" and hp.get("inputsStable") is True
            and isinstance(hp.get("calculatedHealth"), dict)
            and hp["calculatedHealth"].get("status") == "calculated-candidate",
            "native HP candidate not type-checked/stable")
    candidate = hp["calculatedHealth"]
    current, maximum = candidate.get("current"), candidate.get("maximum")
    require(type(current) is int and type(maximum) is int
            and 0 < maximum < (1 << 31) and 0 <= current <= maximum,
            "native HP candidate lacks valid numeric current/maximum")
    require(identity.get("executableSha256") == BUILD_SHA
            and type(identity.get("processId")) is int and identity["processId"] > 0
            and type(identity.get("processStartUtcTicks")) is int
            and identity["processStartUtcTicks"] > 0,
            "unsupported native executable or process identity")
    require_recent_review(hp, now)
    return {
        "review": str(path), "observedAtUtc": hp["observedAtUtc"],
        "processId": identity["processId"],
        "processStartUtcTicks": identity["processStartUtcTicks"],
        "executableSha256": BUILD_SHA,
        "hpCandidate": hp["calculatedHealth"],
    }


def target_matches(target, expected):
    return (isinstance(target, dict)
            and target.get("processId") == expected["processId"]
            and target.get("processStartUtcTicks") == expected["processStartUtcTicks"]
            and target.get("executableSha256") == expected["executableSha256"])


def ready_epoch(status, expected, resource):
    require(isinstance(status, dict), "invalid controller status")
    host, guest = status.get("host"), status.get("guest")
    require(isinstance(host, dict) and isinstance(guest, dict),
            "missing controller/guest status")
    coordination = host.get("coordination")
    console = host.get("consoleReservation")
    supervisor = coordination.get("supervisor") if isinstance(coordination, dict) else None
    target = guest.get("target")
    require(host.get("connected") is True and isinstance(coordination, dict)
            and coordination.get("state") == "ready"
            and coordination.get("shutdownRequested") is False
            and coordination.get("safeToClose") is False
            and coordination.get("resource") == resource
            and isinstance(supervisor, dict) and supervisor.get("state") == "running"
            and supervisor.get("threadAlive") is True
            and supervisor.get("initialCleanupVerified") is True
            and supervisor.get("resource") == resource
            and isinstance(console, dict) and console.get("held") is True
            and console.get("required") is True
            and console.get("faulted") is False and console.get("closing") is False,
            "controller supervision/console not ready")
    require(guest.get("armed") is False and guest.get("busy") is False
            and guest.get("recoveryRequired") is False
            and guest.get("desktopInputsDown") == []
            and isinstance(target, dict) and target.get("isForeground") is True
            and target_matches(target, expected),
            "guest is not idle/foreground or exact native game identity changed")
    epoch = resource_epoch(bind_identity(host, guest))
    require(supervisor.get("epoch") == epoch, "supervisor epoch differs from bound VM/game identity")
    return epoch


def idle_queue(queue, resource, epoch):
    after = 0
    found = None
    while True:
        snapshot = queue.status(after_sequence=after, limit=100)
        matches = [r for r in snapshot["resources"] if r["name"] == resource]
        require(len(matches) == 1, "controller resource not uniquely registered")
        found = matches[0]
        require(found["epoch"] == epoch and not found["blocked"] and found["holder"] is None,
                "controller resource held, blocked or stale")
        require(not any(r["state"] in ("queued", "active", "cleanup")
                        and resource in r["specification"]["resources"]
                        for r in snapshot["requests"]),
                "navigation queue has competing work for this lab")
        after = snapshot["next_sequence"]
        if after is None:
            return found


def await_release(queue, request_id, resource, epoch, *, wait_seconds=CLEANUP_WAIT_SECONDS):
    deadline = time.monotonic() + wait_seconds
    last = None
    while time.monotonic() <= deadline:
        # Request may be beyond first 100 historical entries; page all.
        after = 0
        request = None
        while True:
            status = queue.status(after_sequence=after, limit=100)
            resource_rows = [r for r in status["resources"] if r["name"] == resource]
            require(len(resource_rows) == 1, "resource disappeared during cleanup")
            last = resource_rows[0]
            request = next((r for r in status["requests"]
                            if r["request_id"] == request_id), request)
            after = status["next_sequence"]
            if after is None:
                break
        if (request is not None and request["state"] in TERMINAL
                and last["epoch"] == epoch and last["blocked"] == 0
                and last["holder"] is None and last["cleanup_receipt"]):
            return request["state"]
        time.sleep(0.25)
    raise CaptureBlocked("watchdog release not verified; resource may remain quarantined")


def capture_once(lab, review, output):
    from scripts.ensure_guest_agent import ensure as ensure_guest_agent

    resource = "vm:rift-lab-" + lab[-1]
    # The guest dependency function also ensures the main-PC controller.
    ensure_guest_agent(lab)
    require_recent_review(review)
    config = HostConfig.load(CONFIGS[lab])
    stop_client = ControlClient(config)
    epoch = ready_epoch(stop_client.request("/api/status", method="GET"), review, resource)
    queue = AccessQueue(QUEUE)
    request_id = "hp-capture-" + uuid.uuid4().hex
    with queue.dispatch_fence():
        idle_queue(queue, resource, epoch)
        queue.submit(request_id, "hp-screenshot", "C", {resource: epoch},
                     estimated_ms=2000, ttl_ms=30000, max_ms=120000)
        try:
            grant = queue.dispatch()
        except Exception:
            queue.cancel(request_id, "hp-screenshot")
            raise
        if not isinstance(grant, dict) or grant.get("request_id") != request_id:
            # Never finish or stop another request's grant; retract only ours.
            queue.cancel(request_id, "hp-screenshot")
            raise CaptureBlocked("exact queue grant unavailable; own request cancelled")
    # The dispatch fence MUST be released before the blocking HTTP capture.
    # All validation of our issued grant belongs inside STOP/cleanup protection.
    token = grant.get("token")
    success = False
    stopped = False
    finish_ok = False
    cancelled = False
    result = None
    error = None
    try:
        require(isinstance(token, str) and len(token) == 64
                and all(ch in "0123456789abcdef" for ch in token),
                "issued grant token invalid")
        require(isinstance(grant.get("lease"), dict)
                and grant["lease"].get(resource, {}).get("epoch") == epoch,
                "granted lease epoch changed")
        client = ControlClient(config, access={"request_id": request_id, "token": token})
        require(ready_epoch(client.request("/api/status", method="GET"),
                            review, resource) == epoch, "game epoch changed before capture")
        queue.heartbeat(request_id, token)
        require_recent_review(review)
        result = _capture(client, output)
        require_recent_review(review)
        saved = json.loads((output / "capture.json").read_text(encoding="utf-8"))
        require(target_matches(saved.get("target"), review),
                "screenshot game identity differs from native review")
        require(ready_epoch(client.request("/api/status", method="GET"),
                            review, resource) == epoch, "game epoch changed after capture")
        queue.heartbeat(request_id, token)
        success = True
    except Exception as exc:
        error = exc
    finally:
        try:
            stop_response = stop_client.request("/api/stop", method="POST", payload={})
            require(isinstance(stop_response, dict)
                    and stop_response.get("stopped") is True
                    and stop_response.get("recoveryRequired") is False,
                    "guest STOP did not verify release")
            stopped = True
        except Exception as exc:
            error = error or (exc if isinstance(exc, CaptureBlocked) else
                              CaptureBlocked("guest STOP failed: " + type(exc).__name__))
        try:
            if not isinstance(token, str):
                raise CaptureBlocked("issued grant has no finish token")
            queue.finish(request_id, token,
                         "succeeded" if success and stopped else "failed",
                         [str(output / "capture.json") if success else "screenshot failed or refused"])
            finish_ok = True
        except Exception as exc:
            error = error or CaptureBlocked("queue finish failed: " + type(exc).__name__)
            # Owner-only revocation works even for a malformed token. It quarantines
            # an active grant for watchdog cleanup; it never attests release.
            try:
                queue.cancel(request_id, "hp-screenshot")
                cancelled = True
            except Exception as cancel_error:
                error = CaptureBlocked("queue finish and own cancellation failed: " +
                                       type(cancel_error).__name__)
    if finish_ok or cancelled:
        try:
            terminal = await_release(queue, request_id, resource, epoch)
            if finish_ok:
                require(terminal == ("succeeded" if success and stopped else "failed"),
                        "unexpected watchdog terminal outcome")
        except Exception as exc:
            error = error or exc
    if error:
        if isinstance(error, CaptureBlocked):
            raise error
        raise CaptureBlocked("capture failed closed: " + type(error).__name__) from error
    require(success and stopped and finish_ok and result is not None,
            "capture not successful")
    return {
        "lab": lab, "status": "captured-after-watchdog-release",
        "nativeReview": review["review"],
        "nativeObservedAtUtc": review["observedAtUtc"],
        "nativeHpCandidate": review["hpCandidate"],
        "image": result["image"], "captureMetadata": result["capture"],
        "captureId": result["captureId"],
        "qualification": "screenshot-only; UI digits not independently read",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--native-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="acquire queue lease and capture one BMP")
    args = parser.parse_args(argv)
    try:
        review = native_review(args.lab, args.native_review)
        output = args.output.resolve()
        allowed = (ROOT / "artifacts" / "native-hp-screenshots" / args.lab).resolve()
        require(output.parent == allowed and not output.exists(),
                "output must be a new direct child of artifacts/native-hp-screenshots/<lab>")
        if args.run:
            allowed.mkdir(parents=True, exist_ok=True)
            value = capture_once(args.lab, review, output)
        else:
            value = {"status": "dry-run", "lab": args.lab, "nativeReview": review["review"],
                     "output": str(output), "noControllerOrGameAction": True}
        print(json.dumps({"ok": True, "value": value}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__,
                          "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
