import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts import survival_actions as actions_module
from scripts.survival_actions import (ActionBackend, ActionPin, SurvivalActions,
                                      SurvivalActionError, SurvivalActionPreInputError,
                                      client_rectangle,
                                      native_combat_click)


TARGET = {"machineName": "AMD-DESKTOP", "processId": 7,
          "processStartUtcTicks": 9, "executableSha256": "A" * 64,
          "windowHandle": "0x123", "clientX": -1600, "clientY": 20,
          "clientWidth": 1600, "clientHeight": 900}
BASIS = {"qualified": True, "space": "UIParent-to-client-pixels",
         "viewportWidth": 800, "viewportHeight": 450,
         "clientWidth": 1600, "clientHeight": 900,
         "scaleX": 2.0, "scaleY": 2.0, "offsetX": 0.0, "offsetY": 0.0}
PIN = ActionPin.from_values(TARGET, player_id="uPLAYER", target_id="uTARGET",
                            session_id="a" * 32)


def frame():
    return {"ready": True, "telemetry": {"ready": True}, "snapshot": {
        "status": "observed", "sessionId": "a" * 32, "epoch": 2,
        "sequence": 4, "frameTime": 10.0, "playerId": "uPLAYER",
        "targetId": "uTARGET", "readiness": {"status": "ready"},
        "ability": {"lookupId": "ability-1", "name": "Bolt", "target": "uTARGET"},
        "catalog": {"status": "observed", "sampledAt": 9.0,
                    "entries": {"ability-1": "Bolt"}},
        "controls": {"visible": True, "space": "UIParent",
                     "viewportWidth": 800, "viewportHeight": 450,
                     "actions": {"ability-1": {"mapped": True, "visible": True,
                              "readiness": {"status": "ready"}, "slot": 1,
                              "left": 100, "top": 200,
                              "width": 40, "height": 20, "abilityId": "ability-1",
                              "abilityName": "Bolt", "uniqueLearnedName": True,
                              "ability": {"idNew": "ability-1", "target": "uTARGET"},
                              "macro": "cast Bolt\nstopattack"}},
                     "cancel": {"mapped": True, "visible": True,
                                "macro": "stopcasting\nstopattack",
                                "effectQualification": "unverified",
                                "left": 200, "top": 200,
                                "width": 40, "height": 20}}}}


def receipt(action, rectangle):
    return {"trustedReceipt": True, "status": "completed", "inputSent": True,
            "releaseSucceeded": True, "desktopInputsDown": [],
            "responseVerified": False, "action": action, "rectangle": rectangle,
            "nonce": "a" * 32, "playerId": "uPLAYER", "targetId": "uTARGET",
            "target": TARGET, "mouseSendEvents": [
                {"phase": "button-down"}, {"phase": "button-up"}]}


class Lease:
    def __init__(self, log): self.log = log
    def __enter__(self): self.log.append("enter"); return self
    def check(self): self.log.append("check")
    def __exit__(self, *_): self.log.append("exit")


