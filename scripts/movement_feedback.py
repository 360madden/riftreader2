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
_MAX_ACTION_READY_WAIT_SECONDS = 10.0
# Preserve the complete six-second post-action evidence window plus the
# worst-case reviewed 150 ms hold and a small dispatch margin.
_MIN_FAST_ACTION_ANCHOR_REMAINING_MILLISECONDS = 6_250.0
# A full-scan result is still technically fresh just before its five-second
# expiry. Require enough remaining lifetime to dispatch an action and receive
# the next fresh observation instead of arming on an almost-expired sample.
# Historical Lab2 full scan reached 3596.7ms while its separate fast source
# advanced; this full-only guard is not a claimed fix for that elapsed-budget run.
_MIN_FULL_ACTION_FRESHNESS_REMAINING_MILLISECONDS = 2_500.0
# A post-action observation can require three complete acquisition intervals:
# one scan that began before the action and is therefore unusable, one strict
# post-action barrier, and one later scan that proves the barrier was crossed.
# Observed ~1.45 second scans leave too little transport/poll margin at 4.5s.
# This changes only the bounded wait; all freshness, identity and advancement
# checks below remain unchanged.
_MAX_ACTION_WAIT_SECONDS = 6.0
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
    source_scope: str
    source_provenance: str
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
            "sourceScope": self.source_scope,
            "sourceProvenance": self.source_provenance,
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
        self._receipt_reader = receipt_reader or _movement_receipt
        self._monotonic = monotonic
        self._sleep = sleep
        self._ready_index = 0
        self._last_action_ready: MovementSample | None = None

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

    def wait_action_ready(
        self,
        timeout_seconds: float = _MAX_ACTION_READY_WAIT_SECONDS,
    ) -> MovementSample:
        """Wait until the selected source can cover one action and its feedback."""
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= _MAX_ACTION_READY_WAIT_SECONDS):
            _console._fail("movement-feedback-invalid-timeout")
        deadline = self._monotonic() + float(timeout_seconds)
        while True:
            try:
                receipt, data, gate = self._receipt_reader(self._pin, initial=False)
            except _console.Blocked as error:
                if str(error) != "live-receipt-not-fresh":
                    raise
            else:
                block = gate.get("sourceBlock")
                if block == "riftReader2":
                    inner_age = gate.get("effectiveInnerAgeMilliseconds")
                    inner_max = gate.get("freshnessTimeoutMilliseconds")
                    if (isinstance(inner_age, bool) or not isinstance(inner_age, (int, float))
                            or not math.isfinite(float(inner_age))
                            or isinstance(inner_max, bool) or not isinstance(inner_max, (int, float))
                            or not math.isfinite(float(inner_max))
                            or not 0 <= float(inner_age) < float(inner_max)):
                        _console._fail("movement-feedback-full-budget-invalid")
                    ready = float(inner_max) - float(inner_age) \
                        >= _MIN_FULL_ACTION_FRESHNESS_REMAINING_MILLISECONDS
                elif block == "fastObservation":
                    anchor_age = gate.get("anchorAgeMilliseconds")
                    anchor_max = gate.get("anchorMaxAgeMilliseconds")
                    if (isinstance(anchor_age, bool) or not isinstance(anchor_age, (int, float))
                            or not math.isfinite(float(anchor_age))
                            or isinstance(anchor_max, bool) or not isinstance(anchor_max, (int, float))
                            or not math.isfinite(float(anchor_max))
                            or not 0 <= float(anchor_age) <= float(anchor_max)):
                        _console._fail("movement-feedback-anchor-budget-invalid")
                    ready = float(anchor_max) - float(anchor_age) \
                        >= _MIN_FAST_ACTION_ANCHOR_REMAINING_MILLISECONDS
                else:
                    _console._fail("movement-feedback-source-unavailable")
                if ready and self._last_action_ready is not None:
                    # A later outer transport receipt can replay the same Lua
                    # frame. Never accept it as readiness for another pulse.
                    _require_prior_pin(self._pin, self._last_action_ready)
                    ready = _validate_next(self._last_action_ready, receipt) == "accept"
                if ready:
                    self._ready_index += 1
                    outer = receipt["observation"]["sequence"]
                    sample = _sample_from_receipt(
                        self._pin, receipt, data, self.evidence_dir,
                        f"ready-{self._ready_index}-{outer}")
                    self._last_action_ready = sample
                    return sample
            if self._monotonic() >= deadline:
                _console._fail("movement-feedback-anchor-budget-timeout")
            self._sleep(0.05)

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
                    # Delivery after the action is a causal HTTP barrier.
                    # An async full scan in a later receipt may still have
                    # started before the action. The barrier itself is never
                    # evidence of post-action movement.
                    _write_receipt(
                        self.evidence_dir,
                        f"barrier-{prior.outer_sequence}-{current_outer}",
                        data)
                    barrier_outer = current_outer
                    barrier_selected = _selected(receipt)
                    barrier_addon_sequence = barrier_selected["sequence"]
                    barrier_addon_clock = float(barrier_selected["clock"]["value"])
            # Only a later scoped-fast scan is guaranteed to have started
            # after this HTTP barrier: the reader performs that scan in its
            # next publication iteration, unlike a pending async full scan.
            elif (_validate_advancing(prior, receipt, completed) == "accept"
                    and receipt.get("_movementSource") == "fast"
                    and current_outer > barrier_outer
                    and _selected(receipt)["sequence"] > barrier_addon_sequence
                    and float(_selected(receipt)["clock"]["value"])
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
    selected = _selected(current)
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
    selected = _selected(current)
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
    selected = _selected(receipt)
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
        source_scope=_source_scope(receipt)[0],
        source_provenance=_source_scope(receipt)[1],
        target={
            "processId": target["processId"],
            "processStartUtcTicks": target["processStartUtcTicks"],
            "executablePath": target["executablePath"],
            "executableSha256": target["executableSha256"],
        },
        raw_receipt_path=path.resolve(),
        raw_receipt_sha256=digest,
    )


