# Offline review: RVA 0x1A96CB0

Exact-build retained Ghidra raw window `[0x1A96CB0,0x1A970B0)` (1,024 bytes) SHA-256 `F661D037C4134C05B46B2419EEC90D2BB50955D798D9640D299AD198A74664F9` was independently reproduced from stdout and decoded with GNU objdump x86-64. Source executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; source job `rr2-root-ghidra-position-producer-1a96cb0-20261108-01` exit 0; exporter SHA-256 `BDC95F2C515492FD1292B1FD7768ECB32D670B3E41E8A9561DDE32FE71FD0A80`.

At RVA `0x1A96CB0`, the function copies `*[RDX]` into `*[RCX]`. If non-null it increments the pointed object's DWORD at `+0x08`, calls `0x127303C` with that original pointer, and accepts only return `AX == 0x25B`. On mismatch it decrements `+0x08`, calls `0x1272C18` if the count becomes zero, and clears the destination pointer. It returns destination `RCX` in RAX at `0x1A96D14`; INT3 padding follows before the next routine at `0x1A96D20`.

This is a **type-filtering pointer-wrapper candidate**, not a demonstrated vector/XYZ generator. Its returned pointer derives from the caller-supplied pointer-to-pointer; trace that caller's RDX input and the source object to determine provenance. The call's type meaning and runtime branch are not established. Neighboring routines and the truncated window do not establish the complete producer chain; no live freshness, writer execution, player ownership or movement semantics follow.

## Caller register bridge confirmed — RVA 0x6984C0

Root job `rr2-root-ghidra-position-caller-6984c0-20261108-01` exited0. Exact-build raw `[0x6984C0,0x698580)` is192bytes, SHA256 `ED1C1F0DC5F4C333232E3BFA62AD5F9576853EF52432B0E53F55476C4EE21E8A`, independently length/hash-verified and decoded with GNU objdump2.44 binary x86-64/Intel. Exporter `artifacts/rea/position-caller-6984c0-review1/Rr2PositionCaller6984C0RawExport.java` SHA256 `D801B121F21C75A76E237F6D2AAF7FA4D7E7BB65F59705D148FDF36356C0BD25`; same directory `headless.log` SHA256 `1DC2516443E9552B0ABD5EB613E4A51D68441CBF157345E5B25965E4EAB916EE`.

| RVA | Exact register/call evidence |
| --- | --- |
| `0x6984CA` | `RBX=entry RCX` (receiver) |
| `0x6984CD` | `RDI=entry RDX`; RDX itself is unchanged |
| `0x6984D0/0x6984D5` | `RCX=&stack[0x38]`; CALL `0x1A96CB0` with **entry RDX unchanged** |
| `0x6984DA/0x6984DF/0x6984E2` | `RDX=&stack[0x38]`, `RCX=RBX`; CALL `0x6990D0` |

Thus the type-filtered temporary pointer is passed directly to the bulk XYZ writer, with the original receiver. This body does not manufacture a vector or identify the upstream object owner.

**Consumed input:** `0x6984EC` calls `0x75C7F0` on the temporary. `0x6984F1` loads `*entry RDX`; if nonnull, `0x6984F9` decrements its DWORD `+0x08`, `0x6984FF` calls `0x1272C18` if zero, and `0x698504` clears the original pointer slot. Normal path sets `AL=1` at `0x698510` and RETs `0x698517`; **not a proven source-validity result**.

There is no explicit filtered-null/tag-mismatch test before the bulk writer call; `0x6990D0` dereferences its pointer input. Do not assume graceful rejection or a complete callable contract. Coherent caller body/return/padding are observed; PE unwind boundary remains unchecked. Next entry `0x698520` is truncated by the raw window and is not analyzed as a complete function.

**Remaining upstream bound:** trace callers of `0x6984C0` for the actual receiver, pointer-slot origin and `*entry RDX` type/lifetime. The register bridge is now established; actual current-player/source ownership, runtime reachability, live execution, freshness and restart remain unqualified. No new Ghidra run, live operation or commit occurred during this review.
