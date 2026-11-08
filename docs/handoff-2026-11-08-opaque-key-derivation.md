# Opaque source-cache key: exact-build static return map

Checkpoint: 2026-11-08 UTC. Authoritative checkout: C:\work\riftreader2.
Initial reviewed HEAD: 001b14abedc1b3b97a23708049978dc888888e2f.
Import-symbol checkpoint HEAD: c1185051cf1e91d0b1b93bdebd19527418384d8a.
Static evidence only; no live field, freshness or writer qualification.

## Result

The metadata QWORD X at record+0x38 is an INPUT to 0x1145C20, not universally
the opaque cache key K. The helper's complete local normal-return control flow
is now covered by retained bytes at RVA [0x1145C20,0x1145EE2).

| Path | Exact return |
| --- | --- |
| X == 0 | K = 0; RET 0x1145C36 |
| Table candidate B == X | Increment QWORD(B-0x10), then K = B = X |
| Nonnull B passes size-token test and comparison helper returns zero | Increment QWORD(B-0x10), then K = B; equality of B and X is NOT required |
| No match | Obtain A from 0x11883A0; construct P=A+0x10, populate header/payload, insert P into table, then K=P |

The two nonnull paths return through RET 0x1145EE1. All direct branch targets
within this helper are inside the combined export; no local tailcall was found.
This describes normal local control flow, assuming external calls return normally;
callee failures/exceptions, concurrency and runtime invariants were not qualified.

The exact imported strlen/strcmp references now substantiate NUL-terminated
byte-string canonicalization into a refcounted payload pointer. The copy/allocation
callee identities remain unresolved; K is a pointer-like token, NOT the hash index.

## Instruction evidence

- 0x1145C26 preserves X in R14. 0x1145C29..0x1145C36 returns zero for null.
- 0x1145C5A calls strlen(X) through import thunk 0x2504857; byte length is retained in R15.
- Global service S is read from module+0x33D7D98.
- 0x1145C95 calls 0x1145EF0(X,R15). Its EAX selects a 24-byte-stride entry:
  WORD(S+24*index+0x12) is iteration count and QWORD(S+24*index+0x08) the array.
- 0x1145CD9 branches to 0x1145E1A for B==X. Otherwise nonnull B must satisfy
  zero-extended WORD(B-0x08)==R15, and strcmp(B,X) through thunk 0x250487B must return EAX==0.
- Match block 0x1145E35 atomically increments QWORD(B-0x10);
  0x1145E57 sets RAX=B and jumps to the common return epilogue.
- Miss block 0x1145D19..0x1145D32 requests aligned-up-to-8 size R15+0x11
  from 0x11883A0(size,0). The allocator interpretation is inferred from use.
- 0x1145D40 sets P=A+0x10. 0x1145D57 writes QWORD(A)=2.
  0x1145D5E writes a packed header at A+8 from R15 OR
  zero-extended uint32(index<<16). 0x1145D68 calls 0x25047A9(P,X,R15+1).
- 0x1145E5C or 0x1145E77 stores P into a table slot; 0x1145EB5 sets RAX=P.
  A defensive P==0 branch at 0x1145DAD skips insertion, still reaching return P.
- Table growth calls 0x10B3820. Indirect calls use IAT RVAs
  0x25EF6E8, 0x25EF700 and 0x25EF6F0. Their names are not asserted.
- Multiple service counters/table stores and atomic refcount changes mean calling
  the native helper is NOT passive read-only retrieval.

## Integration with 0x6126F0

V7 raw instructions, not the lossy decompiler argument list, establish:

1. K starts as sentinel QWORD(module+0x274C990).
2. Resolve metadata record using the selected collection index.
3. X=QWORD(record+0x38). If X equals the sentinel, skip 0x1145C20 and retain K.
4. Otherwise K=0x1145C20(X), using the return map above.
5. Resolve the actor component from sourceComponent+0x10 using selector
   module+0x2F58490; pass &K to 0x67BFB0.

The collection's entry+0x18 match key, player-system self key, position refresh
handle and resulting opaque K are DISTINCT roles. No equality is assumed.

## Passive reproduction: remaining bounds

This closes the unknown nonnull RETURN SHAPE, not the full passive locating recipe.

- Pointer-equality match can preserve X, but X cannot be substituted universally.
- Existing equivalent bytes can resolve to another B. Imported strlen/strcmp
  semantics and indexing are now resolved; current source/table validity is not.
- The initial export cut off 0x1145EF0 at 0x1145F1F; the third bounded export
  closes that former gap. The entire index helper is now covered.
