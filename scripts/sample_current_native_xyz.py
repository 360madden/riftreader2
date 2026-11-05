"""On-demand, no-input native XYZ candidate samples from one current-build RIFT lab.

Reuses the exact SHA-pinned .NET 10 sampler and a per-SHA guest helper copy.
An authenticated VMware session discovers the current game PID/epoch on every
call; old addresses, reader nonces, addon bindings, and input are not reused.
Reports are candidate-only; never substitute for independently fresh Lua XYZ.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal

GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
READER_SHA = "B8A725E6A9CE663C36CB836681ED660261B07FDA4118A0167262E92131B2373E"
READER = ROOT / "artifacts/native-current-sampler-20261105/publish/RiftReader2.Live.exe"
EVIDENCE = ROOT / "artifacts/native-current-sampler-20261105/runs"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def bounded_options(lab: str, samples: int, interval_ms: int) -> None:
    if lab not in ("lab1", "lab2") or type(samples) is not int or not 1 <= samples <= 30:
        raise ValueError("invalid-lab-or-sample-count")
    if type(interval_ms) is not int or not 0 <= interval_ms <= 2000:
        raise ValueError("invalid-sampling-interval")
    if (samples - 1) * interval_ms > 60_000:
        raise ValueError("sampling-delay-budget-exceeded")


def validate_report(report: dict, *, pid: int, ticks: int,
                    samples: int) -> dict:
    if (not isinstance(report, dict) or report.get("schemaVersion") != 1
            or report.get("contractVersion") != "native-current-position-candidate-samples/1"
            or report.get("qualification") != "candidate-only-not-passive-fresh-or-player-semantic-qualified"
            or report.get("status") != "complete"
            or report.get("sourceBuildSha256") != GAME_SHA
            or report.get("completedSamples") != samples
            or report.get("requestedSamples") != samples):
        raise ValueError("native-candidate-sample-report-invalid")
    identity = report.get("identity")
    if (not isinstance(identity, dict) or identity.get("processId") != pid
            or identity.get("processStartUtcTicks") != ticks
            or identity.get("executableSha256", "").upper() != GAME_SHA):
        raise ValueError("native-candidate-game-identity-mismatch")
    rows = report.get("observations")
    if not isinstance(rows, list) or len(rows) != samples:
        raise ValueError("native-candidate-sample-count-mismatch")
    prev_start = None
    previous_utc = None
    timings = []
    intervals = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("index") != number:
            raise ValueError("native-candidate-sample-sequence-invalid")
        xyz = (row.get("x"), row.get("y"), row.get("z"))
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in xyz):
            raise ValueError("native-candidate-sample-coordinate-invalid")
        start = row.get("monotonicStartMilliseconds")
        end = row.get("monotonicEndMilliseconds")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start or (prev_start is not None and start <= prev_start)):
            raise ValueError("native-candidate-sample-timing-invalid")
        try:
            begun = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
            finished = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError) as exc:
            raise ValueError("native-candidate-sample-clock-invalid") from exc
        if (begun.tzinfo is None or finished.tzinfo is None or finished < begun
                or (previous_utc is not None and begun <= previous_utc)):
            raise ValueError("native-candidate-sample-clock-invalid")
        timings.append(end - start)
        if prev_start is not None:
            intervals.append(start - prev_start)
        prev_start, previous_utc = start, begun
    return {
        "sampleCount": samples,
        "firstXyz": {axis: rows[0][axis.lower()] for axis in ("X", "Y", "Z")},
        "lastXyz": {axis: rows[-1][axis.lower()] for axis in ("X", "Y", "Z")},
        "maxReadMilliseconds": max(timings),
        "maxStartGapMilliseconds": max(intervals, default=None),
        "continuousCadenceUnder4Point5s": max(timings + intervals) < 4500,
        "positionChanged": any(
            any(row[axis] != rows[0][axis] for axis in ("x", "y", "z"))
            for row in rows[1:]),
        "qualification": report["qualification"]
    }


def run(lab: str, samples: int = 3, interval_ms: int = 400) -> dict:
    bounded_options(lab, samples, interval_ms)
    if not READER.is_file() or READER.is_symlink() or digest(READER) != READER_SHA:
        raise ValueError("published-native-reader-sha-or-path-mismatch")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\current-native-" + READER_SHA[:16]
    guest_exe = guest_root + r"\RiftReader2.Live.exe"
    guest_report = guest_root + r"\sample-" + token + ".json"
    guest_probe = guest_root + r"\identity-" + token + ".json"

    with api._session(config, settings, vm, output) as guest:
        preflight = (
            "$ErrorActionPreference='Stop';"
            "$folder=" + ps_literal(guest_root) + ";"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;"
            "if($sha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$exe=" + ps_literal(guest_exe) + ";"
            "$installed=Test-Path -LiteralPath $exe -PathType Leaf;"
            "if($installed -and (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
            + ps_literal(READER_SHA) + "){throw 'guest-reader-hash-collision'};"
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;"
            "sha=$sha;installed=[bool]$installed};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_probe) + ","
            "($data|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))"
        )
        guest.powershell(preflight, timeout=80)
        guest.copy_from_guest(guest_probe, output / "identity.json", timeout=50)
        identity = json.loads((output / "identity.json").read_text(encoding="utf-8-sig"))
        pid, ticks = identity["pid"], identity["ticks"]
        if (type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0
                or identity.get("sha") != GAME_SHA or type(identity.get("installed")) is not bool):
            raise ValueError("guest-native-sampler-identity-invalid")
        installed = identity["installed"]
        if not installed:
            guest.run("copyFileFromHostToGuest", str(READER), guest_exe, timeout=180)
        launch = (
            "$ErrorActionPreference='Stop';"
            "$exe=" + ps_literal(guest_exe) + ";"
            "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
            + ps_literal(READER_SHA) + "){throw 'guest-reader-sha-mismatch'};"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if($g.ProcessName -cne 'rift_x64' -or "
            "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
            + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
            "$out=" + ps_literal(guest_report) + ";"
            "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
            "& $exe sample-current-position --pid " + str(pid) + " --start-ticks " + str(ticks)
            + " --samples " + str(samples) + " --interval-ms " + str(interval_ms)
            + " --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
            "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'}"
        )
        guest.powershell(launch, timeout=130)
        guest.copy_from_guest(guest_report, output / "samples.json", timeout=70)
    raw = (output / "samples.json").read_bytes()
    parsed = json.loads(raw.decode("utf-8-sig"))
    metrics = validate_report(parsed, pid=pid, ticks=ticks, samples=samples)
    summary = {
        "schemaVersion": 1,
        "status": "candidate-only",
        "lab": lab,
        "vmIdentity": vm,
        "gameProcessId": pid,
        "gameProcessStartUtcTicks": ticks,
        "gameSha256": GAME_SHA,
        "readerExecutableSha256": READER_SHA,
        "guestReaderReused": installed,
        "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceReport": str(output / "samples.json"),
        "metrics": metrics,
        "limitation": "Current-process cached XYZ candidates only; independent player-motion and passive-freshness proof pending."
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=400)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.lab, args.samples, args.interval_ms)), flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:160]}), flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
