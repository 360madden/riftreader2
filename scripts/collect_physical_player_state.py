"""One no-input physical RIFT state read using existing native readers.

Independent context, XYZ and vitals readings share an exact host/process/module/self
owner. Not an atomic snapshot, live Lua reference or qualified gameplay telemetry.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import physical_rift
from scripts.compare_physical_player_context_pair import BUILD_SHA

HOST = "AMD-DESKTOP"
KINDS = ("player-context", "position", "vitals")


def require(ok, reason):
    if not ok:
        raise ValueError("physical-player-state-" + reason)


def pin(pid):
    require(socket.gethostname().upper() == HOST, "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    selection = physical_rift.select_physical(HOST, pid)
    target = selection.get("target")
    require(selection.get("status") == "ready"
            and selection.get("ownerHost") == HOST and isinstance(target, dict)
            and target.get("hostName") == HOST and target.get("processId") == pid
            and str(target.get("processStartUtcTicks", "")).isdecimal()
            and str(target.get("executableSha256", "")).upper() == BUILD_SHA
            and type(target.get("hwnd")) is int and target["hwnd"] > 0,
            "physical-process-identity-unavailable")
    return selection


def collect(pid, output_dir, *, samples=3, interval_ms=200):
    require(type(samples) is int and 2 <= samples <= 10
            and type(interval_ms) is int and 0 <= interval_ms <= 1000,
            "invalid-sampling-bounds")
    first = pin(pid)
    owner = first["target"]
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    require(not output_dir.exists() and output_dir.parent.is_dir(),
            "new-output-directory-required")
    output_dir.mkdir()
    results, module, self_key = {}, None, None
    for kind in KINDS:
        require(pin(pid)["target"] == owner, "epoch-changed-before-read")
        path = output_dir / (kind + ".json")
        result = physical_rift.read_native(first, kind, path,
                                           samples=samples, interval_ms=interval_ms)
        require(result.get("status") == "complete"
                and result.get("nativeRead") == kind
                and result.get("target") == owner
                and Path(result.get("nativeOutput", "")) == path,
                kind + "-read-unavailable")
        require(path.is_file() and not path.is_symlink()
                and 0 < path.stat().st_size <= 8_000_000,
                kind + "-source-unavailable")
        raw = path.read_bytes()
        report = json.loads(raw.decode("utf-8-sig"))
        identity = report.get("identity")
        require(isinstance(identity, dict)
                and identity.get("processId") == pid
                and str(identity.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                and str(identity.get("executableSha256", "")).upper() == BUILD_SHA
                and type(identity.get("moduleBaseAddress")) is int
                and type(identity.get("moduleSize")) is int
                and identity["moduleBaseAddress"] > 0 and identity["moduleSize"] > 0
                and report.get("status") == "complete"
                and report.get("completedSamples") == samples,
                kind + "-source-identity-invalid")
        current_module = (identity["moduleBaseAddress"], identity["moduleSize"])
        if module is None:
            module = current_module
        require(current_module == module, "module-owner-changed")
        values = result.get("nativeValues")
        require(isinstance(values, dict) and isinstance(values.get("unitKey"), str)
                and values["unitKey"].isdecimal() and int(values["unitKey"]) > 0,
                kind + "-self-key-unavailable")
        if self_key is None:
            self_key = values["unitKey"]
        require(values["unitKey"] == self_key, "self-key-changed")
        require(pin(pid)["target"] == owner, "epoch-changed-after-read")
        results[kind] = {
            "path": str(path), "sourceSha256": hashlib.sha256(raw).hexdigest().upper(),
            "samples": samples, "candidateValues": values,
            **({"burstSummary": result["nativeBurstSummary"]}
               if "nativeBurstSummary" in result else {}),
        }
    summary = {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-candidate/1",
        "status": "complete-candidate", "ownerHost": HOST, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": self_key, "sources": results,
        "qualification": ("Sequential read-only exact-PID/epoch/build/module/self-key "
                          "candidate correlation; NOT atomic, passive-fresh, independently "
                          "Lua-qualified, changed-state or restart-qualified."),
    }
    destination = output_dir / "summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")
    return destination, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=200)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-state-" + uuid.uuid4().hex))
    args = parser.parse_args(argv)
    try:
        path, report = collect(args.physical_pid, args.output_dir,
                               samples=args.samples, interval_ms=args.interval_ms)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}))
        return 2
    print(json.dumps({"status": report["status"], "summary": str(path),
                      "selfKeyCandidate": report["selfKeyCandidate"],
                      "sources": {k: v["sourceSha256"] for k, v in report["sources"].items()},
                      "qualification": report["qualification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
