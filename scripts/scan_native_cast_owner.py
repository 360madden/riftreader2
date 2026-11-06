"""Bounded exact-build scan for direct-call candidates in the cast producer.

This is deliberately an opcode scanner, not a disassembler.  It confines the
search to the PE unwind range already assigned to the cast producer and reports
only E8-relative byte patterns whose computed target is in the caller-supplied
allowlist.  Each result remains an instruction-boundary candidate until decoded
independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.find_native_api_xrefs import _sections, _runtime_functions


BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
PRODUCER_RVA = 0x91DED0
KNOWN_TARGETS = {
    0x4A4750: "manager",
    0x6A0040: "key-to-entity",
    0x5A75C0: "child-280-id",
    0x5A7570: "child-290-id",
    0x5A9940: "refcounting-smart-reference-copy",
    0x5A6CB0: "downstream-cast-state",
    0x49F960: "downstream-field-helper",
    0x49D440: "downstream-field-helper",
    0x49DFE0: "downstream-field-helper",
    0x49D210: "downstream-field-helper",
    0x4948E0: "downstream-field-helper",
}


def scan(data: bytes, *, expected_sha: str = BUILD_SHA) -> dict:
    digest = hashlib.sha256(data).hexdigest().upper()
    if digest != expected_sha.upper():
        raise ValueError("executable-sha-mismatch")
    sections = _sections(data)
    functions = _runtime_functions(data, sections)
    owners = [(begin, end, unwind) for begin, end, unwind in functions
              if begin <= PRODUCER_RVA < end]
    if len(owners) != 1:
        raise ValueError("cast-producer-unwind-owner-not-unique")
    begin, end, unwind = owners[0]
    if begin != PRODUCER_RVA or end - begin > 0x1000:
        raise ValueError("cast-producer-unwind-range-unexpected")
    text_rva, text_at, text_size = sections[".text"]
    if not text_rva <= begin < end <= text_rva + text_size:
        raise ValueError("cast-producer-outside-text")
    body = data[text_at + begin - text_rva:text_at + end - text_rva]
    calls = []
    for offset in range(len(body) - 4):
        if body[offset] != 0xE8:
            continue
        displacement = int.from_bytes(body[offset + 1:offset + 5], "little", signed=True)
        source = begin + offset
        target = source + 5 + displacement
        if target in KNOWN_TARGETS:
            calls.append({
                "sourceRva": f"0x{source:X}",
                "targetRva": f"0x{target:X}",
                "targetRole": KNOWN_TARGETS[target],
                "encodedBytes": body[offset:offset + 5].hex().upper(),
                "instructionBoundaryVerified": False,
            })
    return {
        "schemaVersion": 1,
        "evidenceKind": "offline-cast-owner-direct-call-candidates/1",
        "executableSha256": digest,
        "producerRva": f"0x{PRODUCER_RVA:X}",
        "producerUnwindRange": {
            "beginRva": f"0x{begin:X}",
            "endRvaExclusive": f"0x{end:X}",
            "unwindInfoRva": f"0x{unwind:X}",
        },
        "calls": calls,
        "qualification": "bounded-opcode-candidates-require-independent-instruction-decoding",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = scan(args.exe.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
