"""Passive localization layout seeds; neither native types nor names are qualified."""
import struct

MAX_ADDRESS = 0x7fffffffffff


def ptr(v):
    return type(v) is int and 0x10000 <= v <= MAX_ADDRESS and v % 8 == 0


def read_localization_context(read_ranges, *, module_base, module_size, dictionary_mode=False):
    """Acquire raw context without verification; caller must bracket this observation."""
    if not ptr(module_base) or type(module_size) is not int or module_size <= 0x3373770 or module_base + module_size - 1 > MAX_ADDRESS:
        raise ValueError('invalid module')
    def read(name, ranges):
        values = read_ranges(name, ranges)
        for a, n in ranges:
            if not isinstance(values.get(a), bytes) or len(values[a]) != n:
                raise ValueError('short read')
        return values
    addresses = [module_base + 0x33623e8, module_base + 0x3373768]
    roots = read('localization_roots', [(a, 8) for a in addresses])
    manager, provider = (struct.unpack('<Q', roots[a])[0] for a in addresses)
    if not ptr(manager) or (not dictionary_mode and not ptr(provider)) or (provider and not ptr(provider)):
        raise ValueError('null or invalid context root')
    ranges = [(manager, 8), (manager + 0x98, 8)]
    if not dictionary_mode:
        ranges.append((provider + 0x40, 2))
    values = read('localization_context', ranges)
    mode, locale = values[manager][0], struct.unpack_from('<i', values[manager], 4)[0]
    obj = struct.unpack('<Q', values[manager + 0x98])[0]
    if obj != module_base + 0x2f59b20:
        raise ValueError('unavailable provider override')
    vtable = struct.unpack('<Q', read('localization_provider', [(obj, 8)])[obj])[0]
    if vtable != module_base + 0x26c1e90:
        raise ValueError('unavailable provider vtable')
    slot = struct.unpack('<Q', read('localization_provider_slot', [(vtable, 8)])[vtable])[0]
    if slot != module_base + 0x7d1790:
        raise ValueError('unavailable provider slot')
    return {'manager': manager, 'mode': mode, 'locale': locale, 'provider': provider,
            'selector': None if dictionary_mode else struct.unpack('<H', values[provider + 0x40])[0],
            'provider_object': obj, 'provider_vtable': vtable, 'provider_slot': slot}


