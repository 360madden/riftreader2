"""Read candidate per-thread TLS selections without calling target code."""

_MAX_PTR = 0x7FFFFFFFFFFF


def _number(value, minimum=0, maximum=_MAX_PTR):
    return type(value) is int and minimum <= value <= maximum


def _pointer(value, maximum=_MAX_PTR):
    return _number(value, 0x10000, maximum) and value % 8 == 0


def read_tls_collections(read_ranges, *, threads, tls_index, embedded_collection, process_id):
    """Snapshot x64 TEB identity and TLS slots; caller pins process and thread epochs.

    read_ranges(name, ranges) returns {start_address: bytes}. A candidate is
    an observation per enumerated thread, not identification of the executing thread.
    """
    def unavailable(reason):
        return {"status": "unavailable", "reason": reason, "threads": []}

    if not callable(read_ranges) or not _number(process_id, 1, 0xffffffff):
        return unavailable("invalid process or reader")
    if not _number(tls_index, 0, 1087) or not _pointer(embedded_collection):
        return unavailable("invalid index or embedded collection")
    if not isinstance(threads, list) or not 1 <= len(threads) <= 256:
        return unavailable("invalid thread list")
    ids, tebs = set(), set()
    for thread in threads:
        if not isinstance(thread, dict):
            return unavailable("invalid thread")
        tid, ticks, teb = (thread.get(k) for k in ("threadId", "startUtcTicks", "tebAddress"))
        if (not _number(tid, 1, 0xffffffff) or not isinstance(ticks, str)
                or not ticks.isascii() or not ticks.isdigit() or len(ticks) > 20 or int(ticks) <= 0
                or not _pointer(teb, _MAX_PTR - 0x1788)
                or tid in ids or teb in tebs):
            return unavailable("invalid or duplicate thread identity")
        ids.add(tid)
        tebs.add(teb)

    consumed = {}

    def capture(name, ranges):
        for offset in range(0, len(ranges), 128):
            batch = ranges[offset:offset + 128]
            data = read_ranges(name, batch)
            if not isinstance(data, dict):
                raise ValueError("invalid read result")
            for address, length in batch:
                value = data.get(address)
                if not isinstance(value, bytes) or len(value) != length:
                    raise ValueError("short or missing read")
                if address in consumed and consumed[address] != value:
                    raise ValueError("overlapping read changed")
                consumed[address] = value

    try:
        ranges = []
        for thread in threads:
            teb = thread["tebAddress"]
            ranges.append((teb + 0x30, 0x20))
            ranges.append((teb + (0x1480 + tls_index * 8 if tls_index < 64 else 0x1780), 8))
        capture("tls-teb", ranges)
        expansion = []
        for thread in threads:
            teb = thread["tebAddress"]
            identity = consumed[teb + 0x30]
            if (int.from_bytes(identity[0:8], "little") != teb
                    or int.from_bytes(identity[0x10:0x18], "little") != process_id
                    or int.from_bytes(identity[0x18:0x20], "little") != thread["threadId"]):
                return unavailable("TEB identity mismatch")
            if tls_index >= 64:
                pointer = int.from_bytes(consumed[teb + 0x1780], "little")
                displacement = (tls_index - 64) * 8
                if pointer:
                    if not _pointer(pointer, _MAX_PTR - displacement - 7):
                        return unavailable("invalid expansion pointer")
                    expansion.append((pointer + displacement, 8))
        capture("tls-expansion", expansion)
        rows = []
        for thread in threads:
            teb = thread["tebAddress"]
            if tls_index < 64:
                raw = consumed[teb + 0x1480 + tls_index * 8]
                value = int.from_bytes(raw, "little")
            else:
                pointer = int.from_bytes(consumed[teb + 0x1780], "little")
                value = int.from_bytes(consumed[pointer + (tls_index - 64) * 8], "little") if pointer else 0
            if value and not _pointer(value):
                return unavailable("invalid TLS collection pointer")
            rows.append({"threadId": thread["threadId"], "startUtcTicks": thread["startUtcTicks"],
                         "tebAddress": teb, "tlsValue": value,
                         "selectedCollection": value or embedded_collection,
                         "usesEmbedded": not value or value == embedded_collection})
        original = list(consumed.items())
        for offset in range(0, len(original), 128):
            batch = original[offset:offset + 128]
            data = read_ranges("tls-recheck", [(address, len(value)) for address, value in batch])
            if not isinstance(data, dict) or any(data.get(address) != value for address, value in batch):
                return unavailable("TLS snapshot changed or reread failed")
        return {"status": "candidate", "threads": rows}
    except Exception:
        return unavailable("TLS read failed")
