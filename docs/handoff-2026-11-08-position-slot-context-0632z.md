# RR2 current-build position slot context — static evidence (2026-11-08 06:32 UTC)

**Finding:** The sole retained DATA reference to the position-owner caller at RVA `0x6984C0` was a **Windows unwind-function entry in `.pdata`**, not an independently discovered code caller. Separately, raw initialized `.rdata` at candidate address `0x26B4FB0` contains four sequential absolute 64-bit addresses, including `0x6984C0` as its third entry. This supports a **candidate dispatch-table** hypothesis when combined with earlier ctor/dtor V8 evidence, but does not qualify a vtable, live owner, active call, or XYZ reader.

## Provenance and bounds

- Authoritative checkout: `C:\work\riftreader2` (AMD-DESKTOP); existing Ghidra project `artifacts/rea/RiftNativeFocusedV2`, retained program `rift_x64.exe`, image base `0x140000000`.
- Imported executable SHA-256 **metadata** `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; verified by script guard, **not a fresh PE rehash**.
- Script: `artifacts/rea/position-owner-slot-review2/Rr2PositionOwnerSlotContextExport.java`; SHA-256 `dee2c628ec7b9cd24bd89b476fa6434879e1264d1065a939eb2edf4a2b09d493`.
- Host-only job `rr2-position-owner-slot-context-20261108-root-01` **PASS, exit 0**, finished 2026-11-08 06:32:25 UTC; `-readOnly -noanalysis -max-cpu 1`, marker `RR2_POSITION_OWNER_SLOT_COMPLETE`.
- Three fixed initialized 128-byte windows, total 384 bytes; at most eight direct references per anchor; raw LE64 decoding only; **no pointer following, analysis, disassembly, data creation, or live process access**.

## Observed exact mapping

| RVA anchor / section | Existing retained data | Outcome |
|---|---|---|
| `0x363E848` / `.pdata` | `_IMAGE_RUNTIME_FUNCTION_ENTRY`, 12 bytes | DATA ref to function RVA `0x697F20`; this is unwind metadata |
| `0x363E8B4` / `.pdata` | `_IMAGE_RUNTIME_FUNCTION_ENTRY`, 12 bytes | DATA ref to function RVA `0x6984C0`; this **reclassifies** the prior xref as unwind metadata, not a caller |
| `0x26B4FB0` / `.rdata` | Undefined in current Ghidra listing; raw initialized bytes | Four contiguous LE64 values shown below; no direct refs *from the anchor* in retained metadata |

Candidate `.rdata` contiguous 8-byte slots (raw values are absolute VAs, image base `0x140000000`):

| Offset | Raw VA | RVA |
|---:|---|---|
| `+0x00` | `0x1405A9990` | `0x5A9990` |
| `+0x08` | `0x140697F20` | `0x697F20` |
| `+0x10` | `0x1406984C0` | `0x6984C0` |
| `+0x18` | `0x140698300` | `0x698300` |

The prior xref report `handoff-2026-11-08-position-owner-xrefs-0628z.md` remains an accurate index report; its open question about the `0x363E8B4` DATA reference is now **resolved** as `.pdata` unwind metadata. The candidate table's function-like layout and earlier ctor/dtor V8 cross-reference warrant a narrow dispatch-site follow-up; neither fact establishes active runtime usage, object layout, ownership, source freshness, or retrievable world XYZ.

**Next useful check:** correlate the previously retained ctor/dtor V8 writes with this exact `.rdata` address, then inspect bounded existing indirect-call sites without asserting method-slot meaning. No lab actions, guest changes, game input, or fresh process sampling occurred.
