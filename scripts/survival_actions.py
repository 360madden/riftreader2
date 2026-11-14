"""Fail-closed admission for nonce-bound physical survival button clicks.

The addon supplies protected-button rectangles in UIParent coordinates.  This
module never guesses their desktop/client mapping: a separately qualified basis
must provide the exact UIParent-to-client transform.  Native delivery is
injected so the owning CLI can keep process reservation and receipt policy in
one place.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


class SurvivalActionError(ValueError):
    pass


class SurvivalActionPreInputError(SurvivalActionError):
    """A protected action was refused before any survival input was sent."""

    pass


def _require(condition, reason):
    if not condition:
        raise SurvivalActionError(reason)


def _number(value, reason):
    _require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def _same(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right


@dataclass(frozen=True)
class ActionPin:
    host: str
    process_id: int
    process_start_ticks: int
    executable_sha256: str
    window_handle: str
    player_id: str
    target_id: str
    session_id: str

    @classmethod
    def from_values(cls, target, *, player_id, target_id, session_id):
        _require(isinstance(target, dict), "invalid-action-target")
        try:
            start_ticks = int(target.get("processStartUtcTicks"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise SurvivalActionError("invalid-action-pin") from exc
        result = cls(
            host=target.get("machineName"), process_id=target.get("processId"),
            process_start_ticks=start_ticks,
            executable_sha256=target.get("executableSha256"),
            window_handle=str(target.get("windowHandle", target.get("hwnd"))),
            player_id=player_id, target_id=target_id, session_id=session_id)
        _require(isinstance(result.host, str) and result.host
                 and type(result.process_id) is int and result.process_id > 0
                 and type(result.process_start_ticks) is int
                 and result.process_start_ticks > 0
                 and isinstance(result.executable_sha256, str)
                 and len(result.executable_sha256) == 64
                 and result.window_handle not in ("None", "0")
                 and isinstance(result.player_id, str) and result.player_id
                 and isinstance(result.target_id, str) and result.target_id
                 and isinstance(result.session_id, str)
                 and len(result.session_id) == 32,
                 "invalid-action-pin")
        return result


def _snapshot(report, pin):
    _require(isinstance(report, dict), "invalid-survival-report")
    frame = report.get("snapshot", report)
    _require(isinstance(frame, dict), "invalid-survival-frame")
    _require(report.get("ready", True) is True
             and report.get("telemetry", {}).get("ready", True) is True,
             "survival-telemetry-not-ready")
    _require(frame.get("status") == "observed", "survival-frame-not-observed")
    _require(_same(frame.get("sessionId"), pin.session_id), "survival-frame-nonce-mismatch")
    _require(_same(frame.get("playerId"), pin.player_id), "survival-frame-player-mismatch")
    _require(_same(frame.get("targetId"), pin.target_id), "survival-frame-target-mismatch")
    _require(type(frame.get("epoch")) is int and frame["epoch"] > 0
             and type(frame.get("sequence")) is int and frame["sequence"] > 0
             and _number(frame.get("frameTime"), "invalid-survival-frame-time") >= 0,
             "invalid-survival-frame-generation")
    return frame


def _action_rect(frame, action, *, ability_id=None, role=None):
    controls = frame.get("controls")
    _require(isinstance(controls, dict) and controls.get("space") == "UIParent",
             "survival-controls-not-visible")
    item = ((controls.get("actions") or {}).get(ability_id)
            if action == "cast" else controls.get("cancel") if action == "cancel" else None)
    _require(isinstance(item, dict) and item.get("mapped") is True,
             f"survival-{action}-not-mapped")
    if action == "cast":
        catalog = frame.get("catalog")
        action_ability = item.get("ability")
        _require(isinstance(item.get("readiness"), dict)
                 and item["readiness"].get("status") == "ready"
                 and item.get("visible") is True,
                 "survival-cast-not-ready")
        allowed_targets = ({frame.get("playerId")}
                           if role in ("heal", "defense") else {frame.get("targetId")})
        _require(role in ("heal", "defense", "interrupt", "damage")
                 and _same(item.get("abilityId"), ability_id)
                 and isinstance(action_ability, dict)
                 and _same(action_ability.get("idNew", action_ability.get("id")), ability_id)
                 and any(_same(action_ability.get("target"), target)
                         for target in allowed_targets),
                 "survival-cast-ability-mismatch")
        name = item.get("abilityName")
        sampled_at = catalog.get("sampledAt") if isinstance(catalog, dict) else None
        frame_time = frame.get("frameTime")
        _require(isinstance(name, str) and name
                 and item.get("uniqueLearnedName") is True
                 and item.get("macro") == "cast " + name + "\nstopattack",
                 "survival-cast-name-not-unique-current")
        _require(isinstance(catalog, dict)
                 and catalog.get("status") in ("observed", "available")
                 and type(sampled_at) in (int, float) and math.isfinite(sampled_at)
                 and type(frame_time) in (int, float) and math.isfinite(frame_time)
                 and 0 <= frame_time - sampled_at < 2,
                 "survival-catalog-proof-stale")
    else:
        _require(item.get("visible") is True
                 and item.get("macro") == "stopcasting\nstopattack"
                 and item.get("effectQualification") == "unverified",
                 "survival-cancel-contract-mismatch")
    return item, controls


def client_rectangle(frame, action, basis, target, *, ability_id=None, role=None):
    """Map one current protected rectangle using an explicit qualified basis."""
    item, controls = _action_rect(frame, action, ability_id=ability_id, role=role)
    _require(isinstance(basis, dict) and basis.get("qualified") is True
             and basis.get("space") == "UIParent-to-client-pixels",
             "ui-parent-client-basis-unqualified")
    _require(isinstance(target, dict), "invalid-action-target")
    viewport_width = _number(controls.get("viewportWidth"), "invalid-ui-parent-viewport")
    viewport_height = _number(controls.get("viewportHeight"), "invalid-ui-parent-viewport")
    _require(viewport_width > 0 and viewport_height > 0
             and _number(basis.get("viewportWidth"), "invalid-ui-parent-basis") == viewport_width
             and _number(basis.get("viewportHeight"), "invalid-ui-parent-basis") == viewport_height
             and basis.get("clientWidth") == target.get("clientWidth")
             and basis.get("clientHeight") == target.get("clientHeight"),
             "ui-parent-client-basis-mismatch")
    sx = _number(basis.get("scaleX"), "invalid-ui-parent-scale")
    sy = _number(basis.get("scaleY"), "invalid-ui-parent-scale")
    ox = _number(basis.get("offsetX"), "invalid-ui-parent-offset")
    oy = _number(basis.get("offsetY"), "invalid-ui-parent-offset")
    _require(sx > 0 and sy > 0, "invalid-ui-parent-scale")
    left = ox + _number(item.get("left"), "invalid-survival-action-rect") * sx
    top = oy + _number(item.get("top"), "invalid-survival-action-rect") * sy
    width = _number(item.get("width"), "invalid-survival-action-rect") * sx
    height = _number(item.get("height"), "invalid-survival-action-rect") * sy
    _require(width >= 4 and height >= 4, "survival-action-rect-too-small")
    mapped = {"x": int(round(left)), "y": int(round(top)),
              "width": int(round(width)), "height": int(round(height))}
    _require(mapped["x"] >= 0 and mapped["y"] >= 0
             and mapped["x"] + mapped["width"] <= target.get("clientWidth", -1)
             and mapped["y"] + mapped["height"] <= target.get("clientHeight", -1),
             "survival-action-rect-outside-client")
    # Native protected clicks intentionally accept only bounded rectangles.
    # Keep the producer's full control as the admission boundary, then use a
    # centered subrectangle so a large UIParent button retains the same click
    # center without widening the native/desktop allowlist.
    result = {"width": min(128, mapped["width"]),
              "height": min(128, mapped["height"])}
    result["x"] = mapped["x"] + (mapped["width"] - result["width"]) // 2
    result["y"] = mapped["y"] + (mapped["height"] - result["height"]) // 2
    return result


def _validate_receipt(receipt, pin, rect, action):
    _require(isinstance(receipt, dict) and receipt.get("trustedReceipt") is True,
             "untrusted-survival-action-receipt")
    _require(receipt.get("status") == "completed" and receipt.get("inputSent") is True
             and receipt.get("releaseSucceeded") is True
             and receipt.get("desktopInputsDown") == []
             and receipt.get("responseVerified") is False,
             "survival-action-delivery-or-release-unverified")
    _require(receipt.get("action") == action and receipt.get("rectangle") == rect
             and _same(receipt.get("nonce"), pin.session_id)
             and _same(receipt.get("playerId"), pin.player_id)
             and _same(receipt.get("targetId"), pin.target_id),
             "survival-action-receipt-binding-mismatch")
    target = receipt.get("target")
    _require(isinstance(target, dict)
             and _same(target.get("machineName"), pin.host)
             and target.get("processId") == pin.process_id
             and str(target.get("processStartUtcTicks")) == str(pin.process_start_ticks)
             and _same(target.get("executableSha256"), pin.executable_sha256)
             and str(target.get("windowHandle", target.get("hwnd"))) == pin.window_handle
             and target.get("clientWidth") is not None
             and target.get("clientHeight") is not None,
             "survival-action-receipt-target-mismatch")
    events = receipt.get("mouseSendEvents")
    _require(isinstance(events, list) and 2 <= len(events) <= 4
             and events[0].get("phase") == "button-down"
             and events[-1].get("phase") == "button-up",
             "survival-action-mouse-release-unverified")
    return receipt


class SurvivalActions:
    """One-reservation, one-attempt protected-button action owner."""

    def __init__(self, *, target, pin, basis, frame_reader, native_click,
                 reservation=None, stop_event=None, profile=None,
                 minimum_generation=None, monotonic=time.monotonic,
                 cancel_reference=None):
        self.target, self.pin, self.basis = target, pin, basis
        self.frame_reader, self.native_click = frame_reader, native_click
        self.reservation = reservation
        self.profile = profile
        self.stop = stop_event if stop_event is not None else threading.Event()
        self._cleanup_done = False
        self._cleanup_verified = False
        self._cleanup_uncertain = False
        self._cleanup_error = None
        self._cast_active = False
        self._last_generation = minimum_generation
        self._monotonic = monotonic
        self._cancel_admission = None
        self._cancel_reference = cancel_reference
        self._native_attempted = False

    @property
    def cleanup_verified(self):
        return self._cleanup_verified

    @property
    def cleanup_uncertain(self):
        return self._cleanup_uncertain

    @property
    def native_attempted(self):
        return self._native_attempted

    def _run(self, action, *, ability_id=None, allow_stopped=False):
        _require(allow_stopped or not self.stop.is_set(),
                 "survival-action-stopped-before-admission")
        context = self.reservation() if self.reservation is not None else nullcontext()
        with context as lease:
            if lease is not None and hasattr(lease, "check"):
                lease.check()
            _require(allow_stopped or not self.stop.is_set(),
                     "survival-action-stopped-before-frame")
            frame = _snapshot(self.frame_reader(), self.pin)
            generation = (frame["epoch"], frame["sequence"], float(frame["frameTime"]))
            if self._last_generation is not None:
                _require(generation[0] == self._last_generation[0]
                         and generation[1] > self._last_generation[1]
                         and generation[2] > self._last_generation[2],
                         "survival-action-frame-not-advancing")
            self._last_generation = generation
            role = next((name for name, value in (self.profile or {}).get("abilities", {}).items()
                         if value == ability_id), "damage" if self.profile is None else None)
            rect = client_rectangle(frame, action, self.basis, self.target,
                                    ability_id=ability_id, role=role)
            if action == "cast":
                # STOP cleanup must not wait for another producer frame.  Retain
                # the combined idempotent cancel control from this same admitted
                # frame; native still revalidates client/player/target at click.
                self._cancel_admission = {
                    "rectangle": client_rectangle(frame, "cancel", self.basis, self.target),
                    "epoch": frame["epoch"], "sequence": frame["sequence"],
                    "observedAt": self._monotonic()}
            _require(allow_stopped or not self.stop.is_set(),
                     "survival-action-stopped-before-click")
            action_id = ("controls.actions." + ability_id
                         if action == "cast" else "controls.cancel")
            self._native_attempted = True
            receipt = self.native_click(action=action, action_id=action_id,
                                        rectangle=rect, pin=self.pin,
                                        stop_event=self.stop)
            _require(allow_stopped or not self.stop.is_set(),
                     "survival-action-stopped-after-click")
            result = _validate_receipt(receipt, self.pin, rect, action)
            if action == "cast":
                from scripts.survival_live import outcome_baseline
                result.update(
                    admissionEpoch=frame["epoch"],
                    admissionSequence=frame["sequence"],
                    admissionFrameTime=float(frame["frameTime"]),
                    outcomeBaseline=outcome_baseline(frame))
            return result

    def _run_cached_cancel(self, admission):
        context = self.reservation() if self.reservation is not None else nullcontext()
        with context as lease:
            if lease is not None and hasattr(lease, "check"):
                lease.check()
            receipt = self.native_click(
                action="cancel", action_id="controls.cancel",
                rectangle=admission["rectangle"], pin=self.pin,
                stop_event=self.stop)
            return _validate_receipt(
                receipt, self.pin, admission["rectangle"], "cancel")

    def _consumer_cancel_admission(self):
        _require(callable(self._cancel_reference), "cancel-reference-unavailable")
        reference = self._cancel_reference(max_age_seconds=5.0)
        _require(isinstance(reference, dict)
                 and reference.get("status") == "cached-verified-cancel"
                 and _same(reference.get("sessionId"), self.pin.session_id)
                 and _same(reference.get("playerId"), self.pin.player_id)
                 and _same(reference.get("selectedTargetId"), self.pin.target_id)
                 and reference.get("epoch") == (self._last_generation or (None,))[0]
                 and type(reference.get("ageSeconds")) in (int, float)
                 and 0 <= reference["ageSeconds"] <= 5,
                 "cancel-reference-binding-mismatch")
        observed = reference.get("target")
        _require(isinstance(observed, dict)
                 and observed.get("processId") == self.pin.process_id
                 and str(observed.get("processStartUtcTicks")) == str(self.pin.process_start_ticks)
                 and _same(observed.get("executableSha256"), self.pin.executable_sha256),
                 "cancel-reference-target-mismatch")
        synthetic = {"controls": {
            "space": "UIParent", "viewportWidth": self.basis["viewportWidth"],
            "viewportHeight": self.basis["viewportHeight"],
            "cancel": reference.get("cancel")}}
        return {"rectangle": client_rectangle(
                    synthetic, "cancel", self.basis, self.target),
                "epoch": reference["epoch"], "sequence": reference.get("sourceSequence"),
                "observedAt": self._monotonic() - float(reference["ageSeconds"])}

    def cast(self, ability_id):
        _require(isinstance(ability_id, str) and ability_id,
                 "invalid-survival-ability-id")
        _require(not self._cast_active, "survival-cast-already-active")
        _require(not self._cleanup_done,
                 "survival-encounter-cleaned-begin-new-encounter-before-cast")
        self._cast_active = True
        try:
            return self._run("cast", ability_id=ability_id)
        finally:
            self._cast_active = False

    def cancel(self):
        """Click the combined stopcasting/stopattack control at most once."""
        if self._cleanup_done:
            if self._cleanup_verified:
                return {"status": "already-clean", "inputSent": False}
            detail = self._cleanup_error or "unknown-cleanup-failure"
            raise SurvivalActionError(
                "survival-cleanup-previously-failed-no-retry: " + str(detail))
        _require(not self._cast_active, "survival-cancel-before-cast-termination")
        self._cleanup_done = True
        admission = None
        if callable(self._cancel_reference):
            try:
                admission = self._consumer_cancel_admission()
            except Exception:
                admission = None
        if admission is None:
            admission = self._cancel_admission
        try:
            if (isinstance(admission, dict)
                    and self._monotonic() - admission["observedAt"] < 5):
                receipt = self._run_cached_cancel(admission)
            else:
                receipt = self._run("cancel", allow_stopped=True)
        except Exception as exc:
            # No input retry.  If the retained control aged out and fresh
            # telemetry cannot replace it, the cast/attack cleanup state is
            # unknown even when no new click was attempted.
            self._cleanup_uncertain = True
            self._cleanup_error = type(exc).__name__ + ": " + str(exc)
            raise
        self._cleanup_verified = True
        return {"status": "cleaned", "inputSent": True, "receipt": receipt}


def _json_result(completed):
    try:
        return json.loads(completed.stdout.splitlines()[-1])
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SurvivalActionError("native-combat-click-receipt-unavailable-no-retry") from exc


def inspect_client_geometry(adapter, *, native_exe=None, run=subprocess.run):
    """Read current pinned client geometry without focus or input."""
    from scripts import physical_rift
    executable = Path(native_exe or physical_rift.NATIVE_EXE).absolute()
    expected = adapter.target
    command = [str(executable), "move-key", "--inspect", "--pid", str(adapter.pid),
               "--expect-start-ticks", str(expected["processStartUtcTicks"]),
               "--expect-sha256", expected["executableSha256"], "--expect-hwnd",
               hex(expected["hwnd"]), "--json"]
    completed = run(command, cwd=ROOT, capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    result = _json_result(completed)
    target = result.get("target")
    _require(completed.returncode == 0 and result.get("status") == "inspected-target"
             and result.get("inputSent") is False and result.get("focusRequested") is False
             and isinstance(target, dict)
             and _same(target.get("machineName"), adapter.host)
             and target.get("processId") == adapter.pid
             and str(target.get("processStartUtcTicks")) == str(expected["processStartUtcTicks"])
             and _same(target.get("executableSha256"), expected["executableSha256"])
             and int(target.get("windowHandle"), 16) == expected["hwnd"]
             and type(target.get("clientX")) is int and type(target.get("clientY")) is int
             and type(target.get("clientWidth")) is int and target["clientWidth"] > 0
             and type(target.get("clientHeight")) is int and target["clientHeight"] > 0,
             "physical-client-geometry-unavailable")
    return target


def _unit_decimal(value):
    _require(isinstance(value, str) and len(value) == 17 and value[0].casefold() == "u",
             "invalid-survival-unit-key")
    try:
        number = int(value[1:], 16)
    except ValueError as exc:
        raise SurvivalActionError("invalid-survival-unit-key") from exc
    _require(0 < number <= 0xFFFFFFFFFFFFFFFF, "invalid-survival-unit-key")
    return str(number)


def native_combat_click(adapter, target, *, action, action_id, rectangle, pin,
                        stop_event, cleanup=False, native_exe=None,
                        run=subprocess.run, owner_identity=None, stop_file=None):
    """Invoke exactly one physical combat click and normalize a trusted receipt."""
    from scripts import physical_rift
    from scripts.continuous_move import _owner_start_ticks
    executable = Path(native_exe or physical_rift.NATIVE_EXE).absolute()
    owner = owner_identity or (os.getpid(), _owner_start_ticks())
    stop_path = Path(stop_file or ROOT / "artifacts" /
                     ("combat-click-stop-" + uuid.uuid4().hex + ".flag")).absolute()
    _require(cleanup or not stop_event.is_set(), "survival-action-stopped-before-native")
    _require(not stop_path.exists(), "survival-action-stop-file-already-exists")
    if cleanup and stop_event.is_set():
        stop_path.write_text("STOP\n", encoding="ascii")
    command = [str(executable), "combat-click", "--expected-host", adapter.host,
               "--pid", str(adapter.pid), "--expect-start-ticks", str(pin.process_start_ticks),
               "--expect-sha256", pin.executable_sha256, "--expect-hwnd", pin.window_handle,
               "--expect-player-key", _unit_decimal(pin.player_id),
               "--expect-target-key", _unit_decimal(pin.target_id),
               "--owner-pid", str(owner[0]), "--owner-start-ticks", str(owner[1]),
               "--action-id", action_id, "--nonce", pin.session_id,
               "--client-x", str(target["clientX"]), "--client-y", str(target["clientY"]),
               "--client-width", str(target["clientWidth"]),
               "--client-height", str(target["clientHeight"]),
               "--rect-x", str(rectangle["x"]), "--rect-y", str(rectangle["y"]),
               "--rect-width", str(rectangle["width"]),
               "--rect-height", str(rectangle["height"]),
               "--stop-file", str(stop_path), "--execute", "--json"]
    if cleanup:
        command.append("--cleanup")
    monitor_done = threading.Event()
    def publish_stop():
        while not monitor_done.wait(.01):
            if stop_event.is_set():
                try:
                    if not stop_path.exists():
                        stop_path.write_text("STOP\n", encoding="ascii")
                except OSError:
                    pass
                return
    monitor = threading.Thread(target=publish_stop, daemon=True)
    monitor.start()
    try:
        completed = run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        monitor_done.set()
        monitor.join()
    raw = _json_result(completed)
    adapter._survival_action_receipt = raw
    release_fault = (raw.get("inputSent") is True
                     and (raw.get("releaseSucceeded") is not True
                          or raw.get("desktopInputsDown") != []))
    adapter._survival_input_release_fault = release_fault
    if release_fault:
        # Reuse Waypoints' existing movement admission/status fault latch.  A
        # successful later click must not clear an earlier uncertain release;
        # only the owning explicit recovery path may do that.
        adapter._continuous_input_release_fault = True
    observed = raw.get("target")
    exact = (completed.returncode == 0 and raw.get("status") == "completed"
             and raw.get("reason") is None and isinstance(observed, dict)
             and _same(observed.get("machineName"), pin.host)
             and observed.get("processId") == pin.process_id
             and str(observed.get("processStartUtcTicks")) == str(pin.process_start_ticks)
             and _same(observed.get("executableSha256"), pin.executable_sha256)
             and str(observed.get("windowHandle")) == pin.window_handle
             and {k: observed.get(k) for k in ("clientX", "clientY", "clientWidth", "clientHeight")}
                 == {k: target[k] for k in ("clientX", "clientY", "clientWidth", "clientHeight")}
             and raw.get("actionId") == action_id and raw.get("nonce") == pin.session_id
             and raw.get("cleanup") is cleanup
             and raw.get("playerKey") == _unit_decimal(pin.player_id)
             and raw.get("targetKey") == _unit_decimal(pin.target_id)
             and raw.get("reviewedClientGeometry") == {
                 "x": target["clientX"], "y": target["clientY"],
                 "width": target["clientWidth"], "height": target["clientHeight"]}
             and raw.get("rectangle") == rectangle
             and raw.get("inputSent") is True and raw.get("releaseSucceeded") is True
             and raw.get("desktopInputsDown") == [] and raw.get("responseVerified") is False
             and raw.get("stopFile") == str(stop_path)
             and raw.get("owner") == {"processId": owner[0], "processStartUtcTicks": owner[1]})
    events = raw.get("inputEvents")
    preparation = raw.get("cursorPreparation")
    expected_point = {"x": target["clientX"] + rectangle["x"] + rectangle["width"] // 2,
                      "y": target["clientY"] + rectangle["y"] + rectangle["height"] // 2}
    exact = (exact and isinstance(events, list) and len(events) == 2
             and events[0].get("phase") == "button-down" and events[0].get("inserted") is True
             and events[1].get("phase") == "button-up" and events[1].get("inserted") is True
             and isinstance(preparation, dict)
             and preparation.get("preparedPosition") == expected_point)
    _require(exact, raw.get("reason") or "native-combat-click-untrusted-no-retry")
    return {"trustedReceipt": True, "status": "completed", "inputSent": True,
            "releaseSucceeded": True, "desktopInputsDown": [], "responseVerified": False,
            "action": action, "rectangle": rectangle, "nonce": pin.session_id,
            "playerId": pin.player_id, "targetId": pin.target_id, "target": observed,
            "mouseSendEvents": events, "nativeReceipt": raw}


class ActionBackend:
    """Production adapter around current telemetry, geometry and native click."""

    def __init__(self, adapter, frame_provider, profile, stop, *, native_exe=None,
                 run=subprocess.run):
        self.adapter, self.frame_provider, self.profile, self.stop = (
            adapter, frame_provider, profile, stop)
        self.native_exe, self.run = native_exe, run
        self._actions = None
        self._action_diagnostic = None
        self._no_action_owned = None

    def begin_encounter(self):
        """Open a new target pin only after the prior encounter cleaned up."""
        if self._actions is not None:
            _require(self._actions.cleanup_verified,
                     "survival-prior-encounter-cleanup-unverified")
            _require(not self.input_release_fault,
                     "survival-prior-encounter-input-release-fault")
        self._actions = None
        self._no_action_owned = None
        return {"status": "encounter-ready", "inputSent": False}

    @property
    def last_receipt(self):
        return getattr(self.adapter, "_survival_action_receipt", None)

    @property
    def action_diagnostic(self):
        """Return the last failed protected-action diagnostic without retrying it."""
        return deepcopy(self._action_diagnostic)

    @property
    def input_release_fault(self):
        return bool(getattr(self.adapter, "_survival_input_release_fault", False)
                    or getattr(self.adapter, "_survival_cleanup_uncertain", False)
                    or getattr(self.adapter, "_continuous_input_release_fault", False))

    def _build(self):
        report = self.frame_provider()
        frame = report.get("snapshot", report) if isinstance(report, dict) else None
        _require(isinstance(frame, dict), "invalid-survival-frame")
        _require(type(frame.get("epoch")) is int and type(frame.get("sequence")) is int
                 and type(frame.get("frameTime")) in (int, float),
                 "invalid-survival-frame-generation")
        generation = (frame["epoch"], frame["sequence"], float(frame["frameTime"]))
        target = inspect_client_geometry(self.adapter, native_exe=self.native_exe, run=self.run)
        basis = self.profile.get("coordinateBasis") if isinstance(self.profile, dict) else None
        pin = ActionPin.from_values(target, player_id=frame.get("playerId"),
                                    target_id=frame.get("targetId"),
                                    session_id=frame.get("sessionId"))
        def click(**values):
            return native_combat_click(
                self.adapter, target, cleanup=values["action"] == "cancel",
                native_exe=self.native_exe, run=self.run, **values)
        return SurvivalActions(target=target, pin=pin, basis=basis,
            frame_reader=self.frame_provider, native_click=click,
            reservation=self.adapter.reserve, stop_event=self.stop, profile=self.profile,
            minimum_generation=generation,
            cancel_reference=getattr(getattr(self.frame_provider, "__self__", None),
                                     "cancel_reference", None))

    def _cancel_reference_provider(self):
        return getattr(getattr(self.frame_provider, "__self__", None),
                       "cancel_reference", None)

    def _build_cancel_only(self):
        """Bootstrap STOP cleanup without requiring an advancing producer scan."""
        reference_provider = self._cancel_reference_provider()
        _require(callable(reference_provider), "cancel-reference-unavailable")
        reference = reference_provider(max_age_seconds=5.0)
        _require(isinstance(reference, dict)
                 and reference.get("status") == "cached-verified-cancel",
                 "cancel-reference-unavailable")
        target = inspect_client_geometry(self.adapter, native_exe=self.native_exe, run=self.run)
        basis = self.profile.get("coordinateBasis") if isinstance(self.profile, dict) else None
        pin = ActionPin.from_values(
            target, player_id=reference.get("playerId"),
            target_id=reference.get("selectedTargetId"),
            session_id=reference.get("sessionId"))
        generation = (reference.get("epoch"), reference.get("sourceSequence"),
                      float(reference.get("sourceFrameTime")))
        def click(**values):
            return native_combat_click(
                self.adapter, target, cleanup=values["action"] == "cancel",
                native_exe=self.native_exe, run=self.run, **values)
        # Reuse the already-bounded reference.  No snapshot/heap acquisition is
        # allowed merely to clean up autoattack after operator STOP.
        def retained_reference(*, max_age_seconds):
            _require(max_age_seconds == 5.0, "invalid-cancel-reference-age")
            return reference
        return SurvivalActions(
            target=target, pin=pin, basis=basis,
            frame_reader=lambda: (_ for _ in ()).throw(
                SurvivalActionError("cancel-only-backend-has-no-action-frame")),
            native_click=click, reservation=self.adapter.reserve,
            stop_event=self.stop, profile=self.profile,
            minimum_generation=generation, cancel_reference=retained_reference)

    def cast(self, ability_id):
        previous_receipt = getattr(self.adapter, "_survival_action_receipt", None)
        try:
            if self._actions is None:
                self._actions = self._build()
            return self._actions.cast(ability_id)
        except Exception as exc:
            latest_receipt = getattr(self.adapter, "_survival_action_receipt", None)
            attempted = bool(self._actions is not None
                             and self._actions.native_attempted)
            receipt_from_attempt = latest_receipt is not previous_receipt
            explicit_no_input = bool(
                receipt_from_attempt and isinstance(latest_receipt, dict)
                and latest_receipt.get("inputSent") is False)
            if not attempted or explicit_no_input:
                self._no_action_owned = {
                    "status": "no-survival-action-owned", "inputSent": False,
                    "reason": str(exc), "errorType": type(exc).__name__}
                self._action_diagnostic = {
                    "operation": "cast", "stage": "cast-admission",
                    "error": {"type": type(exc).__name__, "reason": str(exc)},
                    "nativeReceiptFromAttempt": receipt_from_attempt,
                    "rawNativeReceipt": deepcopy(latest_receipt)}
                self._actions = None
                raise SurvivalActionPreInputError(
                    "survival-pre-input-action-refused: " + str(exc)) from exc
            raise

    def cancel(self):
        if self._no_action_owned is not None:
            return deepcopy(self._no_action_owned)
        stage = "cancel-existing-owner"
        previous_receipt = getattr(self.adapter, "_survival_action_receipt", None)
        try:
            if self._actions is None:
                stage = "cancel-bootstrap"
                self._actions = self._build_cancel_only()
            stage = "cancel-click"
            result = self._actions.cancel()
            self._action_diagnostic = None
            return result
        except Exception as exc:
            # The entire bootstrap is part of STOP cleanup.  Failure to obtain
            # a recent exact cancel control or current native geometry leaves
            # autoattack/cast cleanup unknown even when no click was attempted.
            self.adapter._survival_cleanup_uncertain = True
            self.adapter._continuous_input_release_fault = True
            # An idempotent second call must surface, not replace, the original
            # failed attempt. It never retries the native click.
            if (self._action_diagnostic is None
                    or "survival-cleanup-previously-failed-no-retry" not in str(exc)):
                latest_receipt = getattr(self.adapter, "_survival_action_receipt", None)
                self._action_diagnostic = {
                    "operation": "cancel",
                    "stage": stage,
                    "error": {"type": type(exc).__name__, "reason": str(exc)},
                    "nativeReceiptFromAttempt": latest_receipt is not previous_receipt,
                    "rawNativeReceipt": deepcopy(latest_receipt),
                }
            raise


def build_survival_actions(adapter, snapshot, profile, stop, *, native_exe=None,
                           run=subprocess.run):
    """Construct the production action backend used by the survival runtime."""
    _require(callable(snapshot), "survival-snapshot-provider-required")
    return ActionBackend(adapter, snapshot, profile, stop,
                         native_exe=native_exe, run=run)
