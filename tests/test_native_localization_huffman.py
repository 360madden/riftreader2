import struct
import json
from pathlib import Path
import unittest
from scripts.native_localization_huffman import decode_localization_huffman


class HuffmanTests(unittest.TestCase):
    def setUp(self):
        # The 255 zero-weight leaves combine to weight zero; symbol 255 is
        # the only nonzero leaf and is the right child of the root.
        self.frequencies = struct.pack('<256i', *([0] * 255 + [1000]))

    def test_known_root_code_and_msb_order(self):
        self.assertEqual(decode_localization_huffman(self.frequencies, b'\xe0', 3), (b'\xff' * 3, 3))

    def test_captured_record_vectors(self):
        fixture = json.loads(Path(__file__).with_name('native_localization_huffman_vectors.json').read_text(encoding='utf-8'))
        frequencies = bytes.fromhex(fixture['frequency_hex'])
        for vector in fixture['vectors']:
            with self.subTest(key=vector['key']):
                self.assertEqual(decode_localization_huffman(frequencies,
                    bytes.fromhex(vector['encoded_hex']), vector['decoded_size']),
                    (bytes.fromhex(vector['decoded_hex']), vector['consumed_bits']))

    def test_input_exhaustion_and_output_bound(self):
        with self.assertRaisesRegex(ValueError, 'input_exhausted'):
            decode_localization_huffman(self.frequencies, b'', 1)
        with self.assertRaisesRegex(ValueError, 'invalid_decoded_size'):
            decode_localization_huffman(self.frequencies, b'', 65536)
        self.assertEqual(decode_localization_huffman(self.frequencies, b'', 0), (b'', 0))

    def test_equal_leaf_tie_root_codes(self):
        # Equal leaves yield a complete depth-eight tree and every byte path
        # must map to a distinct symbol.
        frequency = struct.pack('<256i', *([1] * 256))
        data, bits = decode_localization_huffman(frequency, bytes(range(256)), 256)
        self.assertEqual(bits, 2048)
        self.assertEqual(len(set(data)), 256)


if __name__ == '__main__':
    unittest.main()
