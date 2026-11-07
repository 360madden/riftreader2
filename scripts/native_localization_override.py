"""Read-only candidates from the exact-build localization override cache."""
import struct

_MAX = 0x7fffffffffff


def _ptr(a):
    return type(a) is int and 0x10000 <= a <= _MAX and a % 8 == 0


def read_localization_override(read_ranges, *, module_base, module_size, keys, key_hash, executable_sha256,
                               max_chain_nodes=128):
    """Inspect requested cache keys; misses do not establish translation absence."""
    result = {'status': 'partial', 'reason': None, 'scope': 'requested-keys',
              'entries': [], 'missingKeys': [], 'fallback_resolved': False,
              'inventory': {'visited_heads': 0, 'visited_chain_nodes': 0}}
    consumed = {}
    class Stop(Exception):
        pass
    def read(name, ranges, verify=False):
        try:
            values = read_ranges(name, ranges)
            for a, n in ranges:
                data = values[a]
                if not isinstance(data, bytes) or len(data) != n:
                    raise ValueError('short read')
                if not verify:
                    if a in consumed and consumed[a] != data:
                        raise Stop('changed_during_walk')
                    consumed[a] = data
            return values
        except Stop:
            raise
        except Exception as exc:
            raise Stop('read_failed: ' + type(exc).__name__) from exc
    def q(address):
        if not _ptr(address) or address > _MAX - 7:
            raise Stop('invalid_pointer')
        return struct.unpack('<Q', read('override_pointer', [(address, 8)])[address])[0]
    try:
        if not isinstance(executable_sha256, str) or executable_sha256.upper() != '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8':
            raise Stop('unsupported_build')
        if not _ptr(module_base) or type(module_size) is not int or module_size <= 0x3484007 or module_base + module_size - 1 > _MAX:
            raise Stop('invalid_module')
        if not isinstance(keys, (list, tuple)) or not 1 <= len(keys) <= 8 or any(type(k) is not int or not 0 <= k <= 0xffffffff for k in keys) or len(set(keys)) != len(keys):
            raise Stop('invalid_keys')
        if type(max_chain_nodes) is not int or not 1 <= max_chain_nodes <= 128:
            raise Stop('invalid_bounds')
        manager = q(module_base + 0x33623e8)
        if not _ptr(manager): raise Stop('invalid_manager')
        manager_state = read('override_manager_state', [(manager, 8)])[manager]
        mode, locale = manager_state[0], struct.unpack_from('<i', manager_state, 4)[0]
        wrapper = q(manager + 0x98)
        if not _ptr(wrapper): raise Stop('invalid_wrapper')
        wrapper_data = read('override_wrapper', [(wrapper, 16)])[wrapper]
        vtable, inner = struct.unpack('<QQ', wrapper_data)
        if vtable != module_base + 0x26c1ea8 or q(vtable) != module_base + 0x7d3230:
            raise Stop('provider_mismatch')
        if not _ptr(inner) or inner > _MAX - 0x47: raise Stop('invalid_inner')
        h = inner + 0x28
        base, stride, count, entry_count = struct.unpack('<QQQQ', read('override_header', [(h, 32)])[h])
        result['context'] = {'manager': manager, 'wrapper': wrapper, 'vtable': vtable,
                             'method': module_base + 0x7d3230, 'inner': inner, 'mode': mode, 'locale': locale}
        result['header'] = {'address': h, 'bucket_base': base, 'stride': stride,
                            'count': count, 'entry_count': entry_count}
        if stride != 24 or count > 4096 or entry_count > 64:
            raise Stop('invalid_header')
        if count == 0:
            if base != 0 or entry_count != 0: raise Stop('invalid_header')
            heads = {}
        else:
            if not _ptr(base) or base + count * stride - 1 > _MAX: raise Stop('invalid_header')
            try:
                heads = {key: base + (key_hash(key) % count) * stride for key in keys}
            except Exception as exc:
                raise Stop('hash_failed: ' + type(exc).__name__) from exc
        found = {}
        if heads:
            values = read('override_heads', [(a, 24) for a in dict.fromkeys(heads.values())])
            frontier = [(k, a, values[a], True, frozenset()) for k, a in heads.items()]
        else:
            frontier = []
        while frontier:
            pending = []
            for key, address, data, head, seen in frontier:
                if address in seen: raise Stop('chain_cycle')
                seen = seen | {address}
                result['inventory']['visited_heads' if head else 'visited_chain_nodes'] += 1
                link = struct.unpack_from('<Q', data)[0]
                if (not head or not link & 1) and struct.unpack_from('<I', data, 8)[0] == key:
                    holder = struct.unpack_from('<Q', data, 16)[0]
                    if holder and not _ptr(holder): raise Stop('invalid_holder')
                    found[key] = {'key': key, 'node_address': address, 'raw_node': data.hex(),
                                  'holder_address': holder, 'result_pointer': None, 'type_verified': False}
                    continue
                next_address = link & ~1
                if next_address:
                    if not _ptr(next_address) or next_address > _MAX - 23: raise Stop('invalid_chain_pointer')
                    if len(seen) - 1 >= max_chain_nodes: raise Stop('chain_budget')
                    pending.append((key, next_address, seen))
            if pending:
                values = read('override_chain', [(a, 24) for a in dict.fromkeys(a for _, a, _ in pending)])
                frontier = [(key, a, values[a], False, seen) for key, a, seen in pending]
            else:
                frontier = []
        def check_type(obj, object_vt_rva, getter_rva, descriptor_rva, descriptor_vt_rva, descriptor_getter_rva, known_vtable=None):
            if (q(obj) if known_vtable is None else known_vtable) != module_base + object_vt_rva:
                raise Stop('type_fingerprint_mismatch')
            if q(module_base + object_vt_rva + 0x40) != module_base + getter_rva:
                raise Stop('type_fingerprint_mismatch')
            if q(module_base + descriptor_rva) != module_base + descriptor_vt_rva:
                raise Stop('descriptor_uninitialized_or_mismatch')
            if q(module_base + descriptor_vt_rva + 8) != module_base + descriptor_getter_rva:
                raise Stop('type_fingerprint_mismatch')
        def text_at(address):
            if type(address) is not int or address < 0x10000 or address > _MAX or address % 2:
                raise Stop('invalid_text_pointer')
            length = min(256, 4096 - (address & 0xfff)) & ~1
            try:
                raw = read_ranges('override_text', [(address, length)])[address]
                if not isinstance(raw, bytes) or len(raw) != length:
                    raise ValueError('short read')
            except Exception as exc:
                raise Stop('read_failed: ' + type(exc).__name__) from exc
            end = next ( (i for i in range(0, length, 2) if raw[i:i+2] == b'\0\0'), None)
            if end is None: raise Stop('unterminated_text')
            anchored = raw[:end+2]
            if address in consumed and consumed[address] != anchored: raise Stop('changed_during_walk')
            consumed[address] = anchored
            try: return raw[:end].decode('utf-16-le', errors='strict')
            except UnicodeError as exc: raise Stop('invalid_utf16') from exc
        for row in found.values():
            holder = row['holder_address']
            if holder:
                obj = q(holder + 0x18)
                row['result_pointer'] = obj
                if obj:
                    if not _ptr(obj) or obj > _MAX - 0x47: raise Stop('invalid_result')
                    raw = read('override_result', [(obj, 0x48)])[obj]
                    vt = struct.unpack_from('<Q', raw)[0]
                    check_type(obj, 0x295dc10, 0x1a4faf0, 0x3484000, 0x2963030, 0x1a779e0, vt)
                    row.update(raw_result=raw.hex(), result_vtable=vt, result_vtable_rva=0x295dc10,
                               type_getter=module_base+0x1a4faf0, type_getter_rva=0x1a4faf0,
                               type_verified=True, candidate_text=None)
                    root = struct.unpack_from('<Q', raw, 0x28)[0]
                    count = struct.unpack_from('<Q', raw, 0x40)[0]
                    if not count or not _ptr(root): raise Stop('tree_unavailable')
                    found_node = None
                    for target in dict.fromkeys((locale, 1)):
                        current, seen = root, set()
                        while current:
                            if not _ptr(current) or current in seen or len(seen) >= 64: raise Stop('invalid_tree_or_cycle')
                            seen.add(current)
                            node = read('override_locale_tree', [(current, 48)])[current]
                            left, right, node_key, child = struct.unpack_from('<QQi4xQ', node, 16)
                            if node_key == target:
                                found_node = (current, child, target)
                                break
                            current = left if target < node_key else right
                        if found_node: break
                    if found_node:
                        node_address, child, locale_found = found_node
                        if not _ptr(child): raise Stop('invalid_child')
                        check_type(child, 0x2804120, 0x173c790, 0x3420930, 0x2820340, 0x177ce30)
                        fields = read('override_text_fields', [(child+0x30, 16)])[child+0x30]
                        first, second = struct.unpack('<QQ', fields)
                        text_ptr = first if mode else second
                        text = text_at(text_ptr)
                        if not text and text_ptr != first: text_ptr, text = first, text_at(first)
                        row.update(locale_found=locale_found, tree_node=node_address, child_address=child,
                                   child_type_verified=True, text_pointer=text_ptr, candidate_text=text)
        items = list(consumed.items())
        for i in range(0, len(items), 128):
            batch = items[i:i+128]
            values = read('resolver_verify', [(a, len(data)) for a, data in batch], verify=True)
            if any(values[a] != data for a, data in batch): raise Stop('changed_during_walk')
        result.update(status='complete', entries=[found[k] for k in keys if k in found],
                      missingKeys=[k for k in keys if k not in found])
    except Stop as exc:
        result['reason'] = str(exc)
    return result
