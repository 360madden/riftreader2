"""Native unit candidate and original Lua NPC survey cross-source replay tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import join_physical_nearby_npc_survey as joined
from scripts import npc_survey_live as npc
from scripts import physical_nearby_units as native
from scripts import physical_rift
from tests.test_physical_unit_names import report as name_report
from tests.test_physical_unit_positions import report as position_report

UNIT_KEY = str(2 ** 64 - 1)
UNIT = "uFFFFFFFFFFFFFFFF"
PLAYER = "u000000000000002A"
NONCE = "a" * 32
NATIVE_AT = "2026-11-12T04:00:00.2000000Z"
SAMPLE_TIMES = ("2026-11-12T04:00:00.3000000Z",
                "2026-11-12T04:00:00.4000000Z")


def save(path, document):
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def npc_frame(seq, *, name="Unit 1", x=7430, level=13, relation="hostile",
              player=False):
    return {
        "schemaVersion": 1, "addon": "RiftReader2NpcSurvey",
        "addonVersion": "0.1.0", "source": "Inspect.Unit.Detail",
        "status": "observed", "sessionId": NONCE,
        "playerId": PLAYER, "epoch": 1, "sequence": seq,
        "frameTime": float(seq),
        "mode": "explicit", "page": None,
        "selectionScope": "explicit-native-id-detail",
        "units": {UNIT: {"status": "observed", "id": UNIT,
                         "name": name, "level": level,
                         "coordX": x, "coordY": 871,
                         "coordZ": 2950, "relation": relation,
                         "player": player}},
    }


class NearbyNpcJoinTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native_dir = self.root / "native"
        self.native_dir.mkdir()
        self.npc_dir = self.root / "npc"
        self.npc_dir.mkdir()
        pos = position_report()
        name = name_report([UNIT_KEY], timestamp=NATIVE_AT)
        exact_executable = r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe"
        pos["observation"]["identity"]["executablePath"] = exact_executable
        name["observation"]["identity"]["executablePath"] = exact_executable
        name["observation"]["rows"][0]["entityAddressDecimal"] = pos["observation"]["rows"][1]["entityAddressDecimal"]
        self.pos_raw, self.name_raw = pos, name
        self.pos_values = physical_rift._native_values("unit-positions", pos)
        self.name_values = physical_rift._native_values("unit-names", name)
        pos_sha = save(self.native_dir / "unit-positions-native.json", pos)
        names_sha = save(self.native_dir / "unit-names-native.json", name)
        selected, total = native.choose_nearby(self.pos_values, radius=35.0, limit=18)
        report = native.combine(selected, total, pos, self.pos_values, name,
                                self.name_values, pos_sha, names_sha,
                                radius=35.0, limit=18)
        self.native_summary = self.native_dir / "nearby-report.json"
        save(self.native_summary, report)
        self.make_npc()

    def make_npc(self, *, name="Unit 1", x=7430, level=13,
                 relation="hostile", player=False):
        first = npc_frame(1, name=name, x=x, level=level,
                          relation=relation, player=player)
        after = npc_frame(2, name=name, x=x, level=level,
                          relation=relation, player=player)
        sources = []
        for i, frame in enumerate((first, after), 1):
            raw = npc.PREFIX + json.dumps(frame, separators=(",", ":")).encode() + npc.SUFFIX
            path = self.npc_dir / f"frame-{i:02d}.wire"
            path.write_bytes(raw)
            sources.append({
                "address": f"0x{0x11000+i*0x1000:X}",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retainedWire": str(path), "sequence": i, "epoch": 1,
                "frameTime": float(i), "attempt": i,
                "readSeconds": 0.05,
                "capturedAtUtc": SAMPLE_TIMES[i-1],
            })
        identity = self.pos_raw["observation"]["identity"]
        summary = {
            "schemaVersion": 1, "evidenceKind": "physical-npc-api-survey/1",
            "status": "advancing", "inputSent": False, "host": "AMD-DESKTOP",
            "target": {"processId": identity["processId"],
                       "processStartUtcTicks": str(identity["processStartUtcTicks"]),
                       "executableSha256": identity["executableSha256"]},
            "playerId": PLAYER, "seedIndex": "synthetic-offline-only",
            "sources": sources, "relativeSourceLagSeconds": 0.1,
            "confirmedUnitIds": [UNIT], "observedUnits": 1,
            "snapshot": after,
            "qualification": "synthetic-offline",
        }
        self.npc_summary = self.npc_dir / "result.json"
        save(self.npc_summary, summary)

    def call(self, **kwargs):
        return joined.correlate(self.native_summary, self.npc_summary, **kwargs)

    def test_original_native_and_api_sources_match_without_authorizing_action(self):
        result = self.call()
        self.assertEqual(result["status"], "joined-candidates")
        self.assertEqual(result["crossSourceCandidateCount"], 1)
        row = result["samples"][0]
        self.assertEqual(row["unitIdCandidate"], UNIT)
        self.assertEqual(row["nameAgreement"], "matches")
        self.assertEqual(row["positionAgreement"], "within-tolerance")
        self.assertEqual(row["apiLevelCandidate"], 13)
        self.assertEqual(row["apiRelationCandidate"], "hostile")
        self.assertEqual(row["apiPlayerFlagCandidate"], False)
        self.assertEqual(row["combatSuitabilityStatus"], "unqualified")
        self.assertFalse(result["combatAuthorized"])
        self.assertFalse(result["moveAuthorized"])
        self.assertFalse(result["inputSent"])

    def test_native_summary_tamper_is_refused(self):
        document = json.loads(self.native_summary.read_text())
        document["samples"][0]["nameCandidate"] = "Invented"
        save(self.native_summary, document)
        with self.assertRaisesRegex(ValueError, "nearby-source-projection-mismatch"):
            self.call()

    def test_native_original_source_sha_mismatch_is_refused(self):
        p = self.native_dir / "unit-names-native.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "name-source-sha-mismatch"):
            self.call()

    def test_api_wire_tamper_is_refused(self):
        p = self.npc_dir / "frame-02.wire"
        p.write_bytes(p.read_bytes().replace(b"hostile", b"neutral"))
        with self.assertRaisesRegex(ValueError, "source-sha-or-envelope-mismatch"):
            self.call()

    def test_wrong_pid_and_player_cannot_cross_link(self):
        document = json.loads(self.npc_summary.read_text())
        document["target"]["processId"] += 1
        save(self.npc_summary, document)
        with self.assertRaisesRegex(ValueError, "native-api-owner-or-player-mismatch"):
            self.call()
        document["target"]["processId"] -= 1
        document["playerId"] = "u0000000000000001"
        save(self.npc_summary, document)
        with self.assertRaises(ValueError):
            self.call()

    def test_name_and_position_disagreement_withhold_level_relation(self):
        for kwargs, expected in (({"name": "Other Name"}, "nameAgreement"),
                                 ({"x": 7500}, "positionAgreement")):
            with self.subTest(kwargs=kwargs):
                self.make_npc(**kwargs)
                result = self.call()
                self.assertEqual(result["crossSourceCandidateCount"], 0)
                self.assertIsNone(result["samples"][0]["apiRelationCandidate"])
                self.assertIsNone(result["samples"][0]["apiLevelCandidate"])
                self.assertNotEqual(result["samples"][0][expected],
                                    "matches" if expected == "nameAgreement"
                                    else "within-tolerance")

    def test_stale_api_capture_not_joined(self):
        document = json.loads(self.npc_summary.read_text())
        document["sources"][-1]["capturedAtUtc"] = "2026-11-12T04:00:50Z"
        save(self.npc_summary, document)
        with self.assertRaisesRegex(ValueError, "native-api-source-gap"):
            self.call()

    def test_max_gap_and_position_tolerance_are_bounded(self):
        for opts in ({"max_gap_seconds": -1}, {"max_gap_seconds": float("nan")},
                     {"max_gap_seconds": True},
                     {"position_tolerance": float("inf")},
                     {"position_tolerance": 25}):
            with self.subTest(opts=opts):
                with self.assertRaisesRegex(ValueError, "invalid-comparison-bounds"):
                    self.call(**opts)

    def test_cli_writes_candidate_only_report(self):
        out = self.root / "joined.json"
        self.assertEqual(joined.main([
            "--nearby", str(self.native_summary),
            "--npc-survey", str(self.npc_summary),
            "--output", str(out)]), 0)
        self.assertTrue(out.is_file())
        self.assertEqual(json.loads(out.read_text())["crossSourceCandidateCount"], 1)
        self.assertEqual(joined.main([
            "--nearby", str(self.native_summary),
            "--npc-survey", str(self.npc_summary),
            "--output", str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