- A genuine miss constructs/inserts a new token. A passive reader must report
  unavailable for an unmaterialized key, not allocate/invoke the helper.
- Upstream metadata resolution, current table/pointer validity, stable ownership and
  snapshot freshness still need separate evidence. No live address is supplied.
- 0x67BFB0 cache-hit layout remains supported by V7 pseudocode, not independently
  complete raw-instruction confirmation in this report. Its miss path may mutate.

## Provenance and reproduction

Executable identity (retained original-import metadata):
1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.
No current installed PE rehash or new PE import was performed by this analysis.

| Input | SHA256 |
| --- | --- |
| RVA 0x1145C20, 256 bytes | CA748A53F956B446A28E9897AA2F86193A7EAD60EBEA5443EDC921FDE283CD95 |
| RVA 0x1145D20, 512 bytes | A40ADA4771C1E4372FCEA49C45E6EFFE6FF6FE91B014454A6F4F65D83C709FED |
| Concatenated 768 bytes | f0aec894ba84494e56f63021eecf6ecacb21e9716f279065509eea68b6b25d3c |
| Helper body prefix, 706 bytes through RET inclusive | 615a8ef33e4c396118a0e87af7e6cd5726767407f130bb9e0edd0b0b61579d40 |
| V7 caller instructions | ca66aca8543b4e2f0b70f7669025c0d3fe419c4a0864a7ae9832ac625e1ac530 |
| V7 pseudocode | 8ff54a70f56c18f453494b7977598ebfaea91f05920565f7563df99aac166c45 |

Raw export receipts:
- rr2-root-ghidra-opaque-helper-1145c20-20261108-01: passed/exit0, untruncated.
- rr2-root-ghidra-opaque-key-continuation-1145d20-20261108-01: passed/exit0, untruncated.

Retained headless logs under artifacts/rea:
- opaque-key-1145c20-review1/headless.log:
  4d8bf2fb11ecf3ffc0ea06f144c3d9e3ad5b8b2406af43d051d391439c540cb2
- opaque-key-1145d20-review2/headless.log:
  f9136cd5edbc12ea76f4c976a7b5b7651fd0e43d1192e526c1381c57e575902c

Root executed the retained guarded exports with -readOnly -noanalysis. This worker
only decoded retained hex with GNU objdump 2.44 in x86-64 Intel mode via transient
Linux memory-backed descriptors, independently verifying the source byte digests.
No Ghidra rerun, live memory, input, VM operation or commit occurred in this analysis.
The companion JSON retains raw hex windows and the exact symbol-export payload and machine-readable conclusions.

## Index helper resolved: 0x1145EF0 (third bounded export)

RVA [0x1145EF0,0x1145F7E) is a complete 142-byte leaf helper: one RET at
0x1145F7D, no calls, no memory stores, and no direct branch outside that body.
Input RCX is byte pointer X; only the low 32 bits of input RDX control the prefix.

Exact algorithm:
1. Set uint32 h=0; p=0; prefix=uint32(RDX)&0xFFFFFFFC.
2. For each of the first prefix bytes, including any embedded zero, update
   h=uint32(33*h+int8(X[p])) and advance p. The code unrolls four bytes at a time.
3. Starting at p, repeat the same update until the first zero byte; do not hash
   that terminating zero. This suffix is NOT bounded by the original RDX value.
4. Return uint32 h modulo 513 (0x201), hence index range 0..512.

MOVSX at 0x1145F10/1A/24/2E and 0x1145F58 proves SIGNED byte contributions;
all multiply/add operations use 32-bit registers. The reduction at 0x1145F66..7A
uses q=(uint64(h)*0xFF803FE1)>>41, followed by h-q*513. It is exact unsigned
division: 513*0xFF803FE1-2^41=481, and the conservative maximum of
floor((2^32-1)/513)*481+512*0xFF803FE1 is 2198763715647 < 2^41.
Thus no random-sample-only assertion is needed for the modulo equivalence.

Imported strlen now proves the length input. For a stable valid NUL-terminated
byte sequence this reduces to the zero-seeded 33x signed-byte polynomial over all
bytes before NUL, modulo 513. Preserve the raw prefix-plus-NUL description for
contradictory/changing inputs; the separate strlen/hash reads are not atomic.
A passive implementation must impose a safe read budget and report a missing
terminator or missing bytes unavailable.

Independent arithmetic fixtures (hex includes terminator):
| Bytes | RDX | uint32 h | Index |
| --- | ---: | --- | ---: |
| 00 | 0 | 0x00000000 | 0 |
| 61626300 | 3 | 0x0001A9A6 | 210 |
| 6162636400 | 4 | 0x0036DECA | 361 |
| 80FF00 | 2 | 0xFFFFEF7F | 360 |
| 6100626300 | 4 | 0x00353DC6 | 309 |

