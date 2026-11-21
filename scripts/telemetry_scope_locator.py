"""Bounded, read-only relocation of Telemetry Lua frames across private memory regions.

A locator hit is only an address candidate. The caller must independently rescan,
check advancing source frames, native owner, source bytes and replay before success.
"""
from __future__ import annotations

from collections import Counter
import math
import time

CHUNK = 64 * 1024
MAX_SCAN_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 12
MAX_CHECKS = 1024
MAX_ADDR = 0x7FFF_FFFF_FFFF


def discover(reader, *, marker, scan_bytes, validate_at, max_scopes=4,
             max_bytes=MAX_SCAN_BYTES, max_seconds=MAX_SECONDS,
             monotonic=time.monotonic):
    """Return plausible address windows; never assert publisher freshness."""
    if (type(marker) is not bytes or not marker or len(marker) >= CHUNK
            or type(scan_bytes) is not int or scan_bytes < CHUNK
            or scan_bytes > 128 * 1024 * 1024
            or type(max_scopes) is not int or not 1 <= max_scopes <= 8
            or type(max_bytes) is not int or not CHUNK <= max_bytes <= MAX_SCAN_BYTES
            or type(max_seconds) not in (int, float)
            or not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS
            or not callable(validate_at)):
        raise ValueError("telemetry-scope-locator-invalid-budget")
    regions = reader.readable_private_regions()
    if not isinstance(regions, (tuple, list)) or len(regions) > 100000:
        raise ValueError("telemetry-scope-locator-invalid-regions")
    started, last_end = monotonic(), 0
    buckets = Counter()
    scanned, markers, accepted, checks, incomplete = 0, 0, 0, 0, 0
    exhausted = False
    for begin, end in regions:
        if (type(begin) is not int or type(end) is not int
                or begin < 0x10000 or end <= begin or end >= MAX_ADDR
                or begin < last_end):
            raise ValueError("telemetry-scope-locator-invalid-region")
        last_end = end
        address, previous = begin, b""
        while address < end:
            if scanned >= max_bytes or monotonic() - started >= max_seconds or checks >= MAX_CHECKS:
                exhausted = True
                break
            size = min(CHUNK, end - address, max_bytes - scanned)
            if size <= 0:
                exhausted = True
                break
            raw = reader.read(address, size)
            if type(raw) is not bytes or len(raw) > size:
                raise ValueError("telemetry-scope-locator-invalid-read")
            scanned += len(raw)
            if len(raw) != size:
                incomplete += 1
            combined = previous + raw
            cursor = 0
            while checks < MAX_CHECKS:
                hit = combined.find(marker, cursor)
                if hit < 0:
                    break
                cursor = hit + 1
                location = address - len(previous) + hit
                if not begin <= location < end:
                    continue
                markers += 1
                checks += 1
                if validate_at(location):
                    accepted += 1
                    bucket = max(0x10000, location // scan_bytes * scan_bytes)
                    if bucket + scan_bytes < MAX_ADDR:
                        buckets[bucket] += 1
            previous = (raw[-(len(marker) - 1):]
                        if len(raw) == size and len(marker) > 1 else b"")
            address += size
        if exhausted:
            break
    ranked = sorted(buckets, key=lambda address: (-buckets[address], address))
    selected = sorted(ranked[:max_scopes])
    return {
        "status": "scope-locations-candidate" if selected else "unqualified",
        "candidateStartAddresses": [f"0x{address:X}" for address in selected],
        "markerHits": markers, "validatedMarkerCandidates": accepted,
        "scannedBytes": scanned, "shortReads": incomplete,
        "regionCount": len(regions), "searchExhausted": exhausted,
        "candidateScopeCount": len(buckets),
        "searchByteBudget": max_bytes, "searchTimeBudgetSeconds": max_seconds,
        "qualification": ("Bounded map-aware read-only candidate location only; "
                          "the address, publisher freshness, session and native "
                          "agreement require new source-hashed capture/replay.")
    }