def read_localization_seeds(read_ranges, *, module_base, module_size, entries, max_records=8, dictionary_mode=False):
    """Return bracketed raw candidates; record and child types remain unverified."""
    result = {'status': 'partial', 'reason': None, 'context': None, 'records': [],
              'type_verified': False, 'dictionary_only': dictionary_mode,
              'apiRouteUnavailable': dictionary_mode}
    consumed = {}
    class Stop(Exception):
        pass
    def read(name, ranges):
        try:
            values = read_ranges(name, ranges)
            for a, n in ranges:
                d = values[a]
                if not isinstance(d, bytes) or len(d) != n:
                    raise ValueError('short read')
                if a in consumed and consumed[a] != d:
                    raise Stop('changed_during_walk')
                consumed[a] = d
            return values
        except Stop:
            raise
        except Exception as exc:
            raise Stop('read_failed: ' + type(exc).__name__) from exc
    def q(a):
        if not ptr(a) or a > MAX_ADDRESS - 7:
            raise Stop('invalid_pointer')
        return struct.unpack('<Q', read('localization_pointer', [(a, 8)])[a])[0]
    def fingerprint(obj):
        v = q(obj)
        if not ptr(v):
            raise Stop('invalid_vtable')
        getter = q(v + 0x40)
        return {'vtable': v, 'vtable_rva': v - module_base if module_base <= v < module_base + module_size else None,
                'getter': getter, 'getter_rva': getter - module_base if module_base <= getter < module_base + module_size else None}
    try:
        if type(max_records) is not int or not 1 <= max_records <= 8 or not isinstance(entries, (list, tuple)) or len(entries) > max_records:
            raise Stop('invalid_bounds')
        try:
            context = read_localization_context(read, module_base=module_base, module_size=module_size, dictionary_mode=dictionary_mode)
        except Stop:
            raise
        except Exception as exc:
            raise Stop('context_unavailable: ' + str(exc)) from exc
        result['context'] = context
        records = []
        for entry in entries:
            address, holder, record = entry.get('node_address'), entry.get('holder_address'), entry.get('result_pointer')
            if not ptr(address) or not ptr(holder) or not ptr(record) or type(entry.get('selector')) is not int or not 0 <= entry['selector'] <= 0xffff or (not dictionary_mode and entry['selector'] != context['selector']):
                raise Stop('invalid_entry')
            data = read('localization_cache_node', [(address, 24)])[address]
            if struct.unpack_from('<H', data, 8)[0] != entry['selector'] or struct.unpack_from('<I', data, 12)[0] != entry.get('key') or struct.unpack_from('<Q', data, 16)[0] != holder or q(holder + 0x18) != record:
                raise Stop('entry_changed')
            record_fp = fingerprint(record)
            root = q(record + 0x28)
            tree_count = q(record + 0x40)
            if not tree_count or not ptr(root):
                raise Stop('tree_unavailable')
            found = None
            for target in dict.fromkeys((context['locale'], 1)):
                current, seen = root, set()
                while current:
                    if not ptr(current) or current in seen or len(seen) >= 64:
                        raise Stop('invalid_tree_or_cycle')
                    seen.add(current)
                    d = read('localization_tree', [(current, 48)])[current]
                    left, right, key, child = struct.unpack_from('<QQi4xQ', d, 16)
                    if target == key:
                        found = (current, child, target)
                        break
                    current = left if target < key else right
                if found:
                    break
            if not found:
                records.append({'key': entry['key'], 'selector': entry['selector'], 'record_address': record, 'record_fingerprint': record_fp,
                                'type_verified': False, 'locale_found': None, 'candidate_text': None})
                continue
            node, child, locale = found
            if not ptr(child):
                raise Stop('invalid_child')
            child_fp = fingerprint(child)
            fields = read('localization_text_fields', [(child + 0x30, 16)])[child + 0x30]
            first, second = struct.unpack('<QQ', fields)
            def text_at(address):
                if type(address) is not int or not 0x10000 <= address <= MAX_ADDRESS or address % 2:
                    raise Stop('invalid_text_pointer')
                length = min(256, 4096 - (address & 0xfff)) & ~1
                try:
                    raw = read_ranges('localization_text', [(address, length)])[address]
                    if not isinstance(raw, bytes) or len(raw) != length:
                        raise ValueError('short read')
                except Exception as exc:
                    raise Stop('read_failed: ' + type(exc).__name__) from exc
                end = next((i for i in range(0, len(raw), 2) if raw[i:i+2] == b'\0\0'), None)
                if end is None:
                    raise Stop('unterminated_text')
                anchored = raw[:end + 2]
                if address in consumed and consumed[address] != anchored:
                    raise Stop('changed_during_walk')
                consumed[address] = anchored
                try:
                    return raw[:end].decode('utf-16-le', errors='strict')
                except UnicodeError as exc:
                    raise Stop('invalid_utf16') from exc
            text_pointer = first if context['mode'] else second
            text = text_at(text_pointer)
            if not text and text_pointer != first:
                text_pointer, text = first, text_at(first)
            records.append({'key': entry['key'], 'selector': entry['selector'], 'record_address': record, 'record_fingerprint': record_fp,
                            'type_verified': False, 'locale_found': locale, 'tree_node': node,
                            'child_address': child, 'child_fingerprint': child_fp,
                            'text_pointer': text_pointer, 'candidate_text': text})
        items = list(consumed.items())
        for i in range(0, len(items), 128):
            batch = items[i:i + 128]
            values = read_ranges('resolver_verify', [(a, len(d)) for a, d in batch])
            if any(values.get(a) != d for a, d in batch):
                raise Stop('changed_during_walk')
        result.update(status='complete', records=records)
    except Exception as exc:
        result['reason'] = str(exc)
    return result
