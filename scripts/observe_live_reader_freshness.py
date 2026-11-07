"""Bounded no-input freshness observer for one exact RIFT live-reader epoch.

This tool only reads the pinned receiver receipt and writes evidence. It never
starts a reader, controls a VM, sends game input or promotes stale reader data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
for search in (ROOT, ROOT / "scripts"):
    if str(search) not in sys.path:
        sys.path.insert(0, str(search))

from scripts import addon_command_console as console
from scripts import build_live_source_pin as builder
from scripts import movement_feedback as feedback


class ObserverError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObserverError(reason)


def _int(value, name: str) -> int:
    require(type(value) in (int, str) and str(value).isdigit(), f"invalid-{name}")
    return int(value)


def _time(value: str) -> datetime:
    require(isinstance(value, str), "invalid-reader-expiry")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ObserverError("invalid-reader-expiry") from error
    require(parsed.tzinfo is not None, "invalid-reader-expiry")
    return parsed.astimezone(timezone.utc)


def validate_binding(pin: dict, summary: dict, *, now: datetime,
                     duration_seconds: float = 480, expiry_margin_seconds: float = 45
                     ) -> datetime:
    builder.validate_reader_summary(summary)
    require(pin.get("lab") == summary["lab"], "reader-lab-mismatch")
    reader, game, receiver = pin.get("reader"), pin.get("gameIdentity"), pin.get("receiver")
    require(all(isinstance(item, dict) for item in (reader, game, receiver)),
            "source-pin-invalid")
    require(reader.get("nonce") == summary["nonce"]
            and _int(reader.get("processId"), "reader-pid") == _int(summary["readerPid"], "reader-pid")
            and _int(reader.get("processStartUtcTicks"), "reader-start")
            == _int(summary["readerStartUtcTicks"], "reader-start")
            and str(reader.get("executableSha256", "")).casefold()
            == str(summary["readerSha256"]).casefold(), "reader-summary-pin-mismatch")
    require(_int(game.get("processId"), "game-pid") == _int(summary["gamePid"], "game-pid")
            and _int(game.get("processStartUtcTicks"), "game-start")
            == _int(summary["gameStartUtcTicks"], "game-start")
            and str(game.get("executableSha256", "")).casefold()
            == str(summary["gameSha256"]).casefold(), "game-summary-pin-mismatch")
    expected_receiver = summary["receiver"]
    require(_int(receiver.get("processId"), "receiver-pid")
            == _int(expected_receiver["pid"], "receiver-pid")
            and _int(receiver.get("processStartUtcTicks"), "receiver-start")
            == _int(expected_receiver["processStartUtcTicks"], "receiver-start"),
            "receiver-summary-pin-mismatch")
    require(type(duration_seconds) in (int, float) and math.isfinite(duration_seconds)
            and 480 <= duration_seconds <= 3600, "duration-must-be-at-least-480s")
    require(type(expiry_margin_seconds) in (int, float)
            and math.isfinite(expiry_margin_seconds)
            and expiry_margin_seconds >= 45, "expiry-margin-must-be-at-least-45s")
    expiry = _time(summary["expiresAtUtc"])
    require(now.tzinfo is not None and
            expiry > now.astimezone(timezone.utc)
            + timedelta(seconds=duration_seconds + expiry_margin_seconds),
            "reader-expiry-budget-insufficient")
    return expiry


def _publish(path: Path, value: dict) -> None:
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         prefix="." + path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            temp = Path(stream.name)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _planar_distance(first, current) -> float:
    return math.hypot(current.xyz[0] - first.xyz[0],
                      current.xyz[2] - first.xyz[2])


def observe(pin: dict, summary: dict, output_dir: Path, *,
            duration_seconds: float = 480, expiry_margin_seconds: float = 45,
            max_gap_seconds: float = 4.5, max_planar_drift: float = .05,
            clock=time.monotonic, now=lambda: datetime.now(timezone.utc),
            sleep=time.sleep, feedback_factory=None, receipt_reader=None) -> dict:
    require(type(max_gap_seconds) in (int, float) and math.isfinite(max_gap_seconds)
            and 0 < max_gap_seconds <= 4.5, "invalid-max-gap")
    require(type(max_planar_drift) in (int, float) and math.isfinite(max_planar_drift)
            and 0 <= max_planar_drift <= .5, "invalid-max-drift")
    expiry = validate_binding(pin, summary, now=now(),
                              duration_seconds=duration_seconds,
                              expiry_margin_seconds=expiry_margin_seconds)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir = output_dir / "raw"
    maker = feedback_factory or (lambda value, dest: feedback.PinnedFeedback(value, dest))
    read_receipt = receipt_reader or feedback._movement_receipt
    result = {"schemaVersion": 1, "status": "failed", "reason": "interrupted",
              "observerSideNoInputOnly": True, "lab": pin["lab"],
              "readerNonce": pin["reader"]["nonce"], "readerPid": pin["reader"]["processId"],
              "gamePid": pin["gameIdentity"]["processId"], "expiresAtUtc": expiry.isoformat(),
              "durationRequiredSeconds": duration_seconds, "expiryMarginSeconds": expiry_margin_seconds,
              "maxAllowedGapSeconds": max_gap_seconds, "acceptedSamples": 0,
              "transientUnavailableReads": 0}
    ledger_path = output_dir / "samples.jsonl"
    try:
        initial = maker(pin, evidence_dir).wait_initial(timeout_seconds=4.5)
        started, last = clock(), clock()
        previous = initial
        maximum_gap = 0.0
        maximum_capture_gap = 0.0
        with ledger_path.open("x", encoding="utf-8", newline="\n") as ledger:
            def record(sample, elapsed):
                row = {"index": result["acceptedSamples"], "elapsedSeconds": elapsed,
                       "sample": sample.to_dict()}
                ledger.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                ledger.flush()
                result["acceptedSamples"] += 1

            record(initial, 0.0)
            while True:
                current = clock()
                require(current - last < max_gap_seconds, "observation-gap-exceeded")
                require(expiry > now() + timedelta(seconds=expiry_margin_seconds),
                        "reader-expiry-margin-exceeded")
                try:
                    receipt, raw, _ = read_receipt(pin, initial=False)
                except console.Blocked as error:
                    reason = str(error)
                    if reason == "live-receipt-unavailable":
                        result["transientUnavailableReads"] += 1
                    elif reason != "live-receipt-not-fresh":
                        raise
                else:
                    if feedback._validate_next(previous, receipt) == "accept":
                        current = clock()
                        gap = current - last
                        require(0 <= gap < max_gap_seconds, "observation-gap-exceeded")
                        sample = feedback._sample_from_receipt(
                            pin, receipt, raw, evidence_dir,
                            f"observer-{result['acceptedSamples']:05d}")
                        require(_planar_distance(initial, sample) <= max_planar_drift,
                                "stationary-planar-drift")
                        require(sample.addon_epoch == initial.addon_epoch
                                and sample.player == initial.player, "observation-identity-changed")
                        capture_gap = (sample.captured_at_utc - previous.captured_at_utc).total_seconds()
                        require(0 < capture_gap < max_gap_seconds, "source-capture-gap-exceeded")
                        maximum_gap = max(maximum_gap, gap)
                        maximum_capture_gap = max(maximum_capture_gap, capture_gap)
                        last, previous = current, sample
                        record(sample, current - started)
                        if current - started >= duration_seconds:
                            require(expiry > now() + timedelta(seconds=expiry_margin_seconds),
                                    "reader-expiry-margin-exceeded")
                            require(clock() - current < max_gap_seconds,
                                    "observation-processing-gap-exceeded")
                            result.update(status="passed", reason=None,
                                          observedSeconds=current - started,
                                          maximumGapSeconds=maximum_gap,
                                          maximumCaptureGapSeconds=maximum_capture_gap,
                                          maximumAcceptanceGapSeconds=maximum_gap,
                                          sourceQualification="observer-side-480s")
                            break
                sleep(.2)
        result["ledgerSha256"] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    except (Exception, KeyboardInterrupt) as error:
        result["reason"] = str(error)
        result["status"] = "failed"
        if ledger_path.exists():
            result["ledgerSha256"] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        raise
    finally:
        _publish(output_dir / "summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pin", type=Path, required=True)
    parser.add_argument("--reader-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=480)
    args = parser.parse_args(argv)
    try:
        pin, _ = console.load_source_pin(args.source_pin)
        summary, _ = builder.read_json(args.reader_summary)
        result = observe(pin, summary, args.output_dir,
                         duration_seconds=args.duration_seconds)
        print(json.dumps({"status": result["status"], "output": str(args.output_dir.resolve()),
                          "acceptedSamples": result["acceptedSamples"]}))
        return 0
    except (OSError, ValueError, console.Blocked, RuntimeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
