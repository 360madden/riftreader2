from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import build_live_source_pin as builder


NONCE = "0123456789abcdef0123456789abcdef"
SHA = "A" * 64


class BuildLiveSourcePinTests(unittest.TestCase):
    def summary(self, receiver_image: Path) -> dict:
        return {
            "status": "reader-running-postflight-verified", "lab": "lab2", "runId": "run",
            "readerPid": 12, "readerStartUtcTicks": 13, "readerSha256": SHA,
            "nonce": NONCE, "expiresAtUtc": "2026-10-30T00:00:00Z",
            "guestDirectory": r"C:\reader", "guestOutput": r"C:\reader\latest.json",
            "gamePid": 21, "gameStartUtcTicks": "22", "gameSha256": SHA,
            "receiver": {"pid": 31, "processStartUtcTicks": 32,
                         "image": str(receiver_image), "address": "192.168.56.1",
                         "port": 49813, "configSha256": SHA},
            "vmIdentityStable": True, "inputSent": False, "controlAgentStopped": False,
            "cleanup": "bounded", "atUtc": "2026-10-29T00:00:00Z",
        }

    @staticmethod
    def receipt() -> dict:
        return {"sourceAddress": "0x1234", "receiverInstance": "receiver-one",
                "observation": {"nonce": NONCE, "instanceId": "reader-one",
                    "target": {"processId": 21, "processStartUtcTicks": 22,
                        "executablePath": r"C:\RIFT\rift_x64.exe",
                        "executableSha256": SHA,
                        "readerSessionNonce": NONCE}}}

    def test_accepts_legacy_and_new_launcher_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "receiver.exe"; image.write_bytes(b"receiver")
            receipt_path = root / "latest.json"
            receipt_path.write_text(json.dumps(self.receipt()), encoding="utf-8")
            legacy = self.summary(image)
            current = {**legacy, "maxScanBytes": 4 * 1024**3}
            for summary in (legacy, current):
                with self.subTest(fields=set(summary)):
                    pin = builder.build_pin(summary, {"machineName": "RIFT-LAB-2"},
                                            receipt_path, self.receipt())
                    self.assertEqual(set(pin), {"schemaVersion", "lab", "vmIdentity",
                        "gameIdentity", "reader", "receiver", "receiptPath", "receiptSha256"})
                    self.assertEqual(NONCE, pin["reader"]["nonce"])

    def test_rejects_unknown_or_invalid_new_summary_field(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "receiver.exe"; image.write_bytes(b"x")
            baseline = self.summary(image)
            cases = ({**baseline, "unexpected": 1},
                     {**baseline, "maxScanBytes": True},
                     {**baseline, "maxScanBytes": builder.MAX_SCAN_BYTES + 1})
            for value in cases:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    builder.validate_reader_summary(value)

    def test_cli_publishes_pin_after_live_receipt_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "receiver.exe"; image.write_bytes(b"receiver")
            summary = root / "summary.json"
            summary.write_text(json.dumps({**self.summary(image),
                                           "maxScanBytes": 6 * 1024**3}), encoding="utf-8")
            vm = root / "vm.json"; vm.write_text(json.dumps({"machineName": "RIFT-LAB-1"}))
            receipt = root / "latest.json"; receipt.write_text(json.dumps(self.receipt()))
            output = root / "pin.json"
            with mock.patch.object(builder.console, "_fast_receipt") as check:
                self.assertEqual(0, builder.main(["--reader-summary", str(summary),
                    "--vm-identity", str(vm), "--receipt", str(receipt),
                    "--output", str(output)]))
            check.assert_called_once()
            self.assertEqual(NONCE, json.loads(output.read_text())["reader"]["nonce"])


if __name__ == "__main__":
    unittest.main()
