"""Offline checks of the existing C# Power sampler's physical wrapper contract."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as reader
from tests.test_postpatch_native_admission import BUILD_1179, selection

OLD_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"


class PhysicalPowerTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.exe = self.folder / "reader.exe"
        self.exe.touch()
        self.enterContext(patch.object(reader, "NATIVE_EXE", self.exe))
        self.enterContext(patch.dict("os.environ", {
            "RR2_NATIVE_READER": "", "RR2_PHYSICAL_TOOLS_ROOT": "debug",
        }))
        self.enterContext(patch.object(reader.socket, "gethostname", return_value="AMD-DESKTOP"))

    def capture(self, *, sha=BUILD_1179, count=2, change=None, change_receipt=None, cli=False):
        """Synthetic subprocess writes a new native report while the wrapper is timing it."""
        path = self.folder / "power.json"
        path.unlink(missing_ok=True)
        target = selection(sha.lower())

        def invoke(args, **kwargs):
            self.assertEqual(args[:6], [str(self.exe), "sample-power", "--pid", "12345",
                                        "--start-ticks", "638000000000000001"])
            self.assertEqual(args[args.index("--sha256") + 1], sha)
            if count is not None:
                self.assertEqual(args[args.index("--samples") + 1], str(count))
            else:
                self.assertNotIn("--samples", args)
            self.assertEqual(args[args.index("--interval-ms") + 1], "200")
            rows = []
            for n in range(count or 1):
                stamp = datetime.now(timezone.utc).isoformat()
                rows.append(dict(startedAtUtc=stamp, completedAtUtc=stamp, status="complete",
                                 reason=None, power=n, maximum=100, baseValue=0,
                                 rate=1200, sequence=21, clockSeconds=100.0+n, anchorSeconds=99.0))
            report = dict(schemaVersion=1, contractVersion="native-power-samples/1",
                          qualification="candidate-only", recipe=reader.POWER_RECIPES[sha],
                          status="complete", requestedSamples=count or 1, samples=rows,
                          identity=dict(processId=12345, processStartUtcTicks=638000000000000001,
                                        executableSha256=sha))
            if change:
                change(report)
            path.write_text(json.dumps(report), encoding="utf-8")
            receipt = dict(status="complete", samples=count or 1, output=str(path))
            if change_receipt:
                change_receipt(receipt)
            # C# emits a single pretty-printed object, not a JSON-lines receipt.
            return subprocess.CompletedProcess(args, 0, json.dumps(receipt, indent=2), "")

        with patch.object(reader.subprocess, "run", side_effect=invoke):
            if cli:
                args = ["--expected-host", "AMD-DESKTOP", "--physical-pid", "12345",
                        "--read-native", "power", "--interval-ms", "200", "--output", str(path)]
                if count is not None:
                    args.extend(["--samples", str(count)])
                with patch.object(reader, "select_physical", return_value=target), redirect_stdout(io.StringIO()) as stream:
                    self.assertEqual(reader.main(args), 0)
                return json.loads(stream.getvalue()), path
            return reader.read_native(target, "power", path, samples=count, interval_ms=200), path

    def test_multiline_receipt_preserves_zero_and_provenance(self):
        result, path = self.capture(cli=True)
        self.assertEqual(result["status"], "complete")
        values = result["nativeValues"]
        self.assertEqual(values["status"], "candidate")
        self.assertEqual((values["current"], values["maximum"], values["sampleCount"]), (1, 100, 2))
        self.assertEqual([row["current"] for row in values["samples"]], [0, 1])
        self.assertEqual(result["nativeSourceSha256"], sha256(path.read_bytes()).hexdigest())

    def test_historical_build_uses_its_own_explicit_recipe(self):
        result, _ = self.capture(sha=OLD_SHA, count=None)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["current"], 0)
        self.assertEqual(result["nativeValues"]["recipe"], "player-power-7C356C9D-v1")

    def test_unknown_build_and_invalid_schedule_never_launch(self):
        with patch.object(reader.subprocess, "run") as run:
            self.assertEqual(reader.read_native(selection("A"*64), "power")["reason"],
                             "native-power-build-unqualified")
            self.assertEqual(reader.read_native(selection(), "power", samples=31)["reason"],
                             "invalid-position-sampling")
            self.assertEqual(reader.read_native(selection(), "power", interval_ms=-1)["reason"],
                             "invalid-position-sampling")
            run.assert_not_called()

    def test_bad_receipt_never_publishes_values(self):
        for fault in ({"samples": True}, {"samples": 1}, {"status": "partial"},
                      {"output": str(self.folder / "wrong.json")}, {"recordType": "forged"}):
            with self.subTest(fault=fault):
                result, _ = self.capture(change_receipt=lambda r: r.update(fault))
                self.assertEqual(result["reason"], "invalid-native-reader-receipt")
                self.assertNotIn("nativeValues", result)

    def test_bad_report_never_publishes_values(self):
        old = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        faults = [
            lambda r: r.update(recipe="player-power-7C356C9D-v1"),
            lambda r: r.update(requestedSamples=True),
            lambda r: r["samples"].pop(),
            lambda r: r["identity"].update(processStartUtcTicks=1),
            lambda r: r.update(status="partial"),
            lambda r: r["samples"][0].update(status="unavailable"),
            lambda r: r["samples"][0].update(power=True),
            lambda r: r["samples"][0].update(power=101),
            lambda r: r["samples"][0].update(maximum=0),
            lambda r: r["samples"][0].update(clockSeconds=10**500),
            lambda r: r["samples"][0].update(clockSeconds=98),
            lambda r: r["samples"][0].update(startedAtUtc=old, completedAtUtc=old),
            lambda r: r["samples"][1].update(startedAtUtc=old),
        ]
        for n, change in enumerate(faults):
            with self.subTest(fault=n):
                result, _ = self.capture(change=change)
                self.assertEqual(result["reason"], "invalid-native-reader-report")
                self.assertNotIn("nativeValues", result)

    def test_partial_native_exit_stays_unavailable(self):
        with patch.object(reader.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 3, "", "unavailable")):
            result = reader.read_native(selection(), "power")
        self.assertEqual(result["reason"], "native-reader-failed")
        self.assertNotIn("nativeValues", result)


if __name__ == "__main__":
    unittest.main()
