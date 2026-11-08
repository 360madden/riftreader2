# RR2 constructor RVA 0x698170 — exact-SHA offline scans (2026-11-08 06:41 UTC)

**Result:** No raw `.text` `E8 rel32` direct-call or `E9 rel32` jump byte-pattern candidates targeting RVA `0x698170`; **one** exact absolute-VA 8-byte match in `.rdata`, at RVA `0x26B5040` (+`0x90` after candidate position table `0x26B4FB0`). This is **untyped initialized data**, not verified constructor factory, runtime dispatch, object ownership, active call, or XYZ source.

## Source-locked evidence

- Retained PE file: `artifacts/lab2-rift-exe-20261027-01-copy.exe`, size **60,493,640 bytes**; full file SHA-256 verified **`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`**. The scanners read this exact file; **no fresh installed executable/process hash** was acquired.
- **P1** script: `artifacts/rea/constructor-e8-scan-review1/scan_constructor_direct_calls.py`; SHA-256 `a472cbb527d8b282b87d9b82fd37144391b930df9f6f9e6ac2cc47f79db040b2`; job `rr2-constructor-e8-scan-20261108-root-01` **PASS exit 0** (06:40:05 UTC).
- **P2** script: `artifacts/rea/constructor-indirect-scan-review1/scan_constructor_tail_or_pointer_candidates.py`; SHA-256 `ea85f56f1fdf334cef1efd110e58527589fdfcab2f12247251a3973dfcc94380`; job `rr2-constructor-tail-and-pointer-20261108-root-01` **PASS exit 0** (06:41:30 UTC).
- Both read raw file bytes only; no Ghidra, VM, controller, game or native process operation.

| Search | Exact scoped bytes | Verified output |
|---|---|---|
| `.text` E8 rel32 target `0x698170` | 39,772,160 bytes; section SHA `76E504D8F26BA7B01CB97BB9741EFB158B15F4324D8DB5EA094866D9A4884D7C` | **0 byte-pattern candidates** |
| `.text` E9 rel32 target `0x698170` | Same `.text` section and SHA | **0 byte-pattern candidates** |
| `.rdata` LE64 exact VA `0x140698170` | 9,855,488 bytes; section SHA `76B9083D6BCB051640362DE1012CB35F6CDAE7BCBDEAFCE311ED64605A10DE73` | **1** 8-byte-aligned match at RVA `0x26B5040`, file offset `40584256`, raw hex `7081694001000000` |

The negative E8/E9 result applies **only** to exact 5-byte opcode/displacement patterns within raw `.text`. It cannot exclude indirect calls, other sections, instruction alternatives, inlining or runtime pointers. The `.rdata` match may be inert data or a table entry: no instruction boundary, surrounding object type, factory interpretation, active invocation or ownership was proven.

**Next bounded investigation:** Examine a small read-only static window around `.rdata` RVA `0x26B5040` and compare neighboring entry layout against the earlier candidate table at `0x26B4FB0`; do not promote the match to an owner/factory until code/instance evidence establishes it.
