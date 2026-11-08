# RR2 constructor/table bridge — bounded static correlation (2026-11-08 06:43 UTC)

**Discovery:** The earlier exact retained-PE constructor-address match at RVA `0x26B5040` is the **19th contiguous 8-byte code-address-shaped value** (zero-based candidate slot **18**) starting from `.rdata` RVA `0x26B4FB0`. The run then changes to non-address-shaped numeric values at +`0x98` and +`0xA0`, followed by a fresh function-address-shaped run starting +`0xA8`. This supports a **candidate table boundary and virtual-slot arrangement**; it does **not** prove a real vtable, factory, active dispatch, live player owner or XYZ source.

## Evidence/identity

- Source script: `artifacts/rea/constructor-vtable-bridge-review1/Rr2ConstructorVtableBridgeExport.java`; SHA-256 `449626e90b5251f985f3be0488e9273bdabaf3be4b00cae5a8f9f25c1cd25c4c`.
- Retained Ghidra project `artifacts/rea/RiftNativeFocusedV2`, program `rift_x64.exe`, image base `0x140000000`; imported PE SHA-256 **metadata guard** `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` (**not a fresh installed executable rehash**).
- Host-only job `rr2-constructor-vtable-bridge-20261108-root-01`: **PASS exit 0**, finished 2026-11-08 06:43:36 UTC, marker `RR2_CONSTRUCTOR_VTABLE_BRIDGE_COMPLETE`. Ghidra read-only/noanalysis, no live process.
- Fixed `.rdata` read: RVA `0x26B4FB0` through `0x26B50CF`, exactly `0x120` (**288**) bytes = **36 LE64 QWORDs**. No pointer following. Both exact anchors `0x26B4FB0` and `0x26B5040` are currently **undefined** in retained listing and have zero existing incoming/outgoing references at those exact addresses.

| Offset from `0x26B4FB0` | Raw LE64 value | Interpretation |
|---:|---|---|
| `+0x00` (candidate index 0) | `0x1405A9990` | Known static thunk entry from prior RTTI windows |
| `+0x08` through `+0x88` (indices 1–17) | 17 additional image-address-shaped values | Only numeric grouping; not individually qualified virtual methods |
| `+0x90` (candidate index **18**) | `0x140698170` | Exact constructor RVA `0x698170` address match from the [offline PE scan](handoff-2026-11-08-constructor-static-scans-0641z.md) |
| `+0x98` | `0x4036DB6E3E99999A` | Numeric/non-image-pointer-shaped; **possible** boundary |
| `+0xA0` | `0x0000000041800000` | Numeric/non-image-pointer-shaped |
| `+0xA8` | `0x1405A9990` | Start of another code-address-shaped run; does not prove a second vtable |

This observation reconciles the zero incoming Ghidra xrefs to `0x26B4FB0` (untyped data can lack indexed references) with the exact raw pointer hit 0x90 bytes later. Neither the label “constructor” nor slot index 18 implies a factory method: a path from a *live object instance* to this table and a reachable call site are still unverified.

**Next focused discovery:** inspect exact existing ctor/dtor instructions that appear to write a table pointer, and whether the written address is `0x26B4FB0` versus another subtable. Keep current-process identity, owner and field semantics unqualified until tested. No lab input/deployment/native sample occurred.
