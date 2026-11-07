"""Bounded, passive candidate inventory of one epoch-pinned resolver cache.

The caller owns process identity and provides a read-only exact-range callback.
A complete cache inventory does not establish absence from the unresolved fallback.
"""
import struct

_MAX_BYTES = 2 * 1024 * 1024
_MAX_MATCHES = 512
_MAX_HOPS = 16384
_MAX_ADDRESS = 0x00007FFFFFFFFFFF


def _pointer(value):
    return isinstance(value, int) and 0x10000 <= value <= _MAX_ADDRESS and value % 8 == 0


class SnapshotPageReader:
    """Two sequential page snapshots; verification never reuses first-phase bytes."""
    def __init__(self, read_ranges, max_pages=128):
        if type(max_pages) is not int or not 1 <= max_pages <= 128:
            raise ValueError("invalid page limit")
        self.read_ranges = read_ranges
        self.max_pages = max_pages
        self.pages = {}
        self.verified = None
        self.read_calls = 0

    def __call__(self, name, ranges):
        requested = set()
        for address, length in ranges:
            if type(address) is not int or type(length) is not int or length <= 0 or address < 0x10000 or address + length - 1 > _MAX_ADDRESS:
                raise ValueError("invalid range")
            requested.update(range(address & ~0xfff, ((address + length - 1) & ~0xfff) + 4096, 4096))
        if name == "resolver_verify":
            if self.verified is None:
                self.verified = self._capture("resolver_verify_pages", sorted(self.pages))
            if not requested <= self.verified.keys():
                raise ValueError("verification page not captured")
            source = self.verified
        else:
            if self.verified is not None:
                raise ValueError("forward read after verification")
            missing = requested - self.pages.keys()
            if len(self.pages) + len(missing) > self.max_pages:
                raise ValueError("page budget")
            if missing:
                self.pages.update(self._capture("resolver_snapshot_pages", sorted(missing)))
            source = self.pages
        result = {}
        for address, length in ranges:
            parts = []
            cursor = address
            while cursor < address + length:
                page = cursor & ~0xfff
                size = min(address + length - cursor, 4096 - (cursor - page))
                parts.append(source[page][cursor - page:cursor - page + size])
                cursor += size
            result[address] = b"".join(parts)
        return result

    def _capture(self, name, pages):
        if not pages:
            return {}
        self.read_calls += 1
        values = self.read_ranges(name, [(page, 4096) for page in pages])
        if any(not isinstance(values.get(page), bytes) or len(values[page]) != 4096 for page in pages):
            raise ValueError("short page read")
        return {page: values[page] for page in pages}


