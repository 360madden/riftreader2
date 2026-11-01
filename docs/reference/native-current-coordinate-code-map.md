# Current-build RIFT native coordinate code map — 2026-10-31

**Status: verified offline CODE path, no live-qualified player DATA pointer.** This note applies only to executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` (`rift_x64.exe`, 60,493,640 file bytes). All offsets are **module RVAs**, not process absolute addresses.

## Repeatable evidence

- Bounded read-only Windows PE scan located exactly one null-terminated `.rdata` string for each coordinate key, then evaluated x86-64 RIP-relative `LEA` candidates in `.text`; file SHA was rechecked before scanning.
- Workbridge retained offline jobs: `rr2-coordinate-string-scan-20261031-01`, `rr2-coordinate-code-xrefs-20261031-01`, `rr2-coord-detail-code-slice-20261031-01`. A 400-byte original `.text` slice at RVA `0x9BA900` was independently decoded with cloud GNU objdump; `Inspect.Unit.Detail` field-key assignments aligned at exact instruction boundaries.
- No game process, addon, VM, controller, UI, memory write or RIFT file was changed. This was static inspection of the installed executable only.

## Reproduce this discovery

The committed SHA-gated, offline-only utility `scripts/find_native_api_xrefs.py` reproduces the coordinate key/xref evidence with no game process access:

```powershell
& C:\Python314\python.exe scripts\find_native_api_xrefs.py `
  --exe C:\PROGRA~2\Glyph\Games\RIFT\Live\rift_x64.exe `
  --sha256 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8 `
  --fields coordX coordY coordZ `
  --start-rva 0x9B8900 --end-rva 0x9BAB00
