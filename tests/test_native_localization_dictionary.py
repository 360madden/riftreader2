import struct
import unittest
from scripts.native_localization_dictionary import read_localization_dictionary
B=0x10000000
M,W,I,N,C,BL=(0x20000000+i*0x1000 for i in range(6))
SHA='1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
def fixture():
    mem={}
    def put(a,d):
        for i,b in enumerate(d): mem[a+i]=b
    def q(a,v): put(a,struct.pack('<Q',v))
    q(B+0x33623e8,M); q(M+0x98,W); put(W,struct.pack('<QQ',B+0x26c1ea8,I)); q(B+0x26c1ea8,B+0x7d3230)
    put(I+0x78,struct.pack('<QQQQ',N,16,1,1)); put(I+0xb8,bytes(1024)); put(I+0x4b8,struct.pack('<QI',BL,8))
    put(N,struct.pack('<QII',C|1,2,0)); put(C,struct.pack('<QII',0,7,0)); put(BL,b'\x03\x04abcXYZ')
    def read(name,ranges): return {a:bytes(mem[x] for x in range(a,a+n)) for a,n in ranges}
    return put,read
def call(read): return read_localization_dictionary(read,module_base=B,module_size=0x3500000,executable_sha256=SHA,keys=[7,8],key_hash=lambda x:x)
class DictionaryTests(unittest.TestCase):
    def test_raw_framing_and_miss(self):
        _,read=fixture(); r=call(read)
        self.assertEqual(r['status'],'complete',r); self.assertEqual(r['missingKeys'],[8]); self.assertEqual(r['entries'][0]['apparent_input_length'],3)
        self.assertFalse(r['entries'][0]['framing_verified']); self.assertEqual(r['entries'][0]['blob_prefix_hex'],'030461626358595a')
    def test_bad_varint_and_torn(self):
        put,read=fixture(); put(BL,b'\xff\xff\xff\xff\x10abc'); self.assertEqual(call(read)['reason'],'invalid_varint')
        _,read=fixture()
        def torn(name,ranges):
            d=read(name,ranges)
            if name=='resolver_verify' and BL in d: d[BL]=b'\x02'+d[BL][1:]
            return d
        self.assertEqual(call(torn)['reason'],'changed_during_walk')
