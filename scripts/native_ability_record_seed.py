"""Passive, bounded raw seeds; no native type or ownership is established."""
import struct

_MAX = 0x7FFFFFFFFFFF
_PROFILE_SHA = "1935a05c9db6d468e34e0055014a4a99c1b5afceb1695884e24600f5c20a4be8"
_RECORD = (0x28A08C0, 0x1899BF0, 0x344A6B0, 0x28A9C38, 0x18C06C0, 0x51)
_CHILD = (0x27F24F8, 0x170C5D0, 0x3417970, 0x2802E40, 0x17361E0, 0x1E17)


def _address(value, size=1, alignment=8):
    return (type(value) is int and value >= 0x10000 and value % alignment == 0
            and value + size - 1 <= _MAX)


def read_ability_record_seeds(read_ranges, *, entries, module_base, module_size, build_sha, key_hash, max_records=8):
    """Inspect selected cache entries; caller pins process/build and provides fresh verification.

    The callback returns address-to-bytes mappings and must acquire a fresh phase
    for ``resolver_verify``. Sequential snapshots cannot rule out ABA or reuse.
    """
    if (type(max_records) is not int or not 1 <= max_records <= 8
            or not _address(module_base, alignment=1) or type(module_size) is not int
            or module_size <= 0 or module_base + module_size - 1 > _MAX):
        raise ValueError("invalid bounds")
    if not isinstance(build_sha, str) or build_sha.lower() != _PROFILE_SHA:
        raise ValueError("unsupported_build_sha")
    if module_size <= max(_RECORD[2], _CHILD[2], _RECORD[3] + 8, _CHILD[3] + 8) + 8:
        raise ValueError("module_too_small_for_profile")
    if not callable(key_hash):
        raise ValueError("invalid_key_hash")
    selected = [e for e in entries if e.get("result_pointer")][:max_records]
    records = []
    consumed = []

    def read(row, address, size, alignment=8):
        if not _address(address, size, alignment):
            raise ValueError("noncanonical_or_unaligned_address")
        try:
            value = read_ranges("ability_seed", [(address, size)])[address]
            if not isinstance(value, bytes) or len(value) != size:
                raise ValueError("short read")
        except Exception as exc:
            raise ValueError("read_failed: " + type(exc).__name__) from exc
        consumed.append((row, address, value))
        return value

    def qword(row, address):
        return struct.unpack("<Q", read(row, address, 8))[0]

    def getter(row, vtable):
        if not module_base <= vtable <= module_base + module_size - 0x48:
            raise ValueError("vtable_outside_module")
        target = qword(row, vtable + 0x40)
        if not module_base <= target < module_base + module_size:
            raise ValueError("getter_outside_module")
        return target - module_base

    # Prewarm dependent pages in three bounded batches. These bytes only guide
    # further prefetches; the ordinary reads below anchor every consumed field.
    # A bad optional row must not prevent the other rows from being inspected.
    def prefetch(ranges):
        ranges = list(dict.fromkeys(ranges))
        if not ranges:
            return {}
        try:
            return read_ranges("ability_prewarm", ranges)
        except Exception:
            return {}

    def value(values, address, size):
        data = values.get(address)
        return data if isinstance(data, bytes) and len(data) == size else None

    stage1_ranges = [(module_base + profile[2], 8) for profile in (_RECORD, _CHILD)]
    stage1_ranges += [(module_base + profile[3] + 8, 8) for profile in (_RECORD, _CHILD)]
    for entry in selected:
        slot, record = entry.get("result_slot_address"), entry.get("result_pointer")
        node = entry.get("node_address")
        if _address(node, 24):
            stage1_ranges.append((node + 8, 16))
        if _address(slot, 8) and _address(record, 0x960):
            stage1_ranges.extend(( (slot, 8), (record, 8),
                                  (record + 0x8e0, 8), (record + 0x958, 8) ))
    first = prefetch(stage1_ranges)
    valid = []
    stage2_ranges = []
    for entry in selected:
        slot, record = entry.get("result_slot_address"), entry.get("result_pointer")
        if not _address(slot, 8) or not _address(record, 0x960):
            continue
        node, holder = entry.get("node_address"), entry.get("holder_address")
        if not _address(node, 24) or not _address(holder, 0x20) or slot != holder + 0x18:
            continue
        binding = value(first, node + 8, 16)
        try:
            key_bytes = bytes.fromhex(entry.get("raw_key"))
        except (TypeError, ValueError):
            continue
        if (len(key_bytes) != 8 or type(entry.get("selector")) is not int
                or struct.unpack_from("<H", key_bytes)[0] != entry["selector"]
                or type(entry.get("key")) is not int
                or struct.unpack_from("<I", key_bytes, 4)[0] != entry["key"]
                or binding is None or binding[:8] != key_bytes
                or struct.unpack_from("<Q", binding, 8)[0] != holder):
            continue
        slot_data, vt_data, child_data = (value(first, slot, 8), value(first, record, 8),
                                           value(first, record + 0x8e0, 8))
        if not slot_data or not vt_data or not child_data or struct.unpack("<Q", slot_data)[0] != record:
            continue
        vt, child = struct.unpack("<Q", vt_data)[0], struct.unpack("<Q", child_data)[0]
        if module_base <= vt <= module_base + module_size - 0x48 and _address(vt + 0x40, 8):
            stage2_ranges.append((vt + 0x40, 8))
        secondary_data = value(first, record + 0x958, 8)
        secondary = struct.unpack("<Q", secondary_data)[0] if secondary_data else 0
        for candidate in (child, secondary):
            if _address(candidate, 0x28):
                stage2_ranges.append((candidate, 0x28))
                valid.append(candidate)
    second = prefetch(stage2_ranges)
    stage3_ranges = []
    for child in valid:
        data = value(second, child, 0x28)
        if data is None:
            continue
        vt = struct.unpack_from("<Q", data)[0]
        pointer = struct.unpack_from("<Q", data, 0x20)[0]
        if module_base <= vt <= module_base + module_size - 0x48 and _address(vt + 0x40, 8):
            stage3_ranges.append((vt + 0x40, 8))
        if _address(pointer, 2, 2):
            stage3_ranges.append((pointer, min(256, 4096 - (pointer & 0xfff)) & ~1))
    prefetch(stage3_ranges)

    def fingerprint(row, vtable, getter_rva, profile):
        vt, getter_rva_expected, descriptor, desc_vt, desc_getter, code = profile
        if vtable != module_base + vt or getter_rva != getter_rva_expected:
            raise ValueError("object_fingerprint_mismatch")
        descriptor_vtable = qword(row, module_base + descriptor)
        if descriptor_vtable != module_base + desc_vt:
            raise ValueError("descriptor_uninitialized_or_mismatch")
        if qword(row, descriptor_vtable + 8) != module_base + desc_getter:
            raise ValueError("descriptor_getter_mismatch")
        return code

    for entry in selected:
        row = {"key": entry.get("key"), "node_address": entry.get("node_address"),
               "result_slot_address": entry.get("result_slot_address"),
               "record_address": entry.get("result_pointer"), "status": "unavailable",
               "reason": None, "record_type_verified": False, "child_type_verified": False,
               "fallbackNameCandidate": None, "fullNewIdCandidate": None}
        records.append(row)
        try:
            slot = row["result_slot_address"]
            record = row["record_address"]
            node = row["node_address"]
            raw_key = entry.get("raw_key")
            try:
                key_bytes = bytes.fromhex(raw_key)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_cache_key") from exc
            if (len(key_bytes) != 8 or type(entry.get("selector")) is not int
                    or struct.unpack_from("<H", key_bytes)[0] != entry["selector"]
                    or type(entry.get("key")) is not int
                    or struct.unpack_from("<I", key_bytes, 4)[0] != entry["key"]):
                raise ValueError("invalid_cache_key")
            holder = entry.get("holder_address")
            if not _address(holder, 0x20) or not _address(node, 24) or slot != holder + 0x18:
                raise ValueError("invalid_cache_binding")
            binding = read(row, node + 8, 16)
            if binding[:8] != key_bytes or struct.unpack_from("<Q", binding, 8)[0] != holder:
                raise ValueError("stale_cache_binding")
            if qword(row, slot) != record:
                raise ValueError("stale_result_slot")
            if not _address(record, 0x960):
                raise ValueError("invalid_record_pointer")
            vtable = qword(row, record)
            row["record_vtable"] = vtable
            row["record_getter_rva"] = getter(row, vtable)
            child = qword(row, record + 0x8e0)
            row["child_address"] = child
            row["raw_958"] = qword(row, record + 0x958)
            row["record_type"] = fingerprint(row, vtable, row["record_getter_rva"], _RECORD)
            row["record_type_verified"] = True
            def child_key(address, prefix):
                if not address:
                    row[prefix + "_absent"] = True
                    return 0
                if not _address(address, 0x28):
                    raise ValueError("invalid_" + prefix + "_pointer")
                child_vtable = qword(row, address)
                row[prefix + "_vtable"] = child_vtable
                child_getter = getter(row, child_vtable)
                row[prefix + "_getter_rva"] = child_getter
                row[prefix + "_type"] = fingerprint(row, child_vtable, child_getter, _CHILD)
                row[prefix + "_type_verified"] = True
                key = struct.unpack("<I", read(row, address + 0x18, 4, 4))[0]
                row[prefix + "_localization_key_candidate"] = key
                try:
                    result = key_hash(key)
                    if type(result) is not int:
                        raise ValueError("noninteger hash")
                    return result
                except Exception as exc:
                    raise ValueError("key_hash_failed") from exc

            term1 = child_key(child, "child")
            term2 = child_key(row["raw_958"], "secondary_child")
            row["fullNewIdCandidate"] = "A" + format((entry["key"] << 32) | ((term1 + term2) & 0xffffffff), "016X")
            if not child:
                row["reason"] = "null_child"
                continue
            row["localization_key_candidate"] = row["child_localization_key_candidate"]
            pointer = qword(row, child + 0x20)
            row["fallback_string_address"] = pointer
            if not pointer:
                raise ValueError("null_string_pointer")
            if not _address(pointer, 2, 2):
                raise ValueError("invalid_string_pointer")
            length = min(256, 4096 - (pointer & 0xfff)) & ~1
            raw = read(row, pointer, length, 2)
            end = next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), None)
            if end is None:
                raise ValueError("unterminated_string")
            consumed[-1] = (row, pointer, raw[:end + 2])
            try:
                row["fallbackNameCandidate"] = raw[:end].decode("utf-16-le", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid_utf16") from exc
            row["status"] = "candidate"
        except ValueError as exc:
            row["reason"] = str(exc)

    # One final verification phase. Discard candidate values on changes or failure.
    try:
        for start in range(0, len(consumed), 128):
            batch = consumed[start:start + 128]
            values = read_ranges("resolver_verify", [(address, len(data)) for _, address, data in batch])
            for row, address, data in batch:
                if values.get(address) != data:
                    row["status"] = "unavailable"
                    row["reason"] = "changed_during_read"
                    row["fallbackNameCandidate"] = None
                    row["fullNewIdCandidate"] = None
                    row["secondary_child_type_verified"] = False
                    row["record_type_verified"] = row["child_type_verified"] = False
    except Exception:
        for row in records:
            row["status"] = "unavailable"
            row["reason"] = "verification_failed"
            row["fallbackNameCandidate"] = None
            row["fullNewIdCandidate"] = None
            row["secondary_child_type_verified"] = False
            row["record_type_verified"] = row["child_type_verified"] = False
    return records
