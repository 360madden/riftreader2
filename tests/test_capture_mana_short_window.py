import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.capture_mana_short_window as workflow
from scripts.native_mana_candidate import BUILD_SHA


IDENTITY = {"processId": 1, "processStartUtcTicks": 2, "executableSha256": BUILD_SHA,
            "moduleBaseAddress": 3, "moduleSize": 4}
VM = {"vmx": "lab1", "pid": 5, "startTicks": 6, "logEpoch": "epoch"}


class ManaCaptureWorkflowTests(unittest.TestCase):
    def test_identity_helper_accepts_capture_and_owner_shapes(self):
        self.assertEqual(workflow._identity({"target": IDENTITY}), (1, 2, BUILD_SHA))
        self.assertEqual(workflow._identity({"identity": IDENTITY}), (1, 2, BUILD_SHA))

    def test_reports_selects_only_usable_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            recovered = Path(folder) / "recovered/run-01"
            recovered.mkdir(parents=True)
            one, two = recovered / "one.snapshot.json", recovered / "two.snapshot.json"
            one.write_text("{}", encoding="utf-8")
            two.write_text("{}", encoding="utf-8")
            usable = {"selected": {"frameTime": 2.0, "sequence": 3}}
            with patch.object(workflow, "inspect", side_effect=[workflow.ResourceInspectionError("bad"), usable]):
                result = workflow._reports({"output": folder})
        self.assertEqual(result, [usable])

    def test_reports_requires_one_complete_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            recovered = Path(folder) / "recovered/run-01"
            recovered.mkdir(parents=True)
            (recovered / "one.snapshot.json").write_text("{}", encoding="utf-8")
            with patch.object(workflow, "inspect", side_effect=workflow.ResourceInspectionError("bad")):
                with self.assertRaisesRegex(workflow.ManaCaptureError, "no-complete"):
                    workflow._reports({"output": folder})

    def test_source_drift_fails(self):
        with self.assertRaisesRegex(workflow.ManaCaptureError, "source-changed"):
            workflow._require_pins({"scripts/capture_mana_short_window.py": "0" * 64})

    def test_descriptor_producer_is_source_pinned(self):
        self.assertIn("scripts/probe_native_mana_descriptor.py", workflow.PINNED_SOURCES)
        self.assertEqual(workflow._sha(Path("scripts/probe_native_mana_descriptor.py")),
                         workflow._pins()["scripts/probe_native_mana_descriptor.py"])

    def test_descriptor_hash_mismatch_stops_before_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            descriptor = Path(folder) / "descriptor.json"
            descriptor.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(workflow.ManaCaptureError, "descriptor-review"):
                workflow.run(Path("reader.exe"), "A" * 64, descriptor, "0" * 64, 180,
                             capture_fn=lambda *_: self.fail("capture must not run"))

    def test_realistic_default_gap_is_bounded(self):
        self.assertLessEqual(180, 300)


class RR2ReportBindingTests(unittest.TestCase):
    def test_conflicting_snapshot_is_not_hidden_by_older_good_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            recovered = Path(folder) / "recovered/run-01"
            recovered.mkdir(parents=True)
            for name in ("one", "two"):
                (recovered / (name + ".snapshot.json")).write_text("{}")
            with patch.object(workflow, "inspect", side_effect=[workflow.ResourceInspectionError("reference-epoch-conflict"), {}]):
                with self.assertRaisesRegex(workflow.ResourceInspectionError, "epoch-conflict"):
                    workflow._reports({"output": folder}, "a" * 32)

    def test_cross_snapshot_epoch_or_player_conflict_fails(self):
        nonce = "a" * 32
        base = {"protocol": "RR2R1", "addon": "RiftReader2", "addonVersion": "0.2.0",
                "source": "rift-api", "sessionId": nonce, "epoch": 1, "playerUnitId": "u1"}
        for changes in ({"epoch": 2}, {"playerUnitId": "u2"}):
            with tempfile.TemporaryDirectory() as folder:
                recovered = Path(folder) / "recovered/run-01"
                recovered.mkdir(parents=True)
                for name in ("one", "two"):
                    (recovered / (name + ".snapshot.json")).write_text("{}")
                with patch.object(workflow, "inspect", side_effect=[{"selected": base}, {"selected": dict(base, **changes)}]):
                    with self.assertRaisesRegex(workflow.ManaCaptureError, "epoch-or-player-conflict"):
                        workflow._reports({"output": folder}, nonce)


if __name__ == "__main__":
    unittest.main()
