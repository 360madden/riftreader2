import hashlib
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zlib

from scripts import readerbridge_v3 as rb


def section(tag, body):
    return tag.encode() + f"{len(body):08X}".encode() + body


def slot(sequence, clock, flags, mask, body, fixed_crc=None):
    header = f"SH|{sequence:016X}|{clock:012X}|{flags:08X}|{len(body):08X}|{mask:08X}|03|\n".encode()
    crc = zlib.crc32(header + body) if fixed_crc is None else fixed_crc
    return header + body.ljust(4096, b".") + f"{crc:08X}".encode() + b"==RBRG=="


NAME = "É;:=|".encode()
PLAYER = (b"name=6:" + NAME + b";level=45;calling=7:warrior;guild=0:;hp=18208;hpMax=18208;"
          b"hpPct=100;resKind=5:power;resCur=96;resMax=100;resPct=96;x=-3.01;y=10.00;z=12.05;")
STATS = b"dps1s=0.00;dps5s=0.00;hps1s=0.00;hps5s=0.00;in1s=0.00;in5s=0.00;"
BODY = section("P", PLAYER) + section("S", STATS)
EMPTY = slot(0, 0, 0, 0, b"")


def packet(body=BODY, mask=129, flags=0, seq=1, previous=EMPTY, active="B"):
    control = f"{active}|{seq:016X}|{123:012X}\n".encode()
    latest = slot(seq, 123, flags, mask, body)
    return rb.MAGIC + control + (previous + latest if active == "B" else latest + previous)


class PacketTests(unittest.TestCase):
    def test_unicode_and_punctuation_count_bytes(self):
        data = packet()
        r = rb.decode_packet(data)
        self.assertEqual(r["sections"]["P"]["name"], NAME.decode())
        self.assertEqual(r["health"], {"current": 18208, "maximum": 18208})
        self.assertEqual(r["power"], {"current": 96, "publishedMaximum": 100, "maximumMayBeAddonDefault": True})
        self.assertEqual(r["crcModes"], ["unsigned-ieee"])
        self.assertEqual(r["packetSha256"], hashlib.sha256(data).hexdigest().upper())

    def test_installed_producer_crc_vectors_and_mixed_runtime_rejection(self):
        # Exact disk-pinned 0.3.2 buildSlot/buildEmptySlot, executed offline with
        # this BODY under Lua 5.1 arithmetic fallback and LuaJIT 2.1 bit.bxor.
        data = packet()
        self.assertEqual((data[4200:4208], data[-16:-8]), (b"40506131", b"D41BADB7"))
        signed = data[:4200] + b"E50FB030" + data[4208:-16] + b"19D6B935" + data[-8:]
        self.assertEqual(rb.decode_packet(signed)["crcModes"], ["signed-lua-bit"])
        with self.assertRaisesRegex(ValueError, "different-crc-algorithms"):
            rb.decode_packet(data[:-16] + signed[-16:])

    def test_repeated_fields_in_multiple_items_and_target_flag(self):
        target = b"name=3:Foo;level=45;hpPct=99;rel=7:hostile;"
        buff = b"id=1.23456e+16;nm=3:a;b;stk=1;rem=50;self=1;"
        event = b"t=77;src=2:aa;dst=2:bb;abi=1;ty=3:dmg;amt=10;crit=0;abs=0;"
        body = (section("P", PLAYER) + section("T", target) + section("Z", b"id=9;name=0:;")
                + section("S", STATS) + section("B", b"n=2;" + buff * 2) + section("C", b"n=1;" + event))
        r = rb.decode_packet(packet(body, mask=1+2+4+64+128+256, flags=3,
                                    seq=2, previous=slot(1, 111, 0, 129, BODY), active="A"))
        self.assertTrue(r["flags"]["inCombat"])
        self.assertEqual(len(r["sections"]["B"]), 2)
        self.assertEqual(r["sections"]["B"][0]["nm"], "a;b")
        self.assertEqual(r["sections"]["B"][0]["id"], 12345600000000000)
        self.assertFalse(r["sections"]["C"][0]["crit"])
        self.assertEqual(r["sections"]["T"]["rel"], "hostile")

    def test_resource_availability_and_published_maximum(self):
        resource = rb.decode_packet(packet(BODY.replace(b"resMax=100", b"resMax=110")))["power"]
        self.assertFalse(resource["maximumMayBeAddonDefault"])
        nonpower = rb.decode_packet(packet(BODY.replace(b"5:power", b"5:combo")))
        self.assertIsNone(nonpower["power"])

    def test_valid_active_can_follow_truncated_inactive_history(self):
        old = slot(1, 122, 64, 129, b"cut" * 100)
        self.assertEqual(rb.decode_packet(packet(seq=2, previous=old, active="A"))["sequence"], 2)

    def test_torn_control_or_slot_and_crc_corruption_refused(self):
        data = packet()
        for name, broken in (
            ("short", data[:-1]), ("excess", data + b"x"), ("magic", b"x" + data[1:]),
            ("control", data[:10] + b"1" + data[11:]), ("sequence", packet(seq=3)),
            ("clock", data[:27] + b"F" + data[28:]),
            ("crc", data.replace(b"resCur=96", b"resCur=95")), ("end", data[:-1] + b"!"),
            ("padding", data.replace(b".....", b".x...", 1)),
            ("bad-inactive-crc", data[:4200] + b"F" * 8 + data[4208:]),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                rb.decode_packet(broken)

    def test_length_types_record_boundaries_and_masks(self):
        bad = [
            (BODY, 129, 64), (BODY, 129, 32), (BODY, 129, 2), (BODY, 1, 0),
            (section("P", PLAYER.replace(b"name=6:", b"name=5:")) + section("S", STATS), 129, 0),
            (BODY.replace(b"x=-3.01", b"x=nan  "), 129, 0),
            (BODY + section("P", PLAYER), 129, 0),
            (BODY + section("B", b"n=1;"), 133, 0),
            (BODY + section("C", b"n=65;"), 193, 0),
            (BODY.replace(b"P0000", b"PFFFF"), 129, 0),
            (section("P", PLAYER + b"hp=3;") + section("S", STATS), 129, 0),
        ]
        for body, mask, flags in bad:
            with self.subTest(mask=mask, flags=flags), self.assertRaises(ValueError):
                rb.decode_packet(packet(body, mask, flags))

    def test_cli_reads_exact_raw_packet(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "packet.bin"
            for data, code in [(packet(), 0), (packet() + b"\x00", 2)]:
                file.write_bytes(data)
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(rb.main(["--packet", str(file)]), code)
                self.assertEqual(json.loads(output.getvalue())["status"], "decoded" if code == 0 else "blocked")


if __name__ == "__main__":
    unittest.main()
