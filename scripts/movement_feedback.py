"""Pinned, read-only movement feedback from a RiftReader2 live receipt.

This module does not start readers, send game input, or recover a control
session.  It turns the existing reviewed fast-source pin into immutable XYZ
samples and waits for strictly newer post-action evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Callable

_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)
import addon_command_console as _console


_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_MAX_INITIAL_WAIT_SECONDS = 4.5
_MAX_ACTION_WAIT_SECONDS = 4.5
_MAX_NEXT_WAIT_SECONDS = 3.0


@dataclass(frozen=True)
class MovementSample:
    lab: str
    xyz: tuple[float, float, float]
    received_at_utc: datetime
    captured_at_utc: datetime
    outer_sequence: int
    addon_sequence: int
    addon_epoch: int
    addon_clock: float
    player: str
    source_address: str
    reader_process_id: int
    reader_process_start_utc_ticks: int
    reader_executable_sha256: str
    reader_instance: str
    reader_nonce: str
    receiver_instance: str
    target: dict
    raw_receipt_path: Path
    raw_receipt_sha256: str

    def to_dict(self) -> dict:
        return {
            "lab": self.lab,
            "xyz": {"x": self.xyz[0], "y": self.xyz[1], "z": self.xyz[2]},
            "receivedAtUtc": self.received_at_utc.isoformat(),
            "capturedAtUtc": self.captured_at_utc.isoformat(),
            "outerSequence": self.outer_sequence,
            "addonSequence": self.addon_sequence,
            "addonEpoch": self.addon_epoch,
            "addonClock": self.addon_clock,
            "player": self.player,
            "sourceAddress": self.source_address,
            "readerProcessId": self.reader_process_id,
            "readerProcessStartUtcTicks": self.reader_process_start_utc_ticks,
            "readerExecutableSha256": self.reader_executable_sha256,
            "readerInstance": self.reader_instance,
            "readerNonce": self.reader_nonce,
            "receiverInstance": self.receiver_instance,
            "target": dict(self.target),
            "rawReceiptPath": str(self.raw_receipt_path),
            "rawReceiptSha256": self.raw_receipt_sha256,
        }


class PinnedFeedback:
    def __init__(
        self,
        pin: dict,
        evidence_dir: Path,
        *,
        receipt_reader: Callable[..., tuple[dict, bytes, dict]] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._pin = copy.deepcopy(pin)
        self.evidence_dir = Path(evidence_dir)
        self._receipt_reader = receipt_reader or _console._fast_receipt
        self._monotonic = monotonic
        self._sleep = sleep

    def read(self, label: str) -> MovementSample:
        receipt, data, _ = self._receipt_reader(self._pin, initial=False)
        return _sample_from_receipt(self._pin, receipt, data, self.evidence_dir, label)

    def wait_initial(
        self,
        timeout_seconds: float = _MAX_INITIAL_WAIT_SECONDS,
    ) -> MovementSample:
        """Wait boundedly for the pre-arm exact-pin receipt to become fresh."""
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= _MAX_INITIAL_WAIT_SECONDS):
            _console._fail("movement-feedback-invalid-timeout")
        deadline = self._monotonic() + float(timeout_seconds)
        while True:
            try:
                receipt, data, _ = self._receipt_reader(self._pin, initial=False)
            except _console.Blocked as error:
                if str(error) != "live-receipt-not-fresh":
                    raise
                if self._monotonic() >= deadline:
                    _console._fail("movement-feedback-timeout")
                self._sleep(0.05)
                continue
            return _sample_from_receipt(
                self._pin, receipt, data, self.evidence_dir, "initial")

    def wait_after(
        self,
        action_completed_at: datetime,
        prior: MovementSample,
        timeout_seconds: float = _MAX_ACTION_WAIT_SECONDS,
    ) -> MovementSample:
        if action_completed_at.tzinfo is None:
            _console._fail("movement-feedback-action-time-must-be-aware")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= _MAX_ACTION_WAIT_SECONDS):
            _console._fail("movement-feedback-invalid-timeout")
        _require_prior_pin(self._pin, prior)

        completed = action_completed_at.astimezone(timezone.utc)
        deadline = self._monotonic() + float(timeout_seconds)
        barrier_outer: int | None = None
        barrier_addon_sequence: int | None = None
        barrier_addon_clock: float | None = None
        while True:
            try:
                receipt, data, _ = self._receipt_reader(self._pin, initial=False)
            except _console.Blocked as error:
                if str(error) != "live-receipt-not-fresh":
                    raise
                if self._monotonic() >= deadline:
                    _console._fail("movement-feedback-timeout")
                self._sleep(0.05)
                continue

            current_outer = receipt["observation"]["sequence"]
            if barrier_outer is None:
                if _validate_barrier(prior, receipt, completed) == "accept":
                    # The receiver handled this POST after the action.  Because
                    # delivery is synchronous, a later outer sequence from the
                    # same pinned reader must belong to an iteration whose full
                    # scan began after this response, and therefore after the
                    # action.  This receipt is only the barrier; it is never
                    # promoted to post-action movement evidence itself.
                    _write_receipt(
                        self.evidence_dir,
                        f"barrier-{prior.outer_sequence}-{current_outer}",
                        data)
                    barrier_outer = current_outer
                    barrier_selected = _console._selected(receipt)
                    barrier_addon_sequence = barrier_selected["sequence"]
                    barrier_addon_clock = float(barrier_selected["clock"]["value"])
            elif (_validate_advancing(prior, receipt, completed) == "accept"
                    and current_outer > barrier_outer
                    and _console._selected(receipt)["sequence"] > barrier_addon_sequence
                    and float(_console._selected(receipt)["clock"]["value"])
                    > barrier_addon_clock):
                label = f"after-{prior.outer_sequence}-{current_outer}"
                return _sample_from_receipt(
                    self._pin, receipt, data, self.evidence_dir, label)
            if self._monotonic() >= deadline:
                _console._fail("movement-feedback-timeout")
            self._sleep(0.05)

    def wait_next(
        self,
        prior: MovementSample,
        timeout_seconds: float = _MAX_NEXT_WAIT_SECONDS,
    ) -> MovementSample:
        """Wait for a distinct fresh sample when no new input was sent."""
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= _MAX_NEXT_WAIT_SECONDS):
            _console._fail("movement-feedback-invalid-timeout")
        _require_prior_pin(self._pin, prior)
        deadline = self._monotonic() + float(timeout_seconds)
        while True:
            try:
                receipt, data, _ = self._receipt_reader(self._pin, initial=False)
            except _console.Blocked as error:
                if str(error) != "live-receipt-not-fresh":
                    raise
                if self._monotonic() >= deadline:
                    _console._fail("movement-feedback-timeout")
                self._sleep(0.05)
                continue
            if _validate_next(prior, receipt) == "accept":
                current_outer = receipt["observation"]["sequence"]
                return _sample_from_receipt(
                    self._pin, receipt, data, self.evidence_dir,
                    f"next-{prior.outer_sequence}-{current_outer}")
            if self._monotonic() >= deadline:
                _console._fail("movement-feedback-timeout")
            self._sleep(0.05)


def _validate_advancing(
    prior: MovementSample,
    current: dict,
    action_completed_at: datetime,
) -> str:
    """Return ``accept`` or ``wait``; permanent continuity failures raise."""
    observation = current["observation"]
    selected = _console._selected(current)
    outer = observation.get("sequence")
    addon_sequence = selected.get("sequence")
    addon_clock = selected.get("clock", {}).get("value")
    if type(outer) is not int or type(addon_sequence) is not int:
        _console._fail("movement-feedback-invalid-sequence")
    if (isinstance(addon_clock, bool) or not isinstance(addon_clock, (int, float))
            or not math.isfinite(float(addon_clock))):
        _console._fail("movement-feedback-invalid-clock")

    if selected.get("epoch") != prior.addon_epoch or \
            selected.get("player", {}).get("value") != prior.player:
        _console._fail("movement-feedback-continuity-lost")
    if outer < prior.outer_sequence or addon_sequence < prior.addon_sequence \
            or float(addon_clock) < prior.addon_clock:
        _console._fail("movement-feedback-continuity-lost")

    received = _console._parse_time(current["receivedAtUtc"])
    captured = _console._parse_time(observation["capturedAtUtc"])
    threshold = action_completed_at.astimezone(timezone.utc) + timedelta(
        seconds=_console._live_gate.CLOCK_SKEW_SECONDS)
    if (outer == prior.outer_sequence or addon_sequence == prior.addon_sequence
            or float(addon_clock) == prior.addon_clock
            or received < action_completed_at.astimezone(timezone.utc)
            or captured <= prior.captured_at_utc or captured < threshold):
        return "wait"
    return "accept"


def _validate_barrier(
    prior: MovementSample,
    current: dict,
    action_completed_at: datetime,
) -> str:
    """Accept an exact advancing delivery boundary, never movement evidence."""
    if _validate_next(prior, current) != "accept":
        return "wait"
    completed = action_completed_at.astimezone(timezone.utc)
    received = _console._parse_time(current["receivedAtUtc"])
    captured = _console._parse_time(current["observation"]["capturedAtUtc"])
    if received <= completed or captured <= completed:
        return "wait"
    return "accept"


def _validate_next(prior: MovementSample, current: dict) -> str:
    observation = current["observation"]
    selected = _console._selected(current)
    outer = observation.get("sequence")
    addon_sequence = selected.get("sequence")
    addon_clock = selected.get("clock", {}).get("value")
    if type(outer) is not int or type(addon_sequence) is not int:
        _console._fail("movement-feedback-invalid-sequence")
    if (isinstance(addon_clock, bool) or not isinstance(addon_clock, (int, float))
            or not math.isfinite(float(addon_clock))):
        _console._fail("movement-feedback-invalid-clock")
    if selected.get("epoch") != prior.addon_epoch or \
            selected.get("player", {}).get("value") != prior.player:
        _console._fail("movement-feedback-continuity-lost")
    if outer < prior.outer_sequence or addon_sequence < prior.addon_sequence \
            or float(addon_clock) < prior.addon_clock:
        _console._fail("movement-feedback-continuity-lost")
    captured = _console._parse_time(observation["capturedAtUtc"])
    if (outer == prior.outer_sequence or addon_sequence == prior.addon_sequence
            or float(addon_clock) == prior.addon_clock
            or captured <= prior.captured_at_utc):
        return "wait"
    return "accept"


def _require_prior_pin(pin: dict, prior: MovementSample) -> None:
    reader = pin.get("reader")
    receiver = pin.get("receiver")
    game = pin.get("gameIdentity")
    if not all(isinstance(value, dict) for value in (reader, receiver, game)):
        _console._fail("movement-feedback-invalid-pin")
    if prior.lab != pin.get("lab"):
        _console._fail("movement-feedback-prior-lab-mismatch")
    if (prior.receiver_instance != receiver.get("instanceId")
            or prior.reader_instance != reader.get("instanceId")
            or prior.reader_nonce != reader.get("nonce")
            or prior.source_address != reader.get("sourceAddress")
            or prior.reader_process_id != reader.get("processId")
            or prior.reader_process_start_utc_ticks != reader.get("processStartUtcTicks")
            or prior.reader_executable_sha256.casefold()
            != str(reader.get("executableSha256", "")).casefold()):
        _console._fail("movement-feedback-prior-reader-mismatch")
    for key, expected in game.items():
        actual = prior.target.get(key)
        if key in ("executablePath", "executableSha256"):
            if not isinstance(actual, str) or actual.casefold() != str(expected).casefold():
                _console._fail("movement-feedback-prior-target-mismatch")
        elif actual != expected:
            _console._fail("movement-feedback-prior-target-mismatch")


def _sample_from_receipt(
    pin: dict,
    receipt: dict,
    data: bytes,
    evidence_dir: Path,
    label: str,
) -> MovementSample:
    if not isinstance(label, str) or _LABEL.fullmatch(label) is None:
        _console._fail("movement-feedback-invalid-label")
    selected = _console._selected(receipt)
    player = selected.get("player", {})
    clock = selected.get("clock", {})
    if player.get("status") != "ok" or not isinstance(player.get("value"), str) \
            or clock.get("status") != "ok":
        _console._fail("movement-feedback-source-unavailable")
    fields = selected.get("fields")
    if not isinstance(fields, dict):
        _console._fail("movement-feedback-invalid-fields")
    xyz = tuple(_coordinate(fields, axis) for axis in ("X", "Y", "Z"))
    addon_clock = clock.get("value")
    if (isinstance(addon_clock, bool) or not isinstance(addon_clock, (int, float))
            or not math.isfinite(float(addon_clock))):
        _console._fail("movement-feedback-invalid-clock")
    if type(selected.get("sequence")) is not int or type(selected.get("epoch")) is not int:
        _console._fail("movement-feedback-invalid-sequence")

    path, digest = _write_receipt(evidence_dir, label, data)

    observation = receipt["observation"]
    target = observation["target"]
    return MovementSample(
        lab=pin["lab"],
        xyz=xyz,
        received_at_utc=_console._parse_time(receipt["receivedAtUtc"]),
        captured_at_utc=_console._parse_time(observation["capturedAtUtc"]),
        outer_sequence=observation["sequence"],
        addon_sequence=selected["sequence"],
        addon_epoch=selected["epoch"],
        addon_clock=float(addon_clock),
        player=player["value"],
        source_address=receipt["sourceAddress"],
        reader_process_id=pin["reader"]["processId"],
        reader_process_start_utc_ticks=pin["reader"]["processStartUtcTicks"],
        reader_executable_sha256=pin["reader"]["executableSha256"],
        reader_instance=observation["instanceId"],
        reader_nonce=observation["nonce"],
        receiver_instance=receipt["receiverInstance"],
        target={
            "processId": target["processId"],
            "processStartUtcTicks": target["processStartUtcTicks"],
            "executablePath": target["executablePath"],
            "executableSha256": target["executableSha256"],
        },
        raw_receipt_path=path.resolve(),
        raw_receipt_sha256=digest,
    )


def _write_receipt(evidence_dir: Path, label: str, data: bytes) -> tuple[Path, str]:
    path = evidence_dir / f"{label}-receipt.json"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        _console._fail("movement-feedback-evidence-exists")
    return path, hashlib.sha256(data).hexdigest()


def _coordinate(fields: dict, axis: str) -> float:
    value = fields.get(f"coord{axis}")
    if not isinstance(value, dict) or value.get("status") != "ok":
        _console._fail("movement-feedback-coordinate-unavailable")
    number = value.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)) \
            or not math.isfinite(float(number)):
        _console._fail("movement-feedback-invalid-coordinate")
    return float(number)
