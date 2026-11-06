#!/usr/bin/env python3
"""Keep one prepared movement lease alive during explicit screenshot review.

This helper talks only to the local navigation queue. It cannot connect to the
control host, arm controls, or execute input. The reviewed runner remains the
owner of finishing its lease; this helper only heartbeats until a bounded local
window or the queue's already-pinned absolute deadline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from scripts.nav_access_queue import AccessQueue, QueueError


class ReviewLeaseError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReviewLeaseError(message)


def load(path: Path, *, limit=1024 * 1024) -> tuple[dict, str]:
    path = Path(path)
    require(not path.is_symlink(), "symbolic input is not allowed")
    path = path.resolve(strict=True)
    require(path.is_file() and path.stat().st_size <= limit,
            "missing or oversized JSON input")
    data = path.read_bytes()
    value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(
        ReviewLeaseError("nonfinite JSON")))
    require(isinstance(value, dict), "JSON object required")
    return value, hashlib.sha256(data).hexdigest().upper()


def find_request(queue, request_id):
    after = 0
    while True:
        page = queue.status(after_sequence=after, limit=100)
        found = next((row for row in page.get("requests", [])
                      if row.get("request_id") == request_id), None)
        if found is not None:
            return found
        after = page.get("next_sequence")
        if after is None:
            return None


def hold_review_lease(session_path: Path, *, interval_seconds=8.0,
                      max_seconds=110.0, queue_factory=AccessQueue,
                      monotonic=time.monotonic,
                      wall_ms=lambda: time.time_ns() // 1_000_000,
                      sleep=time.sleep) -> dict:
    require(isinstance(interval_seconds, (int, float)) and not isinstance(interval_seconds, bool)
            and math.isfinite(interval_seconds) and 1 <= interval_seconds <= 15,
            "heartbeat interval must be from 1 through 15 seconds")
    require(isinstance(max_seconds, (int, float)) and not isinstance(max_seconds, bool)
            and math.isfinite(max_seconds) and 1 <= max_seconds <= 110,
            "hold window must be from 1 through 110 seconds")
    session, session_sha = load(session_path)
    require(session.get("schemaVersion") == 1
            and session.get("evidenceKind") == "reviewed-movement-session/1",
            "reviewed movement session required")
    require(isinstance(session.get("hostPlan"), str) and session["hostPlan"],
            "host plan path is missing")
    host, host_sha = load(Path(session["hostPlan"]))
    require(host_sha == session.get("hostPlanSha256"), "host plan pin changed")
    database = host.get("database")
    require(isinstance(database, str) and Path(database).is_absolute(),
            "host plan queue database is invalid")
    require(isinstance(session.get("privateGrant"), str) and session["privateGrant"],
            "private grant path is missing")
    grant, _ = load(Path(session["privateGrant"]), limit=8192)
    require(set(grant) == {"request_id", "token"}, "private grant is invalid")
    lease_pin = session.get("lease")
    require(isinstance(lease_pin, dict)
            and grant["request_id"] == lease_pin.get("request_id"),
            "private grant differs from session")

    queue = queue_factory(database)
    record = queue.check(grant["request_id"], grant["token"])
    require(record.get("state") == "active"
            and record.get("request_id") == grant["request_id"]
            and type(record.get("deadline_ms")) is int
            and record.get("deadline_ms") == lease_pin.get("deadline_ms")
            and record.get("lease") == lease_pin.get("lease"),
            "active queue lease differs from session pin")
    remaining = (record["deadline_ms"] - wall_ms()) / 1000
    require(remaining > 1, "review lease is at its absolute deadline")
    started = monotonic()
    stop_at = started + min(float(max_seconds), remaining - 1)
    heartbeats = 0
    reason = "bounded-window-ended"
    while monotonic() < stop_at:
        try:
            heartbeat = queue.heartbeat(grant["request_id"], grant["token"])
        except QueueError:
            current = find_request(queue, grant["request_id"])
            if current is not None and current.get("state") in (
                    "cleanup", "succeeded", "failed", "cancelled", "expired"):
                reason = "lease-ended-by-owner-or-queue"
                break
            raise
        require(heartbeat.get("deadline_ms") == record["deadline_ms"]
                and heartbeat.get("expires_ms") <= record["deadline_ms"],
                "queue changed the pinned absolute deadline")
        heartbeats += 1
        delay = min(float(interval_seconds), stop_at - monotonic())
        if delay > 0:
            sleep(delay)
    return {"schemaVersion": 1, "status": "stopped", "reason": reason,
            "heartbeats": heartbeats, "heldSeconds": max(0.0, monotonic() - started),
            "sessionPlanSha256": session_sha,
            "absoluteDeadlineMs": record["deadline_ms"],
            "authorityAction": "heartbeat-only; no arm, input, finish, or cancel"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--session-plan", type=Path, required=True)
    result.add_argument("--interval-seconds", type=float, default=8.0)
    result.add_argument("--max-seconds", type=float, default=110.0)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        result = hold_review_lease(args.session_plan,
                                   interval_seconds=args.interval_seconds,
                                   max_seconds=args.max_seconds)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, json.JSONDecodeError, QueueError, ReviewLeaseError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)},
                         sort_keys=True, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