class SurvivalActionTests(unittest.TestCase):
    def actions(self, *, value=None, stop=None):
        log = []
        value = value or frame()
        def click(**kwargs):
            log.append((kwargs["action"], kwargs["rectangle"]))
            return receipt(kwargs["action"], kwargs["rectangle"])
        owner = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=lambda: value, native_click=click,
            reservation=lambda: Lease(log), stop_event=stop)
        return owner, log

    def test_cast_pins_current_unique_ready_ability_and_maps_qualified_scale(self):
        owner, log = self.actions()
        result = owner.cast("ability-1")
        self.assertTrue(result["releaseSucceeded"])
        self.assertEqual((2, 4, 10.0),
                         (result["admissionEpoch"], result["admissionSequence"],
                          result["admissionFrameTime"]))
        self.assertIsNone(result["outcomeBaseline"])
        self.assertEqual(log, ["enter", "check", ("cast", {
            "x": 200, "y": 400, "width": 80, "height": 40}), "exit"])

    def test_cast_metadata_uses_exact_admission_frame_not_older_outer_telemetry(self):
        value = frame()
        snapshot = value["snapshot"]
        snapshot.update(epoch=3, sequence=12, frameTime=50.0)
        snapshot["catalog"]["sampledAt"] = 49.5
        snapshot["lastEvent"] = {"sequence": 8, "clock": 47.0}
        snapshot["lastPositiveEvent"] = {"sequence": 9, "clock": 48.0}
        snapshot["positiveEvents"] = {
            "ability-1": {"sequence": 10, "clock": 49.0}}
        owner, _log = self.actions(value=value)
        result = owner.cast("ability-1")
        self.assertEqual(3, result["admissionEpoch"])
        self.assertEqual(12, result["admissionSequence"])
        self.assertEqual(50.0, result["admissionFrameTime"])
        self.assertEqual({"sequence": 10, "clock": 49.0,
                          "sources": ["lastEvent", "lastPositiveEvent",
                                      "positiveEvents.ability-1"]},
                         result["outcomeBaseline"])

    def test_profile_action_does_not_depend_on_globally_selected_dashboard_ability(self):
        value = frame()
        value["snapshot"]["ability"] = {"lookupId": "other-selected", "name": "Other",
                                          "target": "uSOMEONE"}
        value["snapshot"]["catalog"]["entries"]["ability-2"] = "Heal"
        value["snapshot"]["controls"]["actions"]["ability-2"] = {
            "mapped": True, "visible": True, "readiness": {"status": "ready"},
            "slot": 2, "left": 300, "top": 200, "width": 40, "height": 20,
            "abilityId": "ability-2", "abilityName": "Heal",
            "uniqueLearnedName": True, "ability": {"idNew": "ability-2", "target": "uTARGET"},
            "macro": "cast Heal\nstopattack"}
        owner, log = self.actions(value=value)
        owner.cast("ability-2")
        self.assertIn(("cast", {"x": 600, "y": 400, "width": 80, "height": 40}), log)

    def test_profile_roles_allow_exact_self_heal_but_damage_requires_selected_target(self):
        value = frame()
        value["snapshot"]["catalog"]["entries"] = {}  # Current page need not contain this slot.
        action = value["snapshot"]["controls"]["actions"]["ability-1"]
        action["ability"]["target"] = "uPLAYER"
        value["snapshot"]["controls"]["actions"]["ability-2"] = {
            "mapped": True, "visible": True, "readiness": {"status": "ready"},
            "slot": 2, "left": 300, "top": 200, "width": 40, "height": 20,
            "abilityId": "ability-2", "abilityName": "Strike",
            "uniqueLearnedName": True, "ability": {"idNew": "ability-2", "target": "uTARGET"},
            "macro": "cast Strike\nstopattack"}
        profile = {"abilities": {"heal": "ability-1", "damage": "ability-2"}}
        log = []
        def click(**kwargs):
            log.append(kwargs["action_id"])
            return receipt(kwargs["action"], kwargs["rectangle"])
        heal = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=lambda: value, native_click=click,
            reservation=lambda: Lease(log), profile=profile)
        heal.cast("ability-1")
        self.assertIn("controls.actions.ability-1", log)

        damage = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=lambda: value, native_click=click,
            reservation=lambda: Lease(log), profile=profile)
        damage.cast("ability-2")
        self.assertIn("controls.actions.ability-2", log)

        damage_profile = {"abilities": {"damage": "ability-1"}}
        invalid_damage = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=lambda: value, native_click=click,
            reservation=lambda: Lease([]), profile=damage_profile)
        with self.assertRaisesRegex(SurvivalActionError, "ability-mismatch"):
            invalid_damage.cast("ability-1")

    def test_cast_refuses_stale_identity_readiness_or_ability_before_input(self):
        for mutate in (
            lambda f: f["snapshot"].update(sessionId="b" * 32),
            lambda f: f["snapshot"]["controls"]["actions"]["ability-1"].update(abilityId="other"),
            lambda f: f["snapshot"]["controls"]["actions"]["ability-1"]["readiness"].update(status="waiting"),
            lambda f: f["snapshot"]["controls"]["actions"]["ability-1"].update(uniqueLearnedName=False),
            lambda f: f["snapshot"]["controls"]["actions"]["ability-1"].update(visible=False)):
            value = frame(); mutate(value)
            owner, log = self.actions(value=value)
            with self.assertRaises(SurvivalActionError): owner.cast("ability-1")
            self.assertNotIn("cast", [v[0] for v in log if isinstance(v, tuple)])

    def test_unqualified_or_mismatched_basis_is_never_inferred(self):
        value = frame()["snapshot"]
        for change in ({"qualified": False}, {"scaleX": None}, {"clientWidth": 1599}):
            basis = dict(BASIS, **change)
            with self.assertRaises(SurvivalActionError):
                client_rectangle(value, "cast", basis, TARGET, ability_id="ability-1")

    def test_large_real_cancel_control_uses_centered_native_bounded_subrectangle(self):
        value = frame()["snapshot"]
        value["controls"]["viewportWidth"] = 1965.3360595703
        value["controls"]["viewportHeight"] = 1024.0
        value["controls"]["cancel"].update(left=515.0, top=225.0,
                                             width=236.0, height=40.0)
        target = dict(TARGET, clientWidth=1902, clientHeight=991)
        basis = {"qualified": True, "space": "UIParent-to-client-pixels",
                 "viewportWidth": 1965.3360595703, "viewportHeight": 1024.0,
                 "clientWidth": 1902, "clientHeight": 991,
                 "scaleX": .9677734375, "scaleY": .9677734375,
                 "offsetX": 0.0, "offsetY": 0.0}
        result = client_rectangle(value, "cancel", basis, target)
        # Full mapped width rounds to 228px at x=498; the 128px subrectangle
        # begins 50px inward and preserves the original 612px center.
        self.assertEqual({"x": 548, "y": 218, "width": 128, "height": 39}, result)
        self.assertEqual(612, result["x"] + result["width"] // 2)

    def test_stop_is_checked_before_frame_and_before_delivery(self):
        stop = threading.Event(); stop.set()
        owner, log = self.actions(stop=stop)
        with self.assertRaisesRegex(SurvivalActionError, "stopped-before-admission"):
            owner.cast("ability-1")
        self.assertEqual(log, [])

    def test_untrusted_or_unreleased_receipt_is_not_retried(self):
        calls = []
        def click(**kwargs):
            calls.append(kwargs)
            bad = receipt(kwargs["action"], kwargs["rectangle"])
            bad["releaseSucceeded"] = False
            return bad
        owner = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=frame, native_click=click, reservation=lambda: Lease([]))
        with self.assertRaises(SurvivalActionError): owner.cast("ability-1")
        self.assertEqual(len(calls), 1)

    def test_cancel_runs_combined_cleanup_once_and_is_idempotent(self):
        owner, log = self.actions()
        cleaned = owner.cancel()
        again = owner.cancel()
        self.assertEqual(cleaned["status"], "cleaned")
        self.assertEqual(again, {"status": "already-clean", "inputSent": False})
        self.assertEqual([v[0] for v in log if isinstance(v, tuple)], ["cancel"])

    def test_latched_stop_blocks_cast_but_allows_one_post_termination_cleanup(self):
        stop = threading.Event(); stop.set()
        owner, log = self.actions(stop=stop)
        with self.assertRaisesRegex(SurvivalActionError, "stopped-before-admission"):
            owner.cast("ability-1")
        self.assertEqual(owner.cancel()["status"], "cleaned")
        self.assertEqual(owner.cancel(), {"status": "already-clean", "inputSent": False})
        self.assertEqual([v[0] for v in log if isinstance(v, tuple)], ["cancel"])

    def test_production_native_invoker_pins_full_command_and_normalizes_receipt(self):
        rectangle = {"x": 200, "y": 400, "width": 80, "height": 40}
        commands = []
        with tempfile.TemporaryDirectory() as directory:
            stop_file = Path(directory) / "stop.flag"
            def run(command, **_kwargs):
                commands.append(command)
                raw = {"status": "completed", "reason": None, "target": TARGET,
                       "actionId": "controls.actions.ability-1", "nonce": "a" * 32,
                       "cleanup": False, "cleanupSemantics": None,
                       "playerKey": "1", "targetKey": "2",
                       "reviewedClientGeometry": {"x": -1600, "y": 20,
                                                  "width": 1600, "height": 900},
                       "rectangle": rectangle,
                       "cursorPreparation": {"originalPosition": {"x": 1, "y": 2},
                                             "preparedPosition": {"x": -1360, "y": 440},
                                             "repositioned": True},
                       "holdMilliseconds": 40,
                       "inputEvents": [{"phase": "button-down", "inserted": True},
                                       {"phase": "button-up", "inserted": True}],
                       "inputSent": True, "releaseSucceeded": True,
                       "desktopInputsDown": [], "stopFile": str(stop_file),
                       "owner": {"processId": 11, "processStartUtcTicks": 12},
                       "responseVerified": False}
                return SimpleNamespace(returncode=0, stdout=json.dumps(raw), stderr="")
            adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7)
            numeric_pin = ActionPin.from_values(
                TARGET, player_id="u0000000000000001", target_id="u0000000000000002",
                session_id="a" * 32)
            result = native_combat_click(adapter, TARGET, action="cast",
                action_id="controls.actions.ability-1", rectangle=rectangle,
                pin=numeric_pin, stop_event=threading.Event(), native_exe="native.exe",
                run=run, owner_identity=(11, 12), stop_file=stop_file)
        self.assertTrue(result["trustedReceipt"])
        command = commands[0]
        self.assertEqual(command[command.index("--expect-player-key") + 1], "1")
        self.assertEqual(command[command.index("--expect-target-key") + 1], "2")
        self.assertEqual(command[command.index("--action-id") + 1],
                         "controls.actions.ability-1")
        self.assertNotIn("--cleanup", command)
        self.assertFalse(adapter._survival_input_release_fault)
        self.assertEqual("completed", adapter._survival_action_receipt["status"])

    def test_native_fault_latch_only_follows_attempted_unverified_release(self):
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7)
        numeric_pin = ActionPin.from_values(
            TARGET, player_id="u0000000000000001", target_id="u0000000000000002",
            session_id="a" * 32)
        rectangle = {"x": 200, "y": 400, "width": 80, "height": 40}
        with tempfile.TemporaryDirectory() as directory:
            def invoke(name, raw, returncode):
                path = Path(directory) / name
                def run(_command, **_kwargs):
                    return SimpleNamespace(returncode=returncode,
                                           stdout=json.dumps(raw), stderr="")
                with self.assertRaises(SurvivalActionError):
                    native_combat_click(adapter, TARGET, action="cast",
                        action_id="controls.actions.ability-1", rectangle=rectangle,
                        pin=numeric_pin, stop_event=threading.Event(), native_exe="native.exe",
                        run=run, owner_identity=(11, 12), stop_file=path)
            invoke("blocked.flag", {"status": "blocked", "reason": "target-changed",
                   "inputSent": False, "releaseSucceeded": False,
                   "desktopInputsDown": []}, 2)
            self.assertFalse(adapter._survival_input_release_fault)
            self.assertFalse(hasattr(adapter, "_continuous_input_release_fault"))
            invoke("halted.flag", {"status": "halted", "reason": "release-unverified",
                   "inputSent": True, "releaseSucceeded": False,
                   "desktopInputsDown": ["mouse-left"]}, 3)
            self.assertTrue(adapter._survival_input_release_fault)
            self.assertTrue(adapter._continuous_input_release_fault)

    def test_backend_rebinds_two_encounters_only_after_verified_cancel(self):
        def report(sequence, target_id):
            value = frame()
            snapshot = value["snapshot"]
            snapshot.update(sequence=sequence, frameTime=float(sequence), targetId=target_id)
            snapshot["catalog"]["sampledAt"] = float(sequence) - .25
            snapshot["controls"]["actions"]["ability-1"]["ability"]["target"] = target_id
            return value
        reports = iter([report(1, "uTARGET"), report(2, "uTARGET"),
                        report(4, "uSECOND"),
                        report(5, "uSECOND")])
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7, reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        pins = []
        def native(_adapter, target, **values):
            pin = values["pin"]; pins.append(pin.target_id)
            return receipt(values["action"], values["rectangle"]) | {
                "targetId": pin.target_id}
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click", side_effect=native):
            backend = ActionBackend(adapter, lambda: next(reports), profile,
                                    threading.Event())
            backend.begin_encounter()
            backend.cast("ability-1")
            backend.cancel()
            with self.assertRaisesRegex(SurvivalActionError, "begin-new-encounter"):
                backend.cast("ability-1")
            backend.begin_encounter()
            backend.cast("ability-1")
        self.assertEqual(pins, ["uTARGET", "uTARGET", "uSECOND"])

    def test_stop_cleanup_uses_recent_cast_admission_without_another_frame(self):
        first, second = frame(), frame()
        first["snapshot"].update(sequence=1, frameTime=1.0)
        first["snapshot"]["catalog"]["sampledAt"] = .75
        second["snapshot"].update(sequence=2, frameTime=2.0)
        second["snapshot"]["catalog"]["sampledAt"] = 1.75
        reports = iter([first, second])
        reads = []
        def provider():
            reads.append(True)
            return next(reports)
        stop = threading.Event()
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7, reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        def native(_adapter, _target, **values):
            return receipt(values["action"], values["rectangle"])
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click", side_effect=native):
            backend = ActionBackend(adapter, provider, profile, stop)
            backend.cast("ability-1")
            stop.set()
            self.assertEqual("cleaned", backend.cancel()["status"])
        self.assertEqual(2, len(reads))  # bootstrap + cast; cancel used retained geometry

    def test_aged_cancel_geometry_and_failed_refresh_marks_cleanup_uncertain(self):
        calls = [frame()]
        def provider():
            if calls:
                return calls.pop(0)
            raise TimeoutError("producer deadline")
        clocks = iter([0.0, 6.0])
        def click(**values):
            return receipt(values["action"], values["rectangle"])
        owner = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=provider, native_click=click, reservation=lambda: Lease([]),
            monotonic=lambda: next(clocks))
        owner.cast("ability-1")
        with self.assertRaisesRegex(TimeoutError, "producer deadline"):
            owner.cancel()
        self.assertTrue(owner.cleanup_uncertain)
        self.assertFalse(owner.cleanup_verified)
        with self.assertRaisesRegex(
                SurvivalActionError,
                "previously-failed-no-retry: TimeoutError: producer deadline"):
            owner.cancel()

    def test_documented_consumer_cancel_reference_is_preferred_without_scan(self):
        reports = [frame()]
        clicked = []
        cancel_control = copy.deepcopy(frame()["snapshot"]["controls"]["cancel"])
        cancel_control["left"] = 220
        def reference(*, max_age_seconds):
            self.assertEqual(5.0, max_age_seconds)
            return {"status": "cached-verified-cancel", "ageSeconds": .2,
                    "sessionId": "a" * 32, "epoch": 2,
                    "playerId": "uPLAYER", "selectedTargetId": "uTARGET",
                    "target": TARGET, "sourceSequence": 4,
                    "cancel": cancel_control}
        def click(**values):
            clicked.append(values["rectangle"])
            return receipt(values["action"], values["rectangle"])
        owner = SurvivalActions(target=TARGET, pin=PIN, basis=BASIS,
            frame_reader=lambda: reports.pop(0), native_click=click,
            reservation=lambda: Lease([]), cancel_reference=reference)
        owner.cast("ability-1")
        owner.cancel()
        self.assertEqual([], reports)
        self.assertEqual({"x": 440, "y": 400, "width": 80, "height": 40}, clicked[-1])

    def test_backend_refuses_target_reset_without_verified_prior_cancel(self):
        first, second = frame(), frame()
        first["snapshot"].update(sequence=1, frameTime=1.0)
        first["snapshot"]["catalog"]["sampledAt"] = .75
        second["snapshot"].update(sequence=2, frameTime=2.0)
        second["snapshot"]["catalog"]["sampledAt"] = 1.75
        reports = iter([first, second])
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7, reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click") as native:
            native.side_effect = lambda _adapter, _target, **values: receipt(
                values["action"], values["rectangle"])
            backend = ActionBackend(adapter, lambda: next(reports), profile,
                                    threading.Event())
            backend.cast("ability-1")
            with self.assertRaisesRegex(SurvivalActionError, "cleanup-unverified"):
                backend.begin_encounter()

    def test_first_action_stop_cancel_uses_reference_with_zero_frame_reads(self):
        stop = threading.Event(); stop.set()
        calls = []
        cancel_control = copy.deepcopy(frame()["snapshot"]["controls"]["cancel"])
        class Consumer:
            def snapshot(self):
                raise AssertionError("STOP cleanup must not read an advancing frame")
            def cancel_reference(self, *, max_age_seconds):
                calls.append(("reference", max_age_seconds))
                return {"status": "cached-verified-cancel", "ageSeconds": .1,
                        "sessionId": "a" * 32, "epoch": 2,
                        "playerId": "uPLAYER", "selectedTargetId": "uTARGET",
                        # Real consumer reference intentionally retains only
                        # capture identity; fresh native inspect owns HWND/client.
                        "target": {"processId": 7, "processStartUtcTicks": 9,
                                   "executableSha256": "A" * 64},
                        "sourceSequence": 4,
                        "sourceFrameTime": 10.0, "cancel": cancel_control}
        consumer = Consumer()
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7, reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        def native(_adapter, _target, **values):
            calls.append(("native", values["action"], values["cleanup"]))
            return receipt(values["action"], values["rectangle"])
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click", side_effect=native):
            backend = ActionBackend(adapter, consumer.snapshot, profile, stop)
            backend.begin_encounter()
            self.assertEqual("cleaned", backend.cancel()["status"])
        self.assertEqual([("reference", 5.0), ("native", "cancel", True)], calls)
        self.assertFalse(backend.input_release_fault)

    def test_first_action_cancel_bootstrap_failure_latches_cleanup_uncertain(self):
        class Consumer:
            def snapshot(self):
                raise AssertionError("must not scan")
            def cancel_reference(self, *, max_age_seconds):
                raise TimeoutError("cancel reference expired")
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7, reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        backend = ActionBackend(adapter, Consumer().snapshot, profile, threading.Event())
        with self.assertRaisesRegex(TimeoutError, "expired"):
            backend.cancel()
        self.assertTrue(adapter._survival_cleanup_uncertain)
        self.assertTrue(adapter._continuous_input_release_fault)
        self.assertEqual("cancel-bootstrap", backend.action_diagnostic["stage"])
        self.assertEqual(
            {"type": "TimeoutError", "reason": "cancel reference expired"},
            backend.action_diagnostic["error"])
        self.assertFalse(backend.action_diagnostic["nativeReceiptFromAttempt"])
        self.assertIsNone(backend.action_diagnostic["rawNativeReceipt"])

    def test_cancel_failure_retains_raw_native_receipt_and_refuses_retry(self):
        cancel_control = copy.deepcopy(frame()["snapshot"]["controls"]["cancel"])
        class Consumer:
            def snapshot(self):
                raise AssertionError("must not scan")
            def cancel_reference(self, *, max_age_seconds):
                return {"status": "cached-verified-cancel", "ageSeconds": .1,
                        "sessionId": "a" * 32, "epoch": 2,
                        "playerId": "uPLAYER", "selectedTargetId": "uTARGET",
                        "target": {"processId": 7, "processStartUtcTicks": 9,
                                   "executableSha256": "A" * 64},
                        "sourceSequence": 4, "sourceFrameTime": 10.0,
                        "cancel": cancel_control}
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7,
                                  reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        raw = {"status": "halted", "reason": "native lease lost", "inputSent": True,
               "releaseSucceeded": False, "desktopInputsDown": ["mouse-left"]}
        def failed_native(_adapter, _target, **_values):
            adapter._survival_action_receipt = raw
            raise SurvivalActionError("native lease lost")
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click", side_effect=failed_native):
            backend = ActionBackend(adapter, Consumer().snapshot, profile,
                                    threading.Event())
            backend.begin_encounter()
            with self.assertRaisesRegex(SurvivalActionError, "native lease lost"):
                backend.cancel()
            with self.assertRaisesRegex(SurvivalActionError, "previously-failed-no-retry"):
                backend.cancel()
        diagnostic = backend.action_diagnostic
        self.assertEqual("cancel-click", diagnostic["stage"])
        self.assertTrue(diagnostic["nativeReceiptFromAttempt"])
        self.assertEqual(raw, diagnostic["rawNativeReceipt"])

    def test_cast_target_disappears_before_native_admission_needs_no_cleanup_click(self):
        initial = frame()
        ended = frame()
        ended["snapshot"].update(sequence=3, frameTime=3.0, targetId=None)
        ended["snapshot"]["target"] = {}
        ended["snapshot"]["controls"]["actions"]["ability-1"]["ability"].pop(
            "target", None)
        reports = iter([initial, ended])
        adapter = SimpleNamespace(host="AMD-DESKTOP", pid=7,
                                  reserve=lambda: Lease([]))
        profile = {"coordinateBasis": BASIS, "abilities": {"damage": "ability-1"}}
        with patch.object(actions_module, "inspect_client_geometry", return_value=TARGET), \
             patch.object(actions_module, "native_combat_click") as native:
            backend = ActionBackend(adapter, lambda: next(reports), profile,
                                    threading.Event())
            backend.begin_encounter()
            with self.assertRaisesRegex(
                    SurvivalActionPreInputError,
                    "survival-pre-input-action-refused: survival-frame-target-mismatch"):
                backend.cast("ability-1")
            release = backend.cancel()
        native.assert_not_called()
        self.assertEqual(
            {"status": "no-survival-action-owned", "inputSent": False,
             "reason": "survival-frame-target-mismatch",
             "errorType": "SurvivalActionError"}, release)
        self.assertFalse(backend.input_release_fault)
        self.assertEqual("cast-admission", backend.action_diagnostic["stage"])
        self.assertFalse(backend.action_diagnostic["nativeReceiptFromAttempt"])


if __name__ == "__main__":
    unittest.main()
