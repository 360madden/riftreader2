"""Bounded passive snapshots of candidate player ability maps."""
import math
import struct

_MAX = 0x7FFFFFFFFFFF


def _ptr(value, length=8):
    return type(value) is int and value >= 0x10000 and value % 8 == 0 and value + length - 1 <= _MAX


def _float(raw):
    value = struct.unpack('<f', raw)[0]
    return value if math.isfinite(value) else None


def read_player_ability_maps(read_ranges, *, context, clock_root_address, max_entries=512):
    """Observe raw maps; the caller must pin process, player and context identity.

    read_ranges(name, [(address, length), ...]) returns {address: bytes}.
    A candidate is not a learned ability, API cooldown or atomic snapshot.
    """
    def unavailable(reason):
        return {'status': 'unavailable', 'reason': reason, 'maps': []}

    if (not callable(read_ranges) or not _ptr(context, 0x260)
            or not _ptr(clock_root_address) or type(max_entries) is not int
            or not 1 <= max_entries <= 512):
        return unavailable('invalid arguments')
    observed = {}

    def read(name, ranges, remember=True):
        result = {}
        for first in range(0, len(ranges), 128):
            batch = ranges[first:first + 128]
            data = read_ranges(name, batch)
            if not isinstance(data, dict):
                raise ValueError('invalid read result')
            for address, size in batch:
                raw = data.get(address)
                if not isinstance(raw, bytes) or len(raw) != size:
                    raise ValueError('missing or short read')
                if remember:
                    old = observed.get((address, size))
                    if old is not None and old != raw:
                        raise ValueError('changed during read')
                    observed[(address, size)] = raw
                result[address] = raw
        return result

    try:
        roots = read('ability-map-roots', [(context + 0x1c0, 32),
                                            (context + 0x240, 32), (clock_root_address, 8)])
        clock = int.from_bytes(roots[clock_root_address], 'little')
        if not _ptr(clock, 0x1c):
            return unavailable('invalid clock pointer')
        clock_before = _float(read('ability-map-clock', [(clock + 0x18, 4)], False)[clock + 0x18])
        if clock_before is None:
            return unavailable('nonfinite clock')
        maps = []
        total = 0
        for offset, expected_stride in ((0x1c0, 0x28), (0x240, 0x18)):
            base, stride, buckets, count = struct.unpack('<QQQQ', roots[context + offset])
            if (stride != expected_stride or buckets > 4096 or count > max_entries
                    or total + count > max_entries or (not buckets and (base or count))
                    or (buckets and (not _ptr(base, (buckets - 1) * stride + 24)))):
                return unavailable('invalid map header or budget')
            total += count
            head_addresses = [base + i * stride for i in range(buckets)]
            heads = read('ability-map-heads', [(a, 24) for a in head_addresses])
            seen = set()
            entries = []
            pending = []

            def add(address, raw):
                if address in seen:
                    raise ValueError('duplicate or cyclic node')
                seen.add(address)
                if len(seen) > count or len(seen) > max_entries:
                    raise ValueError('node count exceeded')
                key = struct.unpack_from('<I', raw, 8)[0]
                v1, v2 = raw[16:20], raw[20:24]
                entries.append({'address': address, 'key': key,
                                'value': _float(v1), 'valueRawHex': v1.hex(),
                                'secondary': _float(v2), 'secondaryRawHex': v2.hex()})

            for address in head_addresses:
                raw = heads[address]
                link = int.from_bytes(raw[:8], 'little')
                if not link & 1:
                    add(address, raw)
                nxt = link & ~1
                if nxt:
                    if not _ptr(nxt, 24):
                        raise ValueError('invalid chain pointer')
                    pending.append(nxt)
            while pending:
                if len(pending) > count or len(pending) + len(seen) > count:
                    raise ValueError('chain budget exceeded')
                if len(set(pending)) != len(pending) or any(a in seen for a in pending):
                    raise ValueError('duplicate or cyclic chain')
                nodes = read('ability-map-chain', [(a, 24) for a in pending])
                nxt_round = []
                for address in pending:
                    raw = nodes[address]
                    add(address, raw)
                    nxt = int.from_bytes(raw[:8], 'little') & ~1
                    if nxt:
                        if not _ptr(nxt, 24):
                            raise ValueError('invalid chain pointer')
                        nxt_round.append(nxt)
                pending = nxt_round
            if len(entries) != count:
                return unavailable('map entry count mismatch')
            maps.append({'offset': offset, 'bucketBase': base, 'stride': stride,
                         'bucketCount': buckets, 'entryCount': count, 'entries': entries})
        original = list(observed.items())
        for first in range(0, len(original), 128):
            batch = original[first:first + 128]
            current = read('resolver_verify', [(a, size) for ((a, size), _) in batch], False)
            if any(current[a] != raw for ((a, _), raw) in batch):
                return unavailable('map snapshot changed')
        clock_after = _float(read('resolver_verify', [(clock + 0x18, 4)], False)[clock + 0x18])
        if clock_after is None or clock_after < clock_before:
            return unavailable('clock unavailable or moved backward')
        if read('resolver_verify', [(clock_root_address, 8)], False)[clock_root_address] != roots[clock_root_address]:
            return unavailable('clock root changed')
        return {'status': 'candidate', 'qualification': 'raw candidates', 'maps': maps,
                'clockPointer': clock, 'clockBefore': clock_before, 'clockAfter': clock_after}
    except Exception:
        return unavailable('map read failed or invalid traversal')
