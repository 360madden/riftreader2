"""Bounded raw capture of the exact-build override provider's resident dictionary."""
import struct

MAX = 0x7fffffffffff
SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'

def ptr(x): return type(x) is int and 0x10000 <= x <= MAX and x % 8 == 0

def read_localization_dictionary(read_ranges, *, module_base, module_size, executable_sha256, keys, key_hash):
    """Capture framing and compressed bytes; no decoding or fallback conclusions."""
    result = {'status':'partial', 'reason':None, 'entries':[], 'missingKeys':[],
              'fallback_resolved':False, 'scope':'requested-keys', 'decoded':False}
    consumed = {}
    total = 0
    class Stop(Exception): pass
    def read(name, ranges, verify=False):
        nonlocal total
        total += sum(n for _,n in ranges)
        if total > 1024*1024: raise Stop('byte_budget')
        try:
            values = read_ranges(name,ranges)
            for a,n in ranges:
                d=values[a]
                if not isinstance(d,bytes) or len(d)!=n: raise ValueError('short read')
                if not verify:
                    if a in consumed and consumed[a]!=d: raise Stop('changed_during_walk')
                    consumed[a]=d
            return values
        except Stop: raise
        except Exception as exc: raise Stop('read_failed: '+type(exc).__name__) from exc
    def q(a):
        if not ptr(a) or a>MAX-7: raise Stop('invalid_pointer')
        return struct.unpack('<Q',read('dictionary_pointer',[(a,8)])[a])[0]
    def varint(data, offset):
        val=0
        for i in range(5):
            if offset+i>=len(data): raise Stop('truncated_varint')
            byte=data[offset+i]
            if i==4 and byte>15: raise Stop('invalid_varint')
            val |= (byte & 127) << (7*i)
            if not byte & 128: return val,offset+i+1
        raise Stop('invalid_varint')
    try:
        if not isinstance(executable_sha256,str) or executable_sha256.upper()!=SHA: raise Stop('unsupported_build')
        if not ptr(module_base) or type(module_size) is not int or module_size<=0x33623ef or module_base+module_size-1>MAX: raise Stop('invalid_module')
        if not isinstance(keys,(list,tuple)) or not 1<=len(keys)<=8 or any(type(k) is not int or not 0<=k<=0xffffffff for k in keys) or len(set(keys))!=len(keys): raise Stop('invalid_keys')
        manager=q(module_base+0x33623e8)
        if not ptr(manager): raise Stop('invalid_manager')
        wrapper=q(manager+0x98)
        if not ptr(wrapper): raise Stop('invalid_wrapper')
        vt,inner=struct.unpack('<QQ',read('dictionary_wrapper',[(wrapper,16)])[wrapper])
        if vt!=module_base+0x26c1ea8 or q(vt)!=module_base+0x7d3230: raise Stop('provider_mismatch')
        if not ptr(inner) or inner>MAX-0x4c3: raise Stop('invalid_inner')
        d=inner+0x78
        base,stride,count,entry_count=struct.unpack('<QQQQ',read('dictionary_header',[(d,32)])[d])
        result['context']={'manager':manager,'wrapper':wrapper,'inner':inner,'dictionary':d}
        result['header']={'base':base,'stride':stride,'bucket_count':count,'entry_count':entry_count}
        if stride!=16 or count>1048576 or (count and (not ptr(base) or base+count*16-1>MAX)) or (not count and (base or entry_count)):
            raise Stop('invalid_header')
        frequency=read('dictionary_frequency',[(d+0x40,1024)])[d+0x40]
        meta=read('dictionary_blob_meta',[(d+0x440,12)])[d+0x440]
        blob,size=struct.unpack('<QI',meta)
        if size and (not ptr(blob) or blob+size-1>MAX): raise Stop('invalid_blob')
        result['blob']={'address':blob,'size':size}
        result['frequency_hex']=frequency.hex()
        heads={}
        if count:
            try: heads={k:base+(key_hash(k)%count)*16 for k in keys}
            except Exception as exc: raise Stop('hash_failed: '+type(exc).__name__) from exc
        rows={}
        if heads:
            vals=read('dictionary_heads',[(a,16) for a in dict.fromkeys(heads.values())])
            frontier=[(k,a,vals[a],True,frozenset()) for k,a in heads.items()]
        else: frontier=[]
        while frontier:
            pending=[]
            for key,a,data,head,seen in frontier:
                if a in seen: raise Stop('chain_cycle')
                seen=seen|{a}
                link=struct.unpack_from('<Q',data)[0]
                if (not head or not link&1) and struct.unpack_from('<I',data,8)[0]==key:
                    offset=struct.unpack_from('<I',data,12)[0]
                    if offset>=size: raise Stop('invalid_blob_offset')
                    rows[key]={'key':key,'node_address':a,'node_hex':data.hex(),'offset':offset}
                    continue
                nxt=link&~1
                if nxt:
                    if not ptr(nxt) or nxt>MAX-15: raise Stop('invalid_chain_pointer')
                    if len(seen)-1>=128: raise Stop('chain_budget')
                    pending.append((key,nxt,seen))
            if pending:
                vals=read('dictionary_chain',[(a,16) for a in dict.fromkeys(a for _,a,_ in pending)])
                frontier=[(k,a,vals[a],False,seen) for k,a,seen in pending]
            else: frontier=[]
        for row in rows.values():
            address=blob+row['offset']
            available=min(4096,size-row['offset'])
            raw=read('dictionary_blob',[(address,available)])[address]
            input_len,p=varint(raw,0); decoded_len,p2=varint(raw,p)
            if decoded_len>=65536: raise Stop('decoded_size_budget')
            if input_len>size-row['offset']-p2 or input_len>4096-p2: raise Stop('input_size_budget')
            row.update(apparent_input_length=input_len, decoded_length=decoded_len, framing_hex=raw[:p2].hex(),
                       blob_prefix_hex=raw.hex(), capture_address=address, framing_verified=False)
        items=list(consumed.items())
        for i in range(0,len(items),128):
            batch=items[i:i+128]
            vals=read('resolver_verify',[(a,len(data)) for a,data in batch],verify=True)
            if any(vals[a]!=data for a,data in batch): raise Stop('changed_during_walk')
        result.update(status='complete',entries=[rows[k] for k in keys if k in rows],missingKeys=[k for k in keys if k not in rows])
    except Stop as exc: result['reason']=str(exc)
    result['bytes_read']=total
    return result
