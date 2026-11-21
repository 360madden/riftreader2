"""Offline-only, self-contained Telemetry Lua vs native-zone evidence tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import replay_physical_telemetry_zone as replay
from tests.test_physical_zone_context import typed_report_1179

SELF = 0x035400012FA2D207
ZONE = "z487C9102D2EA79BE"
TIME = "2026-11-20T10:50:"
SHA = replay.SHA_1179
SESSION = "a" * 32
ROOT = Path(__file__).resolve().parents[1]


class ZoneEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.summary = self.folder / "summary.json"
        self.natives = {}
        native = typed_report_1179()
        # The older unit-test fixture omits the path; physical reader receipts
        # always include it and the replay verifies it against process identity.
        native["observation"]["identity"]["executablePath"] = r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe"
        native["observation"]["selfKey"] = SELF
        native["observation"]["startedAtUtc"] = TIME + "11.0000000+00:00"
        native["observation"]["completedAtUtc"] = TIME + "11.1000000+00:00"
        self.save_native("before", native)
        after = deepcopy(native)
        after["observation"]["startedAtUtc"] = TIME + "13.0000000+00:00"
        after["observation"]["completedAtUtc"] = TIME + "13.1000000+00:00"
        self.save_native("after", after)
        identity = native["observation"]["identity"]
        self.target = {"hostName": replay.HOST, "processId": identity["processId"],
                       "processStartUtcTicks": str(identity["processStartUtcTicks"]),
                       "executablePath": identity["executablePath"],
                       "executableSha256": SHA, "hwnd": 111}
        self.rows = []
        for passn, values in enumerate(((1,2), (2,3)), 1):
            directory = self.folder / f"pass-{passn:02d}"
            directory.mkdir()
            rows = []
            for slot, seq in enumerate(values, 1):
                frame = self.frame(seq)
                wire = b"RIFTTLM1|" + json.dumps(frame, separators=(",", ":")).encode() + b"|ENDRIFTTLM1"
                path = directory / f"frame-{slot:02d}.wire"
                path.write_bytes(wire)
                rows.append({"addr":f"0x{0x10000+seq*0x1000:x}",
                             "seq":seq, "epoch":1, "session":SESSION,
                             "clock":float(seq), "zoneId":ZONE,
                             "wire":str(path), "sha":replay.digest(wire)})
            self.rows.append(rows)
        self.record = {
            "schemaVersion":1, "evidenceKind":"physical-native-telemetry-zone-bracket-candidate/1",
            "status":"matching-candidates", "target":self.target, "sameProcessEpoch":True,
            "nativeBefore":self.native_entry("before"),
            "nativeAfter":self.native_entry("after"),
            "passes":[
                {"startedAtUtc":TIME+"11.2000000+00:00",
                 "completedAtUtc":TIME+"11.5000000+00:00",
                 "readBytes":65536,"failedChunks":0,"hits":2,"frames":self.rows[0]},
                {"startedAtUtc":TIME+"12.0000000+00:00",
                 "completedAtUtc":TIME+"12.4000000+00:00",
                 "readBytes":65536,"failedChunks":0,"hits":2,"frames":self.rows[1]},
            ],"sourceClockProgression":"advancing","newSourceSequenceCount":1,
            "qualification":"source-test-fixture-candidate-only"
        }
        self.save()

    @staticmethod
    def frame(seq):
        return {"schemaVersion":4,"addon":"Telemetry","addonVersion":"0.5.0",
                "source":"rift-api","status":"observed","sessionId":SESSION,"epoch":1,
                "sequence":seq,"frameTime":float(seq),
                "playerId":f"u{SELF:016X}",
                "playerTelemetry":{"status":"observed","id":f"u{SELF:016X}",
                                   "zone":{"status":"observed","id":ZONE,"name":"Fixture Zone",
                                           "sampledAt":float(seq)-0.5}}}

    def native_entry(self, which):
        row=self.natives[which]["observation"]
        path=self.folder/f"native-{which}.json"
        return {"source":str(path),"sha256":replay.digest(path.read_bytes()),
                "zoneIdCandidate":row["zoneIdCandidate"],"startedAtUtc":row["startedAtUtc"],
                "completedAtUtc":row["completedAtUtc"]}

    def save_native(self, which, source):
        self.natives[which]=source
        (self.folder/f"native-{which}.json").write_text(json.dumps(source),encoding="utf-8")

    def save(self):
        self.summary.write_text(json.dumps(self.record),encoding="utf-8")

    def edit_wire(self, passn, slot, transform, *, repin=True, metadata=True):
        path=self.folder/f"pass-{passn:02d}"/f"frame-{slot:02d}.wire"
        raw=path.read_bytes()
        obj=json.loads(raw[len(replay.PREFIX):-len(replay.SUFFIX)])
        transform(obj)
        updated=replay.PREFIX+json.dumps(obj,separators=(",",":")).encode()+replay.SUFFIX
        path.write_bytes(updated)
        row=self.record["passes"][passn-1]["frames"][slot-1]
        if repin:row["sha"]=replay.digest(updated)
        if metadata:
            row.update(seq=obj["sequence"],epoch=obj["epoch"],
                       session=obj["sessionId"],clock=obj["frameTime"],
                       zoneId=obj["playerTelemetry"]["zone"]["id"])
        self.save()

    def install_source_hashed_excluded_generations(self):
        self.record["selectedPublisherGeneration"] = {
            "sessionId": SESSION, "epoch": 1}
        self.record["scopeSurvey"] = {
            "status": "scoped-candidate",
            "selectedStartAddress": "0x13000000",
            "scopes": [{"startAddress": "0x13000000",
                        "topSession": SESSION, "topEpoch": 1}]}
        for passn in (1, 2):
            old = self.frame(10 + passn)
            old["epoch"] = 57
            raw = (replay.PREFIX +
                   json.dumps(old, separators=(",", ":")).encode() +
                   replay.SUFFIX)
            path = self.folder/f"pass-{passn:02d}"/"frame-03.wire"
            path.write_bytes(raw)
            row = {"addr": f"0x{0x10000 + (10+passn)*0x1000:x}",
                   "seq": old["sequence"], "epoch": old["epoch"],
                   "session": old["sessionId"], "clock": old["frameTime"],
                   "zoneId": ZONE, "wire": str(path),
                   "excludedSha256": replay.digest(raw),
                   "error": "nonselected-publisher-generation"}
            entry = self.record["passes"][passn - 1]
            entry["hits"] = 3
            entry["frames"].append(row)
            entry["excludedSourceFrameCount"] = 1
        self.save()

    def test_other_epoch_sources_are_retained_hashed_and_excluded(self):
        self.install_source_hashed_excluded_generations()
        result = replay.replay(self.summary)
        self.assertEqual(result["savedFrames"], [2, 2])
        self.assertEqual(result["excludedPublisherFrames"], [1, 1])
        self.assertEqual(result["selectedPublisherGeneration"],
                         {"sessionId": SESSION, "epoch": 1})
        self.assertEqual(result["uniqueSourceSequences"], 3)
        self.assertEqual(result["sourceEpoch"], 1)

    def test_tampered_excluded_wire_is_rejected(self):
        self.install_source_hashed_excluded_generations()
        path = self.folder/"pass-01"/"frame-03.wire"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "excluded-wire-sha-mismatch"):
            replay.replay(self.summary)

    def test_selected_epoch_frame_cannot_be_disguised_as_excluded(self):
        self.install_source_hashed_excluded_generations()
        path = self.folder/"pass-01"/"frame-03.wire"
        raw = path.read_bytes()
        doc = json.loads(raw[len(replay.PREFIX):-len(replay.SUFFIX)])
        doc["epoch"] = 1
        changed = (replay.PREFIX +
                   json.dumps(doc, separators=(",", ":")).encode() +
                   replay.SUFFIX)
        path.write_bytes(changed)
        row = self.record["passes"][0]["frames"][2]
        row["epoch"] = 1
        row["excludedSha256"] = replay.digest(changed)
        self.save()
        with self.assertRaisesRegex(ValueError,
                                     "selected-source-frame-illegally-excluded"):
            replay.replay(self.summary)

    def test_selected_generation_and_exclusion_count_are_pinned(self):
        self.install_source_hashed_excluded_generations()
        self.record["passes"][0]["excludedSourceFrameCount"] = 0
        self.save()
        with self.assertRaisesRegex(ValueError,
                                     "excluded-source-frame-count-mismatch"):
            replay.replay(self.summary)
        self.record["passes"][0]["excludedSourceFrameCount"] = 1
        self.record["selectedPublisherGeneration"]["epoch"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError,
                                     "selected-publisher-survey-mismatch"):
            replay.replay(self.summary)

    def test_good_synthetic_source_bracket_without_live_process(self):
        with patch.object(replay.physical_rift,"select_physical") as selection, \
             patch.object(replay.physical_rift,"read_native") as reader:
            result=replay.replay(self.summary)
            selection.assert_not_called()
            reader.assert_not_called()
        self.assertEqual(result["status"],"matching-candidates")
        self.assertEqual(result["zoneIdCandidate"],ZONE)
        self.assertEqual(result["luaZoneNameCandidate"],"Fixture Zone")
        self.assertEqual(result["savedFrames"],[2,2])
        self.assertEqual(result["newAdvancingSourceFrames"],1)
        self.assertEqual(result["uniqueSourceSequences"],3)
        self.assertEqual(result["worldInstanceStatus"],"unavailable")
        self.assertLess(result["hostObservationSpanSeconds"],15)

    def test_unrepinned_frame_tamper_refused(self):
        self.edit_wire(2,2,lambda o:o["playerTelemetry"]["zone"].update(name="Changed"),
                       repin=False)
        with self.assertRaisesRegex(ValueError,"wire-source-sha-mismatch"):
            replay.replay(self.summary)

    def test_rehashed_fake_lua_zone_is_not_a_native_match(self):
        self.edit_wire(2,2,lambda o:o["playerTelemetry"]["zone"].update(
            id="z0000000CB7B53FD7"))
        with self.assertRaisesRegex(ValueError,"native-versus-lua-zone-mismatch"):
            replay.replay(self.summary)

    def test_conflicting_duplicate_sequence_is_refused(self):
        self.edit_wire(2,1,lambda o:o["playerTelemetry"]["zone"].update(
            name="Inconsistent name"))
        with self.assertRaisesRegex(ValueError,"conflicting-retained-sequence"):
            replay.replay(self.summary)

    def test_mixed_source_generation_rejected(self):
        self.edit_wire(2,2,lambda o:o.update(epoch=2))
        with self.assertRaisesRegex(ValueError,"source-session-or-epoch-changed"):
            replay.replay(self.summary)

    def test_reverse_source_clock_rejected(self):
        self.edit_wire(2,2,lambda o:(o.update(frameTime=1.5),
                                         o["playerTelemetry"]["zone"].update(sampledAt=1.0)))
        with self.assertRaisesRegex(ValueError,"source-clock-nonadvancing-or-mixed|frame-zone-source-clock-invalid"):
            replay.replay(self.summary)

    def test_stale_api_zone_field_rejected(self):
        self.edit_wire(2,2,lambda o:o["playerTelemetry"]["zone"].update(
            sampledAt=0.0))
        self.edit_wire(2,2,lambda o:o.update(frameTime=100.0))
        with self.assertRaisesRegex(ValueError,"frame-zone-source-clock-invalid"):
            replay.replay(self.summary)

    def test_wrong_player_rejected(self):
        self.edit_wire(2,2,lambda o:o.update(playerId="u0000000000000001"))
        with self.assertRaisesRegex(ValueError,"frame-schema-or-player"):
            replay.replay(self.summary)

    def test_native_epoch_or_sha_tamper_refused_even_rehashed(self):
        for which in ("before","after"):
            with self.subTest(which=which):
                original=deepcopy(self.natives[which])
                source=deepcopy(original)
                source["observation"]["identity"]["processId"]=999
                self.save_native(which,source)
                self.record["nativeBefore" if which=="before" else "nativeAfter"]=self.native_entry(which)
                self.save()
                with self.assertRaisesRegex(ValueError,"native-process-epoch-or-build"):
                    replay.replay(self.summary)
                # Restore the exact original source (including the executable
                # path) before testing the next independent mutation.
                self.save_native(which,original)
                self.record["nativeBefore" if which=="before" else "nativeAfter"]=self.native_entry(which)
                self.save()

    def test_unbounded_or_reordered_host_interval_refused(self):
        self.record["passes"][0]["startedAtUtc"]=TIME+"10.0000000+00:00"
        self.save()
        with self.assertRaisesRegex(ValueError,"native-and-scan-time-order"):
            replay.replay(self.summary)
        self.record["passes"][0]["startedAtUtc"]=TIME+"11.2000000+00:00"
        self.save()
        with self.assertRaisesRegex(ValueError,"capture-window-exceeded"):
            replay.replay(self.summary,max_capture_seconds=0.3)

    def test_no_new_advancing_source_frame_is_not_qualified(self):
        self.edit_wire(2,2,lambda o:(o.update(sequence=1,frameTime=1.0),
                                         o["playerTelemetry"]["zone"].update(sampledAt=0.5)))
        with self.assertRaisesRegex(ValueError,"conflicting-retained-sequence|no-new-advancing-source-frames"):
            replay.replay(self.summary)

    def test_duplicate_json_root_fields_rejected(self):
        path=self.folder/"pass-02"/"frame-02.wire"
        wire=path.read_bytes().replace(b'"schemaVersion":4',b'"schemaVersion":4,"schemaVersion":4')
        path.write_bytes(wire)
        self.record["passes"][1]["frames"][1]["sha"]=replay.digest(wire)
        self.save()
        with self.assertRaisesRegex(ValueError,"duplicate-json-key"):
            replay.replay(self.summary)

    def test_cli_output_never_overwrites(self):
        out=self.folder/"replay.json"
        self.assertEqual(replay.main(["--summary",str(self.summary),"--output",str(out)]),0)
        self.assertEqual(json.loads(out.read_text())["status"],"matching-candidates")
        self.assertEqual(replay.main(["--summary",str(self.summary),"--output",str(out)]),2)

    def test_actual_retained_local_capture_when_present(self):
        real=ROOT/"artifacts"/"physical-telemetry-zone-20261120-0549"/"summary.json"
        if not real.is_file():
            self.skipTest("Ignored real physical source evidence not present")
        value=replay.replay(real)
        self.assertEqual(value["status"],"matching-candidates")
        self.assertEqual(value["savedFrames"],[9,10])
        self.assertEqual(value["luaZoneNameCandidate"],"Silverwood")
        self.assertEqual(value["zoneIdCandidate"],"z0000000CB7B53FD7")
        self.assertEqual(value["processId"],22532)


if __name__=="__main__":
    unittest.main()
