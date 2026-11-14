import unittest
from unittest.mock import Mock

from scripts.player_action_coordinator import ActionCoordinationError, PlayerActionCoordinator


def released(**extra):
    return {"releaseSucceeded": True, "desktopInputsDown": [], **extra}


class PlayerActionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = PlayerActionCoordinator()
        self.move_start, self.move_release = Mock(), Mock(return_value=released(action="movement"))
        self.combat_start, self.combat_release = Mock(), Mock(return_value=released(action="combat"))

    def test_encounter_handoff_releases_movement_before_combat_and_checkpoint_is_external(self):
        order = []
        self.coordinator.new_run(lambda: order.append("move-start"),
                                 lambda reason: order.append("move-release") or released(reason=reason))
        state = self.coordinator.encounter(lambda: order.append("combat-start"),
                                           lambda reason: order.append("combat-release") or released(reason=reason))
        self.assertEqual(["move-start", "move-release", "combat-start"], order)
        self.assertEqual("combat", state["activeAction"])
        self.assertEqual("external-unchanged", state["routeCheckpointPolicy"])
        self.assertFalse(state["coordinatorInputSent"])
        self.assertNotIn("checkpoint", state)

    def test_uncertain_movement_release_blocks_combat_and_all_other_actions(self):
        self.coordinator.new_run(self.move_start,
            Mock(return_value={"releaseSucceeded": False, "desktopInputsDown": ["w"]}))
        state = self.coordinator.encounter(self.combat_start, self.combat_release)
        self.assertEqual(("movement", "uncertain-release"),
                         (state["activeAction"], state["latchReason"]))
        self.combat_start.assert_not_called()
        with self.assertRaisesRegex(ActionCoordinationError, "release the active"):
            self.coordinator.new_run(self.move_start, self.move_release)

    def test_successful_release_retry_stays_latched_until_explicit_resume(self):
        self.coordinator.new_run(self.move_start, Mock(return_value=None))
        self.coordinator.operator_stop()
        retried = self.coordinator.retry_release(Mock(return_value=released()))
        self.assertIsNone(retried["activeAction"])
        self.assertEqual("uncertain-release", retried["latchReason"])
        with self.assertRaisesRegex(ActionCoordinationError, "latched"):
            self.coordinator._start("movement", self.move_start, self.move_release)
        resumed = self.coordinator.resume(self.move_start, self.move_release)
        self.assertEqual(("active", "movement", None),
                         (resumed["status"], resumed["activeAction"], resumed["latchReason"]))

    def test_operator_stop_and_death_latch_after_confirmed_release(self):
        self.coordinator.new_run(self.move_start, self.move_release)
        stopped = self.coordinator.operator_stop()
        self.assertEqual((None, "operator-stop"),
                         (stopped["activeAction"], stopped["latchReason"]))
        self.coordinator.resume(self.move_start, self.move_release)
        dead = self.coordinator.critical("death")
        self.assertEqual((None, "death"), (dead["activeAction"], dead["latchReason"]))

    def test_ready_combat_and_recovery_can_continue_movement(self):
        self.coordinator.new_run(self.move_start, self.move_release)
        self.coordinator.encounter(self.combat_start, self.combat_release)
        recovery_start = Mock()
        recovery_release = Mock(return_value={"allInputsReleased": True})
        recovering = self.coordinator.combat_needs_recovery(recovery_start, recovery_release)
        self.assertEqual("recovery", recovering["activeAction"])
        continued = self.coordinator.recovery_ready(self.move_start, self.move_release)
        self.assertEqual("movement", continued["activeAction"])
        recovery_start.assert_called_once()

    def test_ready_combat_can_continue_without_recovery(self):
        self.coordinator.new_run(self.move_start, self.move_release)
        self.coordinator.encounter(self.combat_start, self.combat_release)
        continued = self.coordinator.combat_ready(self.move_start, self.move_release)
        self.assertEqual("movement", continued["activeAction"])
        self.combat_release.assert_called_once_with("combat-complete")

    def test_reentrant_start_is_refused_without_a_second_lock(self):
        observed = []
        def start():
            observed.append(self.coordinator.snapshot()["activeAction"])
            with self.assertRaisesRegex(ActionCoordinationError, "already owns"):
                self.coordinator._start("combat", self.combat_start, self.combat_release)
        self.coordinator.new_run(start, self.move_release)
        self.assertEqual(["movement"], observed)

    def test_stop_during_encounter_release_runs_callback_once_and_prevents_combat(self):
        def release(reason):
            self.assertEqual(reason, "encounter-interrupt")
            self.assertEqual(self.coordinator.operator_stop()["latchReason"], "operator-stop")
            return released()
        callback = Mock(side_effect=release)
        self.coordinator.new_run(self.move_start, callback)
        state = self.coordinator.encounter(self.combat_start, self.combat_release)
        callback.assert_called_once_with("encounter-interrupt")
        self.combat_start.assert_not_called()
        self.assertEqual((None, "operator-stop"), (state["activeAction"], state["latchReason"]))

    def test_stop_and_critical_are_latched_before_their_release_callback(self):
        for reason in ("operator-stop", "death", "critical-unavailable"):
            with self.subTest(reason=reason):
                def release(received):
                    self.assertEqual(self.coordinator.snapshot()["latchReason"], received)
                    self.assertEqual(self.coordinator.operator_stop()["latchReason"], received)
                    return released()
                callback = Mock(side_effect=release)
                self.coordinator.new_run(self.move_start, callback)
                state = (self.coordinator.operator_stop() if reason == "operator-stop"
                         else self.coordinator.critical(reason))
                callback.assert_called_once_with(reason)
                self.assertEqual((None, reason), (state["activeAction"], state["latchReason"]))

    def test_nested_encounter_refused_while_original_handoff_can_finish(self):
        nested_start = Mock()
        def release(reason):
            with self.assertRaisesRegex(ActionCoordinationError, "release already in progress"):
                self.coordinator.encounter(nested_start, self.combat_release)
            return released()
        callback = Mock(side_effect=release)
        self.coordinator.new_run(self.move_start, callback)
        state = self.coordinator.encounter(self.combat_start, self.combat_release)
        callback.assert_called_once()
        nested_start.assert_not_called()
        self.combat_start.assert_called_once()
        self.assertEqual("combat", state["activeAction"])

    def test_reentrant_stop_cannot_conceal_unconfirmed_release(self):
        def release(reason):
            self.coordinator.operator_stop()
            raise RuntimeError("missing native release receipt")
        self.coordinator.new_run(self.move_start, release)
        state = self.coordinator.encounter(self.combat_start, self.combat_release)
        self.assertEqual(("movement", "uncertain-release"), (state["activeAction"], state["latchReason"]))
        self.combat_start.assert_not_called()

    def test_stop_cannot_erase_terminal_death_or_unavailable_latch(self):
        for reason in ("death", "critical-unavailable"):
            with self.subTest(reason=reason):
                coordinator = PlayerActionCoordinator()
                release = Mock(return_value=released())
                coordinator.new_run(Mock(), release)
                terminal = coordinator.critical(reason)
                self.assertEqual(terminal["latchReason"], reason)
                self.assertIsNone(terminal["activeAction"])
                stopped = coordinator.operator_stop()
                self.assertEqual(stopped["latchReason"], reason)
                self.assertIsNone(stopped["activeAction"])
                release.assert_called_once_with(reason)

    def test_start_failure_remains_owned_and_latched_for_release(self):
        def fail():
            raise RuntimeError("partial start")
        with self.assertRaisesRegex(RuntimeError, "partial start"):
            self.coordinator.new_run(fail, self.move_release)
        state = self.coordinator.snapshot()
        self.assertEqual(("movement", "action-start-failed"),
                         (state["activeAction"], state["latchReason"]))
        stopped = self.coordinator.operator_stop()
        self.assertEqual((None, "operator-stop"),
                         (stopped["activeAction"], stopped["latchReason"]))


if __name__ == "__main__":
    unittest.main()
