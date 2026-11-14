"""No-input headless action-owner dry-run contract tests."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import replay_player_actions as cli

OK = {"releaseSucceeded": True, "desktopInputsDown": []}
BAD = {"releaseSucceeded": False, "desktopInputsDown": ["w"]}


def event(action, receipt=OK):
    return {"action": action, "release": receipt}


class ReplayPlayerActionsTests(unittest.TestCase):
    def run_plan(self, *events):
        return cli.replay({"schemaVersion": 1, "events": list(events)})

    def test_travel_encounter_recovery_route_and_stop(self):
        result = self.run_plan(
            event("new-run"), event("encounter"), event("combat-needs-recovery"),
            event("recovery-ready"), {"action": "operator-stop"})
        self.assertEqual(result["status"], "complete")
        self.assertEqual([s["state"]["activeAction"] for s in result["states"]],
                         ["movement", "combat", "recovery", "movement", None])
        self.assertEqual(result["final"]["latchReason"], "operator-stop")
        self.assertEqual(result["final"]["routeCheckpointPolicy"], "external-unchanged")
        self.assertFalse(result["gameInputSent"])
        self.assertEqual([t["reason"] for t in result["callbackTrace"]
                          if t["callback"] == "release"],
                         ["encounter-interrupt", "combat-to-recovery",
                          "recovery-complete", "operator-stop"])

    def test_release_uncertainty_blocks_encounter_and_requires_explicit_resume(self):
        result = self.run_plan(event("new-run", BAD), event("encounter"),
                               event("combat-ready"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failedStep"], 3)
        self.assertEqual(result["final"]["activeAction"], "movement")
        self.assertEqual(result["final"]["latchReason"], "uncertain-release")
        self.assertFalse(any(t["callback"] == "start" and t["owner"] == "combat"
                             for t in result["callbackTrace"]))

        result = self.run_plan(event("new-run", BAD), event("encounter"),
                               event("retry-release", OK), event("resume"),
                               {"action": "operator-stop"})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["states"][2]["state"]["latchReason"], "uncertain-release")
        self.assertEqual(result["states"][2]["state"]["activeAction"], None)

    def test_critical_death_remains_latched(self):
        result = self.run_plan(event("new-run"), {"action": "critical", "reason": "death"},
                               event("encounter"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["final"]["latchReason"], "death")
        self.assertFalse(result["gameInputSent"])

    def test_invalid_receipt_and_invalid_event_do_not_start_actions(self):
        for case in (event("new-run", {"releaseSucceeded": "true", "desktopInputsDown": []}),
                     {"action": "new-run"},
                     {"action": "operator-stop", "release": OK},
                     {"action": "not-real"}):
            with self.subTest(case=case):
                result = self.run_plan(case)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["callbackTrace"], [])
                self.assertFalse(result["gameInputSent"])

    def test_final_uncertain_release_is_not_reported_as_completed(self):
        # An encounter refusal returns a latched snapshot, not an exception.
        # The CLI must not label the whole run successful if replay ends here.
        result = self.run_plan(event("new-run", BAD), event("encounter"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "unresolved-uncertain-release")
        self.assertEqual(result["failedStep"], 2)
        self.assertEqual(result["final"]["activeAction"], "movement")
        self.assertFalse(any(t["callback"] == "start" and t["owner"] == "combat"
                             for t in result["callbackTrace"]))

    def test_cleanup_retry_still_requires_explicit_resume(self):
        result = self.run_plan(event("new-run", BAD), event("encounter"),
                               event("retry-release", OK))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "unresolved-uncertain-release")
        self.assertIsNone(result["final"]["activeAction"])
        self.assertEqual(result["final"]["latchReason"], "uncertain-release")
        recovered = self.run_plan(event("new-run", BAD), event("encounter"),
                                  event("retry-release", OK), event("resume"),
                                  {"action": "operator-stop"})
        self.assertEqual(recovered["status"], "complete")
        self.assertEqual(recovered["final"]["latchReason"], "operator-stop")

    def test_input_bounds_and_duplicate_json_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid-action-plan"):
            cli.replay({"schemaVersion": 1, "events": [event("new-run")] * 65})
        with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
            json.loads('{"schemaVersion":1,"schemaVersion":1,"events":[]}',
                       object_pairs_hook=cli._unique_object)
        with self.assertRaisesRegex(ValueError, "nonfinite-json-number"):
            json.loads('{"x":NaN}', parse_constant=cli._invalid_constant)

    def test_headless_cli_returns_blocked_exit_for_unresolved_release(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "uncertain.json"
            source.write_text(json.dumps({"schemaVersion": 1, "events": [
                event("new-run", BAD), event("encounter")]}), encoding="utf-8")
            capture = StringIO()
            with redirect_stdout(capture):
                code = cli.main(["--events", str(source)])
            payload = json.loads(capture.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["reason"], "unresolved-uncertain-release")
            self.assertFalse(payload["gameInputSent"])

    def test_real_headless_cli_reads_only_plan_file(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "events.json"
            source.write_text(json.dumps({"schemaVersion": 1, "events": [
                event("new-run"), {"action": "operator-stop"}]}), encoding="utf-8")
            capture = StringIO()
            with redirect_stdout(capture):
                code = cli.main(["--events", str(source)])
            payload = json.loads(capture.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["final"]["latchReason"], "operator-stop")
            self.assertEqual(payload["mode"], "offline-scripted-receipts-only")
            source.write_text('{"schemaVersion":1,"schemaVersion":1,"events":[]}',
                              encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(cli.main(["--events", str(source)]), 2)


if __name__ == "__main__":
    unittest.main()