```

All **five** focused synthetic-PE tests passed; the actual installed EXE run returned exactly the three documented key references (retained jobs `rr2-api-xref-offline-tests-20261031-01` and `rr2-api-xref-live-pe-check-20261031-01`). The scanner intentionally returns **candidate opcode references**, not assertions about instruction boundaries or live pointers.

## Literal coordinate keys and code cross-references

| API key | Unique `.rdata` RVA | `Inspect.Unit.Detail` key-reference RVA |
|---|---:|---:|
| `coordX` | `0x26D1FC4` | `0x9BA9C8` |
| `coordY` | `0x26D1FCC` | `0x9BA9F7` |
| `coordZ` | `0x26D1FD4` | `0x9BAA23` |

These three references occur inside the previously isolated current `Inspect.Unit.Detail` native region, RVA `0x9B89BA..0x9BAABA`. Each uses RIP-relative `LEA R8,[key]`; the common subsequent calls `0x16893D0` and `0x1689A60` build Lua result fields. Those two Lua glue functions are **not** the underlying XYZ getter.

## Other identity/zone keys in the same native routine

A second scoped run of the same utility found additional Lua-key assignment sites, valuable for anchoring identity and same-zone comparison once native values can be followed. They are **field-name code references only**, not discovered data offsets.

| Field key | Reference RVA(s) |
|---|---|
| `id` | `0x9B8AB3` |
| `zone` | `0x9B9DB6` |
| `level` | `0x9B9ECB` |
| `combat` | `0x9B9FC2` |
| `mentoring` | `0x9BA7B4`, `0x9BA7DD`, `0x9BA825` |

Provenance: bounded retained job `rr2-native-unit-identity-field-xrefs-20261031-01`; no process access. Different literal occurrence counts mean a key is not necessarily unique throughout `.rdata`.

Other offline key xrefs (candidate alternate consumers, not yet function-qualified):

| Code region | X RVA | Y RVA | Z RVA |
|---|---:|---:|---:|
| A | `0x952CF0` | `0x952DCF` | `0x952EA6` |
| B | `0x96C8FE` | `0x96C94F` | `0x96C9A0` |
| C | `0x9A9544` | `0x9A9571` | `0x9A959E` |
| D | `0xA06696` | `0xA066BA` | `0xA066DE` |

## Likely dimension-item orientation keys (negative control for player facing)

The exact-SHA scanner finds `pitch`, `roll` and `yaw` field-name instructions near two alternative XYZ code regions. **Important cross-API collision:** the original RIFT [Inspect.Dimension.Layout.Detail](https://www.seebs.net/rift/pts/inspect_dimension_layout_detail.html) documents precisely `coordX/Y/Z` plus `pitch/roll/yaw` for placed **dimension items**, not player units. These clusters therefore plausibly represent dimension-item placement/rotation; they must **not** be treated as a player-facing lead without contrary code-level ownership proof.

| Field | Unique literal RVA | Field-key LEA instruction RVA(s) |
|---|---:|---|
| `pitch` | `0x26D1FDC` | `0x952FA5`, `0xA0671E` |
| `roll` | `0x26A7EE4` | `0x953085`, `0xA06766` |
| `yaw` | `0x26D1FE4` | `0x953165`, `0xA06742` |

The `yaw` and `pitch` strings are adjacent to `coordX/Y/Z` in `.rdata`; their field-assignment code is **not** the same as the `Inspect.Unit.Detail` XYZ assignment at `0x9BA9..`. The distinct `orientation` string at `0x26DC918` has a separate candidate key-reference RVA `0x194B3B`; neither `heading` nor `rotation` had an xref using the scanner's targeted LEA pattern, and no exact null-terminated `facing` key was found.

Provenance: passed offline retained job `rr2-native-orientation-field-xrefs-20261031-01`, `--fields yaw pitch roll heading orientation rotation facing`, exact executable SHA. Scan results remain **opcode candidates** until decoded at valid instruction boundaries and traced to value-producing functions. Next: check nearby dimension-only keys (such as `scale`, `crated`, `selected`) and trace the two clusters to confirm their **dimension-item** owner. Keep player-facing discovery separate; stationary-turn validation would require independently player-owned code and the existing guarded VM workflow.

## Native XYZ data access within `Inspect.Unit.Detail`

At RVA `0x9BA957` the code calls native function `rift_x64.exe+0x698460` with the current unit-associated object in `RCX`. It treats the return in `RAX` as a pointer to at least **three adjacent 32-bit values**:

1. `MOVSD XMM6,[RAX]` loads the first 8 bytes (two 32-bit lanes).
2. `MOV EBX,[RAX+0x08]` loads the third 32-bit lane.
3. Before publishing `coordX`, the code passes the first lane through helper RVA `0xA0E890` (`MOVAPS XMM0,XMM6`).
4. For `coordY`, it selects the second lane (`SHUFPS XMM0,XMM0,0x55`) and calls the same `0xA0E890` helper.
5. For `coordZ`, it moves the third lane into `XMM0` (`MOVD XMM0,EBX`) and calls the same `0xA0E890` helper.
6. Each result is converted to a Lua number and assigned to the corresponding coordinate key.

**Numeric conversion resolved offline:** Current-build helper RVA `0xA0E890` executes `MULSS` by exact float32 `100.0` (constant RVA `0x26A33E8`), calls integer-rounding routine `0x129C0F0`, converts its signed `int32` result to float32, then executes `MULSS` by float32 `0.009999999776482582` (constant RVA `0x26A33CC`). The rounding routine compares against `0.0` and uses `0.5` on sign-dependent branches; its positive branch includes an unresolved indirect import call, so extreme/NaN/tie edge cases are not yet qualified. For ordinary finite world positions, the API output is a **hundredth-quantized coordinate**, not necessarily the original unrounded float32 stored in memory.

**Separate sign-mask operation:** At `0x9BA9A4` an `XORPS` uses 16-byte mask RVA `0x26A7A10` (`0x80000000` in each lane), but it acts on a supplemental stack result from `+0x1144B70` at `[rsp+0x40]`, **not** on the XYZ input lanes held in `XMM6`/`EBX`. Do not negate raw XYZ merely because this neighboring operation exists.

The adjacent code also calls `+0x6983F0` on the unit-associated object and `+0x1144B70` with stack buffers. **The observed three-lane layout is a code-access fact**, but it does not by itself prove a stable player-owned pointer or the same object address in both VMs.

## Exact object offsets and cached-position refresh (new current-build evidence)

Both accessors are now decoded at real instruction boundaries from the exact installed executable:

| Native accessor | Behavior | Returned object-relative pointer |
|---|---|---|
| `0x698460` | Saves the object, calls `0x6996C0`, returns `LEA [object+0x48]` | Float32 XYZ at **`+0x48`, `+0x4C`, `+0x50`** |
| `0x6983F0` | Saves the same object, calls `0x6996C0`, returns `LEA [object+0x60]` | Auxiliary transform-like record starting **`+0x60`** (call site copies 0x24 bytes; exact semantics pending) |

**Important freshness finding:** Native routine `0x6996C0` is not a trivial no-op. One branch resolves the object's `+0x100` handle through global state and calls native `0x612EE0` to produce a three-float stack vector. It compares that vector to `object+0x48/+0x4C/+0x50`, copies newly changed values into those three fields, and invokes a further notification-like function `0x78C2A0` conditionally. Another branch, gated on object `+0x100/+0x108`, obtains source vectors via `0x612B50` and `0x612960`, copying XYZ and auxiliary fields. These are **derived/cached object fields with an explicit refresh path**, not yet independently proven canonical engine position memory. A passive reader of `object+0x48` may still be stale if the refresh path has not run in that epoch. Do not equate field offsets with a durable module root.

**Upstream source path partially decoded:** In the active-handle branch, `0x612EE0` calls resolver `0x6126F0`, obtains an object pointer through a stack out-param, and copies three float32 values from **resolved object `+0xF8/+0xFC/+0x100`** to its XYZ output. The resolver walks reference-like entries under a separate source's `+0x48` pointer, uses begin/end fields `+0x28/+0x30`, and compares an identity-like member `+0x18`; its full type/ownership is not yet established. In an alternate branch, `0x612B50` reads a source provider pointer at `RCX+0x58`, passes the shared clock into an indirect virtual function, and copies three returned floats (or falls back to a supplied vector). **These deeper offsets are code-derived source candidates, not verified player world-position locators**, and interpolated/cache sources remain possible. Passed exact-SHA job `rr2-serialized-native-upstream-xyz-20261031-01` and bounded resolver slice job `rr2-serialized-native-upstream-resolver-20261031-01`, independently disassembled offline.

The adjacent function at `0x698480` reads the same global clock slot `module+0x33DC2B0` used by health/resource code and writes an object timestamp-like member `+0xD4`; that reinforces a shared timebase, **not** a proven shared HP/XYZ player owner. Exact SHA-gated passed jobs: `rr2-serialized-native-xyz-accessor-20261031-01`, `rr2-serialized-native-xyz-refresh-20261031-01`, and `rr2-serialized-native-xyz-refresh-full-20261031-01`; independently disassembled with GNU objdump. Next trace targets: object origin in `Inspect.Unit.Detail`, underlying entity source calls `0x612EE0`/`0x612B50`, and a version-gated module-root locator validated against separately advancing player API data in both labs.

## Follow-up trace failures and serialized recovery

Parallel workers attempted bounded, **read-only** current-build extraction, but several Windows terminal invocations stalled for roughly 1,000 seconds without returning results. **The stalled attempts themselves yielded no evidence:** `rr2-child-coordtransform-20261031-01` (helper bytes), `rr2-coord-owner-pdata-20261031-01` (getter function boundaries), plus alternate XYZ and shared-resource ownership requests. No new unit-owner root or stable data offset was found. Native HP/mana/energy/power/charge getters share clock slot `+0x33DC2B0`, but **a common time source is not a common player-owned component**; see [health/resource map](native-current-client-code-map.md).

**Recovery succeeded after serializing the commands:** `rr2-single-serialized-helper-20261031-01` retrieved the exact helper machine code; `rr2-serialized-transform-constants-20261031-01` verified `100.0`, `0.01` and the sign mask; `rr2-serialized-transform-roundconst-20261031-01` verified `0.0` and `0.5` constants. Cloud GNU objdump independently decoded both bounded byte slices. All three retained jobs passed with exact installed SHA `1935A05C...`; they accessed no game process. This resolves the ordinary finite XYZ rounding pipeline, **not** the owner chain, full rounding edge semantics, or a live player pointer.

Concurrent host extraction is a suspected but **unproven** cause of the stalls. Use one heavy Workbridge/REA job at a time, reusing retained evidence and exact job IDs. The ignored Ghidra project remains available. Do not promote the returned three-lane pointer into production telemetry until ownership and cross-lab changed-state evidence are verified independently.

## Field meaning and validation gates

- The original RIFT `Inspect.Unit.Detail` API documents `coordX`, `coordY`, and `coordZ`, and `Event.Unit.Detail.Coord` provides changed-coordinate values keyed by unit ID. Original ArtifactTracker source describes X as east, Y as vertical, Z as south. Those are independent validation references, not native locator proofs.
- Travel bearing computed from changing XYZ is **not** player facing while stationary; RIFT addon authors report facing is unavailable through those coordinate APIs. Treat native rotation/heading as a separate investigation.
- The old verified module `+0x32E0200` → player owner → XYZ `+0x320/+0x324/+0x328` recipe applies to executable SHA `7C356C9D...`, **not** this build. See [XYZ field catalog](xyz-field-catalog.md).
- Next offline step: decompile `+0x698460` and related helper functions to find a current-build unit-owner path. Then use the existing exact-build/PID/start-gated native reader for **read-only** same-unit observations in both labs. Reject UI/cache copies and require independent changed-state and full-restart tests before promoting a locator.
- Lab 1's last eight-minute source-freshness gate failed and Lab 2's earlier passing gate is from a prior epoch. No supervised movement pulse should occur until current-epoch freshness and exclusive controller/screenshot/lease checks pass; reuse the existing workflow.

See [current health/resource code map](native-current-client-code-map.md) for the companion static fields and the distinct no-live-pointer limitation.