def read_resolver_cache(read_ranges, *, collection: int, selector: int,
                        max_buckets: int = 4096, max_chain_nodes: int = 256):
    """Return raw selector-matched candidates and bounded inventory status.

    ``max_chain_nodes`` bounds depth per chain; a separate total-hop cap applies.
    ``complete`` describes this cache walk only, never resolver absence. Unstable
    snapshots discard entries. Read failures and budget limits are explicit.
    """
    result = {"status": "partial", "reason": None, "entries": [],
              "inventory": {"buckets": 0, "available_heads": 0,
                            "chain_nodes": 0, "selector_matches": 0},
              "fallback_resolved": False}
    consumed = []
    total = 0
    chain_pages = {}

    class Stop(Exception):
        pass

    def read(name, ranges, record=True):
        nonlocal total
        output = {}
        for start in range(0, len(ranges), 128):
            batch = ranges[start:start + 128]
            amount = sum(length for _, length in batch)
            if total + amount > _MAX_BYTES:
                raise Stop("byte_budget")
            total += amount
            try:
                values = read_ranges(name, batch)
                for addr, length in batch:
                    data = values[addr]
                    if not isinstance(data, bytes) or len(data) != length:
                        raise ValueError("short read")
                    output[addr] = data
                    if record:
                        consumed.append((addr, data))
            except Exception as exc:
                raise Stop("read_failed: " + type(exc).__name__) from exc
        return output

    def entry(addr, data):
        inv = result["inventory"]
        word = struct.unpack_from("<H", data, 8)[0]
        if word != selector:
            return
        inv["selector_matches"] += 1
        if len(result["entries"]) >= _MAX_MATCHES:
            raise Stop("match_budget")
        holder = struct.unpack_from("<Q", data, 16)[0]
        if holder and (not _pointer(holder) or holder + 0x18 > _MAX_ADDRESS - 7):
            raise Stop("invalid_holder")
        result["entries"].append({"node_address": addr, "raw_key": data[8:16].hex(),
                                  "selector": word, "key": struct.unpack_from("<I", data, 12)[0],
                                  "holder_address": holder, "result_slot_address": holder + 0x18 if holder else None,
                                  "result_pointer": None})

    try:
        if not _pointer(collection) or collection + 0x20 > _MAX_ADDRESS - 31:
            raise Stop("invalid_collection")
        if type(selector) is not int or not 0 <= selector <= 0xffff:
            raise Stop("invalid_selector")
        if type(max_buckets) is not int or not 1 <= max_buckets <= 4096 or type(max_chain_nodes) is not int or not 1 <= max_chain_nodes <= 2048:
            raise Stop("invalid_bounds")
        h = collection + 0x20
        header = read("resolver_header", [(h, 32)])[h]
        base, stride, count, entry_count = struct.unpack("<QQQQ", header)
        result["header"] = {"address": h, "bucket_base": base, "stride": stride, "count": count, "entry_count": entry_count}
        if entry_count > max_buckets + _MAX_HOPS:
            raise Stop("entry_budget")
        if count > max_buckets:
            raise Stop("bucket_budget")
        if stride != 24:
            raise Stop("unsupported_stride")
        if count and (not _pointer(base) or base + count * stride - 1 > _MAX_ADDRESS):
            raise Stop("invalid_bucket_base")
        blocks = [(base + i * stride, min(160, count - i) * stride) for i in range(0, count, 160)]
        data_blocks = read("resolver_buckets", blocks)
        inv = result["inventory"]
        seen_nodes = set()
        frontier = []
        for addr, length in blocks:
            block = data_blocks[addr]
            for offset in range(0, length, stride):
                node_addr = addr + offset
                node = block[offset:offset + stride]
                link = struct.unpack_from("<Q", node)[0]
                inv["buckets"] += 1
                if not link & 1:
                    inv["available_heads"] += 1
                    seen_nodes.add(node_addr)
                    entry(node_addr, node)
                if link & ~1:
                    frontier.append((link & ~1, frozenset()))
        while frontier:
            next_frontier = []
            for start in range(0, len(frontier), 128):
                batch = frontier[start:start + 128]
                for address, seen in batch:
                    if not _pointer(address) or address > _MAX_ADDRESS - 23:
                        raise Stop("invalid_chain_pointer")
                    if address in seen:
                        raise Stop("chain_cycle")
                    if len(seen) >= max_chain_nodes or inv["chain_nodes"] >= _MAX_HOPS:
                        raise Stop("chain_budget")
                if inv["chain_nodes"] + len(batch) > _MAX_HOPS:
                    raise Stop("chain_budget")
                addresses = list(dict.fromkeys(address for address, _ in batch))
                pages = sorted({page for address in addresses
                                for page in (address & ~0xfff, (address + 23) & ~0xfff)
                                if page not in chain_pages})
                if pages:
                    chain_pages.update(read("resolver_chain_pages", [(page, 4096) for page in pages], record=False))
                chains = {}
                for address in addresses:
                    page = address & ~0xfff
                    offset = address - page
                    data = chain_pages[page][offset:offset + 24]
                    if len(data) < 24:
                        data += chain_pages[page + 4096][:24 - len(data)]
                    chains[address] = data
                    consumed.append((address, data))
                for address, seen in batch:
                    if address in seen_nodes:
                        raise Stop("duplicate_node")
                    seen_nodes.add(address)
                    chain = chains[address]
                    inv["chain_nodes"] += 1
                    entry(address, chain)
                    link = struct.unpack_from("<Q", chain)[0] & ~1
                    if link:
                        next_frontier.append((link, seen | {address}))
            frontier = next_frontier
        if len(seen_nodes) != entry_count:
            raise Stop("entry_count_mismatch")
        slots = list(dict.fromkeys(e["result_slot_address"] for e in result["entries"]
                                   if e["result_slot_address"] is not None))
        values = read("resolver_holders", [(address, 8) for address in slots])
        for candidate in result["entries"]:
            slot = candidate["result_slot_address"]
            if slot is not None:
                value = struct.unpack("<Q", values[slot])[0]
                if value and not _pointer(value):
                    raise Stop("invalid_result_pointer")
                candidate["result_pointer"] = value
        result["status"] = "complete"
    except Stop as exc:
        result["reason"] = str(exc)
        result["entries"] = []

    # Check every successfully consumed byte, including partial acquisitions.
    try:
        unique = {}
        for addr, original in consumed:
            if addr in unique and unique[addr] != original:
                raise Stop("changed_during_walk")
            unique[addr] = original
        items = list(unique.items())
        for start in range(0, len(items), 128):
            batch = items[start:start + 128]
            verified = read("resolver_verify", [(addr, len(data)) for addr, data in batch], record=False)
            if any(verified[addr] != original for addr, original in batch):
                raise Stop("changed_during_walk")
    except Stop as exc:
        result["status"] = "partial"
        result["reason"] = str(exc)
        result["entries"] = []
    result["bytes_read"] = total
    return result


