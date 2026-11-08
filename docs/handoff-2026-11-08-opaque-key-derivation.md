# Opaque source-cache key: exact-build static return map

Checkpoint: 2026-11-08 UTC. Authoritative checkout: C:\work\riftreader2.
Reviewed HEAD: 001b14abedc1b3b97a23708049978dc888888e2f.
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

This is consistent with interning/canonicalization of a refcounted payload pointer.
That semantic label is an inference: exact length/comparison/copy helper identities
remain unverified. K is a pointer-like cache token, not a numeric hash of X.

## Instruction evidence

- 0x1145C26 preserves X in R14. 0x1145C29..0x1145C36 returns zero for null.
- 0x1145C5A calls 0x2504857(X); returned token/length-like value is retained in R15.
- Global service S is read from module+0x33D7D98.
- 0x1145C95 calls 0x1145EF0(X,R15). Its EAX selects a 24-byte-stride entry:
  WORD(S+24*index+0x12) is iteration count and QWORD(S+24*index+0x08) the array.
- 0x1145CD9 branches to 0x1145E1A for B==X. Otherwise nonnull B must satisfy
  zero-extended WORD(B-0x08)==R15, and 0x250487B(B,X) must return EAX==0.
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
- Existing equivalent content can resolve to another B; exact matching needs the
  semantics of 0x2504857 and 0x250487B plus complete 0x1145EF0 indexing.
- 0x1145EF0 begins at the end of the export; its branch to 0x1145F44 lies outside
  coverage and its instruction at 0x1145F1F is truncated. It is NOT fully decoded.
- A genuine miss constructs/inserts a new token. A passive reader must report
  unavailable for an unmaterialized key, not allocate/invoke the helper.
- Upstream metadata resolution, service-table valid bounds, stable ownership and
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

Root executed the two guarded exports with -readOnly -noanalysis. This worker
only decoded retained hex with GNU objdump 2.44 in x86-64 Intel mode via transient
Linux memory-backed descriptors, independently verifying both byte digests.
No Ghidra rerun, live memory, input, VM operation or commit occurred in this analysis.
The companion JSON retains both raw hex windows and machine-readable conclusions.
