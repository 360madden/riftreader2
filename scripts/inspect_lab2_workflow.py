"""Lab 2 only: pinned, queue-leased screenshot inspection; never sends game input.

Use preflight/capture/verify across process boundaries, or run for the same checks
in one process. A failed run is retained; choose a new output root to retry.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient, _capture
from scripts.ensure_controller import CONFIGS, QUEUE, _probe
from scripts.ensure_guest_agent import ensure as ensure_guest_agent, _check_waiting, _idle
from scripts.fresh_game_identity import query
from scripts.vm_console_native import Blocked, validate_config
from scripts.run_movement_session import ManagedPinnedHost, write_managed_host_plan, admit_lab2_inspection_host, load, sanitized
from scripts.control_host import HostConfig
from scripts.nav_access_queue import AccessQueue
from scripts.capture_lab_hp_screenshot import ready_epoch, idle_queue, await_release
from scripts import sample_current_native_vitals as vitals
from scripts.launch_live_reader import LABS

RESOURCE = "vm:rift-lab-2"
OWNER = "lab2-inspection"
OUTPUT_BASE = ROOT / "artifacts/e2e-latency-20261106"


class InspectionBlocked(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise InspectionBlocked(message)


def utc():
    return datetime.now(timezone.utc)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def publish(path, value):
    """Publish complete JSON without replacing an existing result."""
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(sanitized(value), stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows rename refuses to overwrite; hard-link publication is also
        # atomic/no-replace on platforms where rename could overwrite.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Timings:
    def __init__(self):
        self.rows = []

    @contextmanager
    def stage(self, name):
        start, before = time.perf_counter(), utc().isoformat()
        row = {"stage": name, "startMonotonic": start, "startUtc": before}
        try:
            yield
            row["status"] = "ok"
        except BaseException:
            row["status"] = "failed"
            raise
        finally:
            end = time.perf_counter()
            row.update(endMonotonic=end, endUtc=utc().isoformat(), elapsedSeconds=end-start)
            self.rows.append(row)


def output_root(path):
    path = Path(path)
    require(path.is_absolute(), "output must be absolute")
    require(path.parent == OUTPUT_BASE and path.name not in ("", ".", ".."),
            "output must be a direct run child of the canonical artifacts root")
    for candidate in (path, *path.parents):
        if candidate.exists():
            require(not candidate.is_symlink()
                    and not (getattr(candidate.lstat(), "st_file_attributes", 0) & 0x400),
                    "reparse output ancestry refused")
    require(path.resolve().parent == OUTPUT_BASE.resolve(), "output ancestry changed")
    return path.resolve()


def assert_owned(root):
    require(output_root(root) == root, "noncanonical run root")
    marker = load(root / "workflow-owner.json")
    require(marker == {"workflow": "lab2-inspection/1", "output": str(root)},
            "workflow output ownership missing")


def expected_game(state):
    return {"lab": "lab2", **{key: state["target"][key] for key in
            ("processId", "processStartUtcTicks", "executableSha256")}}


def fresh(host, state):
    config = host.config
    native = validate_config(config.vmx, config.vnc_port, config.vmrun,
                             config.output_directory, require_files=True)
    return query(native, state["vmIdentity"], expected_game(state), CONFIGS["lab2"])


def check_status(host, state):
    value = host.status(require_armed=False)
    require(value["guest"]["target"] == state["target"], "full target or geometry changed")
    require(ready_epoch(value, expected_game(state), RESOURCE) == state["epoch"],
            "pinned epoch changed")
    return value


def reopen(root, *, _admitted=None):
    assert_owned(root)
    state = load(root / "state.json")
    receipt = load(root / "state.sha256.json")
    require(digest(root / "state.json") == receipt.get("sha256"), "state hash changed")
    require(state.get("lab") == "lab2" and state.get("resource") == RESOURCE,
            "only Lab 2 is allowed")
    require(state.get("output") == str(root), "run root changed")
    plan_path = root / "managed-host-plan.json"
    require(digest(plan_path) == state.get("planSha256"), "managed plan hash changed")
    plan = load(plan_path)
    require(plan.get("lab") == "lab2" and plan.get("resource") == RESOURCE
            and Path(plan["configPath"]).resolve() == CONFIGS["lab2"].resolve()
            and Path(plan["database"]).resolve() == QUEUE.resolve(), "noncanonical Lab 2 plan")
    if _admitted is None:
        return state, ManagedPinnedHost(plan_path)
    require(_admitted.get("root") == root
            and _admitted.get("planSha256") == digest(plan_path)
            and _admitted.get("stateSha256") == digest(root / "state.json"),
            "in-process admission root, plan or state changed")
    host = _admitted["host"]
    require(host.plan_path == plan_path and host.plan == plan
            and host.config == HostConfig.load(CONFIGS["lab2"])
            and host.plan.get("vmIdentity") == state["vmIdentity"]
            and host.target == {key: state["target"][key] for key in
                 ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")},
            "in-process admission bindings changed")
    host.check()
    return state, host


def require_persistent_capabilities(status):
    guest = status.get("guest") if isinstance(status, dict) else None
    guest = guest if isinstance(guest, dict) else {}
    for key, code in (("freshIdentityVersion", "fresh-identity-unsupported"),
                      ("nativeVitalsVersion", "native-vitals-unsupported")):
        value = guest.get(key)
        require(type(value) is int and value == 1, code)


def ensure_inspection_dependency():
    # This observation grants no authority; managed admission still performs
    # its full independent proofs immediately afterwards.
    config = HostConfig.load(CONFIGS["lab2"])
    lab = LABS["lab2"]
    require(config.expected_machine_name == lab["machine"] and config.vmx is not None
            and config.vmx.resolve() == lab["vmx"].resolve()
            and config.vnc_port == lab["port"] and config.ui_port == 49921,
            "noncanonical Lab 2 controller configuration")
    status = _probe(config)
    if status is not None:
        _check_waiting(status)
        host = status["host"]
        require(host["coordination"].get("resource") == RESOURCE,
                "controller resource differs from Lab 2")
        if host.get("connected") is True:
            require(host.get("machineName") == lab["machine"], "controller guest differs from Lab 2")
        else:
            require(not status.get("guest"), "disconnected controller has guest state")
        if _idle(status):
            return
    ensure_guest_agent("lab2")


def preflight(root, timing, *, _admitted=None, _native=None):
    root.mkdir(parents=True, exist_ok=False)
    publish(root / "workflow-owner.json", {"workflow": "lab2-inspection/1", "output": str(root)})
    with timing.stage("dependency-ensure"):
        if _admitted is None:
            ensure_guest_agent("lab2")
        else:
            ensure_inspection_dependency()
    with timing.stage("managed-plan-admission"):
        if _admitted is None:
            path = write_managed_host_plan("lab2", root)
        else:
            host = admit_lab2_inspection_host(root)
            _admitted.update(host=host, root=root)
            path = host.plan_path
    with timing.stage("managed-host-admission"):
        if _admitted is None:
            host = ManagedPinnedHost(path)
        status = host.status(require_armed=False)
        if _native is not None and _native.get("mode") == "persistent":
            require_persistent_capabilities(status)
    state = {"version": 1, "lab": "lab2", "resource": RESOURCE, "output": str(root),
             "createdAtUtc": utc().isoformat(), "planSha256": digest(path),
             "vmIdentity": host.plan["vmIdentity"], "target": status["guest"]["target"]}
    state["epoch"] = ready_epoch(status, expected_game(state), RESOURCE)
    if _native is not None:
        state["nativeRequest"] = dict(_native)
        if _native.get("mode") == "persistent":
            state["nativeRequest"]["agentInstanceId"] = host.plan["guestInstance"]
    with timing.stage("fresh-identity"):
        fresh(host, state)
    with timing.stage("final-preflight-status"):
        final_status = check_status(host, state)
        if _native is not None and _native.get("mode") == "persistent":
            require_persistent_capabilities(final_status)
    publish(root / "state.json", state)
    publish(root / "state.sha256.json", {"sha256": digest(root / "state.json")})
    if _admitted is not None:
        _admitted.update(root=root, host=host, planSha256=digest(path),
                         stateSha256=digest(root / "state.json"))
    return {"status": "preflight-passed", "epoch": state["epoch"]}


def native_options(args):
    values = (args.native_reader, args.native_reader_sha256, args.guest_reader)
    if args.native_vitals:
        require(args.phase == "run", "native acquisition is supported only by run")
        require(all(value is None for value in values), "persistent native vitals and reader options are mutually exclusive")
        return {"mode": "persistent"}
    require(all(value is not None for value in values) or all(value is None for value in values),
            "native options must be supplied together")
    if values[0] is None:
        return None
    require(args.phase == "run", "native acquisition is supported only by run")
    reader = Path(args.native_reader)
    require(reader.is_absolute() and reader.name == "RiftReader2.Live.exe"
            and reader.is_file() and not reader.is_symlink(), "native reader path invalid")
    sha = vitals.checked_sha(args.native_reader_sha256)
    require(digest(reader) == sha, "native reader SHA mismatch")
    guest = vitals.checked_guest_reader("lab2", args.guest_reader)
    return {"mode": "explicit-reader", "reader": str(reader.resolve()), "readerSha256": sha, "guestReader": guest}


def validate_native(summary, state, before, after):
    request = state["nativeRequest"]
    require(summary.get("status") == "candidate-only" and summary.get("lab") == "lab2"
            and summary.get("vmIdentity") == state["vmIdentity"]
            and summary.get("gameProcessId") == state["target"]["processId"]
            and summary.get("gameProcessStartUtcTicks") == state["target"]["processStartUtcTicks"]
            and summary.get("gameSha256") == state["target"]["executableSha256"], "native summary pin mismatch")
    if request.get("mode") == "persistent":
        require(summary.get("transport") == "persistent-control-agent"
                and isinstance(request.get("agentInstanceId"), str)
                and summary.get("activeAgentInstanceId") == request["agentInstanceId"],
                "persistent native agent binding mismatch")
    else:
        require(summary.get("readerExecutableSha256") == request["readerSha256"]
                and summary.get("guestReaderPath") == request["guestReader"]
                and summary.get("guestReaderReused") is True, "native reader binding mismatch")
    source = Path(summary["sourceReport"])
    allowed = vitals.EVIDENCE / "lab2"
    require(source.is_absolute() and source.name == "samples.json"
            and source.parent.parent.resolve() == allowed.resolve()
            and source.resolve().parent.parent == allowed.resolve()
            and source.parent.name not in ("", ".", "..")
            and source.is_file() and not source.is_symlink() and not source.parent.is_symlink(),
            "native source path refused")
    for candidate in (source, *source.parents):
        require(not candidate.is_symlink()
                and not (getattr(candidate.lstat(), "st_file_attributes", 0) & 0x400),
                "native source reparse ancestry refused")
    raw = vitals.bounded_read(source, vitals.REPORT_MAX_BYTES)
    require(hashlib.sha256(raw).hexdigest().upper() == summary["sourceReportSha256"],
            "native source report hash mismatch")
    report = json.loads(raw.decode("utf-8-sig"), parse_constant=vitals.reject_nonfinite,
                        parse_float=vitals.finite_float)
    if request.get("mode") == "persistent":
        require(isinstance(report, dict) and report.get("contractVersion") == "native-current-vitals-candidate-sample/2",
                "native-vitals-report-contract-invalid")
        from scripts.fresh_native_vitals import validate_response_time
        validate_response_time(report, summary.get("observedAtUtc"), before, after)
    metrics = vitals.validate_report(report, pid=state["target"]["processId"],
                                     ticks=state["target"]["processStartUtcTicks"])
    require(metrics == summary.get("metrics"), "native summary metrics differ from source")
    row = report["observation"]
    start = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
    require(start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0)
            and before - timedelta(seconds=5) <= start <= end <= after + timedelta(seconds=5),
            "native UTC outside acquisition window")
    return metrics, end


def capture_native(root, timing, *, _admitted):
    with timing.stage("native-vitals-candidate"):
        state, host = reopen(root, _admitted=_admitted)
        check_status(host, state)
        fresh(host, state)
        request = state["nativeRequest"]
        before = utc()
        if request.get("mode") == "persistent":
            summary = persistent_native(host, state)
        else:
            summary = vitals.run("lab2", Path(request["reader"]), request["readerSha256"],
                                 request["guestReader"], expected_game(state), expected_vm=state["vmIdentity"])
        after = utc()
        validate_native(summary, state, before, after)
        fresh(host, state)
        check_status(host, state)
        publish(root / "native-vitals-receipt.json", {"summary": summary,
                "beforeUtc": before.isoformat(), "afterUtc": after.isoformat()})
        publish(root / "native-vitals-receipt.sha256.json",
                {"sha256": digest(root / "native-vitals-receipt.json")})


def persistent_native(host, state):
    from scripts.fresh_native_vitals import query as query_vitals
    config = host.config
    native = validate_config(config.vmx, config.vnc_port, config.vmrun,
                             config.output_directory, require_files=True)
    return query_vitals(native, state["vmIdentity"], expected_game(state), CONFIGS["lab2"])


def validate_capture(root, state, before, after):
    metadata = load(root / "capture" / "capture.json")
    require(metadata.get("target") == state["target"], "capture target or geometry changed")
    observed = datetime.fromisoformat(metadata["capturedAtUtc"].replace("Z", "+00:00"))
    require(observed.utcoffset() == timedelta(0)
            and before - timedelta(seconds=5) <= observed <= after + timedelta(seconds=5),
            "capture UTC outside its operation window")
    image = root / "capture" / "image.bmp"
    require(image.is_file() and not image.is_symlink() and image.stat().st_size <= 10*1024*1024,
            "capture image missing or oversized")
    data = image.read_bytes()
    require(data.startswith(b"BM") and len(data) >= 26, "invalid BMP")
    width, height = struct.unpack_from("<ii", data, 18)
    require(width == state["target"]["clientWidth"] and abs(height) == state["target"]["clientHeight"],
            "capture dimensions differ from pinned target")
    saved, artifact = metadata.get("savedImage", {}), metadata.get("artifact", {})
    actual = hashlib.sha256(data).hexdigest().upper()
    require(saved.get("path") == "image.bmp" and saved.get("sha256") == actual
            and artifact.get("sha256") == actual and saved.get("byteLength") == len(data)
            and artifact.get("byteLength") == len(data), "capture image integrity failure")
    return metadata


def capture(root, timing, *, _admitted=None):
    assert_owned(root)
    require(not (root / "capture-receipt.json").exists()
            and not (root / "capture").exists()
            and not (root / "capture-attempt.json").exists(), "capture phase already attempted")
    with timing.stage("capture-admission"):
        state, host = reopen(root, _admitted=_admitted)
        check_status(host, state)
        fresh(host, state)
    publish(root / "capture-attempt.json", {"startedAtUtc": utc().isoformat()})
    queue = AccessQueue(QUEUE)
    request_id = "lab2-inspect-" + uuid.uuid4().hex
    grant = None
    with timing.stage("queue-acquire"):
        with queue.dispatch_fence():
            idle_queue(queue, RESOURCE, state["epoch"])
            queue.submit(request_id, OWNER, "C", {RESOURCE: state["epoch"]},
                         estimated_ms=2000, ttl_ms=30000, max_ms=120000)
            try:
                grant = queue.dispatch(request_id=request_id)
                require(isinstance(grant, dict) and grant.get("request_id") == request_id,
                        "own queue grant unavailable")
            except BaseException:
                queue.cancel(request_id, OWNER)
                raise
    token = grant.get("token")
    success = False
    error = None
    before, after = utc(), utc()
    try:
        require(isinstance(token, str) and len(token) == 64
                and all(c in "0123456789abcdef" for c in token), "invalid issued grant")
        require(grant.get("lease", {}).get(RESOURCE, {}).get("epoch") == state["epoch"],
                "grant epoch changed")
        with timing.stage("capture-before-status"):
            check_status(host, state)
            queue.heartbeat(request_id, token)
        client = ControlClient(host.config, access={"request_id": request_id, "token": token})
        with timing.stage("screenshot"):
            before = utc()
            _capture(client, root / "capture")
            after = utc()
            validate_capture(root, state, before, after)
        with timing.stage("capture-after-identity-status"):
            fresh(host, state)
            check_status(host, state)
            queue.heartbeat(request_id, token)
        success = True
    except BaseException as exc:
        error = exc
    finally:
        with timing.stage("watchdog-stop-and-cleanup"):
            finished = False
            try:
                queue.finish(request_id, token, "succeeded" if success else "failed",
                             [str(root / "capture" / "capture.json")])
                finished = True
            except BaseException as exc:
                error = error or exc
                queue.cancel(request_id, OWNER)
            if _admitted is None:
                terminal = await_release(queue, request_id, RESOURCE, state["epoch"])
            else:
                terminal = await_release(queue, request_id, RESOURCE, state["epoch"], poll_seconds=0.025)
            if finished:
                require(terminal == ("succeeded" if success else "failed"),
                        "unexpected cleanup terminal outcome")
            released = idle_queue(queue, RESOURCE, state["epoch"])
            generation = grant.get("lease", {}).get(RESOURCE, {}).get("generation")
            require(type(generation) is int and released.get("generation") == generation + 1
                    and isinstance(released.get("cleanup_receipt"), str)
                    and bool(released["cleanup_receipt"]), "exact watchdog cleanup proof missing")
    if error:
        raise error
    with timing.stage("released-status"):
        check_status(host, state)
        idle_queue(queue, RESOURCE, state["epoch"])
    result = {"status": "captured-and-released", "requestId": request_id,
              "beforeUtc": before.isoformat(), "afterUtc": after.isoformat(),
              "metadataSha256": digest(root / "capture" / "capture.json"),
              "imageSha256": digest(root / "capture" / "image.bmp"), "epoch": state["epoch"]}
    result["watchdogCleanup"] = {"generation": released["generation"],
                                 "receipt": released["cleanup_receipt"], "stopVerified": True}
    publish(root / "capture-receipt.json", result)
    return result


def verify(root, timing, *, _admitted=None):
    require(not (root / "report.json").exists(), "verification already exists")
    with timing.stage("verify-admission-and-fresh-identity"):
        state, host = reopen(root, _admitted=_admitted)
        fresh(host, state)
        status = check_status(host, state)
        idle_queue(AccessQueue(QUEUE), RESOURCE, state["epoch"])
    with timing.stage("independent-artifact-verification"):
        receipt = load(root / "capture-receipt.json")
        require(receipt.get("status") == "captured-and-released"
                and receipt.get("epoch") == state["epoch"], "capture release receipt invalid")
        require(digest(root / "capture" / "capture.json") == receipt["metadataSha256"]
                and digest(root / "capture" / "image.bmp") == receipt["imageSha256"],
                "capture changed after cleanup")
        metadata = validate_capture(root, state, datetime.fromisoformat(receipt["beforeUtc"]),
                                    datetime.fromisoformat(receipt["afterUtc"]))
        native = None
        if "nativeRequest" in state:
            native_receipt = load(root / "native-vitals-receipt.json", limit=1024*1024)
            native_hash = load(root / "native-vitals-receipt.sha256.json")
            require(digest(root / "native-vitals-receipt.json") == native_hash.get("sha256"),
                    "native receipt changed")
            metrics, completed = validate_native(native_receipt["summary"], state,
                datetime.fromisoformat(native_receipt["beforeUtc"]),
                datetime.fromisoformat(native_receipt["afterUtc"]))
            captured = datetime.fromisoformat(metadata["capturedAtUtc"].replace("Z", "+00:00"))
            gap = (captured - completed).total_seconds()
            require(gap >= 0, "screenshot predates native observation")
            native = {"metrics": metrics, "completedAtUtc": completed.isoformat(),
                      "mode": state["nativeRequest"].get("mode", "explicit-reader"),
                      "sampleToScreenshotSeconds": gap,
                      "sourceReportSha256": native_receipt["summary"]["sourceReportSha256"],
                      "qualification": "candidate-only; semantics/passive-freshness/restart-unverified; UI review required"}
    if _admitted is not None:
        final_inventory(_admitted, timing)
    report = {"status": "verified-awaiting-visual-review", "lab": "lab2", "epoch": state["epoch"],
              "target": state["target"], "image": str(root / "capture" / "image.bmp"),
              "captureId": metadata["captureId"], "capturedAtUtc": metadata["capturedAtUtc"],
              "finalStatus": status, "qualification": "read-only screenshot; visual review required"}
    report["inspectionMode"] = "bounded-direct-vm-with-inventory-brackets" if _admitted is not None else "full-inventory-every-admission"
    if _admitted is not None:
        report["finalInventory"] = _admitted["finalInventory"]
    if native is not None:
        report["nativeVitals"] = native
    publish(root / "report.json", report)
    return report


def final_inventory(admitted, timing):
    with timing.stage("final-full-inventory-and-managed-proofs"):
        admitted["host"].final_inventory_check()
        admitted["finalInventory"] = {"status": "passed", "checkedAtUtc": utc().isoformat(),
                                      "vmIdentity": admitted["host"].plan["vmIdentity"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "capture", "verify", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true", help="include full result and timing rows on stdout")
    parser.add_argument("--native-reader", type=Path)
    parser.add_argument("--native-reader-sha256")
    parser.add_argument("--guest-reader")
    parser.add_argument("--native-vitals", action="store_true", help="sample candidate vitals through the authenticated persistent Lab 2 agent")
    args = parser.parse_args(argv)
    timer = Timings()
    started, before = time.perf_counter(), utc().isoformat()
    root = None
    admitted = {} if args.phase == "run" else None
    try:
        root = output_root(args.output)
        native = native_options(args)
        with timer.stage("phase-total"):
            result = None
            try:
                for phase in (("preflight", "capture", "verify") if args.phase == "run" else (args.phase,)):
                    if phase == "preflight" and native is not None:
                        result = preflight(root, timer, _admitted=admitted, _native=native)
                        capture_native(root, timer, _admitted=admitted)
                    else:
                        result = globals()[phase](root, timer, _admitted=admitted)
            finally:
                if admitted is not None and "host" in admitted and "finalInventory" not in admitted:
                    original_failure = sys.exc_info()[0] is not None
                    try:
                        final_inventory(admitted, timer)
                    except Exception as final_error:
                        admitted["finalInventoryFailure"] = type(final_error).__name__
                        if not original_failure:
                            raise
        receipt = {"phase": args.phase, "status": "ok", "startUtc": before,
                   "endUtc": utc().isoformat(), "processId": os.getpid(),
                   "elapsedSeconds": time.perf_counter()-started, "stages": timer.rows}
        publish(root / (args.phase + "-timings.json"), receipt)
        console = {"status": result["status"], "phase": args.phase, "output": str(root),
                   "inspectionMode": "bounded-direct-vm-with-inventory-brackets" if admitted is not None else "full-inventory-every-admission",
                   "elapsedSeconds": receipt["elapsedSeconds"],
                   "timings": str(root / (args.phase + "-timings.json"))}
        if args.phase in ("run", "verify"):
            console.update(image=result["image"], report=str(root / "report.json"))
        if args.verbose:
            console.update(result=result, timing=receipt)
        print(json.dumps(console))
        return 0
    except Exception as exc:
        safe_capability = isinstance(exc, Blocked) and str(exc) in {
            "fresh-identity-unsupported", "native-vitals-unsupported"}
        failure = {"status": "blocked", "phase": args.phase, "errorType": type(exc).__name__,
                   "reason": str(exc) if isinstance(exc, InspectionBlocked) or safe_capability else "operation refused; inspect retained stage timings",
                   "startUtc": before, "endUtc": utc().isoformat(),
                   "elapsedSeconds": time.perf_counter()-started, "stages": timer.rows}
        if admitted is not None and "finalInventoryFailure" in admitted:
            failure["finalInventoryFailure"] = admitted["finalInventoryFailure"]
        if root is not None and root.is_dir():
            try:
                assert_owned(root)
                publish(root / (args.phase + "-failure.json"), failure)
            except (OSError, ValueError, RuntimeError):
                pass
        console = failure if args.verbose else {key: failure[key] for key in
                   ("status", "phase", "errorType", "reason", "elapsedSeconds")}
        if root is not None:
            console["output"] = str(root)
        print(json.dumps(console), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
