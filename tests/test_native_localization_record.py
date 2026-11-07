import json
from pathlib import Path
import unittest
from scripts.native_localization_record import parse_localization_record

class RecordTests(unittest.TestCase):
    def test_retained_vectors(self):
        path = Path(__file__).with_name('native_localization_huffman_vectors.json')
        vectors = json.loads(path.read_text(encoding='utf-8'))['vectors']
        self.assertEqual([parse_localization_record(bytes.fromhex(v['decoded_hex']))['candidate_text'] for v in vectors], ['Break Free', 'Soul Recall'])
        self.assertFalse(parse_localization_record(bytes.fromhex(vectors[0]['decoded_hex']))['field_mapping_qualified'])
    def test_rejects_changed_shape_trailing_truncation_and_utf8(self):
        raw=bytes.fromhex('9b3ca701bb05029d3c060a427265616b20467265650707')
        for invalid in (raw+b'\0', raw[:-1], raw[:2]+b'\xa6'+raw[3:], raw[:10]+b'\xff'+raw[11:]):
            with self.assertRaises(ValueError): parse_localization_record(invalid)
