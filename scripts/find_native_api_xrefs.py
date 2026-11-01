"""Find candidate RIFT Lua API field-key references in an offline PE64 image.

Read-only static evidence: a RIP-relative LEA opcode pattern is a candidate
xref until instruction boundaries and field semantics are independently checked.
This does not open a game process, run RIFT, or promote a live pointer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_FIELDS = 32
SHA_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
FIELD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,63}\Z")


def _unpack(data: bytes, format_: str, offset: int) -> tuple:
    size = struct.calcsize(format_)
    if offset < 0 or offset + size > len(data):
        raise ValueError("pe-header-truncated")
    return struct.unpack_from(format_, data, offset)


def _sections(data: bytes) -> dict[str, tuple[int, int, int]]:
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise ValueError("pe-dos-signature-invalid")
    pe = _unpack(data, "<I", 0x3C)[0]
    if pe < 0x40 or pe > 0x100000 or pe + 24 > len(data):
        raise ValueError("pe-header-offset-invalid")
    if data[pe:pe + 4] != b"PE\x00\x00":
        raise ValueError("pe-signature-invalid")
    machine, count = _unpack(data, "<HH", pe + 4)
    if machine != 0x8664:
        raise ValueError("pe-not-amd64")
    if not 1 <= count <= 96:
        raise ValueError("pe-section-count-invalid")
    opt_bytes = _unpack(data, "<H", pe + 20)[0]
    if not 112 <= opt_bytes <= 4096:
        raise ValueError("pe-optional-size-invalid")
    if _unpack(data, "<H", pe + 24)[0] != 0x20B:
        raise ValueError("pe-not-pe32plus")
    table = pe + 24 + opt_bytes
    result: dict[str, tuple[int, int, int]] = {}
    for index in range(count):
        item = table + index * 40
        if item + 40 > len(data):
            raise ValueError("pe-section-table-truncated")
        name = data[item:item + 8].rstrip(b"\x00").decode("ascii")
        _vsize, rva, raw_size, raw_at = _unpack(data, "<IIII", item + 8)
        if raw_at > len(data) or raw_size > len(data) - raw_at:
            raise ValueError("pe-section-outside-file")
        if name in result:
            raise ValueError("pe-section-duplicate")
        result[name] = (rva, raw_at, raw_size)
    if ".text" not in result or ".rdata" not in result:
        raise ValueError("pe-required-section-missing")
    return result


def _valid_field(name: str) -> bool:
    return bool(FIELD_RE.fullmatch(name))


def scan_image(
    data: bytes, expected_sha: str, fields: list[str],
    start_rva: int = 0, end_rva: int = 0x100000000,
) -> dict:
    """Return literal matches and candidate RIP-relative LEA xrefs only."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("executable-too-large")
    if not SHA_RE.fullmatch(expected_sha):
        raise ValueError("expected-sha-invalid")
    sha = hashlib.sha256(data).hexdigest().upper()
    if sha != expected_sha.upper():
        raise ValueError("executable-sha-mismatch")
    if not fields or len(fields) > MAX_FIELDS or len(set(fields)) != len(fields):
        raise ValueError("invalid-field-count-or-duplicate")
    if not all(_valid_field(f) for f in fields):
        raise ValueError("invalid-field-name")
    if not 0 <= start_rva < end_rva <= 0x100000000:
        raise ValueError("invalid-rva-scope")

    sections = _sections(data)
    rdata_rva, rdata_at, rdata_size = sections[".rdata"]
    rdata = data[rdata_at:rdata_at + rdata_size]
    literals: dict[str, list[int]] = {}
    by_target: dict[int, list[str]] = {}
    for field in fields:
        needle = field.encode("ascii") + b"\x00"
        at = 0
        results: list[int] = []
        while True:
            found = rdata.find(needle, at)
            if found < 0:
                break
            at = found + 1
            previous = rdata[found - 1] if found else 0
            if previous == 95 or 48 <= previous <= 57 or 65 <= previous <= 90 or 97 <= previous <= 122:
                continue  # Avoid matching a suffix of a longer identifier.
            target = rdata_rva + found
            results.append(target)
            by_target.setdefault(target, []).append(field)
            if len(results) > 1024:
                raise ValueError("too-many-field-literals")
        literals[field] = results

    text_rva, text_at, text_size = sections[".text"]
    code = data[text_at:text_at + text_size]
    refs: list[dict] = []
    at = 0
    while True:
        found = code.find(b"\x8D", at)
        if found < 0:
            break
        at = found + 1
        if found + 6 > len(code) or code[found + 1] & 0xC7 != 0x05:
            continue
        displacement = struct.unpack_from("<i", code, found + 2)[0]
        target = text_rva + found + 6 + displacement
        if target not in by_target:
            continue
        rex = found > 0 and 0x40 <= code[found - 1] <= 0x4F
        instruction_at = found - int(rex)
        instruction_rva = text_rva + instruction_at
        if not start_rva <= instruction_rva < end_rva:
            continue
        encoded = code[instruction_at:found + 6].hex()
        for field in by_target[target]:
            refs.append({
                "field": field,
                "fieldRva": f"0x{target:X}",
                "instructionRva": f"0x{instruction_rva:X}",
                "instructionBytes": encoded,
            })
    refs.sort(key=lambda x: (int(x["instructionRva"], 16), x["field"]))
    return {
        "schemaVersion": 1,
        "evidenceKind": "offline-pe-rip-lea-field-candidates/1",
        "executableSha256": sha,
        "fileBytes": len(data),
        "fields": [{"name": f, "literalRvas": [f"0x{v:X}" for v in literals[f]]} for f in fields],
        "references": refs,
        "scopeStartRva": f"0x{start_rva:X}",
        "scopeEndRvaExclusive": f"0x{end_rva:X}",
        "qualification": "static-opcode-candidate-only-not-function-or-live-pointer-proof",
        "limitations": "RIP-relative LEA byte patterns only; misses other encoding forms and may include false instruction boundaries.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True, help="Existing offline PE64 file")
    parser.add_argument("--sha256", required=True, help="Exact 64-hex expected file SHA-256")
    parser.add_argument("--fields", nargs="+", required=True, help="Exact Lua field keys")
    parser.add_argument("--start-rva", type=lambda x: int(x, 0), default=0)
    parser.add_argument("--end-rva", type=lambda x: int(x, 0), default=0x100000000)
    args = parser.parse_args()
    if not args.exe.is_file() or args.exe.stat().st_size > MAX_FILE_BYTES:
        parser.error("offline-executable-missing-or-too-large")
    try:
        result = scan_image(
            args.exe.read_bytes(), args.sha256, args.fields,
            args.start_rva, args.end_rva,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