These are offline formula checks, not native execution. The last fixture preserves
an embedded zero inside the unconditional prefix.

The same export incidentally covers initializer 0x1146080: constants 0x201 at
0x11460A9 and 0x11460B5, stride 0x18 at 0x11460D1, and the loop ending at
0x11460D9 establish 513 fixed entries (513*24=0x3018). It stores the resulting
service at global 0x33D7D98 at 0x1146104. This proves static index/entry-count
compatibility, not current allocation validity, per-entry array bounds or freshness.
The final unrelated routine at 0x11461C0 is truncated and branches to 0x11461F8
outside the export; this does not truncate the index helper.

Third receipt: rr2-root-ghidra-opaque-index-1145ef0-20261108-01, passed/exit0,
untruncated. Window [0x1145EF0,0x11461F0), 768 bytes:
B762C9E0A7F65156C5B62E6F05171780EB7576D0B9D9A2202390E5AD4FB74D03.
142-byte index body SHA256:
770fbb8ad46121104bb8b072133c572b213351b8ac81669282fb3e72a2f9faaf.
artifacts/rea/opaque-index-1145ef0-review1/headless.log SHA256:
de333eff64f89d2cc4984f86e9e33cd84981dd30c6b4ac34a02fa110a9fb743d.

## Imported string helpers resolved

Raw thunk window [0x2504830,0x2504930), 256 bytes, SHA256:
637F6CE586F613D84A1272FAF789D42BF2E1535C13838611C069B6204A2B6356.
Its first byte is inside a preceding instruction; decode at the known thunk entries.

| Thunk RVA / bytes | IAT RVA | IMPORTED external reference |
| --- | --- | --- |
| 0x2504857 / FF256BBF0E00 | 0x25F07C8 | API-MS-WIN-CRT-STRING-L1-1-0.DLL!strlen |
| 0x250487B / FF252FBE0E00 | 0x25F06B0 | API-MS-WIN-CRT-STRING-L1-1-0.DLL!strcmp |

The exact IAT references have source=IMPORTED and type=DATA, targeting external
locations EXTERNAL:00000288 and EXTERNAL:00000265 respectively. Thunk references
are DEFAULT INDIRECTION. No labels were guessed from behavior. The external
location address fields 02f540ce/02f54118 are retained import metadata, NOT
verified runtime callable addresses. No current IAT/process read was performed.

For stable valid inputs:
- strlen returns the number of bytes before the first zero, excluding terminator.
- strcmp equality (the only outcome used here) means identical byte sequences
  through their first NUL; case-sensitive, not Unicode decoding or normalization.
  Its lexical ordering treats differing bytes as unsigned; the custom HASH
  separately sign-extends bytes. Do not apply signed-byte ordering to strcmp.
- Input index: h starts at zero; each pre-NUL byte contributes
  uint32(h*33 + int8(byte)); index=h%513.
- Candidate iteration compares pointer identity FIRST. Otherwise candidate must
  be nonnull, WORD(B-8) must equal full strlen(X), and strcmp(B,X) must equal zero.
  Preserve this 16-bit header/full-length equality rather than truncating strlen.
- Output remains existing B on hit, not the numeric hash/index. A miss is not
  passively materializable; return unavailable rather than allocating or calling.

Passive key lookup is now statically specifiable for an already materialized
matching table entry, but is NOT implemented/live-qualified by this finding.
Upstream metadata resolution and all exact-epoch/current-memory admission remain
required. The native helper pins a found B by atomic refcount increment; a passive
reader does not. Exported pointer values therefore do not confer a lifetime:
source/table/object may change or be freed between reads; bracketing cannot
exclude ABA. Return only a snapshot-scoped candidate with explicit unavailable
states, never a reusable or independently fresh live pointer promise.

Symbol receipt: rr2-root-ghidra-opaque-import-symbols-20261108-01, passed/exit0,
untruncated. Exact payload from BEGIN through COMPLETE inclusive, LF-normalized
UTF-8 with no trailing newline, SHA256:
572afae2f29241ad1fd732829a87eb6303a787eba1a39a7e589ee9c320be5f8a.
Symbol headless.log SHA256:
531f7157f05c6ceee7450809fcdb0df5a4b96fedcd67cfd496ad18cbc18ac605.
Raw thunk receipt: rr2-root-ghidra-opaque-compare-2504857-20261108-01, passed/exit0;
headless.log SHA256:
f40fa2d415dd593fe192195b952b6ec4f6f018e653309389abc4484f1c0e2298.