def _source_scope(receipt: dict) -> tuple[str, str]:
    chosen = receipt.get("_movementSource")
    if chosen == "full":
        return "whole-readable-private", "nonce-bound-complete-process-scan/1"
    if chosen == "fast":
        fast = receipt["observation"]["fastObservation"]
        return fast["scan"]["scope"], fast["provenance"]
    report = receipt["observation"]["riftReader2"]
    if report.get("bindingStatus") == "bound" and report.get("freshnessStatus") == "fresh":
        return "whole-readable-private", "nonce-bound-complete-process-scan/1"
    fast = receipt["observation"].get("fastObservation")
    if isinstance(fast, dict) and fast.get("bindingStatus") == "bound-scoped" \
            and fast.get("freshnessStatus") == "fresh-scoped":
        return fast["scan"]["scope"], fast["provenance"]
    _console._fail("movement-feedback-source-unavailable")


def _selected(receipt: dict) -> dict:
    chosen = receipt.get("_movementSource")
    if chosen in ("full", "fast"):
        return (receipt["observation"]["riftReader2"]["observation"]
                if chosen == "full"
                else receipt["observation"]["fastObservation"]["observation"])
    scope, _ = _source_scope(receipt)
    return (receipt["observation"]["riftReader2"]["observation"]
            if scope == "whole-readable-private"
            else receipt["observation"]["fastObservation"]["observation"])


def _selected_contract(value) -> bool:
    return isinstance(value, dict) \
        and set(value) == {"schemaVersion", "addonVersion", "sequence", "epoch",
                           "clock", "player", "fields"} \
        and set(value.get("clock", {})) == {"status", "value"} \
        and set(value.get("player", {})) == {"status", "value"}


def _movement_receipt(pin: dict, *, initial: bool) -> tuple[dict, bytes, dict]:
    """Validate both sources and explicitly carry the newest accepted source."""
    _console._validate_receiver_host(pin["receiver"])
    path = Path(pin["receiptPath"])
    data = _console._read_regular(
        path, _console._live_gate.MAX_RECEIPT_BYTES, "live-receipt-unavailable")
    if initial and hashlib.sha256(data).hexdigest() != pin["receiptSha256"].lower():
        _console._fail("live-receipt-sha256-mismatch")
    return _validate_movement_receipt_bytes(pin, data)


