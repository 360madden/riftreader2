from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from scripts import launch_live_reader as launcher


NONCE = "a" * 32
ENDPOINT = "http://192.168.56.1:49813/observation"
ARGS = SimpleNamespace(expected_game_pid=42,
                       expected_game_start_ticks=639032712345678901,
                       expected_game_sha256="A" * 64)


def snapshot():
    return {"nonce": NONCE, "readerStatus": "running", "target": {
        "readerSessionNonce": NONCE,
        "processId": ARGS.expected_game_pid,
        "processStartUtcTicks": ARGS.expected_game_start_ticks,
        "executableSha256": ARGS.expected_game_sha256},
        "delivery": {"enabled": True, "endpoint": ENDPOINT},
        "riftReader2": {"selectionStatus": "unbound"}}


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
class GeneratedReadinessTests(unittest.TestCase):
    def run_wait(self, observations, *, stdout=None, exit_on_poll=0, expire_on_poll=None,
                 clear_stdout_on_poll=0):
        """Run production polling code; only sleep/process and input files are fake."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, value in enumerate(observations, 1):
                raw = value if isinstance(value, str) else json.dumps(value)
                (root / f"poll-{index}.json").write_text(raw, encoding="utf-8")
            (root / "stdout.txt").write_text(
                stdout if stdout is not None else f"/rr2bind {NONCE}\n", encoding="utf-8")
            body = launcher.reader_readiness_script(ARGS, ENDPOINT, timeout_seconds=2, poll_ms=1)
            script = r"""
