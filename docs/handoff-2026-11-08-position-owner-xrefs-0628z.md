# RR2 position-owner xrefs — bounded static result (2026-11-08 06:28 UTC)

**Result:** One retained Ghidra **DATA** reference points at the known position-owner caller entry; the candidate table address has **zero retained incoming references**. This does not establish a caller chain, table role, or live XYZ retrieval.

## Exact evidence

- Authoritative host checkout: `C:\work\riftreader2`, branch `codex/modular-foundation`; existing Ghidra project `artifacts/rea/RiftNativeFocusedV2`, program `rift_x64.exe`.
- Imported executable SHA-256 metadata: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. The script guarded this **imported metadata**; it did **not** rehash a fresh game executable.
- Export script: `artifacts/rea/position-owner-xrefs-review1/Rr2PositionOwnerXrefsExport.java`, SHA-256 `be1f0b32ae1a5fb8c349da6cb502d13e0711defebf340f23a74df05bda310002`.
- Host-only bounded job: `rr2-position-owner-xrefs-20261108-root-01`, completed **exit 0**, 2026-11-08 06:28:23 UTC. Existing project opened **read-only**, `-noanalysis -max-cpu 1`. Output marked `RR2_POSITION_OWNER_XREFS_COMPLETE`.
- Export limited to two exact targets, at most 32 retained incoming refs per target, at most nine existing listing instructions around a ref, and 300,000 output characters. No recursive traversal, disassembly or new analysis.

| Target RVA (image base `0x140000000`) | Retained incoming references | What was actually shown |
|---|---:|---|
| `0x6984C0` (VA `0x1406984C0`, existing `FUN_1406984c0`) | **1**, not truncated | **DATA** ref, operand 0, from RVA `0x363E8B4` (VA `0x14363E8B4`); source function metadata unavailable and no source instruction in retained listing |
| `0x26B4FB0` (VA `0x1426B4FB0`, candidate table address) | **0**, not truncated | No existing Ghidra incoming ref for that **exact** address; no function at target |

## Interpretation and next bounded question

The one DATA ref makes `0x363E8B4` a precise **source-data location to inspect next** for a pointer to `0x6984C0`. It does not prove the type of enclosing object, dispatch-table or vtable structure, ownership, invocation, or source lifetime. The zero-ref exact table result is a **negative only within the retained reference index**; it does not disprove computed, indirect, untyped, or otherwise unindexed uses.

Next: one read-only, exact-build Ghidra inspection of initialized block/bytes and limited nearby pointers at `0x363E8B4`, with source hash and caps; first characterize data layout before expanding into a caller/owner hypothesis. Preserve the established static writer findings separately from any eventual current-process read qualification.

**No guest deployment, native process sampling, game input, controller action, or field qualification was performed.** The independent *Greeting Jimmy* native-read/maintenance window remains unacknowledged in this evidence.
