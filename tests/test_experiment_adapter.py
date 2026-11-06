from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).parents[1] / "scripts"
SCRIPT = SCRIPTS / "rift-experiment.py"
SPEC = importlib.util.spec_from_file_location("rift_experiment_adapter", SCRIPT)
adapter_module = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SCRIPTS))
SPEC.loader.exec_module(adapter_module)


class Blocked(Exception):
    pass


class FakeReadback:
    def __init__(self, samples):
        self.samples = iter(samples)
        self.calls = 0

    def validate_readiness_sample(self, envelope, source, expected):
        self.calls += 1
        return next(self.samples)


class ExperimentAdapterTests(unittest.TestCase):
    def make_adapter(self, samples):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        adapter = object.__new__(adapter_module.LabAdapter)
        adapter.stop_path = Path(temporary.name) / "STOP"
        adapter.config = {"sourceAddress": "192.0.2.1"}
        adapter.game = SimpleNamespace(
            sample=lambda config: {
                "observation": {
                    "machineName": "RIFT-LAB",
                    "target": {"processId": 42},
                }
            }
        )
        adapter.console = SimpleNamespace(Blocked=Blocked)
        adapter.readback = FakeReadback(samples)
        adapter.previous = {"scanSequence": 1, "sourceSampledAt": 10.0}
        adapter.released_utc = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
        return adapter

    def test_post_release_sample_retries_transient_unavailable_player_data(self):
        adapter = self.make_adapter(
            [
                {"playerDataUsable": False},
                {
                    "playerDataUsable": True,
                    "scanSequence": 2,
                    "sourceSampledAt": 11.0,
                    "acquisitionStartedAtUtc": "2026-10-19T12:00:01+00:00",
                },
            ]
        )

        result = adapter.sample(after=True)

        self.assertEqual(result["sample"]["scanSequence"], 2)
        self.assertEqual(adapter.readback.calls, 2)

    def test_before_sample_still_fails_immediately_when_player_data_unavailable(self):
        adapter = self.make_adapter([{"playerDataUsable": False}])

        with self.assertRaisesRegex(ValueError, "Player data unavailable"):
            adapter.sample(after=False)
        self.assertEqual(adapter.readback.calls, 1)

    def test_nonadvancing_or_pre_release_sample_times_out_without_sleeping(self):
        for sequence, source_time, acquisition in (
            (1, 11.0, "2026-10-19T12:00:01+00:00"),
            (2, 10.0, "2026-10-19T12:00:01+00:00"),
            (2, 11.0, "2026-10-19T12:00:00+00:00"),
        ):
            with self.subTest(sequence=sequence, source_time=source_time,
                              acquisition=acquisition):
                adapter = self.make_adapter([{
                    "playerDataUsable": True,
                    "scanSequence": sequence,
                    "sourceSampledAt": source_time,
                    "acquisitionStartedAtUtc": acquisition,
                }])
                with patch.object(adapter_module.time, "monotonic", side_effect=[0, 12]), \
                        patch.object(adapter_module.time, "sleep") as sleep:
                    with self.assertRaisesRegex(ValueError, "No new post-release"):
                        adapter.sample(after=True)
                    sleep.assert_not_called()

    def test_wrong_epoch_or_stale_game_receipt_is_not_retried(self):
        adapter = self.make_adapter([])
        adapter.game.sample = lambda config: (_ for _ in ()).throw(
            Blocked("wrong epoch or stale receipt"))
        with self.assertRaises(Blocked):
            adapter.sample(after=True)
        self.assertEqual(adapter.readback.calls, 0)

    def test_stop_latch_prevents_readback(self):
        adapter = self.make_adapter([])
        adapter.stop_path.touch()
        with self.assertRaises(InterruptedError):
            adapter.sample(after=True)
        self.assertEqual(adapter.readback.calls, 0)


if __name__ == "__main__":
    unittest.main()
