"""CLI-level zone outcomes with a simulated native process; never accesses a game."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as p
from tests.test_physical_zone_context import IDENTITY, SHA_1177, SHA_1179, report, typed_report_1179


class ZoneCliOutcomes(unittest.TestCase):
    def invoke(self, selected_sha, source, *, native_code=0, invalid_receipt=False):
        with TemporaryDirectory() as tmp:
            exe, out = Path(tmp) / "reader.exe", Path(tmp) / "zone.json"
            exe.touch()
            target = dict(IDENTITY, executableSha256=selected_sha)
            selected = dict(status="ready", ownerHost="AMD-DESKTOP", target=target)

            def native(cmd, **kwargs):
                if native_code:
                    return subprocess.CompletedProcess(cmd, native_code, "", "reader refused the sample")
                now = datetime.now(timezone.utc).isoformat()
                row = source["observation"]
                row.update(startedAtUtc=now, completedAtUtc=now)
                out.write_text(json.dumps(source), encoding="utf-8")
                receipt = dict(recordType="native-current-zone-seed-summary/1", status=row["status"], output=str(out))
                return subprocess.CompletedProcess(cmd, 0, "not-json" if invalid_receipt else json.dumps(receipt), "")

            stdout = StringIO()
            with (patch.object(p, "select_physical", return_value=selected),
                  patch.object(p.socket, "gethostname", return_value="AMD-DESKTOP"),
                  patch.object(p, "NATIVE_EXE", exe), patch.object(p.subprocess, "run", side_effect=native),
                  redirect_stdout(stdout)):
                code = p.main(["--expected-host", "AMD-DESKTOP", "--read-native", "zone-context", "--output", str(out)])
            return code, json.loads(stdout.getvalue())

    def test_complete_candidate_or_unavailable_are_successful_cli_reads(self):
        source = typed_report_1179()
        unavailable = typed_report_1179()
        unavailable["observation"].update(status="cache-miss", childStatus=None, childKey=None,
            zoneIdCandidate=None, outerVtableCandidate=None, recordAddress=None, recordVtable=None,
            recordGetterRva=None, rawNameRef=None,
            qualification="1179 outer type candidate only; child, zone ID, API agreement and restart unverified")
        for fixture, semantics in ((source, "available-candidate"), (unavailable, "unavailable")):
            with self.subTest(semantics=semantics):
                code, result = self.invoke(SHA_1179, fixture)
                self.assertEqual((code, result["status"], result["nativeValues"]["status"]), (0, "complete", semantics))
                self.assertEqual(result["nativeValues"]["worldInstanceStatus"], "unavailable")

    def test_reader_receipt_and_cross_version_report_failures_have_distinct_reasons(self):
        for sha, fixture, options, reason in (
                (SHA_1179, typed_report_1179(), {"native_code": 7}, "native-reader-failed"),
                (SHA_1179, typed_report_1179(), {"invalid_receipt": True}, "invalid-native-reader-receipt"),
                (SHA_1179, report(), {}, "invalid-native-reader-report"),
                (SHA_1177, typed_report_1179(), {}, "invalid-native-reader-report")):
            with self.subTest(sha=sha, reason=reason):
                code, result = self.invoke(sha, fixture, **options)
                self.assertEqual((code, result["status"], result["reason"]), (2, "blocked", reason))
                self.assertNotIn("nativeValues", result)
                if "native_code" in options:
                    self.assertEqual(result["exitCode"], options["native_code"])
