import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from native_tls_collections import read_tls_collections


def run(index=2, value=0x90000, *, changed=False, tid=7, expansion=0x50000):
    teb = 0x10000
    identity = teb.to_bytes(8, "little") + bytes(8) + (42).to_bytes(8, "little") + tid.to_bytes(8, "little")
    slot = teb + (0x1480 + index * 8 if index < 64 else 0x1780)
    memory = {teb + 0x30: identity, slot: (value if index < 64 else expansion).to_bytes(8, "little")}
    if index >= 64 and expansion:
        memory[expansion + (index - 64) * 8] = value.to_bytes(8, "little")
    def read(name, ranges):
        result = {address: memory[address] for address, _ in ranges}
        if changed and name == "tls-recheck":
            result[slot] = b"\x01" * 8
        return result
    return read_tls_collections(read, threads=[{"threadId": 7, "startUtcTicks": "123", "tebAddress": teb}],
                                tls_index=index, embedded_collection=0x80000, process_id=42)


def test_inline_and_expansion_selection():
    assert run()["threads"][0]["selectedCollection"] == 0x90000
    assert run(64)["threads"][0]["tlsValue"] == 0x90000
    row = run(1087, expansion=0)["threads"][0]
    assert row["tlsValue"] == 0 and row["selectedCollection"] == 0x80000 and row["usesEmbedded"]


def test_changed_or_wrong_thread_discards_rows():
    for result in (run(changed=True), run(tid=8)):
        assert result["status"] == "unavailable" and result["threads"] == []


def test_invalid_bounds_and_duplicate_threads():
    thread = {"threadId": 7, "startUtcTicks": "123", "tebAddress": 0x10000}
    for index, threads in [(1088, [thread]), (0, [thread, thread]), (0, [thread] * 257)]:
        result = read_tls_collections(lambda *_: {}, threads=threads, tls_index=index,
                                      embedded_collection=0x80000, process_id=42)
        assert result["status"] == "unavailable" and not result["threads"]
    for value in (0x8000, 0x90001, 0x800000000000):
        assert run(value=value)["status"] == "unavailable"
    assert run(index=64, expansion=0x50001)["status"] == "unavailable"


class TestTlsCollections(unittest.TestCase):
    def test_inline_and_expansion_selection(self):
        test_inline_and_expansion_selection()

    def test_changed_or_wrong_thread_discards_rows(self):
        test_changed_or_wrong_thread_discards_rows()

    def test_invalid_bounds_and_duplicate_threads(self):
        test_invalid_bounds_and_duplicate_threads()