def _validate_movement_receipt_bytes(pin: dict, data: bytes, *,
                                     now_monotonic_ns=None, now_utc=None
                                     ) -> tuple[dict, bytes, dict]:
    """Reuse the same source gates for immutable receiver-time journal replay.

    Live movement callers omit time overrides and remain current-time gated.
    """
    receipt = _console._strict_json_bytes(data, "invalid-live-receipt")
    if set(receipt) != {"schemaVersion", "receiverInstance", "receivedAtUtc",
            "receivedMonotonicNs", "sourceAddress", "observation", "gameReady", "note"}:
        _console._fail("unexpected-live-receipt-fields")
    reader, receiver = pin.get("reader"), pin.get("receiver")
    if not isinstance(reader, dict) or set(reader) != {"processId", "processStartUtcTicks",
            "executableSha256", "instanceId", "nonce", "sourceAddress"}:
        _console._fail("invalid-reader-pin")
    observation = receipt.get("observation")
    required = {"schemaVersion", "instanceId", "nonce", "sequence", "capturedAtUtc",
        "monotonicMilliseconds", "readerStatus", "readerReason", "target", "riftReader2",
        "delivery", "nativePower"}
    if not isinstance(observation, dict) or not required.issubset(observation) \
            or set(observation) - required - {
                "fastObservation", "fastObservationDiagnostic"}:
        _console._fail("unexpected-live-observation-fields")
    if receipt.get("sourceAddress") != reader["sourceAddress"] \
            or observation.get("instanceId") != reader["instanceId"]:
        _console._fail("live-reader-identity-mismatch")
    target = observation.get("target")
    if not isinstance(target, dict) or set(target) != {"processId", "processStartUtcTicks",
            "executablePath", "executableSha256", "readerSessionNonce"}:
        _console._fail("unexpected-live-target-fields")
    expected = pin.get("gameIdentity")
    if not isinstance(expected, dict) or set(expected) != {"processId", "processStartUtcTicks",
            "executablePath", "executableSha256"}:
        _console._fail("invalid-source-pin")
    if any(target.get(key).casefold() != value.casefold()
            if key in ("executablePath", "executableSha256") else target.get(key) != value
            for key, value in expected.items()):
        _console._fail("live-target-identity-mismatch")

    accepted = {}
    try:
        full_gate = _console._live_gate.evaluate_receipt(
            receipt, reader["nonce"], receiver["instanceId"],
            now_monotonic_ns=now_monotonic_ns, now_utc=now_utc)
        if _selected_contract(observation["riftReader2"].get("observation")):
            accepted["full"] = full_gate
    except _console._live_gate.GateError:
        pass
    if "fastObservation" in observation:
        try:
            fast_gate = _console._live_gate.evaluate_fast_observation(
                receipt, reader["nonce"], receiver["instanceId"],
            now_monotonic_ns=now_monotonic_ns, now_utc=now_utc)
            if _selected_contract(observation["fastObservation"].get("observation")):
                accepted["fast"] = fast_gate
        except _console._live_gate.GateError:
            pass
    if not accepted:
        _console._fail("live-receipt-not-fresh")

    chosen = "full" if "full" in accepted else "fast"
    if set(accepted) == {"full", "fast"}:
        full = observation["riftReader2"]["observation"]
        fast = observation["fastObservation"]["observation"]
        if fast["epoch"] != full["epoch"] \
                or fast["player"]["value"] != full["player"]["value"]:
            _console._fail("movement-feedback-source-conflict")
        full_position = (full["sequence"], float(full["clock"]["value"]))
        fast_position = (fast["sequence"], float(fast["clock"]["value"]))
        if fast_position[0] > full_position[0] and fast_position[1] > full_position[1]:
            chosen = "fast"
        elif full_position[0] > fast_position[0] and full_position[1] > fast_position[1]:
            chosen = "full"
        elif full_position == fast_position and full != fast:
            _console._fail("movement-feedback-source-conflict")
        elif full_position != fast_position:
            _console._fail("movement-feedback-source-conflict")

    selected = (observation["riftReader2"]["observation"] if chosen == "full"
                else observation["fastObservation"]["observation"])
    if not _selected_contract(selected):
        _console._fail("unexpected-live-selected-fields")
    carried = copy.deepcopy(receipt)
    carried["_movementSource"] = chosen
    gate = dict(accepted[chosen])
    gate["sourceBlock"] = "riftReader2" if chosen == "full" else "fastObservation"
    return carried, data, gate


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
