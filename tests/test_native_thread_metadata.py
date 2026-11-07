import tempfile
import unittest
from pathlib import Path
from scripts.native_thread_metadata import build_thread_metadata_executable

class MetadataTests(unittest.TestCase):
    def test_rejects_non_exe(self):
        with self.assertRaises(ValueError):
            build_thread_metadata_executable(Path('query.txt'))

    def test_existing_source_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'query.exe'
            source = output.with_suffix('.cs')
            source.write_text('existing')
            with self.assertRaises(FileExistsError):
                build_thread_metadata_executable(output)
            self.assertEqual(source.read_text(), 'existing')

if __name__ == '__main__':
    unittest.main()
