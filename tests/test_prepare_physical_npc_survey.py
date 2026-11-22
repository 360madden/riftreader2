"""Pure-Python tests for fresh native-NPC survey preparation, no game input."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import prepare_physical_npc_survey as prep

PID = 37676
START = "639308565554559088"
SHA = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
AT = "2026-11-21T18:00:00.0000000+00:00"
CLOCK = datetime(2026,11,21,18,0,5,tzinfo=timezone.utc)


class NPCPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.installed = self.dir/"Casting"
        self.installed.mkdir()
        self.source = prep.ROOT/"addon"/"RiftReader2NpcSurvey"/"survey.lua"
        (self.installed/"npc_survey.lua").write_bytes(self.source.read_bytes())
        (self.installed/"RiftAddon.toc").write_text(
            'Identifier = "RiftReader2Casting"\n'
            'RunOnStartup = { "npc_survey.lua" }\n')
        self.target = {"hostName": "RIFT-STATION", "processId": PID, "processStartUtcTicks": START,
                       "executableSha256": SHA}
        self.nearby = {
            "host": self.target["hostName"],
            "process": {"processId": PID, "processStartUtcTicks": START,
                        "executableSha256": SHA},
            "samples": [
                {"nameStatus": "available-candidate",
                 "unitIdCandidate": f"u{v:016X}"} for v in (4,5,6)
            ] + [{"nameStatus":"unavailable",
                  "unitIdCandidate":"u0000000000000007"}]
        }
        self.native_call_count = 0

    def collect(self, host, pid, directory, *, radius, limit):
        self.native_call_count += 1
        self.assertEqual((host,pid),("RIFT-STATION",PID))
        self.assertEqual(limit, 18)
        directory.mkdir()
        path = directory/"nearby-report.json"
        path.write_text(json.dumps(self.nearby),encoding="utf-8")
        return path, deepcopy(self.nearby)

    def select(self, host, pid):
        return {"status":"ready","target":deepcopy(self.target)}

    def prepare(self, **overrides):
        kwargs = {
            "casting_dir":self.installed,
            "capture_nearby":self.collect,
            "select":self.select,
            "nonce_factory":lambda _: "a"*32,
            "now":lambda: CLOCK,
        }
        kwargs.update(overrides)
        with patch.object(prep.join, "original_native_nearby",
                          return_value=(deepcopy(self.nearby), "B"*64, (AT, AT))):
            return prep.prepare("RIFT-STATION", PID, self.dir/"plan",
                                **kwargs)

    def test_realistic_plan_needs_one_in_game_bind_but_never_sends_input(self):
        path, result = self.prepare()
        self.assertTrue(path.exists())
        self.assertEqual(result["status"],"prepared-not-activated")
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["addonActivated"])
        self.assertEqual(len(result["unitIds"]),3)
        self.assertEqual(result["nonce"],"a"*32)
        self.assertTrue(result["inGameBindCommand"].startswith(
            "/rr2survey bind " + "a"*32))
        self.assertNotIn("u0000000000000007",result["inGameBindCommand"])
        self.assertIn("--auto-map",result["captureCommand"])
        self.assertIn("scripts/npc_survey_live.py",result["captureCommand"])
        self.assertTrue(result["captureCommand"].startswith("& " + prep._quote(sys.executable)))
        self.assertTrue(result["joinCommand"].startswith("& " + prep._quote(sys.executable)))
        self.assertIn("--max-gap-seconds 120",result["joinCommand"])
        self.assertEqual(result["installedAddon"]["configurationVerified"],True)
        self.assertEqual(result["installedAddon"]["runningAddonLoaded"],"unverified")
        self.assertIn("18:02:00",result["nativeJoinDeadlineUtc"])
        self.assertEqual(json.loads(path.read_text()),result)
        self.assertEqual(self.native_call_count,1)

    def test_wider_native_name_batch_picks_twelve_named_unit_ids(self):
        self.nearby["samples"] = [
            {"nameStatus": "unavailable" if n in (1, 3, 5, 7, 9, 11)
                else "available-candidate",
             "unitIdCandidate": f"u{n:016X}"}
            for n in range(1, 19)
        ]
        _, result = self.prepare()
        self.assertEqual(len(result["unitIds"]), 12)
        self.assertEqual(result["unitIds"][0], "u0000000000000002")
        self.assertEqual(result["unitIds"][-1], "u0000000000000012")
        self.assertEqual(self.native_call_count, 1)
        self.assertLessEqual(len(result["inGameBindCommand"]), 270)

    def test_no_named_candidates_creates_failure_and_not_bind_command(self):
        self.nearby["samples"]=[{"nameStatus":"unavailable",
                                 "unitIdCandidate":"u0000000000000002"}]
        with self.assertRaisesRegex(ValueError,"no-named-unit-candidates"):
            self.prepare()
        self.assertTrue((self.dir/"plan"/"failure.json").exists())
        self.assertFalse((self.dir/"plan"/"plan.json").exists())

    def test_bad_nonce_refuses_and_retains_original_native_source(self):
        with self.assertRaisesRegex(ValueError,"invalid-nonce"):
            self.prepare(nonce_factory=lambda _: "NOTHEX")
        self.assertTrue((self.dir/"plan"/"native"/"nearby-report.json").exists())
        self.assertTrue((self.dir/"plan"/"failure.json").exists())

    def test_stale_or_future_native_source_refused(self):
        for timestamp in ("2026-11-21T17:55:00Z","2026-11-21T18:01:00Z"):
            with self.subTest(timestamp=timestamp):
                with patch.object(prep.join,"original_native_nearby",
                                  return_value=(deepcopy(self.nearby),"A"*64,(timestamp, AT))):
                    kwargs=dict(casting_dir=self.installed,
                                capture_nearby=self.collect,
                                select=self.select,
                                nonce_factory=lambda _: "a"*32,
                                now=lambda: CLOCK)
                    with self.assertRaisesRegex(ValueError,"no-longer-fresh"):
                        prep.prepare("RIFT-STATION",PID,self.dir/"plan",**kwargs)
                self.assertTrue((self.dir/"plan"/"failure.json").is_file())
                from shutil import rmtree
                rmtree(self.dir/"plan")

    def test_installed_module_mismatch_refuses_before_native_collection(self):
        (self.installed/"npc_survey.lua").write_text("not installed source")
        with self.assertRaisesRegex(ValueError,"source-mismatch"):
            self.prepare()
        self.assertEqual(self.native_call_count,0)
        self.assertFalse((self.dir/"plan").exists())

    def test_manifest_mentions_module_but_does_not_load_it(self):
        (self.installed/"RiftAddon.toc").write_text(
            'Identifier = "RiftReader2Casting"\\n'
            '-- npc_survey.lua is not part of RunOnStartup\\n'
            'RunOnStartup = { "main.lua" }\\n')
        with self.assertRaisesRegex(ValueError,"not-listed"):
            self.prepare()
        self.assertEqual(self.native_call_count,0)
        self.assertFalse((self.dir/"plan").exists())

    def test_wrong_manifest_or_host_refuses_before_data_collection(self):
        (self.installed/"RiftAddon.toc").write_text("Identifier = 'Wrong'")
        with self.assertRaisesRegex(ValueError,"not-listed"):
            self.prepare()
        self.assertEqual(self.native_call_count,0)
        with self.assertRaisesRegex(ValueError,"invalid-host"):
            prep.prepare("other/path",PID,self.dir/"plan",
                         casting_dir=self.installed)
        self.assertFalse((self.dir/"plan").exists())

    def test_changed_process_after_native_read_refused(self):
        def changed(host,pid):
            return {"status":"ready","target":dict(self.target, processId=999)}
        with self.assertRaisesRegex(ValueError,"physical-process-changed"):
            self.prepare(select=changed)
        self.assertTrue((self.dir/"plan"/"failure.json").exists())

    def test_invalid_unit_ids_and_too_many_require_no_game_input(self):
        self.nearby["samples"][0]["unitIdCandidate"]="u000000000000000G"
        with self.assertRaisesRegex(ValueError,"invalid-native-unit-ids"):
            self.prepare()
        self.assertTrue((self.dir/"plan"/"failure.json").exists())


if __name__ == "__main__":
    unittest.main()
