"""Explicit unit name batches with synthetic native output and no game access."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as p
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY


KEYS = ("42", "9223372045797034555")
QUALIFICATION = ("cache-only template base-name candidates; names, passive freshness and "
                 "restart unverified; dictionary payload not acquired")


def report(keys=KEYS, timestamp="2026-11-12T22:09:06Z"):
    rows = [dict(unitKey=key, entityAddressDecimal=str(0x20004000+i*0x1000),
                 startedAtUtc=timestamp, completedAtUtc=timestamp, status="raw-candidate",
                 templateKey=55, localizationMode=1, formattingFlag=0, localizationKey=11,
                 fallbackText=f"Unit {i+1}") for i, key in enumerate(keys)]
    return dict(schemaVersion=1, contractVersion="native-unit-template-names-candidate/1", status="complete",
                observation=dict(identity=deepcopy(REPORT_IDENTITY), startedAtUtc=timestamp, completedAtUtc=timestamp,
                                 selfKey="42", rows=rows, qualification=QUALIFICATION))


class UnitNameTests(unittest.TestCase):
    def setUp(self):
        self.selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
        self.directory = self.enterContext(TemporaryDirectory())
        self.exe = Path(self.directory) / "reader.exe"
        self.exe.write_bytes(b"MZ")
        self.enterContext(patch.object(p.socket, "gethostname", return_value="AMD-DESKTOP"))
        self.enterContext(patch.object(p, "NATIVE_EXE", self.exe))

    def read(self, transform=None, cli=False):
        output = Path(self.directory) / "units.json"
        output.unlink(missing_ok=True)
        def run(args, **kwargs):
            self.assertEqual([str(self.exe), "sample-current-unit-template-names", "--pid", "123",
                              "--start-ticks", IDENTITY["processStartUtcTicks"], "--output", str(output),
                              "--keys", ",".join(KEYS)], args)
            doc = report(timestamp=datetime.now(timezone.utc).isoformat())
            if transform is not None:
                transform(doc["observation"])
            output.write_text(json.dumps(doc), encoding="utf-8")
            summary = dict(recordType="native-unit-template-names-summary/1", status="complete", output=str(output))
            return subprocess.CompletedProcess(args, 0, json.dumps(summary), "")
        with patch.object(p.subprocess, "run", side_effect=run):
            if cli:
                with patch.object(p, "select_physical", return_value=self.selection), redirect_stdout(io.StringIO()) as stream:
                    self.assertEqual(0, p.main(["--read-native", "unit-names", "--expected-host", "AMD-DESKTOP",
                                                "--physical-pid", "123", "--unit-keys", ",".join(KEYS), "--output", str(output)]))
                result = json.loads(stream.getvalue())
            else:
                result = p.read_native(self.selection, "unit-names", output, unit_keys=KEYS)
        if result["status"] == "complete":
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), result["nativeSourceSha256"])
        return result

    def test_cli_routes_only_explicit_keys_and_preserves_them(self):
        values = self.read(cli=True)["nativeValues"]
        self.assertEqual("42", values["selfKey"])
        self.assertEqual(KEYS, tuple(row["unitKey"] for row in values["rows"]))
        self.assertEqual(["Unit 1", "Unit 2"], [row["baseNameCandidate"] for row in values["rows"]])
        self.assertEqual(QUALIFICATION, values["qualification"])
        self.assertNotIn("targetKey", values)

    def test_invalid_dispatch_never_launches(self):
        with patch.object(p.subprocess, "run") as run:
            for bad in (None, [], list(map(str, range(1, 34))), "42", ["０１"], [" 42"], ["01"], ["0"],
                        [1], [True], [str(2**64)], ["42", "42"]):
                with self.subTest(keys=bad):
                    self.assertEqual("blocked", p.read_native(self.selection, "unit-names", unit_keys=bad)["status"])
            for kw in (dict(samples=1), dict(interval_ms=0), dict(include_target=True), dict(include_position=True),
                       dict(include_transform_sources=True), dict(start_bucket=0)):
                self.assertEqual("blocked", p.read_native(self.selection, "unit-names", unit_keys=KEYS, **kw)["status"])
            self.assertEqual("blocked", p.read_native(self.selection, "target-name", unit_keys=KEYS)["status"])
            run.assert_not_called()
        with patch.object(p, "select_physical") as select, redirect_stdout(io.StringIO()):
            for args in (["--read-native", "unit-names"], ["--read-native", "position", "--unit-keys", "42"]):
                self.assertEqual(2, p.main(["--expected-host", "AMD-DESKTOP", *args]))
            select.assert_not_called()

    def test_wrong_coverage_epoch_and_timestamps_refuse(self):
        for transform in (lambda batch: batch["rows"].reverse(), lambda batch: batch["rows"].pop(),
                          lambda batch: batch["rows"][0].update(unitKey="77"),
                          lambda batch: batch["identity"].update(processStartUtcTicks=999),
                          lambda batch: batch.update(startedAtUtc="2026-01-01T00:00:00Z"),
                          lambda batch: batch["rows"][0].update(completedAtUtc="2030-01-01T00:00:00Z")):
            self.assertEqual("blocked", self.read(transform)["status"])

    def test_unavailable_rows_keep_identity_and_never_publish_fallback(self):
        for fields, reason in ((dict(localizationMode=2), "unsupported-localization-mode"),
                               (dict(formattingFlag=1), "formatting-required"),
                               (dict(fallbackText="Guard\nSoldier"), "unreadable-fallback"),
                               (dict(fallbackText="  "), "empty-fallback"),
                               (dict(status="cache-miss", localizationKey=None, fallbackText=None), "cache-miss"),
                               (dict(status="unit-missing", entityAddressDecimal=None, templateKey=None,
                                     localizationMode=None, formattingFlag=None, localizationKey=None, fallbackText=None), "unit-missing")):
            with self.subTest(reason=reason):
                doc = report()
                doc["observation"]["rows"][0].update(fields)
                row = p._native_values("unit-names", doc)["rows"][0]
                self.assertEqual(("42", "unavailable", reason, None),
                                 (row["unitKey"], row["status"], row["reason"], row["baseNameCandidate"]))

    def test_native_malformed_name_status_keeps_entity_only(self):
        for status in ("name-unterminated", "name-utf16-invalid"):
            with self.subTest(status=status):
                doc = report()
                raw = doc["observation"]["rows"][0]
                raw.update(status=status, templateKey=None, localizationMode=None, formattingFlag=None,
                           localizationKey=None, fallbackText=None)
                row = p._native_values("unit-names", doc)["rows"][0]
                self.assertEqual((raw["entityAddressDecimal"], "unavailable", status, None),
                                 (row["entityAddressDecimal"], row["status"], row["reason"], row["baseNameCandidate"]))
                raw["templateKey"] = 55
                with self.assertRaises(ValueError):
                    p._native_values("unit-names", doc)

    def test_malformed_rows_fail_closed(self):
        for fields in (dict(status="unknown"), dict(entityAddressDecimal="179"), dict(templateKey=True),
                       dict(status="cache-miss"), dict(status="unit-missing"), dict(fallbackText="x"*128),
                       dict(localizationKey=-1), dict(unitKey=42), dict(unitKey=KEYS[1])):
            with self.subTest(fields=fields):
                doc = report()
                doc["observation"]["rows"][0].update(fields)
                with self.assertRaises(ValueError):
                    p._native_values("unit-names", doc)


if __name__ == "__main__":
    unittest.main()
