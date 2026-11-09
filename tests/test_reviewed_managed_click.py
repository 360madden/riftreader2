"""Offline admission tests for the managed, file-reviewed single-click path."""
import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from scripts.run_targeted_click import review_from_file


class ReviewedClickReceiptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.image = self.root / "image.bmp"
        self.image.write_bytes(b"BMreview-only-fake-image")
        self.capture = {"captureId": "exact-capture", "image": str(self.image)}
        self.rectangle = [670, 358, 106, 20]
        self.review_file = self.root / "review.json"
        self.payload = {
            "decision": "approve",
            "captureId": self.capture["captureId"],
            "captureImageSha256": sha256(self.image.read_bytes()).hexdigest().upper(),
            "rectangle": self.rectangle,
            "note": "Reviewed free Respawn button; no purchase action.",
        }

    def _review(self, payload, timeout=0.6):
        def write_later():
            time.sleep(.03)
            self.review_file.write_text(json.dumps(payload), encoding="utf-8")
        thread = threading.Thread(target=write_later)
        thread.start()
        try:
            with contextlib.redirect_stdout(io.StringIO()) as messages:
                if payload is None:
                    thread.join()
                    return review_from_file(self.capture, self.rectangle, self.review_file, timeout=timeout)
                result = review_from_file(self.capture, self.rectangle, self.review_file, timeout=timeout)
            self.assertIn("captureImageSha256", messages.getvalue())
            return result
        finally:
            thread.join()

    def test_matching_receipt_approves_only_pinned_click(self):
        self.assertEqual(self._review(self.payload), self.payload["note"])

    def test_mismatched_sha_refuses_click(self):
        payload = dict(self.payload, captureImageSha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "exact current capture"):
            self._review(payload)

    def test_mismatched_rectangle_refuses_click(self):
        payload = dict(self.payload, rectangle=[670, 358, 106, 21])
        with self.assertRaisesRegex(ValueError, "exact current capture"):
            self._review(payload)

    def test_decline_refuses_click(self):
        payload = dict(self.payload, decision="decline")
        with self.assertRaisesRegex(ValueError, "exact current capture"):
            self._review(payload)

    def test_stale_preexisting_receipt_refused(self):
        self.review_file.write_text(json.dumps(self.payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "created after capture"):
            review_from_file(self.capture, self.rectangle, self.review_file, timeout=.01)


if __name__ == "__main__":
    unittest.main()
