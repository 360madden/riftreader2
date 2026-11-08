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

## Candidate generic manager dispatch (not yet bound to position)

Retained focused Ghidra output `artifacts/rea/ghidra-manager-notify-trace-v1.txt` (SHA-256 `D74807E7D5F74CFF5451BC1EC571793602CEE63A68AAC0DC45DB4BCA581B3B5F`) reveals a **possible upstream indirect dispatcher**. Function RVA `0x69EC70` calls `receiver.vptr+0x10` with a pointer to a refcounted current entry (`&puStack_108`), at trace line 542. That entry is copied from the selected vector wrapper's current element (lines 515–540); a manager listener can replace the original wrapper before traversal (lines 324–355). The receiver is obtained through a registry node's `+0x30` interface, calling its virtual `+0x08` method (lines 525–535). The already observed position component table at RVA `0x26B4FB0` has `+0x10 → 0x6984C0`, **but the returned receiver has not been identified as that position component**, and no concrete runtime call of `0x6984C0` is established. The retained Ghidra script `artifacts/rea/Rr2ManagerNotifyTraceV1.java` SHA-256 `460731D42B0EC5AE57008D9125E7DD7622F4D8CEEEC0080D0753A37A8125941F` does not itself enforce the executable SHA; preserve this as a same-project static candidate, not independent exact-build/runtime qualification.

A separate **read-only**, bounded Ghidra 12.1.2 check completed successfully (job `rr2-registry-accessor-ps1-20261108-unique-01`, exit 0). Its `artifacts/rea/ghidra-registry-accessor-v1.txt` output (SHA-256 `849B6B6DBB280D94DEE2038656FA18076BD4D4615A6437049D592DA677756A27`) shows `0x6A18C0` is a lazy global registry/tree accessor (`_DAT_14336EF58`), **not** a direct position getter. The upstream bootstrap `0x8730C0` calls `0x8652A0` to rebuild a source-list wrapper before calling `0x69EC70`; `0x8652A0` invokes each input element's virtual `+0x50` method and appends its returned item. Thus the event entry is potentially **transformed/cloned**, not simply the original input object. The focused decompiler reported completion but function bodies of one byte in its metadata; this supports a candidate structural reading, not a fully verified control-flow body or exact-build source binding. No game or VM was accessed.

A further read-only reference check (Ghidra job `rr2-registry-function-xrefs-ghidra-20261108-unique-01`, exit 0; `artifacts/rea/ghidra-registry-refs-v2.txt` SHA-256 `7189D01A64FEE461569D33AEC9D38BDE201C444155316253BDEF15DEEE9D3252`) found four indexed references to the registry global `0x336EF58`, all inside the lazy accessor `0x6A18C0`. The latter has one indexed code caller `0x69EF84` inside `0x69EC70`, and `0x69EC70` has one indexed code caller `0x87339A` in `0x8730C0`. The position vptr RVA `0x26B4FB0` has **zero indexed references** in this retained project, though separately verified raw instructions write it; this is an **index-coverage limit, not absence of use**. The narrow registry-reference route did not identify the returned component, so it is parked rather than expanded into an indiscriminate scan.

**Next useful discovery when justified:** identify node `+0x30` virtual `+0x08` receiver identity from a stronger owner-bound source or a separately admitted live trace; require its vptr `0x26B4FB0` before claiming dispatch to the position callback `0x6984C0`. Actual player/source ownership, execution, changed-state, independent freshness and restart behavior remain unqualified.
