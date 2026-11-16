import json
import tempfile
import unittest
from pathlib import Path

from scripts import summarize_survival_acceptance as summary


class SurvivalAcceptanceSummaryTests(unittest.TestCase):
    def sample(self, clock, self_hp, target_hp, *, state="fight", checkpoint=2,
               incoming=None, outgoing=None, stop=False):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        snapshot = {"sessionId": "a" * 32, "epoch": 3, "sequence": int(clock * 10),
                    "frameTime": clock, "playerId": player_id, "targetId": target_id,
                    "player": {"health": self_hp, "healthMax": 100},
                    "target": {"health": target_hp, "healthMax": 100},
                    "lastIncoming": incoming, "lastPositiveEvent": outgoing}
        return {"type": "telemetry", "wallTime": clock,
                "playerId": player_id, "targetId": target_id,
                "epoch": 3, "sequence": int(clock * 10), "frameTime": clock,
                "native": {}, "snapshot": snapshot,
                "telemetry": {"player": {"healthPct": self_hp, "inCombat": True,
                                           "dead": False},
                              "encounter": {"incomingDamageObserved": incoming is not None}},
                "policy": {"state": state, "checkpoint": checkpoint,
                           "pendingLeg": ["finish", 1, 2]}, "stopSet": stop}

    def test_correlates_exact_incoming_and_outgoing_damage_and_invariants(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id, "selectedTargetId": target_id, "abilityName": "Claw"}
        outgoing = {"sequence": 8, "clock": 10.5, "kind": "damage", "damage": 20,
                    "caster": player_id, "target": target_id, "selectedTargetId": target_id, "abilityName": "Strike"}
        telemetry = [self.sample(10, 100, 100),
                     self.sample(11, 88, 80, incoming=incoming, outgoing=outgoing),
                     self.sample(12, 88, 80, state="retreat"),
                     self.sample(13, 88, 80, state="recover"),
                     self.sample(14, 100, 80, state="rejoin"),
                     self.sample(15, 100, 80, state="travel")]
        route = [{"status": "encounter-interrupted", "releaseSucceeded": True,
                  "desktopInputsDown": []},
                 {"status": "arrived", "releaseSucceeded": True,
                  "desktopInputsDown": [], "nextIndex": 3}]

        value = summary.summarize(route, telemetry)

        self.assertTrue(value["acceptance"]["incomingDamage"])
        self.assertTrue(value["acceptance"]["outgoingDamage"])
        self.assertEqual("preserved", value["acceptance"]["checkpointInvariant"])
        self.assertEqual("preserved", value["acceptance"]["recoveryResumeInvariant"])
        self.assertEqual("clear-throughout", value["acceptance"]["stopInvariant"])
        self.assertTrue(value["route"]["allRetainedReleasesVerified"])

    def test_missing_or_wrong_attribution_is_honestly_unavailable(self):
        telemetry = [self.sample(10, 100, 100), self.sample(11, 90, 80)]
        route = [{"status": "arrived", "releaseSucceeded": True,
                  "desktopInputsDown": []}]
        value = summary.summarize(route, telemetry)
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["acceptance"]["outgoingDamage"])
        self.assertEqual("unavailable", value["telemetry"]["incomingCorrelation"]["status"])

    def test_damage_attribution_rejects_non_damage_and_missing_selected_target(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.4, "kind": "heal", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        route = [{"status": "encounter-interrupted", "releaseSucceeded": True}]
        for replacement in ({"kind": "heal"},
                            {"kind": "damage", "selectedTargetId": None}):
            with self.subTest(replacement=replacement):
                incoming = {**event, **replacement}
                value = summary.summarize(route, [self.sample(10, 100, 100),
                                                  self.sample(11, 88, 100, incoming=incoming)])
                self.assertFalse(value["acceptance"]["incomingDamage"])
                self.assertEqual("unavailable",
                                 value["telemetry"]["incomingCorrelation"]["status"])

    def test_late_event_cannot_be_used_to_explain_earlier_health_loss(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 12.5, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        value = summary.summarize([{"status": "encounter-interrupted"}],
                                  [self.sample(10, 100, 100),
                                   self.sample(11, 88, 100, incoming=event)])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertEqual("observed-unpaired",
                         value["telemetry"]["incomingCorrelation"]["status"])

    def test_changed_selected_target_does_not_validate_old_target_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        after = self.sample(11, 88, 100, incoming=incoming)
        after["snapshot"]["targetId"] = "u0000000000000003"
        after["targetId"] = "u0000000000000003"
        value = summary.summarize([{"status": "encounter-interrupted"}],
                                  [self.sample(10, 100, 100), after])
        self.assertFalse(value["acceptance"]["incomingDamage"])

    def test_old_session_damage_event_cannot_explain_new_session_hp_drop(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.5, "kind": "damage",
                 "damage": 12, "caster": target_id, "target": player_id,
                 "selectedTargetId": target_id}
        old = self.sample(10.5, 100, 100, incoming=event)
        old["snapshot"]["sessionId"] = "a" * 32
        newer_before = self.sample(10, 100, 100)
        newer_before["snapshot"]["sessionId"] = "b" * 32
        newer_after = self.sample(11, 88, 100)
        newer_after["snapshot"]["sessionId"] = "b" * 32
        observed = summary.summarize(
            [{"status": "encounter-interrupted"}],
            [old, newer_before, newer_after])
        self.assertEqual(1, len(observed["telemetry"]["selfHealthDrops"]))
        self.assertTrue(observed["telemetry"]["selfHealthDrops"][0]["attributionEligible"])
        self.assertEqual(0, observed["telemetry"]["incomingCorrelation"]["pairedCount"])
        self.assertEqual("observed-unpaired",
                         observed["telemetry"]["incomingCorrelation"]["status"])

    def test_same_event_counter_after_session_restart_remains_distinct(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.5, "kind": "damage",
                 "damage": 12, "caster": target_id, "target": player_id,
                 "selectedTargetId": target_id}
        old = self.sample(10.5, 100, 100, incoming=event)
        old["snapshot"]["sessionId"] = "a" * 32
        newer_before = self.sample(10, 100, 100)
        newer_before["snapshot"]["sessionId"] = "b" * 32
        newer_after = self.sample(11, 88, 100, incoming=event)
        newer_after["snapshot"]["sessionId"] = "b" * 32
        observed = summary.summarize(
            [{"status": "encounter-interrupted"}],
            [old, newer_before, newer_after])
        self.assertEqual(2, len(observed["telemetry"]["incomingEvents"]))
        self.assertEqual(1, observed["telemetry"]["incomingCorrelation"]["pairedCount"])

    def test_single_boundary_event_cannot_explain_two_health_drops(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 11.0, "kind": "damage", "damage": 10,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        telemetry = [self.sample(10, 100, 100),
                     self.sample(11, 90, 100, incoming=event),
                     self.sample(12, 80, 100, incoming=event)]
        observed = summary.summarize([{"status": "encounter-interrupted"}], telemetry)
        self.assertEqual(2, len(observed["telemetry"]["selfHealthDrops"]))
        self.assertEqual(1, len(observed["telemetry"]["incomingEvents"]))
        self.assertEqual(1, observed["telemetry"]["incomingCorrelation"]["pairedCount"])

    def test_distinct_damage_events_can_correlate_distinct_drops(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        def event(sequence, clock):
            return {"sequence": sequence, "clock": clock, "kind": "damage",
                    "damage": 10, "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        telemetry = [self.sample(10, 100, 100),
                     self.sample(11, 90, 100, incoming=event(7, 10.5)),
                     self.sample(12, 80, 100, incoming=event(8, 11.5))]
        observed = summary.summarize([{"status": "encounter-interrupted"}], telemetry)
        self.assertEqual(2, observed["telemetry"]["incomingCorrelation"]["pairedCount"])

    def test_target_switch_between_samples_blocks_prior_event_attribution(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        before = self.sample(10, 100, 100, incoming=event)
        after = self.sample(11, 88, 100)
        after["snapshot"]["targetId"] = "u0000000000000003"
        after["targetId"] = "u0000000000000003"
        value = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["telemetry"]["selfHealthDrops"][0]["attributionEligible"])
        self.assertEqual("observed-unpaired",
                         value["telemetry"]["incomingCorrelation"]["status"])

    def test_replayed_frame_sequence_cannot_qualify_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        after = self.sample(11, 88, 100, incoming=event)
        after["snapshot"]["sequence"] = before["snapshot"]["sequence"]
        value = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["telemetry"]["selfHealthDrops"][0]["attributionEligible"])

    def test_native_to_normalized_health_fallback_cannot_claim_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        before["native"] = {"player": {"health": {"current": 18208, "maximum": 18208}}}
        after = self.sample(11, 90, 100, incoming=incoming)
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(result["acceptance"]["incomingDamage"])
        self.assertEqual([], result["telemetry"]["selfHealthDrops"])
        self.assertEqual("unavailable", result["telemetry"]["incomingCorrelation"]["status"])

    def test_same_native_health_basis_preserves_exact_damage_correlation(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        before["native"] = {"player": {"health": {"current": 18208, "maximum": 18208}}}
        after = self.sample(11, 90, 100, incoming=incoming)
        after["native"] = {"player": {"health": {"current": 18196, "maximum": 18208}}}
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertTrue(result["acceptance"]["incomingDamage"])
        self.assertEqual(12, result["telemetry"]["selfHealthDrops"][0]["amount"])

    def test_declared_unavailable_native_health_cannot_fabricate_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.5, "kind": "damage",
                    "damage": 25, "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        outgoing = {"sequence": 8, "clock": 10.5, "kind": "damage",
                    "damage": 25, "caster": player_id, "target": target_id,
                    "selectedTargetId": target_id}
        for field, label in (("player", "incomingDamage"),
                             ("selectedTarget", "outgoingDamage")):
            for rejection in ({"available": False, "status": "calculated-candidate"},
                              {"available": True, "status": "unavailable"}):
                with self.subTest(field=field, rejection=rejection):
                    before = self.sample(10, 100, 100)
                    after = self.sample(11, 100, 100,
                                        incoming=incoming, outgoing=outgoing)
                    before["native"] = {field: {"health": {
                        "available": True, "status": "calculated-candidate",
                        "current": 100, "maximum": 100}}}
                    after["native"] = {field: {"health": {
                        **rejection, "current": 75, "maximum": 100}}}
                    result = summary.summarize(
                        [{"status": "encounter-interrupted"}], [before, after])
                    self.assertFalse(result["acceptance"][label])
                    drop_field = ("selfHealthDrops" if field == "player"
                                  else "targetHealthDrops")
                    self.assertEqual([], result["telemetry"][drop_field])

    def test_native_to_snapshot_target_fallback_cannot_claim_outgoing_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        outgoing = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 20,
                    "caster": player_id, "target": target_id,
                    "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        before["native"] = {"selectedTarget": {"health": {"current": 577, "maximum": 577}}}
        after = self.sample(11, 100, 80, outgoing=outgoing)
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(result["acceptance"]["outgoingDamage"])
        self.assertEqual([], result["telemetry"]["targetHealthDrops"])

    def test_maximum_health_change_cannot_claim_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        before["native"] = {"player": {"health": {"current": 100, "maximum": 100}}}
        after = self.sample(11, 90, 100, incoming=incoming)
        after["native"] = {"player": {"health": {"current": 90, "maximum": 120}}}
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(result["acceptance"]["incomingDamage"])
        self.assertEqual([], result["telemetry"]["selfHealthDrops"])

    def test_native_vs_addon_health_disagreement_is_visible_without_qualification(self):
        before = self.sample(10, 100, 100)
        after = self.sample(11, 100, 80)
        before["native"] = {
            "player": {"health": {"available": True, "status": "calculated-candidate",
                                   "current": 100, "maximum": 100}},
            "selectedTarget": {"health": {"available": True, "status": "calculated-candidate",
                                           "current": 100, "maximum": 100}},
        }
        after["native"] = {
            "player": {"health": {"available": True, "status": "calculated-candidate",
                                   "current": 88, "maximum": 100}},
            "selectedTarget": {"health": {"available": True, "status": "calculated-candidate",
                                           "current": 70, "maximum": 100}},
        }
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        concordance = result["telemetry"]["nativeSnapshotHealthComparison"]
        self.assertEqual("mismatch-observed", concordance["status"])
        for key, gap in (("player", -12), ("selectedTarget", -10)):
            data = concordance[key]
            self.assertEqual(2, data["comparableSamples"])
            self.assertEqual(1, data["matchingSamples"])
            self.assertEqual(1, data["mismatchedSamples"])
            self.assertEqual(abs(gap), data["largestAbsoluteCurrentGap"])
            self.assertEqual(gap, data["firstMismatch"]["nativeMinusSnapshotCurrent"])
            self.assertEqual(110, data["firstMismatch"]["sequence"])

    def test_health_concordance_excludes_unavailable_and_invalid_pairs(self):
        before = self.sample(10, 100, 100)
        after = self.sample(11, 80, 80)
        before["native"] = {"player": {"health": {
            "available": False, "status": "calculated-candidate",
            "current": 90, "maximum": 100}}}
        after["native"] = {"player": {"health": {
            "available": True, "status": "calculated-candidate",
            "current": -10, "maximum": 100}}}
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        data = result["telemetry"]["nativeSnapshotHealthComparison"]
        self.assertEqual("unavailable", data["status"])
        self.assertEqual(0, data["player"]["comparableSamples"])
        self.assertEqual(0, data["selectedTarget"]["comparableSamples"])

    def test_conflicting_or_incomplete_release_receipts_fail_closed(self):
        bad_receipts = (
            {"releaseSucceeded": True, "allInputsReleased": False, "desktopInputsDown": []},
            {"releaseSucceeded": True, "allInputsReleased": "true", "desktopInputsDown": []},
            {"releaseSucceeded": True, "allInputsReleased": True, "desktopInputsDown": ["w"]},
            {"releaseSucceeded": True},
        )
        for receipt in bad_receipts:
            with self.subTest(receipt=receipt):
                route = [{"status": "encounter-interrupted", **receipt},
                         {"status": "arrived", **receipt}]
                observed = summary.summarize(route)
                self.assertFalse(observed["route"]["encounterReleaseVerified"])
                self.assertFalse(observed["route"]["allRetainedReleasesVerified"])
                self.assertFalse(observed["route"]["terminalInputsReleased"])

    def test_terminal_without_release_receipt_cannot_borrow_earlier_cleanup(self):
        route = [{"status": "encounter-interrupted", "releaseSucceeded": True,
                  "desktopInputsDown": []}, {"status": "arrived"}]
        observed = summary.summarize(route)
        self.assertTrue(observed["route"]["encounterReleaseVerified"])
        self.assertTrue(observed["route"]["allRetainedReleasesVerified"])
        self.assertFalse(observed["route"]["terminalInputsReleased"])

    def test_duplicate_json_evidence_keys_are_rejected_before_acceptance(self):
        ambiguous = (
            '{"status":"stopped","status":"arrived","releaseSucceeded":false,'
            '"releaseSucceeded":true,"desktopInputsDown":[]}\n',
            '{"status":"arrived","telemetry":{"player":{"healthPct":20,'
            '"healthPct":100}}}\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ambiguous.jsonl"
            for payload in ambiguous:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(summary.AcceptanceError, "duplicate-json-key"):
                        summary._rows(path)

    def test_strict_route_gate_blocks_interruption_without_release_proof(self):
        arrived = {"status": "arrived", "nextWaypoint": 2, "waypointCount": 2,
                   "releaseSucceeded": True, "allInputsReleased": True,
                   "desktopInputsDown": []}
        cases = (
            {"status": "encounter-interrupted"},
            {"status": "encounter-interrupted", "releaseSucceeded": True},
        )
        for interrupted in cases:
            with self.subTest(interrupted=interrupted):
                result = summary.summarize([interrupted, arrived])
                self.assertEqual("prior-release-unverified",
                                 result["route"]["completionGate"]["reason"])
                self.assertFalse(result["route"]["allRetainedReleasesVerified"])
                self.assertFalse(result["route"]["encounterReleaseVerified"])

    def test_strict_route_gate_rejects_earlier_arrival_followed_by_active_work(self):
        arrived = {"status": "arrived", "nextWaypoint": 2, "waypointCount": 2,
                   "releaseSucceeded": True, "allInputsReleased": True,
                   "desktopInputsDown": []}
        result = summary.summarize([arrived, {"status": "moving", "nextWaypoint": 1}])
        self.assertEqual("terminal-not-final", result["route"]["completionGate"]["reason"])

    def test_strict_route_gate_admits_only_full_final_arrival_with_release(self):
        route = [{"status": "moving", "nextWaypoint": 2, "waypointCount": 3},
                 {"status": "arrived", "nextWaypoint": 3, "waypointCount": 3,
                  "releaseSucceeded": True, "desktopInputsDown": [],
                  "allInputsReleased": True}]
        report = summary.summarize(route)
        self.assertEqual({"status": "admitted", "reason": "full-arrival-receipts-only"},
                         report["route"]["completionGate"])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "route.jsonl"
            source.write_text("".join(json.dumps(row) + "\n" for row in route),
                              encoding="utf-8")
            self.assertEqual(0, summary.main(["--route", str(source),
                                              "--require-complete-route"]))

    def test_strict_route_gate_blocks_partial_failure_and_unverified_release(self):
        good = {"status": "arrived", "nextWaypoint": 3, "waypointCount": 3,
                "releaseSucceeded": True, "desktopInputsDown": []}
        cases = (
            ([{**good, "nextWaypoint": 2}], "incomplete-waypoint-progress"),
            ([{**good, "releaseSucceeded": False}], "terminal-release-unverified"),
            ([good, {"status": "failed", "reason": "target-lost"}], "terminal-not-arrived"),
            ([{"status": "encounter-interrupted", "releaseSucceeded": False,
               "desktopInputsDown": ["w"]}, good], "prior-release-unverified"),
            ([{"status": "moving", "nextWaypoint": 3, "waypointCount": 3}],
             "terminal-missing"),
            ([{**good, "waypointCount": None}], "incomplete-waypoint-progress"),
        )
        for route, reason in cases:
            with self.subTest(reason=reason):
                report = summary.summarize(route)
                self.assertEqual("blocked", report["route"]["completionGate"]["status"])
                self.assertEqual(reason, report["route"]["completionGate"]["reason"])
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory) / "route.jsonl"
                    source.write_text("".join(json.dumps(row) + "\n" for row in route),
                                      encoding="utf-8")
                    self.assertEqual(2, summary.main(
                        ["--route", str(source), "--require-complete-route"]))

    def test_incomplete_second_retreat_cannot_borrow_first_resumption(self):
        states = ("travel", "retreat", "recover", "rejoin", "travel",
                  "retreat", "recover")
        telemetry = [self.sample(10 + index, 100, 100, state=state)
                     for index, state in enumerate(states)]
        observed = summary.summarize([{"status": "stopped"}], telemetry)
        self.assertEqual("preserved", observed["acceptance"]["checkpointInvariant"])
        self.assertEqual("violated", observed["acceptance"]["recoveryResumeInvariant"])

    def test_rejoin_after_another_retreat_cannot_complete_first_cycle(self):
        states = ("travel", "retreat", "recover", "retreat", "rejoin", "travel")
        telemetry = [self.sample(10 + index, 100, 100, state=state)
                     for index, state in enumerate(states)]
        observed = summary.summarize([{"status": "stopped"}], telemetry)
        self.assertEqual("violated", observed["acceptance"]["recoveryResumeInvariant"])

    def test_multiple_completed_retreats_still_preserve_recovery_invariant(self):
        states = ("travel", "retreat", "recover", "rejoin", "travel",
                  "retreat", "recover", "rejoin", "travel")
        telemetry = [self.sample(10 + index, 100, 100, state=state)
                     for index, state in enumerate(states)]
        observed = summary.summarize([{"status": "stopped"}], telemetry)
        self.assertTrue(observed["telemetry"]["continuityVerified"])
        self.assertEqual("preserved", observed["acceptance"]["recoveryResumeInvariant"])

    def test_retreat_requires_ordered_recovery_rejoin_and_travel(self):
        # A rejoin/travel pair alone must not masquerade as completed recovery.
        # Travel before rejoin is also not a valid continuation receipt.
        cases = (
            ("travel", "retreat", "rejoin", "travel"),
            ("travel", "retreat", "rejoin", "recover", "travel"),
            ("travel", "retreat", "recover", "travel", "rejoin", "travel"),
        )
        for states in cases:
            with self.subTest(states=states):
                telemetry = [self.sample(10 + index, 100, 100, state=state)
                             for index, state in enumerate(states)]
                observed = summary.summarize([{"status": "stopped"}], telemetry)
                self.assertEqual("preserved", observed["acceptance"]["checkpointInvariant"])
                self.assertEqual("violated", observed["acceptance"]["recoveryResumeInvariant"])

    def test_recovery_receipts_require_one_advancing_producer(self):
        states = ("travel", "retreat", "recover", "rejoin", "travel")
        def frames():
            return [self.sample(10 + i, 100, 100, state=state)
                    for i, state in enumerate(states)]
        for failure in ("session-reset", "sequence-rollback", "clock-rollback",
                        "malformed-session"):
            with self.subTest(failure=failure):
                telemetry = frames()
                if failure == "session-reset":
                    for index in (3, 4):
                        telemetry[index]["snapshot"]["sessionId"] = "b" * 32
                        telemetry[index]["snapshot"]["sequence"] = index - 2
                elif failure == "sequence-rollback":
                    telemetry[3]["snapshot"]["sequence"] = 1
                elif failure == "clock-rollback":
                    telemetry[3]["snapshot"]["frameTime"] = 9.0
                else:
                    telemetry[3]["snapshot"]["sessionId"] = {"not": "a nonce"}
                observed = summary.summarize([{"status": "stopped"}], telemetry)
                self.assertFalse(observed["telemetry"]["continuityVerified"])
                self.assertEqual("unavailable",
                                 observed["acceptance"]["checkpointInvariant"])
                self.assertEqual("unavailable",
                                 observed["acceptance"]["recoveryResumeInvariant"])
                self.assertEqual("unavailable",
                                 observed["acceptance"]["stopInvariant"])

    def test_missing_checkpoint_does_not_claim_retreat_preservation(self):
        states = ("travel", "retreat", "rejoin", "travel")
        telemetry = [self.sample(10 + index, 100, 100, state=state, checkpoint=None)
                     for index, state in enumerate(states)]
        observed = summary.summarize([{"status": "stopped"}], telemetry)
        self.assertEqual("unavailable", observed["acceptance"]["checkpointInvariant"])
        self.assertEqual("violated", observed["acceptance"]["recoveryResumeInvariant"])

    def test_partial_or_empty_checkpoint_cannot_prove_preservation(self):
        states = ("travel", "retreat", "rejoin", "travel")
        for checkpoints in ((2, None, 2, 2), (2, "", 2, 2),
                            (2, {}, 2, 2), (2, [], 2, 2)):
            with self.subTest(checkpoints=checkpoints):
                telemetry = [self.sample(10 + index, 100, 100, state=state,
                                         checkpoint=checkpoints[index])
                             for index, state in enumerate(states)]
                observed = summary.summarize([{"status": "stopped"}], telemetry)
                self.assertEqual("unavailable", observed["acceptance"]["checkpointInvariant"])
                self.assertEqual("violated", observed["acceptance"]["recoveryResumeInvariant"])

    def test_structured_checkpoint_is_comparable_without_hashing(self):
        states = ("travel", "retreat", "rejoin", "travel")
        for last, expected in (({"nextWaypoint": 2, "route": [1, 2]}, "preserved"),
                               ({"nextWaypoint": 3, "route": [1, 2]}, "changed-while-interrupted")):
            with self.subTest(last=last):
                telemetry = [self.sample(10 + index, 100, 100, state=state,
                                         checkpoint=last if index == 2 else
                                         {"nextWaypoint": 2, "route": [1, 2]})
                             for index, state in enumerate(states)]
                observed = summary.summarize([{"status": "stopped"}], telemetry)
                self.assertEqual(expected, observed["acceptance"]["checkpointInvariant"])

    def test_malformed_structured_event_identity_cannot_crash_or_claim_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.5, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id,
                    "selectedTargetId": target_id}
        outgoing = {"sequence": 8, "clock": 10.5, "kind": "damage", "damage": 20,
                    "caster": player_id, "target": target_id,
                    "selectedTargetId": target_id}
        for event_kind, original in (("incoming", incoming), ("outgoing", outgoing)):
            for key, invalid in (("sequence", [7]), ("clock", {"at": 10.5}),
                                 ("caster", {"id": player_id}),
                                 ("target", [target_id])):
                with self.subTest(event=event_kind, field=key):
                    before = self.sample(10, 100, 100)
                    after = self.sample(11, 88, 80,
                                        **{event_kind: {**original, key: invalid}})
                    report = summary.summarize([{"status": "encounter-interrupted"}],
                                               [before, after])
                    self.assertFalse(report["acceptance"]["incomingDamage"])
                    self.assertFalse(report["acceptance"]["outgoingDamage"])
                    self.assertEqual("unavailable",
                                     report["telemetry"][event_kind + "Correlation"]["status"])

    def test_extreme_numeric_receipts_are_unavailable_not_exceptions(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10 ** 400, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id,
                 "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        after = self.sample(11, 88, 100, incoming=event)
        result = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(result["acceptance"]["incomingDamage"])
        self.assertEqual("unavailable", result["telemetry"]["incomingCorrelation"]["status"])

        after = self.sample(11, 88, 100)
        after["native"] = {"player": {"health": {"current": 10 ** 400, "maximum": 10 ** 400}}}
        result = summary.summarize([{"status": "stopped"}], [before, after])
        self.assertEqual("telemetry-percent", result["telemetry"]["selfHealthDrops"][0]["basis"])

    def test_stop_clear_throughout_requires_every_retained_frame(self):
        frames = [self.sample(10 + index, 100, 100, state=state)
                  for index, state in enumerate(
                      ("travel", "retreat", "recover", "rejoin", "travel"))]
        for invalid in (None, "false", [], 0):
            with self.subTest(invalid=invalid):
                samples = [dict(frame) for frame in frames]
                samples[2] = dict(samples[2])
                if invalid is None:
                    samples[2].pop("stopSet")
                else:
                    samples[2]["stopSet"] = invalid
                report = summary.summarize([{"status": "stopped"}], samples)
                self.assertEqual("unavailable", report["acceptance"]["stopInvariant"])

    def test_survival_route_gate_requires_recovery_and_matching_encounters(self):
        interrupted = {"status": "encounter-interrupted", "releaseSucceeded": True,
                       "desktopInputsDown": []}
        arrived = {"status": "arrived", "releaseSucceeded": True,
                   "desktopInputsDown": [], "waypointCount": 3, "nextWaypoint": 3}
        states = ("travel", "retreat", "recover", "rejoin", "travel")
        telemetry = [self.sample(10 + i, 100, 100, state=state)
                     for i, state in enumerate(states)]
        route = [interrupted, arrived]
        admitted = summary.summarize(route, telemetry)
        self.assertEqual("admitted", admitted["route"]["survivalCompletionGate"]["status"])

        missing = summary.summarize(route)
        self.assertEqual("telemetry-missing", missing["route"]["survivalCompletionGate"]["reason"])
        broken = [dict(row) for row in telemetry]
        broken[3] = dict(broken[3])
        broken[3]["snapshot"] = dict(broken[3]["snapshot"])
        broken[3]["snapshot"]["sequence"] = 1
        self.assertEqual("producer-discontinuous",
                         summary.summarize(route, broken)["route"]["survivalCompletionGate"]["reason"])
        self.assertEqual("encounter-retreat-count-mismatch",
                         summary.summarize([interrupted, interrupted, arrived], telemetry)
                         ["route"]["survivalCompletionGate"]["reason"])
        self.assertEqual("route-incomplete",
                         summary.summarize([interrupted, {**arrived, "nextWaypoint": 2}], telemetry)
                         ["route"]["survivalCompletionGate"]["reason"])
        unsafe = [dict(row) for row in telemetry]
        unsafe[2] = dict(unsafe[2])
        unsafe[2].pop("stopSet")
        self.assertEqual("stop-unverified",
                         summary.summarize(route, unsafe)["route"]["survivalCompletionGate"]["reason"])

    def test_survival_route_cli_refuses_unqualified_rejoin(self):
        interrupted = {"status": "encounter-interrupted", "releaseSucceeded": True,
                       "desktopInputsDown": []}
        arrived = {"status": "arrived", "releaseSucceeded": True,
                   "desktopInputsDown": [], "waypointCount": 2, "nextWaypoint": 2}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route = root / "route.jsonl"
            telemetry = root / "telemetry.jsonl"
            route.write_text("".join(json.dumps(row) + "\n" for row in (interrupted, arrived)),
                             encoding="utf-8")
            self.assertEqual(2, summary.main(["--route", str(route),
                                              "--require-survival-route"]))
            states = ("travel", "retreat", "recover", "rejoin", "travel")
            telemetry.write_text("".join(
                json.dumps(self.sample(10 + index, 100, 100, state=state)) + "\n"
                for index, state in enumerate(states)), encoding="utf-8")
            self.assertEqual(0, summary.main(["--route", str(route),
                                              "--telemetry", str(telemetry),
                                              "--require-survival-route"]))

    def test_route_only_never_claims_damage_and_cli_writes_new_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route = root / "route.jsonl"
            output = root / "summary.json"
            route.write_text(json.dumps({"status": "arrived", "releaseSucceeded": True,
                                         "desktopInputsDown": [], "nextIndex": 2}) + "\n",
                             encoding="utf-8")
            self.assertEqual(0, summary.main(["--route", str(route), "--output", str(output)]))
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("unavailable", value["telemetry"]["status"])
            self.assertFalse(value["acceptance"]["incomingDamage"])
            with self.assertRaisesRegex(summary.AcceptanceError, "output-exists"):
                summary.main(["--route", str(route), "--output", str(output)])


if __name__ == "__main__":
    unittest.main()