$ErrorActionPreference='Stop'
$root=ROOT
$stdout=Join-Path $root 'stdout.txt';$latest=Join-Path $root 'latest.json'
$p=[pscustomobject]@{HasExited=$false};$script:poll=0
function Start-Sleep {
    param($Milliseconds)
    $script:poll++
    $source=Join-Path $root ('poll-'+[Math]::Min($script:poll,COUNT)+'.json')
    Copy-Item -LiteralPath $source -Destination $latest -Force
    if(CLEARPOLL -gt 0 -and $script:poll -ge CLEARPOLL){Remove-Item -LiteralPath $stdout -ErrorAction SilentlyContinue}
    if($script:poll -ge EXPIREPOLL){$script:deadline=[DateTime]::UtcNow.AddSeconds(-1)}
    if(EXITPOLL -gt 0 -and $script:poll -ge EXITPOLL){$p.HasExited=$true}
}
try {
BODY
    @{status='ready';nonce=$nonce;polls=$script:poll;snapshot=$snapshot}|ConvertTo-Json -Depth 8 -Compress
} catch {
    @{status='refused';reason=$_.Exception.Message;nonce=$nonce;polls=$script:poll;snapshot=$snapshot}|ConvertTo-Json -Depth 8 -Compress
}
""".replace("ROOT", launcher.quote(str(root))).replace("COUNT", str(len(observations)))
            script = script.replace("EXITPOLL", str(exit_on_poll)).replace("BODY", body)
            script = script.replace("EXPIREPOLL", str(expire_on_poll or len(observations) + 1))
            script = script.replace("CLEARPOLL", str(clear_stdout_on_poll))
            path = root / "test.ps1"
            path.write_text(script, encoding="utf-8-sig")
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)

    def test_exact_large_tick_tuple_and_delivery_succeed_even_on_last_poll(self):
        result = self.run_wait([snapshot()])
        self.assertEqual("ready", result["status"])
        self.assertEqual(ARGS.expected_game_start_ticks,
                         result["snapshot"]["target"]["processStartUtcTicks"])
        self.assertEqual(NONCE, result["nonce"])

    def test_nonempty_mismatched_snapshot_never_becomes_ready_at_timeout(self):
        cases = [("nonce", "b" * 32), ("readerStatus", "terminated"),
                 ("target.readerSessionNonce", "b" * 32), ("target.processId", 43),
                 ("target.processStartUtcTicks", ARGS.expected_game_start_ticks + 1),
                 ("target.executableSha256", "B" * 64),
                 ("delivery.enabled", False), ("delivery.endpoint", ENDPOINT + "/other"),
                 ("nonce", NONCE + "\x00"),
                 ("target.executableSha256", ARGS.expected_game_sha256 + "\u00ad"),
                 ("delivery.endpoint", ENDPOINT + "\u00ad")]
        for field, value in cases:
            with self.subTest(field=field):
                candidate = snapshot()
                parent, _, key = field.rpartition(".")
                (candidate[parent] if parent else candidate)[key] = value
                result = self.run_wait([candidate])
                self.assertEqual("refused", result["status"])
                self.assertEqual("reader-not-ready", result["reason"])

    def test_missing_malformed_and_wrong_types_fail_closed(self):
        cases = [None, [], {}, "{broken", {"nonce": NONCE}, [snapshot()]]
        for field in ("target", "delivery"):
            candidate = snapshot()
            candidate[field] = [candidate[field]]
            cases.append(candidate)
        for field, values in (("processId", ("42", True, 42.0, None)),
                              ("processStartUtcTicks", (str(ARGS.expected_game_start_ticks), True, None))):
            for value in values:
                candidate = snapshot()
                candidate["target"][field] = value
                cases.append(candidate)
            candidate = snapshot()
            del candidate["target"][field]
            cases.append(candidate)
        for field in ("nonce", "readerStatus", "target.readerSessionNonce",
                      "target.executableSha256", "delivery.endpoint"):
            candidate = snapshot()
            parent, _, key = field.rpartition(".")
            container = candidate[parent] if parent else candidate
            container[key] = [container[key]]
            cases.append(candidate)
        for value in ("true", 1, None):
            candidate = snapshot()
            candidate["delivery"]["enabled"] = value
            cases.append(candidate)
        for candidate in cases:
            with self.subTest(candidate=candidate):
                result = self.run_wait([candidate])
                self.assertEqual("refused", result["status"])
                self.assertEqual("reader-not-ready", result["reason"])

    def test_parse_failure_clears_previous_nonmatching_candidate(self):
        candidate = snapshot()
        candidate["nonce"] = "b" * 32
        result = self.run_wait([candidate, "{broken"], exit_on_poll=2)
        self.assertEqual("reader-exited-before-ready", result["reason"])
        self.assertIsNone(result["snapshot"])
        self.assertEqual(2, result["polls"])

    def test_stdout_nonce_is_required_and_must_match(self):
        for stdout in ("", "/rr2bind " + "b" * 32, "prefix /rr2bind " + NONCE,
                       "/rr2bind " + NONCE + "suffix"):
            with self.subTest(stdout=stdout):
                result = self.run_wait([snapshot()], stdout=stdout)
                self.assertEqual("reader-not-ready", result["reason"])

    def test_process_exit_wins_over_matching_final_snapshot(self):
        result = self.run_wait([snapshot()], exit_on_poll=1)
        self.assertEqual("refused", result["status"])
        self.assertEqual("reader-exited-before-ready", result["reason"])

    def test_snapshot_arriving_after_sleep_crosses_deadline_is_refused(self):
        result = self.run_wait([snapshot()], expire_on_poll=1)
        self.assertEqual("reader-not-ready", result["reason"])

    def test_latest_printed_challenge_controls_readiness(self):
        result = self.run_wait([snapshot()], stdout=f"/rr2bind {NONCE}\n/rr2bind {'b' * 32}\n")
        self.assertEqual("reader-not-ready", result["reason"])
        self.assertEqual("b" * 32, result["nonce"])

    def test_disappearing_stdout_cannot_reuse_previous_poll_nonce(self):
        candidate = snapshot()
        candidate["target"]["processId"] += 1
        result = self.run_wait([candidate, snapshot()], clear_stdout_on_poll=2)
        self.assertEqual("reader-not-ready", result["reason"])
        self.assertIsNone(result["nonce"])


class HostSnapshotValidationTests(unittest.TestCase):
    def test_host_rechecks_exact_identity_and_delivery(self):
        launcher.validate_ready_snapshot(snapshot(), ARGS, ENDPOINT, NONCE)
        for field, value in (("processId", True), ("processId", "42"),
                             ("processStartUtcTicks", ARGS.expected_game_start_ticks + 1),
                             ("processStartUtcTicks", str(ARGS.expected_game_start_ticks)),
                             ("executableSha256", "B" * 64)):
            candidate = deepcopy(snapshot())
            candidate["target"][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    RuntimeError, "reader-snapshot-mismatch"):
                launcher.validate_ready_snapshot(candidate, ARGS, ENDPOINT, NONCE)

    def test_host_rejects_terminal_nonce_and_delivery_mismatches(self):
        for field, value in (("readerStatus", "terminated"), ("nonce", "b" * 32),
                             ("target.readerSessionNonce", "b" * 32),
                             ("delivery.enabled", "true"), ("delivery.endpoint", ENDPOINT + "/other")):
            candidate = snapshot()
            parent, _, key = field.rpartition(".")
            (candidate[parent] if parent else candidate)[key] = value
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "reader-snapshot-mismatch"):
                launcher.validate_ready_snapshot(candidate, ARGS, ENDPOINT, NONCE)


if __name__ == "__main__":
    unittest.main()
