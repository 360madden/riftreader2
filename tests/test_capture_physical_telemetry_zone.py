"""Offline, fake-memory tests for the guarded read-only physical Telemetry zone capture."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import capture_physical_telemetry_zone as cap
from scripts import replay_physical_telemetry_zone as verify
from tests.test_physical_zone_context import typed_report_1179
from tests.test_replay_physical_telemetry_zone import ZoneEvidenceTests, SELF, ZONE, SESSION

HOST = cap.HOST
PID = 123
START = 0x13000000
SHA = verify.SHA_1179


def lua(seq, *, player=SELF, zone=ZONE):
    doc = ZoneEvidenceTests.frame(seq)
    doc["playerId"] = f"u{player:016X}"
    doc["playerTelemetry"]["id"] = doc["playerId"]
    doc["playerTelemetry"]["zone"]["id"] = zone
    return verify.PREFIX + json.dumps(doc, separators=(",", ":")).encode() + verify.SUFFIX


class FakeRead:
    def __init__(self, buffer):
        self.buffer = buffer
        self.calls = []

    def read(self, address, size):
        self.calls.append((address, size))
        offset = address - START
        if offset < 0:
            return b""
        return bytes(self.buffer[offset:offset+size])


class FakeProcess:
    def __init__(self, pid):
        self.pid, self.calls = pid, []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, addr, count):
        self.calls.append((addr, count))
        return b""


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.target = {"hostName":HOST,"processId":PID,
                       "processStartUtcTicks":"638000000000000001",
                       "executableSha256":SHA,"executablePath":r"C:\Games\RIFT\rift_x64.exe","hwnd":123}
        self.selection = {"status":"ready","ownerHost":HOST,"target":self.target}

    def test_canonical_bounds_reject_before_process_inspection(self):
        with patch.object(cap.socket, "gethostname", return_value=HOST), \
             patch.object(cap.physical_rift, "select_physical") as select:
            for invalid in ("0x0","0x1000","0X13000000","0x013000000","0x1300000a",
                            "0xgarbage","0x7FFFFFFFFFFF"):
                with self.subTest(start=invalid), self.assertRaises(ValueError):
                    cap.admission(PID, invalid, cap.CHUNK, 0)
            for size in (0,cap.CHUNK-1,128*1024*1024+cap.CHUNK,True):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    cap.admission(PID,"0x13000000",size,0)
            select.assert_not_called()

    def test_exact_1179_admission_and_wrong_build_refusal(self):
        with patch.object(cap.socket, "gethostname", return_value=HOST), \
             patch.object(cap.physical_rift,"select_physical",return_value=self.selection):
            self.assertEqual(cap.admission(PID,"0x13000000",cap.CHUNK,600)[1],START)
        other = deepcopy(self.selection)
        other["target"]["executableSha256"] = "F" * 64
        with patch.object(cap.socket, "gethostname", return_value=HOST), \
             patch.object(cap.physical_rift,"select_physical",return_value=other):
            with self.assertRaisesRegex(ValueError,"physical-epoch-or-build-unavailable"):
                cap.admission(PID,"0x13000000",cap.CHUNK,0)

    def test_bounded_scan_keeps_wire_hashes_and_source_metadata(self):
        data=bytearray(cap.CHUNK + 64*1024)
        first, second=lua(1),lua(2)
        data[300:300+len(first)]=first
        data[10_000:10_000+len(second)]=second
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"pass-01"
            fake=FakeRead(data)
            row=cap.scan(fake,path,start=START,scan_bytes=cap.CHUNK,
                         expected_player=f"u{SELF:016X}")
            self.assertEqual(row["hits"],2)
            self.assertEqual(row["readBytes"],cap.CHUNK)
            self.assertEqual(row["failedChunks"],0)
            self.assertEqual([x["seq"] for x in row["frames"]],[1,2])
            for rec in row["frames"]:
                wire=Path(rec["wire"]).read_bytes()
                self.assertEqual(verify.digest(wire),rec["sha"])
                self.assertEqual(rec["zoneId"],ZONE)
            self.assertEqual(fake.calls[0],(START,cap.CHUNK))
            self.assertEqual(len(fake.calls),3)

    def test_scan_refuses_unknown_player_without_claiming_source(self):
        data=bytearray(cap.CHUNK + 64*1024)
        wire=lua(1,player=98765)
        data[300:300+len(wire)]=wire
        with TemporaryDirectory() as tmp:
            result=cap.scan(FakeRead(data),Path(tmp)/"pass",start=START,
                            scan_bytes=cap.CHUNK,expected_player=f"u{SELF:016X}")
            self.assertEqual(result["hits"],1)
            self.assertEqual(result["frames"][0]["error"],"schema-or-player-zone")

    def _fake_native(self, selection, kind, output):
        self.assertEqual(kind,"zone-context")
        row=typed_report_1179()
        row["observation"]["selfKey"]=SELF
        row["observation"]["identity"]["processId"]=PID
        row["observation"]["identity"]["processStartUtcTicks"]=int(self.target["processStartUtcTicks"])
        row["observation"]["identity"]["executableSha256"]=SHA
        row["observation"]["identity"]["executablePath"]=self.target["executablePath"]
        Path(output).write_text(json.dumps(row),encoding="utf-8")
        from scripts import physical_rift
        return {"status":"complete","target":selection["target"],"nativeRead":kind,
                "nativeOutput":str(output),
                "nativeSourceSha256":verify.digest(Path(output).read_bytes()),
                "nativeValues":physical_rift._native_values("zone-context",row)}

    def test_collect_brackets_two_scans_and_only_claims_after_source_replay(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"result"
            calls=[]
            def scan(reader,folder,**kwargs):
                folder.mkdir()
                n=len(calls)+1
                calls.append((n,kwargs))
                values=(1,2) if n==1 else (2,3)
                return {"startedAtUtc":f"2026-11-20T10:50:{n+10:02d}Z",
                        "completedAtUtc":f"2026-11-20T10:50:{n+10:02d}.5Z",
                        "readBytes":cap.CHUNK,"failedChunks":0,"hits":2,
                        "frames":[{"addr":f"0x{START+x:x}","seq":x,
                                   "epoch":1,"session":SESSION,
                                   "clock":float(x),"zoneId":ZONE,
                                   "wire":str(folder/f"frame-{i:02d}.wire"),
                                   "sha":f"{x:064X}"} for i,x in enumerate(values,1)]}
            with (patch.object(cap.socket,"gethostname",return_value=HOST),
                  patch.object(cap.physical_rift,"select_physical",return_value=self.selection) as select,
                  patch.object(cap.physical_rift,"read_native",side_effect=self._fake_native) as native,
                  patch.object(cap,"scan",side_effect=scan),
                  patch.object(cap.verify,"replay",return_value={"status":"matching-candidates"}) as verify_call,
                  patch.object(cap.time,"sleep") as sleep):
                path,report=cap.collect(PID,root,start_address="0x13000000",
                                        scan_bytes=cap.CHUNK,gap_ms=600,
                                        reader_factory=FakeProcess)
            self.assertEqual(report["status"],"matching-candidates")
            self.assertEqual(report["newSourceSequenceCount"],1)
            self.assertEqual(len(calls),2)
            self.assertEqual(native.call_count,2)
            self.assertEqual(select.call_count,5)
            verify_call.assert_called_once_with(path)
            sleep.assert_called_once_with(0.6)
            self.assertEqual(json.loads(path.read_text()),report)

    def test_changed_process_early_refuses_second_scan(self):
        old, new = self.selection, deepcopy(self.selection)
        new["target"]["processStartUtcTicks"] = "9999"
        with TemporaryDirectory() as tmp, \
             patch.object(cap.socket,"gethostname",return_value=HOST), \
             patch.object(cap.physical_rift,"select_physical",side_effect=[old,new]), \
             patch.object(cap.physical_rift,"read_native",side_effect=self._fake_native) as native, \
             patch.object(cap,"scan") as scan:
            with self.assertRaisesRegex(ValueError,"changed-process-before-scan"):
                cap.collect(PID,Path(tmp)/"test",scan_bytes=cap.CHUNK,gap_ms=0)
            native.assert_called_once()
            scan.assert_not_called()

    def test_missing_frames_never_call_replay_or_claim_success(self):
        with TemporaryDirectory() as tmp, \
             patch.object(cap.socket,"gethostname",return_value=HOST), \
             patch.object(cap.physical_rift,"select_physical",return_value=self.selection), \
             patch.object(cap.physical_rift,"read_native",side_effect=self._fake_native), \
             patch.object(cap.verify,"replay") as verify_call:
            path,report=cap.collect(PID,Path(tmp)/"out",scan_bytes=cap.CHUNK,gap_ms=0,
                                    reader_factory=FakeProcess)
            self.assertEqual(report["status"],"unqualified")
            verify_call.assert_not_called()
            self.assertTrue(path.is_file())


if __name__=="__main__":
    unittest.main()
