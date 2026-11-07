import struct
import unittest
from scripts.native_localization_override import read_localization_override

B=0x10000000
M,W,I,H,N,C,O,V=(0x20000000+i*0x1000 for i in range(8))

def fixture():
    mem={}
    def put(a,d):
        for i,b in enumerate(d): mem[a+i]=b
    def q(a,v): put(a,struct.pack('<Q',v))
    q(B+0x33623e8,M); put(M,struct.pack('<B3xi',0,2)); q(M+0x98,W); put(W,struct.pack('<QQ',B+0x26c1ea8,I)); q(B+0x26c1ea8,B+0x7d3230)
    put(I+0x28,struct.pack('<QQQQ',N,24,1,2))
    put(N,struct.pack('<QI4xQ',C|1,3,0)); put(C,struct.pack('<QI4xQ',0,7,H)); q(H+0x18,O)
    raw=bytearray(72); struct.pack_into('<Q',raw,0,B+0x295dc10); struct.pack_into('<Q',raw,0x28,V); struct.pack_into('<Q',raw,0x40,1); put(O,raw)
    q(B+0x295dc10+0x40,B+0x1a4faf0); q(B+0x3484000,B+0x2963030); q(B+0x2963030+8,B+0x1a779e0)
    child=V+0x1000; text=V+0x2000
    put(V,bytes(16)+struct.pack('<QQi4xQ',0,0,2,child)); q(child,B+0x2804120)
    q(B+0x2804120+0x40,B+0x173c790); q(B+0x3420930,B+0x2820340); q(B+0x2820340+8,B+0x177ce30)
    q(child+0x30,text); q(child+0x38,text); put(text,'Hello'.encode('utf-16-le')+bytes(246))
    def read(name,ranges): return {a:bytes(mem[x] for x in range(a,a+n)) for a,n in ranges}
    return put,read

def call(read,keys):
    return read_localization_override(read,module_base=B,module_size=0x3500000,keys=keys,key_hash=lambda x:x,executable_sha256="1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8")

class OverrideTests(unittest.TestCase):
    def test_chain_candidate_and_miss(self):
        _,read=fixture(); r=call(read,[7,8])
        self.assertEqual(r['status'],'complete',r)
        self.assertEqual(r['entries'][0]['result_pointer'],O)
        self.assertTrue(r['entries'][0]['type_verified'])
        self.assertEqual(r['entries'][0]['candidate_text'],'Hello')
        self.assertEqual(r['missingKeys'],[8])
    def test_empty_and_wrong_provider(self):
        put,read=fixture(); put(I+0x28,struct.pack('<QQQQ',0,24,0,0))
        self.assertEqual(call(read,[7])['missingKeys'],[7])
        put(W,struct.pack('<Q',B+0x26c1e90))
        self.assertEqual(call(read,[7])['reason'],'provider_mismatch')
    def test_torn_result_rejected(self):
        _,read=fixture()
        def torn(name,ranges):
            values=read(name,ranges)
            if name=='resolver_verify' and O in values: values[O]=bytes([values[O][0]^1])+values[O][1:]
            return values
        r=call(torn,[7]); self.assertEqual(r['reason'],'changed_during_walk'); self.assertEqual(r['entries'],[])

    def test_uninitialized_descriptor_fails_before_text(self):
        put,read=fixture(); put(B+0x3484000,bytes(8))
        self.assertEqual(call(read,[7])['reason'],'descriptor_uninitialized_or_mismatch')
