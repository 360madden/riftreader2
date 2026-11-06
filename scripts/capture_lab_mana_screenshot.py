"""Capture one foreground RIFT screenshot for visual Mana corroboration.

The operation is capture-only: it never arms the guest and sends no gameplay
input.  ``--run`` requires a recent, exact-build Mana descriptor receipt and
the receipt's hash-bound owner-after review.  A screenshot remains visual
evidence; this helper performs no OCR and does not qualify Mana semantics.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_lab_hp_screenshot import (
    CLEANUP_WAIT_SECONDS, CaptureBlocked, await_release, idle_queue, require,
    target_matches,
)
from scripts.control_client import ControlClient, _capture
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS, QUEUE
from scripts.nav_access_queue import AccessQueue
from scripts.nav_control_watchdog import bind_identity, resource_epoch
from scripts.probe_native_mana_descriptor import owner_mutable_observation
from scripts.probe_native_unit_manager import BUILD_SHA

MAX_REVIEW_AGE_SECONDS = 300
MANA_TYPE = "0x072A"
DESCRIPTOR_PROBE_SHA256 = "231B56A2B8B03B4181B4C4ED1EE92872D6D189589498548347421CA3C4C6C945"
OWNER_PROBE_SHA256 = "9326E2C23EAE05AF2900DBC5F6E9C78F8C9C3D4B9B222394FD4FF77AE695349A"
PROBE_SOURCES = {
    "descriptor": Path(__file__).resolve().with_name("probe_native_mana_descriptor.py"),
    "owner": Path(__file__).resolve().with_name("probe_native_unit_manager.py"),
}
EXACT_FINGERPRINT = {
    "typeCode": MANA_TYPE,
    "recordVtableRva": "0x2A6ACD8",
    "descriptorGetterRva": "0x1CCB460",
    "descriptorGlobalRva": "0x34D8990",
    "descriptorVtableRva": "0x2A7C418",
    "typeGetterRva": "0x1CF9F10",
}


def _require_probe_sources() -> None:
    expected = {"descriptor": DESCRIPTOR_PROBE_SHA256, "owner": OWNER_PROBE_SHA256}
    for name, path in PROBE_SOURCES.items():
        require(path.is_file() and not path.is_symlink(),
                f"reviewed {name} probe source must be a regular file")
        actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        require(actual == expected[name], f"reviewed {name} probe source changed")


def _receipt(path: Path) -> tuple[dict, str]:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 * 1024,
            "review must be a bounded regular file")
    raw = path.read_bytes()
    require(0 < len(raw) <= 1024 * 1024, "review must have bounded nonempty bytes")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise CaptureBlocked("duplicate JSON property in review: " + key)
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    except CaptureBlocked:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise CaptureBlocked("review JSON invalid") from exc
    require(isinstance(value, dict), "review JSON object required")
    return value, hashlib.sha256(raw).hexdigest().upper()


def require_recent(observed_at: object, now=None) -> None:
    try:
        require(isinstance(observed_at, str), "Mana observation timestamp invalid")
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        require(observed.tzinfo is not None and observed.utcoffset().total_seconds() == 0,
                "Mana observation timestamp must be UTC")
        age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    except (AttributeError, TypeError, ValueError) as exc:
        raise CaptureBlocked("Mana observation timestamp invalid") from exc
    require(-15 <= age <= MAX_REVIEW_AGE_SECONDS,
            "Mana owner review too old or future-dated for screenshot comparison")


def mana_review(lab: str, path: Path, now=None) -> dict:
    _require_probe_sources()
    require(lab == "lab1", "current Mana screenshot path is Lab1-only")
    path = path.resolve(strict=True)
    allowed = (ROOT / "artifacts/native-mana-descriptor" / lab).resolve()
    require(path.is_relative_to(allowed) and path.name == "review.json",
            "review must be retained same-lab Mana descriptor evidence")
    descriptor, descriptor_sha = _receipt(path)
    identity = descriptor.get("identity")
    fingerprint = descriptor.get("fingerprint")
    require(descriptor.get("schemaVersion") == 1 and
            descriptor.get("status") == "type-checked-record-candidate" and
            descriptor.get("lab") == lab and isinstance(identity, dict) and
            isinstance(fingerprint, dict) and
            all(fingerprint.get(key) == value for key, value in EXACT_FINGERPRINT.items()),
            "Mana descriptor receipt is not type-checked")
    require(descriptor.get("probeSha256") == DESCRIPTOR_PROBE_SHA256 and
            descriptor.get("ownerProbeSha256") == OWNER_PROBE_SHA256,
            "Mana descriptor producer sources are not the reviewed files")
    require(identity.get("executableSha256") == BUILD_SHA and
            type(identity.get("processId")) is int and identity["processId"] > 0 and
            type(identity.get("processStartUtcTicks")) is int and
            identity["processStartUtcTicks"] > 0,
            "Mana descriptor process identity invalid")
    require(isinstance(descriptor.get("nativePlayerUnitId"), str) and
            descriptor["nativePlayerUnitId"].startswith("u"),
            "Mana descriptor player identity invalid")

    owner_dir = Path(descriptor.get("afterOwnerEvidence", "")).resolve(strict=True)
    owner_allowed = (ROOT / "artifacts/native-unit-manager" / lab).resolve()
    require(owner_dir.is_relative_to(owner_allowed) and owner_dir.parent == owner_allowed and
            not owner_dir.is_symlink(), "owner evidence is outside the same-lab evidence root")
    owner_path = owner_dir / "review.json"
    require(owner_path.is_file() and not owner_path.is_symlink(),
            "Mana owner review must be a regular file")
    expected_owner_sha = descriptor.get("afterOwnerReviewSha256")
    owner, actual_owner_sha = _receipt(owner_path)
    require(isinstance(expected_owner_sha, str) and len(expected_owner_sha) == 64 and
            actual_owner_sha == expected_owner_sha,
            "Mana owner review hash differs from descriptor receipt")
    resource = owner.get("resourceRecordCandidate")
    fields = resource.get("fields") if isinstance(resource, dict) else None
    require(owner.get("lab") == lab and owner.get("status") == "complete" and
            owner.get("sourceStableAtPublish") is True and
            owner.get("identity") == identity and
            owner.get("nativePlayerUnitId") == descriptor["nativePlayerUnitId"] and
            isinstance(owner.get("vmIdentity"), dict) and owner["vmIdentity"] and
            owner.get("readerSha256") == descriptor.get("readerSha256") and
            owner.get("workflowSha256") == descriptor.get("workflowSha256") and
            owner.get("probeSha256") == OWNER_PROBE_SHA256 and
            isinstance(resource, dict) and resource.get("kind") == 3 and
            resource.get("name") == "mana" and resource.get("inputsStable") is True and
            resource.get("recordVtableRva") == fingerprint.get("recordVtableRva") and
            resource.get("candidateDescriptorGetterRva") == fingerprint.get("descriptorGetterRva") and
            isinstance(fields, dict) and fields.get("revisionConsistent") is True,
            "Mana owner review is not bound to the descriptor receipt")
    try:
        mutable = owner_mutable_observation(owner)
    except ValueError as exc:
        raise CaptureBlocked("Mana owner review lacks a coherent value interval: " + str(exc)) from exc
    transition_status = resource["mutableTransition"].get("status")
    require(transition_status in ("unchanged", "coherent-cache-transition") and
            resource.get("mutableInputsChanged") is
            (transition_status == "coherent-cache-transition"),
            "Mana owner mutable transition status is inconsistent")
    current, maximum = fields.get("baseRaw"), fields.get("maximumRaw")
    require(type(current) is int and type(maximum) is int and
            0 < maximum < (1 << 31) and 0 <= current <= maximum,
            "Mana owner review lacks bounded raw values")
    observed = mutable["observedAtUtc"]
    require_recent(observed, now)
    return {
        "review": str(path), "ownerReview": str(owner_path),
        "descriptorReviewSha256": descriptor_sha, "ownerReviewSha256": actual_owner_sha,
        "descriptorProbeSha256": DESCRIPTOR_PROBE_SHA256,
        "ownerProbeSha256": OWNER_PROBE_SHA256,
        "observedAtUtc": observed, "processId": identity["processId"],
        "processStartUtcTicks": identity["processStartUtcTicks"],
        "executableSha256": BUILD_SHA, "vmIdentity": owner["vmIdentity"],
        "nativePlayerUnitId": descriptor["nativePlayerUnitId"],
        "rawManaCandidate": {"current": current, "maximum": maximum},
        "observationIntervalUtc": mutable["observationIntervalUtc"],
        "mutableTransition": {
            "status": transition_status,
            "secondaryRevision": mutable["secondaryRevision"],
            "recordRevision": mutable["fields"]["recordRevision"],
            "wrapperRevision": mutable["fields"]["wrapperRevision"],
        },
    }


def ready_epoch(status: dict, expected: dict, resource: str) -> str:
    require(isinstance(status, dict), "invalid controller status")
    host, guest = status.get("host"), status.get("guest")
    require(isinstance(host, dict) and isinstance(guest, dict),
            "missing controller/guest status")
    coordination = host.get("coordination")
    console = host.get("consoleReservation")
    supervisor = coordination.get("supervisor") if isinstance(coordination, dict) else None
    target = guest.get("target")
    require(host.get("connected") is True and host.get("vmIdentity") == expected["vmIdentity"] and
            isinstance(coordination, dict) and coordination.get("state") == "ready" and
            coordination.get("shutdownRequested") is False and
            coordination.get("safeToClose") is False and coordination.get("resource") == resource and
            isinstance(supervisor, dict) and supervisor.get("state") == "running" and
            supervisor.get("threadAlive") is True and
            supervisor.get("initialCleanupVerified") is True and
            supervisor.get("resource") == resource and isinstance(console, dict) and
            console.get("held") is True and console.get("required") is True and
            console.get("faulted") is False and console.get("closing") is False,
            "controller supervision or exact VM epoch not ready")
    require(guest.get("armed") is False and guest.get("busy") is False and
            guest.get("recoveryRequired") is False and guest.get("desktopInputsDown") == [] and
            isinstance(target, dict) and target.get("isForeground") is True and
            target_matches(target, expected),
            "guest is not idle/foreground or exact Mana process changed")
    epoch = resource_epoch(bind_identity(host, guest))
    require(supervisor.get("epoch") == epoch,
            "supervisor epoch differs from bound VM/game identity")
    return epoch


def capture_once(lab: str, review: dict, output: Path) -> dict:
    from scripts.ensure_guest_agent import ensure as ensure_guest_agent

    resource = "vm:rift-lab-" + lab[-1]
    _require_probe_sources()
    ensure_guest_agent(lab)
    require_recent(review["observedAtUtc"])
    config = HostConfig.load(CONFIGS[lab])
    stop_client = ControlClient(config)
    epoch = ready_epoch(stop_client.request("/api/status", method="GET"), review, resource)
    queue = AccessQueue(QUEUE)
    request_id = "mana-screenshot-" + uuid.uuid4().hex
    owner = "mana-screenshot"
    with queue.dispatch_fence():
        idle_queue(queue, resource, epoch)
        queue.submit(request_id, owner, "C", {resource: epoch},
                     estimated_ms=2000, ttl_ms=30000, max_ms=120000)
        try:
            grant = queue.dispatch()
        except Exception:
            queue.cancel(request_id, owner)
            raise
        if not isinstance(grant, dict) or grant.get("request_id") != request_id:
            queue.cancel(request_id, owner)
            raise CaptureBlocked("exact queue grant unavailable; own request cancelled")

    token = grant.get("token")
    success = stopped = finish_ok = cancelled = False
    result = error = None
    try:
        require(isinstance(token, str) and len(token) == 64 and
                all(ch in "0123456789abcdef" for ch in token),
                "issued grant token invalid")
        require(isinstance(grant.get("lease"), dict) and
                grant["lease"].get(resource, {}).get("epoch") == epoch,
                "granted lease epoch changed")
        client = ControlClient(config, access={"request_id": request_id, "token": token})
        require(ready_epoch(client.request("/api/status", method="GET"), review, resource) == epoch,
                "game epoch changed before capture")
        queue.heartbeat(request_id, token)
        require_recent(review["observedAtUtc"])
        result = _capture(client, output)
        _require_probe_sources()
        require_recent(review["observedAtUtc"])
        saved = json.loads((output / "capture.json").read_text(encoding="utf-8"))
        require(target_matches(saved.get("target"), review),
                "screenshot game identity differs from Mana review")
        require(ready_epoch(client.request("/api/status", method="GET"), review, resource) == epoch,
                "game epoch changed after capture")
        queue.heartbeat(request_id, token)
        success = True
    except Exception as exc:
        error = exc
    finally:
        try:
            response = stop_client.request("/api/stop", method="POST", payload={})
            require(isinstance(response, dict) and response.get("stopped") is True and
                    response.get("recoveryRequired") is False,
                    "guest STOP did not verify release")
            stopped = True
        except Exception as exc:
            error = error or (exc if isinstance(exc, CaptureBlocked) else
                              CaptureBlocked("guest STOP failed: " + type(exc).__name__))
        try:
            if not isinstance(token, str):
                raise CaptureBlocked("issued grant has no finish token")
            queue.finish(request_id, token, "succeeded" if success and stopped else "failed",
                         [str(output / "capture.json") if success else "screenshot failed or refused"])
            finish_ok = True
        except Exception as exc:
            error = error or CaptureBlocked("queue finish failed: " + type(exc).__name__)
            try:
                queue.cancel(request_id, owner)
                cancelled = True
            except Exception as cancel_error:
                error = CaptureBlocked("queue finish and own cancellation failed: " +
                                       type(cancel_error).__name__)
    if finish_ok or cancelled:
        try:
            terminal = await_release(queue, request_id, resource, epoch,
                                     wait_seconds=CLEANUP_WAIT_SECONDS)
            if finish_ok:
                require(terminal == ("succeeded" if success and stopped else "failed"),
                        "unexpected watchdog terminal outcome")
        except Exception as exc:
            error = error or exc
    if error:
        if isinstance(error, CaptureBlocked):
            raise error
        raise CaptureBlocked("capture failed closed: " + type(error).__name__) from error
    require(success and stopped and finish_ok and result is not None, "capture not successful")
    return {
        "lab": lab, "status": "captured-after-watchdog-release",
        "manaReview": review["review"], "manaOwnerReview": review["ownerReview"],
        "manaReviewSha256": review["descriptorReviewSha256"],
        "manaOwnerReviewSha256": review["ownerReviewSha256"],
        "manaDescriptorProbeSha256": review["descriptorProbeSha256"],
        "manaOwnerProbeSha256": review["ownerProbeSha256"],
        "nativeObservedAtUtc": review["observedAtUtc"],
        "nativeObservationIntervalUtc": review["observationIntervalUtc"],
        "nativeMutableTransition": review["mutableTransition"],
        "nativePlayerUnitId": review["nativePlayerUnitId"],
        "rawManaCandidate": review["rawManaCandidate"],
        "image": result["image"], "captureMetadata": result["capture"],
        "captureId": result["captureId"],
        "qualification": "screenshot-only; UI digits not automatically read",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1",), required=True)
    parser.add_argument("--mana-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true",
                        help="acquire one screenshot-only queue lease")
    args = parser.parse_args(argv)
    try:
        review = mana_review(args.lab, args.mana_review)
        output = args.output.resolve()
        allowed = (ROOT / "artifacts/native-mana-screenshots" / args.lab).resolve()
        require(output.parent == allowed and not output.exists(),
                "output must be a new child of artifacts/native-mana-screenshots/<lab>")
        if args.run:
            allowed.mkdir(parents=True, exist_ok=True)
            value = capture_once(args.lab, review, output)
        else:
            value = {"status": "dry-run", "lab": args.lab,
                     "manaReview": review["review"], "output": str(output),
                     "noControllerOrGameAction": True}
        print(json.dumps({"ok": True, "value": value}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__,
                          "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
