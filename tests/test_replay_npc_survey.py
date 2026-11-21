"""Pure-Python retained-wire tests; no Lua engine or live game required."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import npc_survey_live as survey
from scripts import replay_npc_survey as cold

NONCE = "a" * 32
PLAYER = "u0000000000000001"
UNIT = "u0000000000000002"
TARGET = {"processId": 37676, "processStartUtcTicks": "639308565554559088",
          "executableSha256": "D" * 64}


def wire(sequence, *, clock=None, target_id=UNIT, epoch=1):
    clock = float(sequence) if clock is None else clock
    doc = {
        "schemaVersion": 1, "addon": "RiftReader2NpcSurvey",
        "addonVersion": "0.1.0", "source": "Inspect.Unit.Detail",
        "status": "observed", "sessionId": NONCE, "playerId": PLAYER,
        "epoch": epoch, "sequence": sequence, "frameTime": clock,
        "mode": "explicit", "page": None,
        "selectionScope": "explicit-native-id-detail",
        "units": {UNIT: {"status": "observed", "id": target_id,
                         "name": "Coastal Stalker", "level": 13,
                         "coordX": 12.5, "coordY": 5.0, "coordZ": -2.0,
                         "relation": "hostile", "player": False}},
    }
    return survey.PREFIX + json.dumps(doc, separators=(",", ":")).encode() + survey.SUFFIX


class NpcSourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "survey"
        self.source = [wire(10), wire(11)]
        self.target = deepcopy(TARGET)
        seed = Path(self.tmp.name) / "seed.json"
        seed.write_text("{}", encoding="utf-8")
        self.seed = seed

    def acquire(self):
        chunks = [[({"address": f"0x{0x11000+i*0x1000:X}"}, raw)]
                  for i, raw in enumerate(self.source)]
        with (patch.object(survey.physical_rift, "select_physical",
                           return_value={"status": "ready",
                                         "target": self.target}),
              patch.object(survey, "_target", side_effect=lambda obj: obj),
              patch.object(survey, "_same_target", return_value=True),
              patch.object(survey, "_validate_seed",
                           return_value=(0x10000, 16 * 1024 * 1024)),
              patch.object(survey, "PhysicalAdapter") as adapter,
              patch.object(survey, "scout", side_effect=chunks),
              patch.object(survey.time, "sleep")):
            adapter.return_value.target = self.target
            adapter.return_value.unit_key = "1"
            return survey.acquire("AMD-DESKTOP", TARGET["processId"],
                                  NONCE, [UNIT], self.output,
                                  seed_index=self.seed,
                                  attempts=2)

    def saved(self):
        return self.output / "result.json"

    def rewrite(self, update):
        p = self.saved()
        doc = json.loads(p.read_text(encoding="utf-8"))
        update(doc)
        p.write_text(json.dumps(doc), encoding="utf-8")

    def test_acquire_retains_original_wires_and_cold_replay(self):
        result = self.acquire()
        self.assertEqual(result["status"], "advancing")
        self.assertEqual(result["confirmedUnitIds"], [UNIT])
        self.assertEqual(len(result["sources"]), 2)
        for index, original in enumerate(self.source, 1):
            path = self.output / f"frame-{index:02d}.wire"
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(result["sources"][index-1]["retainedWire"], str(path))
        replay = cold.replay(self.saved())
        self.assertEqual(replay["status"], "advancing-source-replayed-candidate")
        self.assertEqual(replay["confirmedUnitIds"], [UNIT])
        self.assertEqual(replay["snapshot"]["units"][UNIT]["level"], 13)
        self.assertEqual(replay["snapshot"]["units"][UNIT]["relation"], "hostile")
        self.assertEqual(len(replay["sourceReceipts"]), 2)
        self.assertFalse(replay["inputSent"])

    def test_retained_bytes_mutation_fails(self):
        self.acquire()
        file = self.output / "frame-02.wire"
        file.write_bytes(file.read_bytes().replace(b"hostile", b"neutral"))
        with self.assertRaisesRegex(ValueError, "source-sha-or-envelope-mismatch"):
            cold.replay(self.saved())

    def test_summary_snapshot_mutation_fails(self):
        self.acquire()
        self.rewrite(lambda doc:
                     doc["snapshot"]["units"][UNIT].update(level=60))
        with self.assertRaisesRegex(ValueError, "snapshot-not-source-replayed"):
            cold.replay(self.saved())

    def test_source_sequence_and_owner_mutation_fail(self):
        self.acquire()
        self.rewrite(lambda doc: doc["sources"][-1].update(sequence=22))
        with self.assertRaisesRegex(ValueError, "source-receipt-mismatch"):
            cold.replay(self.saved())
        self.rewrite(lambda doc: doc["sources"][-1].update(sequence=11))
        self.rewrite(lambda doc: doc.update(playerId="u0000000000000003"))
        with self.assertRaisesRegex(ValueError, "survey-binding-mismatch"):
            cold.replay(self.saved())

    def test_confirmed_unit_list_is_replayed_not_trusted(self):
        self.acquire()
        self.rewrite(lambda doc: doc.update(confirmedUnitIds=[],
                                             observedUnits=0))
        with self.assertRaisesRegex(ValueError, "confirmed-id-mismatch"):
            cold.replay(self.saved())

    def test_original_wire_missing_or_old_summary_unqualified(self):
        self.acquire()
        (self.output / "frame-01.wire").unlink()
        with self.assertRaisesRegex(ValueError, "source-byte-file-unavailable"):
            cold.replay(self.saved())

    def test_duplicate_json_summary_rejected(self):
        self.acquire()
        p = self.saved()
        raw = p.read_text()
        p.write_text(raw.replace('"status": "advancing",',
                                 '"status": "advancing", "status": "advancing",', 1))
        with self.assertRaisesRegex(ValueError, "duplicate-native-json-key"):
            cold.replay(p)

    def test_acquire_refuses_ambiguous_mismatched_original_wire(self):
        changed = wire(11).replace(b"hostile", b"neutral")
        self.source = [wire(10), changed]
        # Even source changes should be replayed only as the actual bytes read.
        result = self.acquire()
        self.assertEqual(result["snapshot"]["units"][UNIT]["relation"],
                         "neutral")
        self.assertEqual(cold.replay(self.saved())["sourceReceipts"][-1]
                         ["sequence"], 11)


if __name__ == "__main__":
    unittest.main()
