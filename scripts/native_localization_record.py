"""Strict candidate parser for one observed localization serialization shape."""

def parse_localization_record(data):
    """Parse the single locale-1 field shape; field meaning is not qualified."""
    if type(data) is not bytes:
        raise ValueError('bytes required')
    pos = 0
    def uleb():
        nonlocal pos
        value = 0
        for i in range(5):
            if pos >= len(data): raise ValueError('truncated varint')
            b = data[pos]; pos += 1
            if i == 4 and b > 15: raise ValueError('invalid varint')
            value |= (b & 127) << (7*i)
            if not b & 128: return value
        raise ValueError('invalid varint')
    for expected in (0x1e1b, 167, 699, 2, 0x1e1d, 6):
        if uleb() != expected: raise ValueError('unsupported record shape')
    length = uleb()
    if length >= 65536 or pos + length > len(data): raise ValueError('invalid text length')
    try:
        text = data[pos:pos+length].decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('invalid UTF-8') from exc
    pos += length
    if uleb() != 7 or uleb() != 7 or pos != len(data):
        raise ValueError('invalid record ending')
    return {'locale': 1, 'candidate_text': text, 'field_mapping_qualified': False}