def lookup_resolver_cache(read_ranges, *, collection, selector, keys, key_hash, max_chain_nodes=128):
    """Inspect only requested cache keys; misses say nothing about fallback lookup."""
    result = {"status": "partial", "scope": "requested-keys-any-selector" if selector is None else "requested-keys", "reason": None,
              "entries": [], "missingKeys": [], "fallback_resolved": False,
              "inventory": {"visited_heads": 0, "visited_chain_nodes": 0}}
    consumed = {}
    class Stop(Exception):
        pass
    def read(name, ranges, verify=False):
        try:
            values = read_ranges(name, ranges)
            for address, size in ranges:
                data = values[address]
                if not isinstance(data, bytes) or len(data) != size:
                    raise ValueError("short read")
                if not verify:
                    if address in consumed and consumed[address] != data:
                        raise Stop("changed_during_walk")
                    consumed[address] = data
            return values
        except Stop:
            raise
        except Exception as exc:
            raise Stop("read_failed: " + type(exc).__name__) from exc
    try:
        if not _pointer(collection) or collection + 0x20 > _MAX_ADDRESS - 31:
            raise Stop("invalid_collection")
        if selector is not None and (type(selector) is not int or not 0 <= selector <= 0xffff):
            raise Stop("invalid_selector")
        if type(max_chain_nodes) is not int or not 1 <= max_chain_nodes <= 128:
            raise Stop("invalid_bounds")
        if not isinstance(keys, (list, tuple)) or not 1 <= len(keys) <= 8 or any(type(k) is not int or not 0 <= k <= 0xffffffff for k in keys) or len(set(keys)) != len(keys):
            raise Stop("invalid_keys")
        h = collection + 0x20
        base, stride, count, entry_count = struct.unpack("<QQQQ", read("resolver_header", [(h, 32)])[h])
        result["header"] = {"address": h, "bucket_base": base, "stride": stride, "count": count, "entry_count": entry_count}
        if not 1 <= count <= 4096 or stride != 24 or not _pointer(base) or base + count * stride - 1 > _MAX_ADDRESS:
            raise Stop("invalid_header")
        try:
            heads = {key: base + (key_hash(key_hash(key)) % count) * stride for key in keys}
        except Exception as exc:
            raise Stop("hash_failed: " + type(exc).__name__) from exc
        head_data = read("resolver_heads", [(a, 24) for a in dict.fromkeys(heads.values())])
        frontier = [(key, address, head_data[address], True, frozenset()) for key, address in heads.items()]
        found = {key: [] for key in keys}
        while frontier:
            pending = []
            for key, address, data, head, seen in frontier:
                if address in seen:
                    raise Stop("chain_cycle")
                seen = seen | {address}
                if head:
                    result["inventory"]["visited_heads"] += 1
                else:
                    result["inventory"]["visited_chain_nodes"] += 1
                link = struct.unpack_from("<Q", data)[0]
                node_selector = struct.unpack_from("<H", data, 8)[0]
                if (not head or not link & 1) and (selector is None or node_selector == selector) and struct.unpack_from("<I", data, 12)[0] == key:
                    holder = struct.unpack_from("<Q", data, 16)[0]
                    if holder and (not _pointer(holder) or holder + 0x18 > _MAX_ADDRESS - 7):
                        raise Stop("invalid_holder")
                    if sum(map(len, found.values())) >= 256:
                        raise Stop("match_budget")
                    found[key].append({"node_address": address, "raw_key": data[8:16].hex(), "selector": node_selector, "key": key,
                                  "holder_address": holder, "result_slot_address": holder + 0x18 if holder else None, "result_pointer": None})
                    if selector is not None:
                        continue
                next_address = link & ~1
                if next_address:
                    if not _pointer(next_address) or next_address > _MAX_ADDRESS - 23:
                        raise Stop("invalid_chain_pointer")
                    if len(seen) - 1 >= max_chain_nodes:
                        raise Stop("chain_budget")
                    pending.append((key, next_address, seen))
            if pending:
                values = read("resolver_chain", [(a, 24) for a in dict.fromkeys(a for _, a, _ in pending)])
                frontier = [(key, a, values[a], False, seen) for key, a, seen in pending]
            else:
                frontier = []
        slots = list(dict.fromkeys(row["result_slot_address"] for rows in found.values() for row in rows if row["result_slot_address"] is not None))
        if slots:
            values = read("resolver_holders", [(a, 8) for a in slots])
            for row in (row for rows in found.values() for row in rows):
                slot = row["result_slot_address"]
                if slot is not None:
                    value = struct.unpack("<Q", values[slot])[0]
                    if value and not _pointer(value):
                        raise Stop("invalid_result_pointer")
                    row["result_pointer"] = value
        items = list(consumed.items())
        for start in range(0, len(items), 128):
            batch = items[start:start + 128]
            verified = read("resolver_verify", [(a, len(data)) for a, data in batch], verify=True)
            if any(verified[a] != data for a, data in batch):
                raise Stop("changed_during_walk")
        result["entries"] = [row for k in keys for row in found[k]]
        result["missingKeys"] = [k for k in keys if not found[k]]
        result["status"] = "complete"
    except Stop as exc:
        result["reason"] = str(exc)
    return result
