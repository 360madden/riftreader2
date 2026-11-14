"""Decode one retained 8,392-byte ReaderBridge v3 Lua-heap packet. No process access."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import zlib

MAGIC = b"RBRG3\n=="
PACKET_SIZE = 8392
SLOT_SIZE = 4176
CONTROL = re.compile(rb"([AB])\|([0-9A-F]{16})\|([0-9A-F]{12})\n")
HEADER = re.compile(rb"SH\|([0-9A-F]{16})\|([0-9A-F]{12})\|([0-9A-F]{8})\|([0-9A-F]{8})\|([0-9A-F]{8})\|03\|\n")
SECTION = re.compile(rb"([PTZSBDbdC])([0-9A-F]{8})")
LENGTH = re.compile(rb"(0|[1-9][0-9]*):")
NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)")
LUA_LARGE_INT = re.compile(rb"-?[1-9](?:\.[0-9]+)?e\+[0-9]{2,3}")
DECIMAL = re.compile(rb"-?(?:0|[1-9][0-9]*)\.[0-9]{2}")
SECTIONS = {"P": 1, "T": 2, "B": 4, "D": 8, "b": 16, "d": 32, "C": 64, "S": 128, "Z": 256}
FLAGS = {"inCombat": 1, "hasTarget": 2, "grouped": 4, "resting": 8, "mounted": 16,
         "partial": 32, "truncated": 64}
SCHEMAS = {
    "P": "name:s level:i calling:s guild:s hp:i hpMax:i hpPct:i resKind:s resCur:i resMax:i resPct:i x:f y:f z:f",
    "T": "name:s level:i hpPct:i rel:s",
    "Z": "id:i name:s",
    "S": "dps1s:f dps5s:f hps1s:f hps5s:f in1s:f in5s:f",
    "buff": "id:i nm:s stk:i rem:i self:b",
    "C": "t:i src:s dst:s abi:i ty:s amt:i crit:b abs:i",
}
PRODUCER = {
    "schemaSourceVersion": "0.3.2",
    "schemaSourcePath": r"C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\ReaderBridge\ReaderBridge.lua",
    "schemaSourceSha256": "8D2734776A319173EC27F6679A2F8EA11E07E8A666FD7D7D47F1B22D02ECEBF1",
    "startupManifestSha256": "4040E44E7458A76B7972CCE68CA0CB7CC00FCAE8153E313D262D68C670245F70",
}


def signed32(value):
    return ((value + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def signed_crc_entry(value):
    for _ in range(8):
        value = signed32((value >> 1) ^ 0xEDB88320) if value & 1 else value >> 1
    return value


SIGNED_CRC_TABLE = tuple(signed_crc_entry(i) for i in range(256))


def crc_modes(data, expected):
    # The producer uses floor(crc / 256) even when Lua bit.bxor returns a
    # signed int32. Its bit32/arithmetic branches use unsigned IEEE CRC32.
    modes = set()
    if zlib.crc32(data) == expected:
        modes.add("unsigned-ieee")
    crc = 0xFFFFFFFF
    for byte in data:
        crc = signed32((crc >> 8) ^ SIGNED_CRC_TABLE[(crc ^ byte) & 255])
    if (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF == expected:
        modes.add("signed-lua-bit")
    if not modes:
        raise ValueError("slot-crc-mismatch")
    return modes


class SectionReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def fields(self, schema):
        result = {}
        for field in schema.split():
            name, kind = field.split(":")
            prefix = name.encode("ascii") + b"="
            if not self.data.startswith(prefix, self.pos):
                raise ValueError("missing-or-unexpected-field:" + name)
            self.pos += len(prefix)
            if kind == "s":
                length = LENGTH.match(self.data, self.pos)
                if not length:
                    raise ValueError("invalid-string-length:" + name)
                start = length.end()
                end = start + int(length[1])
                if end >= len(self.data) or self.data[end] != ord(";"):
                    raise ValueError("string-length-exceeds-field:" + name)
                result[name] = self.data[start:end].decode("utf-8")
            else:
                end = self.data.find(b";", self.pos)
                if end < 0:
                    raise ValueError("missing-field-terminator:" + name)
                raw = self.data[self.pos:end]
                if kind == "b" and raw in (b"0", b"1"):
                    result[name] = raw == b"1"
                elif kind == "i" and NUMBER.fullmatch(raw):
                    result[name] = int(raw)
                elif kind == "i" and LUA_LARGE_INT.fullmatch(raw) and math.isfinite(float(raw)):
                    # Lua tostring(floor(value)) can use scientific notation,
                    # particularly for numeric buff or event IDs.
                    value = Decimal(raw.decode("ascii"))
                    if value != value.to_integral_value():
                        raise ValueError("invalid-integer:" + name)
                    result[name] = int(value)
                elif kind == "f" and DECIMAL.fullmatch(raw) and math.isfinite(float(raw)):
                    result[name] = float(raw)
                else:
                    raise ValueError("invalid-field-type:" + name)
            self.pos = end + 1
        return result


def sections(body, mask, flags):
    result = {}
    pos = 0
    while pos < len(body):
        match = SECTION.match(body, pos)
        if not match:
            raise ValueError("invalid-section-header")
        tag = match[1].decode("ascii")
        end = match.end() + int(match[2], 16)
        if tag in result or end > len(body):
            raise ValueError("duplicate-or-overrun-section:" + tag)
        reader = SectionReader(body[match.end():end])
        if tag in ("B", "D", "b", "d", "C"):
            count = reader.fields("n:i")["n"]
            if not 1 <= count <= (64 if tag == "C" else len(reader.data)):
                raise ValueError("invalid-section-item-count:" + tag)
            schema = SCHEMAS["C" if tag == "C" else "buff"]
            result[tag] = [reader.fields(schema) for _ in range(count)]
        else:
            result[tag] = reader.fields(SCHEMAS[tag])
        if reader.pos != len(reader.data):
            raise ValueError("unexpected-trailing-field:" + tag)
        pos = end
    if (sum(SECTIONS[t] for t in result) != mask or not {"P", "S"} <= result.keys()
            or bool(flags & FLAGS["hasTarget"]) != ("T" in result)):
        raise ValueError("section-mask-or-target-flag-mismatch")
    return result


def slot(data):
    head = HEADER.fullmatch(data[:64])
    if not head or len(data) != SLOT_SIZE or data[-8:] != b"==RBRG==":
        raise ValueError("invalid-slot-header-or-terminator")
    seq, clock, flags, length, mask = (int(piece, 16) for piece in head.groups())
    if length > 4096 or flags & ~0x7F or mask & ~0x1FF:
        raise ValueError("slot-size-flags-or-mask-out-of-range")
    body = data[64:64 + length]
    if data[64 + length:4160] != b"." * (4096 - length):
        raise ValueError("invalid-slot-padding")
    if not re.fullmatch(rb"[0-9A-F]{8}", data[4160:4168]):
        raise ValueError("invalid-slot-crc-format")
    modes = crc_modes(data[:64] + body, int(data[4160:4168], 16))
    return seq, clock, flags, mask, body, modes


def decode_packet(data: bytes):
    if len(data) != PACKET_SIZE or not data.startswith(MAGIC):
        raise ValueError("expected-8392-byte-RBRG3-packet")
    control = CONTROL.fullmatch(data[8:40])
    if not control:
        raise ValueError("invalid-control")
    active = control[1].decode("ascii")
    slots = {"A": slot(data[40:4216]), "B": slot(data[4216:])}
    seq, clock, flags, mask, body, modes = slots[active]
    previous = slots["B" if active == "A" else "A"]
    if seq == 0 or (seq, clock) != (int(control[2], 16), int(control[3], 16)):
        raise ValueError("active-slot-control-disagreement")
    if previous[0] != seq - 1 or (previous[0] == 0 and previous[1:5] != (0, 0, 0, b"")):
        raise ValueError("invalid-previous-generation")
    common = modes & previous[5]
    if not common:
        raise ValueError("slots-use-different-crc-algorithms")
    if flags & (FLAGS["partial"] | FLAGS["truncated"]):
        raise ValueError("active-slot-partial-or-truncated")
    decoded = sections(body, mask, flags)
    player = decoded["P"]
    power = None
    if player["resKind"] == "power":
        power = {"current": player["resCur"], "publishedMaximum": player["resMax"],
                 "maximumMayBeAddonDefault": player["resMax"] == 100}
    return {"evidenceKind": "readerbridge-v3-packet/1", "status": "decoded",
            "packetSha256": hashlib.sha256(data).hexdigest().upper(), "schemaProducer": PRODUCER,
            "activeSlot": active, "sequence": seq, "sourceTimeMs": clock, "crcModes": sorted(common),
            "flags": {name: bool(flags & bit) for name, bit in FLAGS.items()}, "sections": decoded,
            "health": {"current": player["hp"], "maximum": player["hpMax"]}, "power": power,
            "qualification": "Retained packet only. Process, player identity and advancing freshness require separate evidence.",
            "fieldLimits": ["Missing player HP/maximum and combat can be published as zero/false.",
                            "The producer supplies 100 when Power maximum is missing.",
                            "Target detail lacks a target unit ID. Death, learned abilities and readiness are absent."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True, help="Raw 8392 bytes starting at RBRG3 magic")
    args = parser.parse_args(argv)
    try:
        with args.packet.open("rb") as stream:
            result = decode_packet(stream.read(PACKET_SIZE + 1))
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
