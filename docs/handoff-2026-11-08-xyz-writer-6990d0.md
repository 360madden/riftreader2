# Current-build direct XYZ writers at 0x6990D0 / 0x6995A0

**Meaningful offline discovery:** exact-build raw bytes reveal primary XYZ stores outside the previously inspected `0x6996C0` refresh branches. No live writer execution or freshness qualification follows.

## Source and method

Root job `rr2-root-ghidra-writer6990d0-20261108-01` exited0. Retained program executable SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, base `0x140000000`. Export interval `[0x6990D0,0x6996D0)`: **1536 bytes**, SHA256 `37105C6813AD95805B83CBEC7DF4659BCDC6AD321DAB271D90A5B1FB46AAED9D`, independently rehashed before GNU objdump2.44 binary/x86-64/Intel decode. No new Ghidra, live access or program mutation.

Source directory `artifacts/rea/position-writer-6990d0-review1/`: exporter SHA256 `15c06011ed8d4de662b91c12a45a8700268e7a42660b4b925b3081f1102e7ac8`; `headless.log` SHA256 `feedef89f42034cf673353bd2db8e321257b28cbbcd1e57558d215c14d5fe710`. The sibling [machine report](handoff-2026-11-08-xyz-writer-6990d0.json) lists exact store/provenance RVAs, calls and limits.

## 0x6990D0: bulk direct primary writer

Observed coherent body `0x6990D0..0x699595` (251 instructions), ending RET then INT3 padding before next entry `0x6995A0`. All direct non-call branches stay in this body. **Not independently checked against PE unwind/exception boundaries**; callees/exceptional paths remain unexpanded.

Entry `RCX` becomes receiver `RDI`; entry `RDX` becomes `RSI`; source is `[RSI]` (a pointer-to-pointer input). These are static argument/dataflow bindings, not live player-owner proof.

| Store RVA | Receiver destination | Source value |
| --- | --- | --- |
| `0x6992AA` | `+0x48` | source `+0x44` via stack `+0x58` → XMM2 |
| `0x6992B2` | `+0x4C` | source `+0x48` via stack `+0x5C` → XMM1 |
| `0x6992B7` | `+0x50` | source `+0x4C` → R8D |

The same three values are copied to `+0xE4/+0xE8/+0xEC` immediately before these stores. Later `0x69947A/0x699486` copy primary XYZ to secondary `+0x88/+0x8C/+0x90`.

Other side effects: string-like receiver `+0x20` assignment from source `+0x68`; source `+0x20` qword → receiver `+0x40`; source `+0x28/+0x2C/+0x30` → `+0xD8/+0xDC/+0xE0`; source `+0x34/+0x38/+0x3C` → `+0x54/+0x58/+0x5C`; source `+0x40` → `+0xB8`. Input vector `source+0x54` feeds helper/arithmetic and nine matrix-like scalar stores `+0x60..+0x80`, then matrix copies to `+0x94..+0xB7`. Clears `+0xF0/+0xCC`, sets qword `+0xC4=0x000000003F800000`, copies `+0xB8` to `+0xBC/+0xC0/+0xD0`. At `0x699563`, helper `0x1CE3D20` receives `RCX=receiver+0xF8`; its actual stores/type were not inspected.

**Inference:** bulk initialization/refresh from a structured source, not proven constructor semantics. Sixteen external/IAT call instructions occur; no tail branch leaves this body. The error path has INT3 at `0x6991DF`.

## 0x6995A0: second, smaller direct XYZ setter

UCOMISS/JNE/JE comparisons precede a qword copy at `0x6995CC` (input XY → receiver `+0x48/+0x4C`) and dword copy at `0x6995D4` (input Z → `+0x50`). No direct secondary-cache store. A selected owner component from metadata RVA `0x2F59778` can receive tail jump **`0x78C2A0`** at `0x699608`, with `RDX=receiver+0x48`; otherwise RET `0x69960D`. Tail target lies outside this window.

Do not simplify its comparison to total IEEE equality: unordered/NaN flags lack explicit checks. The owner table is dereferenced before a later owner-null test; that test is not a safe-null guarantee.

## Window boundaries and next use

Adjacent `0x699610` is a Boolean/tag predicate with returns `0x69968E/0x699696`, not another direct XYZ writer. `0x6996A0` conditionally branches out to `0x6988D0` if `[[RCX+0x10]+0xC0]!=1`; otherwise returns. `0x6996C0` is only an incomplete next-routine prologue at the export end; do not decode continuation from missing bytes.

Next useful work is bounded caller/source provenance for **receiver RCX and pointer-to-pointer RDX**, plus the separate `0x6995A0` setter. Static destination-matched stores do not establish actual current-player pointers, source ownership, world-frame meaning, passive freshness, changed-state or restart durability. Do not invoke native candidates.
