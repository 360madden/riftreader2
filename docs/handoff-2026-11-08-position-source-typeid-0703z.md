# Current-build position source type-ID dispatch — exact retained PE

**Checkpoint:** 2026-11-08 07:03 UTC / 02:03 EST. **Scope:** bounded offline analysis only, no game/VM/reader access. **Authoritative checkout:** `C:\work\riftreader2` (AMD-DESKTOP).

## Result

The generic type-tag helper at **RVA `0x127303C`** does **not** read a fixed scalar tag field from a known object offset. The retained instruction bytes instead show **two consecutive indirect dispatches**:

```asm
0x127303C  sub rsp,0x28
0x1273040  mov rax,[rcx]          ; original input's dispatch pointer
0x1273043  call qword ptr [rax+0x40]
0x1273046  mov rcx,[rax]          ; RAX is returned by preceding call
0x1273049  mov rdx,[rcx+0x08]
0x127304D  mov rcx,rax
0x1273050  add rsp,0x28
0x1273054  jmp rdx                ; tail dispatch with returned object
0x1273057  int3                   ; padding
```

The first call selects a method at `[input.vptr+0x40]`; the returned pointer-like value is then dispatched through its first QWORD and `+0x08` entry. **Interpretation as a type-information path is inferred from callers and return comparisons**, not an independently established object schema. The shown sequence is a 27-byte direct body followed by INT3; exceptional/tail-callee behavior is outside this window.

At `0x1A96CB0`, the position-source pointer wrapper copies `*entry RDX`, manages its `+0x08` count, invokes this dynamic `0x127303C` service on the pointed object, and compares the returned low 16-bit value to **`0x25B`**; a mismatch releases and clears the temporary. Another existing V8 caller at `0x69A800` uses the **same service** but compares to **`0xEDA`**, supporting a generic type discriminator. The numeric `0x25B` is **not a proven type name, memory-field offset, or ownership proof**.

The caller bridge `0x6984C0` preserves incoming `RDX` into this wrapper and forwards the temporary to the bulk writer `0x6990D0`, which copies source object's float-like `+0x44/+0x48/+0x4C` values into a receiver position component's primary `+0x48/+0x4C/+0x50` cache. **The upstream owner/producer of that incoming RDX object remains unknown.** No current-player runtime call, independent changed-state, passive freshness or restart inference follows.

## Exact sources

- Retained PE `artifacts/lab2-rift-exe-20261027-01-copy.exe`, **60,493,640 bytes**, SHA-256 **`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`**, rehashed by this analysis. This is a retained file, **not a fresh installed-PE or live module hash**.
- Surgical `.text` window `[0x127303C,0x12730FC)`, **192 bytes**, RVA file offset `0x127243C`, raw slice SHA-256 **`1491B03AAAB230A8D40E59E6AB324A3BEA1E6E7CFC6C75E608EE8A8C4C9BA460`**. First 28 hex bytes including INT3: `4883EC28488B01FF5040488B08488B5108488BC84883C42848FFE2CC`.
- Host-only source job `rr2-xyzprov-typeid-127303c-raw-20261108-01`, **PASS/exit 0**, finished `2026-11-08T07:02:47.900Z`. Single bounded Python `-c` against retained PE, with section mapping and full-file SHA check; no script file was saved or hashed.
- Earlier `0x1A96CB0` raw window `[0x1A96CB0,0x1A970B0)`, 1024 bytes SHA `F661D037C4134C05B46B2419EEC90D2BB50955D798D9640D299AD198A74664F9`. Reviewed explanation `docs/position-producer-1a96cb0-offline-review-20261108.md` SHA `D1BB664160235091A1E89334BACE383F8555042828983D8CDE6D32DFF804BFD6`.
- V8 retained pseudocode `artifacts/rea/ghidra-v8-pseudocode.txt` SHA `D2EDA069932B441F59520CE51C3904B21FF84AD92E088EAC333F50E5ACDC7961` (alternate `0xEDA` type check and `0x6984C0` caller).
- Primary writer source `docs/handoff-2026-11-08-xyz-writer-6990d0.md` SHA `046D748B99EFEB6ADE1CBB3BD70BBDA32AA94CA423814CD146EBA1C2F05DB95D`.

## Next highest-signal narrow trace

Find an actual engine dispatch/callsite supplying **entry RDX** to `0x6984C0` (candidate component table method at `+0x10`), then classify the source object's vptr and dynamic type discriminator while preserving exact build/source evidence. Only after its owner is bound to the self entity can source+0x44/48/4C be evaluated as an independent changing position source. This remains a **static candidate route**, separate from both cache getter refresh and any live admission.
