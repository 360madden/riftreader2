"""Offline exact-build localization Huffman tree candidate; output is raw bytes."""
import struct


def decode_localization_huffman(frequency_bytes, encoded_bytes, decoded_size):
    """Decode bounded input; return (bytes, bits consumed), never padded input.

    Frequencies are 256 signed little-endian words. Tree arithmetic wraps signed
    32-bit as in the investigated client. The caller owns record framing and must
    establish the input bound independently of the native first varint.
    """
    if not isinstance(frequency_bytes, bytes) or len(frequency_bytes) != 1024:
        raise ValueError("frequency_table_must_be_1024_bytes")
    if not isinstance(encoded_bytes, bytes):
        raise ValueError("encoded_input_must_be_bytes")
    if type(decoded_size) is not int or not 0 <= decoded_size < 65536:
        raise ValueError("invalid_decoded_size")
    weights = struct.unpack('<256i', frequency_bytes)
    heap = [None] + [(i, weights[i]) for i in range(256)]
    left, right = [None] * 256, [None] * 256

    def sift(index, size):
        while 2 * index <= size:
            child = 2 * index
            if child < size and heap[child][1] > heap[child + 1][1]:
                child += 1
            if heap[index][1] <= heap[child][1]:
                break
            heap[index], heap[child] = heap[child], heap[index]
            index = child

    for i in range(128, 0, -1):
        sift(i, 256)
    size = 256
    while size > 1:
        first = heap[1]
        heap[1] = heap[size]
        size -= 1
        sift(1, size)
        second = heap[1]
        left[size], right[size] = first[0], second[0]
        if size == 1:
            break
        total = (first[1] + second[1]) & 0xffffffff
        if total >= 0x80000000:
            total -= 0x100000000
        heap[1] = (-size, total)
        sift(1, size)

    output = bytearray()
    bits = 0
    for _ in range(decoded_size):
        node = -1
        depth = 0
        while node < 0:
            index = -node
            if index >= len(left) or left[index] is None or depth >= 255:
                raise ValueError("invalid_tree")
            if bits >= len(encoded_bytes) * 8:
                raise ValueError("input_exhausted")
            bit = (encoded_bytes[bits // 8] >> (7 - bits % 8)) & 1
            bits += 1
            node = right[index] if bit else left[index]
            depth += 1
        if node > 255:
            raise ValueError("invalid_symbol")
        output.append(node)
    return bytes(output), bits
