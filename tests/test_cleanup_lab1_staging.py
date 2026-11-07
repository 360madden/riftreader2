import unittest

from scripts import cleanup_lab1_staging as cleanup


class CleanupLab1StagingTests(unittest.TestCase):
    def test_guest_program_is_fixed_and_metadata_only(self):
        body = cleanup.guest_body()

        self.assertIn(cleanup.GUEST_FILE, body)
        self.assertIn(cleanup.GUEST_PARENT, body)
        self.assertIn("CreateFile(", body)
        self.assertIn("DELETE | FILE_READ_ATTRIBUTES, 0", body)
        self.assertIn("FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT", body)
        self.assertIn("FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000", body)
        self.assertIn("GetFileInformationByHandle", body)
        self.assertIn("SetFileInformationByHandle", body)
        self.assertIn("FileDispositionInfo is 4", body)
        self.assertIn("staging-leaf-too-large", body)
        self.assertIn("staging-parent-reparse-point", body)
        self.assertIn("staging-leaf-reparse-point", body)
        self.assertIn("live-reader-or-unknown-command-already-running", body)
        self.assertNotIn("Get-Content", body)
        self.assertNotIn("ReadAll", body)
        self.assertNotIn("Remove-Item", body)
        self.assertNotIn("-Recurse", body)
        self.assertNotIn("DeleteOnClose", body)
        self.assertNotIn("FileAccess]::Read", body)

    def test_native_disposition_occurs_after_handle_validation(self):
        body = cleanup.guest_body()
        method = body.index("public static void DeleteAfterHandleChecks")
        handle_info = body.index("GetFileInformationByHandle(handle", method)
        length_check = body.index("actualLength != expectedLength", handle_info)
        disposition = body.index("SetFileInformationByHandle(", length_check)

        self.assertLess(handle_info, length_check)
        self.assertLess(length_check, disposition)

    def test_accepts_deleted_receipt(self):
        receipt = {
            "status": "deleted",
            "fileExisted": True,
            "deleted": True,
            "otherReaderCountBefore": 0,
            "otherReaderCountAfter": 0,
            "inputSent": False,
        }

        self.assertEqual(cleanup.validate_receipt(receipt), receipt)

    def test_accepts_idempotent_already_absent_receipt(self):
        receipt = {
            "status": "already-absent",
            "fileExisted": False,
            "deleted": False,
            "otherReaderCountBefore": 0,
            "otherReaderCountAfter": 0,
            "inputSent": False,
        }

        self.assertEqual(cleanup.validate_receipt(receipt), receipt)

    def test_rejects_reader_or_input_guard_failure(self):
        receipt = {
            "status": "already-absent",
            "fileExisted": False,
            "deleted": False,
            "otherReaderCountBefore": 1,
            "otherReaderCountAfter": 0,
            "inputSent": False,
        }

        with self.assertRaisesRegex(RuntimeError, "cleanup-receipt-guard-failed"):
            cleanup.validate_receipt(receipt)

    def test_rejects_extra_fields_that_could_expose_private_content(self):
        receipt = {
            "status": "deleted",
            "fileExisted": True,
            "deleted": True,
            "otherReaderCountBefore": 0,
            "otherReaderCountAfter": 0,
            "inputSent": False,
            "content": "private",
        }

        with self.assertRaisesRegex(RuntimeError, "cleanup-receipt-fields"):
            cleanup.validate_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
