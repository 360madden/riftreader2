# Current-build RIFT native coordinate code map — 2026-10-31

**Status: verified native CODE path and two-lab current-process lookup candidates; no production-qualified passive-fresh/restart-safe DATA locator.** This note applies only to executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` (`rift_x64.exe`, 60,493,640 file bytes). All offsets are **module RVAs**, not process absolute addresses.

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

**Unit-to-position-component selector now decoded:** Inside current `Inspect.Unit.Detail`, RVA `0x9B8FA1` reads signed `int32` component-index metadata at **module RVA `0x2F588A0`**. With the unit-entity pointer in `R15`, it selects the byte at `unitEntity + 0x18 + thatIndex`; if the selector is not `0xFF`, it reads `componentTable = *(unitEntity+0x78)` then `component = *(componentTable+selector*8)` and stores that position component pointer at stack `[rbp-0x60]` (RVA `0x9B8FBB`). At `0x9BA947` this same stack slot is loaded into `RDI` and passed to the accessor `0x698460`. The missing-selector branch instead records null (`0x9B8FC1`). This is a verified **native code lookup topology**: *unit entity → dynamic component selector → component table → position-component object → XYZ cache fields*.

**Manager root and entity lookup:** The entity pointer in `R15` comes from native call **`0x69FFD0`** at `0x9B8A36`, using a manager returned by **`0x4A4750`** and the current unit-identity/handle stack argument. `0x4A4750` first loads a singleton pointer from exact current-build **module RVA `0x33624A8`**, performing lazy initialization when it is null. `0x69FFD0` then uses an identity lookup structure under the manager's `+0x50` (via helper `0x58C990`) to find and return an entity pointer; `0x6A0040` is the related out-param lookup used elsewhere. This establishes an offline **module-rooted native lookup *code path***: `module+0x33624A8 → manager/handle lookup → unit entity → dynamic component selector (module+0x2F588A0) → position component → +0x48 XYZ`. It is **not by itself a production-qualified player locator**: the static key mapping and native self-key root are now decoded below, but actual runtime ownership, changed-state freshness and restart qualification remain separate gates. Both manager and selector module RVAs belong only to the exact pinned build; they are not the old SHA `7C356...` player root. Passed exact-SHA jobs `rr2-serialized-unit-object-slot-20261031-01`, `rr2-serialized-unit-select-context-20261031-01`, `rr2-serialized-unit-entity-origin-20261031-01`, and `rr2-serialized-unit-manager-root-20261031-01`, with independently decoded instruction boundaries.

**Historical two-lab memory corroboration (read-only retained snapshots, not live telemetry):** Both complete, SHA-verified main-EXE `.data` captures from 2026-10-31 ~21:27 UTC contain nonzero values at the manager pointer slot and the same signed component-index value `34` at module RVA `0x2F588A0`. Each 4 KiB source chunk's byte SHA was independently rechecked before extracting these values:

| Lab | Exact prior process PID/start ticks | Manager slot at `module+0x33624A8` | Saved manager pointer | Position component index |
|---|---|---|---|---:|
| Lab 1 | `8164 / 639290507142219120` | `0x7FF76CC424A8` | `0x23D3FAB0D50` | `34` |
| Lab 2 | `7012 / 639290507554340644` | `0x7FF67BD724A8` | `0x21839E50EA0` | `34` |

Provenance: passed job `rr2-serialized-two-lab-manager-slot-20261031-01`; snapshot JSON hashes Lab1 `8A42DF19375EBF6B139B61244C4B08909A9D986C67F7B5940BA7818D6EA10E91` and Lab2 `74651FA7937E7DB12CBCBC3E4605B2B795285F47E034386D4B139CB8A5F654C9`. **This is not a fresh observation or a player entity locator**: the snapshots cover the main module `.data`, not the heap objects pointed to by the manager, and the unit-handle mapping has not been followed. Do not treat these absolute historical addresses as usable after a PID/start change. Recheck with exact current identity and independent changed-state data before qualification.

**Important freshness finding:** Native routine `0x6996C0` is not a trivial no-op. One branch resolves the object's `+0x100` handle through global state and calls native `0x612EE0` to produce a three-float stack vector. It compares that vector to `object+0x48/+0x4C/+0x50`, copies newly changed values into those three fields, and invokes a further notification-like function `0x78C2A0` conditionally. Another branch, gated on object `+0x100/+0x108`, obtains source vectors via `0x612B50` and `0x612960`, copying XYZ and auxiliary fields. These are **derived/cached object fields with an explicit refresh path**, not yet independently proven canonical engine position memory. A passive reader of `object+0x48` may still be stale if the refresh path has not run in that epoch. Do not equate field offsets with a durable module root.

**Upstream source path partially decoded:** In the active-handle branch, `0x612EE0` calls resolver `0x6126F0`, obtains an object pointer through a stack out-param, and copies three float32 values from **resolved object `+0xF8/+0xFC/+0x100`** to its XYZ output. The resolver walks reference-like entries under a separate source's `+0x48` pointer, uses begin/end fields `+0x28/+0x30`, and compares an identity-like member `+0x18`; its full type/ownership is not yet established. In an alternate branch, `0x612B50` reads a source provider pointer at `RCX+0x58`, passes the shared clock into an indirect virtual function, and copies three returned floats (or falls back to a supplied vector). **These deeper offsets are code-derived source candidates, not verified player world-position locators**, and interpolated/cache sources remain possible. Passed exact-SHA job `rr2-serialized-native-upstream-xyz-20261031-01` and bounded resolver slice job `rr2-serialized-native-upstream-resolver-20261031-01`, independently disassembled offline.

The adjacent function at `0x698480` reads the same global clock slot `module+0x33DC2B0` used by health/resource code and writes an object timestamp-like member `+0xD4`; that reinforces a shared timebase, **not** a proven shared HP/XYZ player owner. Exact SHA-gated passed jobs: `rr2-serialized-native-xyz-accessor-20261031-01`, `rr2-serialized-native-xyz-refresh-20261031-01`, and `rr2-serialized-native-xyz-refresh-full-20261031-01`; independently disassembled with GNU objdump. Next trace targets: object origin in `Inspect.Unit.Detail`, underlying entity source calls `0x612EE0`/`0x612B50`, and a version-gated module-root locator validated against separately advancing player API data in both labs.

## Player-owned transform-matrix candidates — 2026-11-01 UTC

Six read-only specialist tracks found two **nine-float32 Y-rotation-like matrices**
in the already verified native player position component. The coordinator
independently decoded the original retained component snapshot bytes:

| Position-component offset | Raw interpretation | Evidence status |
|---|---|---|
| +0x48/+0x4C/+0x50 | Float32 XYZ | Previously decoded position cache |
| +0x60..+0x83 | First row-major 3×3 float32 matrix | Strong structural orientation candidate |
| +0x88/+0x8C/+0x90 | Second XYZ copy | Equal to first XYZ in inspected frames |
| +0x94..+0xB7 | Second, nearly identical 3×3 matrix | Strong structural orientation candidate |

Each matrix closely fits [cos(theta),0,-sin(theta); 0,1,0; sin(theta),0,cos(theta)].
Using atan2(m[2,0],m[0,0]) as a *numeric descriptor*, not qualified game yaw:

| Retained native frame | First matrix angle | Second matrix angle |
|---|---:|---:|
| Lab1 01:30 UTC, PID8164 | 3.465055° | 3.464628° |
| Lab2 01:32 UTC, PID7012 | 32.810855° | 32.810213° |
| Lab2 13:46 UTC, same PID7012 | 32.810855° | 32.810213° |

The off-axis terms are approximately zero; unit cosine/sine norm error is
about 10^-7. The already disassembled native accessor RVA 0x6983F0 returns
positionComponent+0x60; its caller copies 0x24 bytes. This independently
supports the first matrix layout.

**New decisive exact-PE code evidence:** RVA 0x612960 reads a
provider-returned float32 quaternion (x,y,z,w) and computes all nine
components of the canonical row-major 3×3 rotation matrix, with
diagonal terms 1−2(y²+z²), 1−2(x²+z²), 1−2(x²+y²) and cross terms
2(xy±wz), 2(xz±wy), 2(yz±wx); the constant at RVA 0x26A33D8 is
float32 1.0. The native function writes those nine floats at output
offsets +0..+0x20 (RVA 0x612A9E..0x612B15). If its provider is
null, RVA 0x612B1C..0x612B30 **copies a cached 36-byte fallback**;
this explains why a passive cached matrix alone is not freshness proof.
Within position refresh 0x6996C0, RVA 0x6999FE writes the first
matrix's ninth float at component+0x80; an R9=1 follow-up
0x699A04..0x699A21 writes the second matrix at +0x94..+0xB4.
The active branch also constructs the second matrix via
0x613080/0x698EC0. This is full SHA-pinned, bounded instruction
decoding of the saved PE, not a live behavior claim.

**Upstream active-handle source:** The fully decoded 0x613080 path
calls 0x6126F0 and, when its source flag at object+0x35 is set,
copies a 36-byte rotation matrix from resolved object
**+0xD4..+0xF7**; the already verified 0x612EE0 reads XYZ
immediately after that at **+0xF8/+0xFC/+0x100**. The matrix and
position therefore occupy one contiguous candidate source layout.
If this source is unavailable, 0x613080 instead finds the entity
position component via selector module+0x2F588A0 and copies its
cached +0x60 matrix (circular freshness fallback). The intermediate
0x698EC0 compares and copies nine floats to component+0x60..+0x80,
then computes a third-column dot product involving the +0x94 matrix
and stores a result-like value at component+0xF0, with a +0xF4 flag.
These are **native instruction facts**, not proof of canonical owner,
a reliable angle, or passively advancing facing.

Which matrix is current versus cached, the angular sign/axis, and
**whether either is character-body facing** remain unverified. The
reviewed snapshots did not include a deliberate turn. These buffers
are separate from dimension-item Lua yaw/pitch/roll.

**2026-11-01 static disconfirmation of passive matrix freshness:** The
exact-build `0x6996C0` refresh branches test position component
`QWORD(+0x100)` and then `BYTE(+0x108)`; when both are zero the accessor
returns without consulting a pose provider. Both were zero in retained
Lab2 samples. The optional provider selector metadata indexes 22/46
are absent (`0xFF`) on both retained self entities. Provider helpers
`0x612960` (quaternion to 3×3) and `0x612B50` (XYZ) call a
`+0x58` provider vtable slot when available, but otherwise copy a
cached fallback. `0x698480` writes the shared game clock to position
component `+0xD4`; that timestamp advance **does not prove fresh
rotation**. Thus the nearly identical 32.81° matrices remain
stale-capable, and may not encode live body heading.

**Separate actor/model world-transform candidate (offline exact PE):**
Function `0x613800` selects self entity metadata index 30
(`module+0x2F58490`, retained player component-table slot **17**)
and position index 34 (slot 6), then calls `0x687320` to copy the
secondary position matrix/XYZ to slot-17 `+0x398..+0x3B8` (nine
float32) and `+0x3BC..+0x3C4`. `0x688F20` obtains a conditional
render object via `0x67BA80`, multiplies slot-17 matrices at
`+0x398` and `+0x3EC` via `0x676B40`, and writes the composed 3×3
to render-object `+0xA0..+0xC0`, XYZ to `+0xC4..+0xCC`.
Normal render pointer is `QWORD(slot17+0x410)` only when
`(slot17+0x1C0)&1==0`; alternate reference paths have NOT been
runtime-qualified. This is a plausible **model/world rotation
candidate**, not established avatar-body heading. No slot-17/render
bytes have yet been sampled. Next: exact-epoch bounded read with
rechecked ownership, controlled A/D before/after and independent
visual/camera negative control, then full game restart.

**Actor/world transform refinement, exact SHA offline:** Accessors
`0x698410` and `0x698440` provide the secondary position matrix
`position+0x94` (nine float32) and XYZ `position+0x88`,
respectively. `0x687320` copies the secondary matrix to
`actor+0x398` and computes `actor+0x3BC..0x3C4` as
`positionSecondaryXYZ + actor(+0x4F8/+0x4FC/+0x500)
+ actor(+0x770/+0x774/+0x778)` by axis. Matrix helper `0x676B40`
performs ordinary row-major multiplication:
`renderMatrix = (actor+0x398) × (actor+0x3EC)`; `0x688F20`
writes this 3×3 at `render+0xA0` and actor XYZ at `render+0xC4`.
Therefore render XYZ is *not* necessarily the same as Lua's
hundredth-quantized primary XYZ at position `+0x48`, and a simple
angle extracted from either cached position matrix is **not
absolute player body facing**. If actor bit0 at `+0x1C0` is set,
`0x67BA80` uses indirect reference helpers `0x98040/0x103970`;
these are unqualified for passive pointer following.

A future **read-only, identity-bracketed** sample should resolve actor
and position selectors from current module metadata and full player
key (historical slot17/slot6 are only evidence), assert aligned,
non-null, disjoint owner pointers, then record bounded `position+0x48`
length `0x70`, `position+0x100` length9, actor regions
`+0x1C0` length4, `+0x398` length0x30, `+0x3EC` length0x24,
`+0x410` length8 and translation triplets. Follow the renderer
pointer only when the normal bit0-clear branch holds. Check all
matrices finite/near-orthonormal and multiplication/XYZ relationships,
then re-read every ownership anchor and relevant matrix. Correlate
native-primary XYZ to an independent same-unit addon coordinate read
after hundredth-unit quantization, with native-before/API/native-after
ordering. No slot17 or renderer bytes were sampled in this trace,
nor was a controlled turn or full restart performed.

Original source JSON files and independently verified SHA256 digests:
- Lab1 artifacts/native-unit-manager/lab1/5a654fbadb324803a6bba83520329d46/component-values.json — E5DBE57BBE80B9D6D03228630CBD5E96DF80975B5263D01CDD6B91FDA0B26971
- Lab2 artifacts/native-unit-manager/lab2/a4e8474dbfef4a1490b7cee6655e46c8/component-values.json — FE34732A410CDF3098635F42563F8F5B43757A7AE4981783F8992C2ED6B41253
- Lab2 later artifacts/native-unit-manager/lab2/74d4209587794a8c9ffae0559517db6f/component-values.json — 77882FB170113031A241EE36D2805FF5C465DDE4A58BE9EFD297D21C65C87

**Next dual-method experiment:** Under fresh current-epoch source freshness
and sole-owner reviewed controller lease, read native-before, execute one
short stationary A/D turn with STOP/release, read native-after, and inspect
independent visual change. Require matrix rotation coherent with the actual
turn while XYZ stays approximately unchanged; separately establish passive
freshness and full game exit/relaunch recovery. The historical Lab1 480s
FAIL and prior-epoch Lab2 pin cannot be bypassed.

## Native self identity and deterministic entity lookup — 2026-11-01 UTC

The missing identity conversion is now decoded from the **same pinned build**. The actual `Inspect.Unit.Detail` prologue starts at RVA `0x9B8960`; its unwind records split at `0x9B89BA`, which was previously mistaken for the full routine's start.

- At `0x9B89A7`, helper `0xA1AAA0` converts the Lua argument to a 64-bit key saved at `[rsp+0x48]`. It accepts a Lua string and delegates to `0xA07060`.
- The literal at `0x26D0D3C` is **`player`**. Its branch calls singleton accessor `0x49A020` and reads the key at returned object **`+0x360`**. The accessor's nonnull path loads **`[module+0x33623E0]`** and returns it. This is a native self-key root, distinct from entity-manager root `0x33624A8`.
- The explicit-ID branch requires `u` followed by 16 hexadecimal characters, then NUL or a dot. Import `api-ms-win-crt-convert-l1-1-0.dll!_strtoui64` at IAT RVA `0x25F00C0` parses `input+1` in base 16. Thus a **bare** `u035400012FA2D207` parses to key `0x035400012FA2D207`. Additional validity checks remain, and dotted suffixes enter further resolution; do not apply bare-ID semantics to those suffixes.
- Other exact literals include focus, mouseover, group, and target. **Important correction:** in this parser target is a **dotted suffix**, not a proven initial standalone alias. The parser handles focus via 0x54F2C0, mouseover via 0x550420, and group via 0x54F2D0; these are distinct sources.

**Native player.target follow-up:** After a base unit key, 0xA0722E..0xA07359 parses the dotted target suffix at literal RVA 0x26A5E84, resolves the base entity using manager 0x6A0040, selects its health-associated component using module selector 0x2F57850 and entity+0x78 component table, then calls native getter **0x5ECCA0** to produce the next key. Missing entity (0xA07322), absent selector (0xA0733D) or null component (0xA0734E) produce a zero key without necessarily invalidating syntax; a genuinely invalid expression instead clears the validity flag at 0xA075A4. Its data ownership and live target change behavior remain unproven. The getter's conditional source paths are decoded below; next static check is its fallback-key writer, and the dynamic check is: selected-target changes and no-target case through the guarded controller and independent native/API observations.

**The exact native target getter 0x5ECCA0 is now decoded farther:**
its default/fallback key is the qword at
**QWORD(QWORD(healthComponent+0x40)+0x20)**, loaded at
0x5ECCB4..0x5ECCBC. It resolves a separate selection component using
module selector 0x2F57260 and checks presence of selector 0x2F582E0.
Conditional alternate candidates are reference pairs at selection
component +0x280/+0x288 and +0x290/+0x298. If 0x49C170 accepts either,
the result is QWORD(QWORD(candidate+0x18)+0x18). If both are absent,
a state check 0x4AA9D0 accepts 6..11 before considering a +0x2A0
candidate and 0x49C2B0, which can return QWORD(candidate+0x18).
Otherwise the direct fallback key is returned. **These branches are
not a single fixed target pointer chain**; the canonical writer and
correct branch under each gameplay state remain unknown. Reference
helpers update counts, and 0x49C170/0x49C2B0 set a cache flag bit
0x10 and increment counters. A passive reader must NEVER invoke
0x5ECCA0; reimplement only specifically validated, bounded read
branches, with exact type/epoch checks and observed target changes.
All claims are from the current full-SHA PE, no live target selection
or game input in this static trace.

### Shared native player health-owner fields — 2026-11-01 static follow-up

The exact-build player health component resolves one owner pointer,
`owner = QWORD(healthComponent+0x40)`, for three independently decoded
getters:

| Field | Owner-relative read | Native path | Confidence |
|---|---|---|---|
| `player.target` | `QWORD(owner+0x20)` fallback key | `0x5ECCA0`, with conditional selection-component overrides | Getter/branch proven; target changes unmeasured |
| `level` | `DWORD(owner+0x100)` | `0x9200C0` via `Inspect.Unit.Detail`, unless alternate selector present | Current Lab2 self selector22=`0xFF`, direct branch |
| `combat` | `BYTE(owner+0x19D) != 0` | `0x5F2FB0`; `Inspect.Unit.Detail` emits `combat=true` only when nonzero | Getter proven; authoritative writer unknown |

Retained Lab2 self entity has health selector metadata index6→slot15,
alternate-level metadata index22→`0xFF`, and target selector metadata
index24→5. Historical owner `0x2180657DBA0` gives candidate reads at
`0x2180657DBC0`, `0x2180657DCA0`, `0x2180657DD3D`,
respectively; **do not reuse these as unvalidated current pointers**.
The target change handler `0x5FE9B0` stores a replacement key in the
same owner at `0x5FEAD8`, but alternate target branches still matter.
A bounded exact-PE 12MiB displacement scan found no authoritative
`combat` field writer; an apparent `+0x19D` store at `0xDFED1E`
addresses a stack local. `0x603F60` compares state and performs
side effects, not a proven field write.

Next validation is a read-only, identity-bracketed triad capture with
health component type/vtable and owner rereads, correlated with
independent live `Inspect.Unit.Detail(player)` and
`Inspect.Unit.Lookup("player.target")`. The current Casting addon
exposes target and combat but not `level`. No changed-state, restart,
passive freshness or direct heading claim follows from these getters.

### Hash table, not a fixed player-object pointer

`0x69FFD0` reads (not takes the address of) `*(manager+0x50)` and passes that table pointer to `0x58C990`. The table header is `{bucketBase:u64, stride:u64, count:u64}` at offsets `0/8/0x10`.

The hash uses signed low32(key). Exact imported Windows `ldiv(seed,127773)` returns quotient/remainder; native 32-bit arithmetic computes `z = remainder*16807 - quotient*2836`, selecting `z` when nonnegative or `z+2147483647` otherwise. Unsigned `hash % count` selects a bucket at `bucketBase + index*stride`.

Each bucket/node is `{taggedNext:u64, fullKey:u64, entity:u64}`. An inline bucket is checked only when its next word's low bit is clear. Otherwise, or after an inline-key mismatch, the lookup follows `next & ~1`, comparing the **entire 64-bit key** at each node. Entity payload `node+0x10` is valid only after equality; the native not-found iterator is not an entity.

The committed `scripts/probe_native_unit_manager.py` reproduces this lookup with **eight-node limit, cycle detection, no broad scanning**, exact build/PID/start gates, byte/request hashes, and final rereads of all traversed links and ownership anchors. It uses the existing installed reader and `LabCodex._session` cached-credential/VM-identity workflow; no controller, receiver, addon, input, process writes, or game helper execution is involved. Original requests/reports are retained separately per lab under `artifacts/native-unit-manager/`.

```powershell
C:\Python314\python.exe -B scripts\probe_native_unit_manager.py --lab lab1
C:\Python314\python.exe -B scripts\probe_native_unit_manager.py --lab lab2
```

The probe's `nativePlayerUnitId` is the native self key formatted in the decoded bare-ID notation, **not a newly sampled Lua correlation**. Its XYZ values are explicitly cached candidates. Stable ownership anchors across sequential reads do not exclude transient ABA changes or establish passive freshness/restart durability. A first-lab failure does not authorize carrying its addresses or identity into the other lab.

Static provenance: passed exact-SHA jobs `rr2-serialized-manager-lookup-code-20261101-01`, `rr2-serialized-manager-hash-health-prologue-20261101-01`, `rr2-serialized-unit-key-parser-20261101-01`, `rr2-serialized-unit-string-parser-20261101-01`, `rr2-serialized-player-identity-root-20261101-01`, and `rr2-serialized-player-root-return-20261101-01`. Original byte slices were independently decoded with GNU objdump; import names and literals came from the exact PE. Fifteen focused synthetic tests passed, including negative hash seeds, tagged inline slots, full-key collisions, cycles, holes, corrupt hashes and wrong epochs.

**Avoid circular freshness validation:** `Inspect.Unit.Detail` itself invokes the XYZ refresh path. Sampling the native cache only *after* querying Lua may prove merely that Lua refreshed it. A later comparison must include native-before / API / native-after observations and independently changed state. The nearby `+0xD4` timestamp-like field has not been proven to timestamp XYZ refresh.

### First two-lab live lookup check — 2026-11-01 01:30–01:32 UTC

Both probes completed through independently checked VM credentials and current game identities; all requests, chunk hashes, pointer-chain anchors and end-of-run identities passed. This is **live current-process ownership evidence**, not merely the earlier retained module snapshots.

| Lab | PID / start ticks | Native self key | Entity | Position / health component slots | Cached XYZ candidate |
|---|---|---|---|---|---|
| Lab1 | `8164 / 639290507142219120` | `u035400012FA2D207` | `0x23D7D333610` | `6 / 15` | `7415.63671875, 863.5847778320312, 2928.161376953125` |
| Lab2 | `7012 / 639290507554340644` | `u035400012DFEB5BC` | `0x2186DD41C10` | `6 / 15` | `7153.22265625, 825.9457397460938, 3162.858642578125` |

Both metadata indexes were position `34` and health `6`; runtime table bucket counts differed (`681` versus `303`), and each full player key matched its computed inline bucket. Position/health components were distinct in each lab: Lab1 `0x23D011C0150 / 0x23D011C1BB0`; Lab2 `0x2187FE4F400 / 0x2187FE4F650`. The native IDs match prior retained identities, **not a fresh independent Lua observation**.

Original evidence:
- Lab1 `artifacts/native-unit-manager/lab1/5a654fbadb324803a6bba83520329d46/review.json`, SHA `B24487B1857502D0D6DA3688A99AEB7344B46478B6B1D26D05D9FCC18035CF32`; completion `01:30:58.868 UTC`.
- Lab2 `artifacts/native-unit-manager/lab2/a4e8474dbfef4a1490b7cee6655e46c8/review.json`, SHA `761BCC15D1F66E7EFB18EFA13F42DBC995D8E39D8BEDA7517D5E61E1BD72D114`; completion `01:32:41.552 UTC`.
- Passed bounded jobs `rr2-serialized-native-unit-manager-lab1-20261101-01` and `rr2-serialized-native-unit-manager-lab2-20261101-01`; reader executable SHA `362ECD5A1BE3F10BD3AE9E78B66FA0B56D390E5DD7234B4B5997649926B83A53` checked before every invocation.
- No addon query, controller startup, gameplay input, game function invocation, game/VM restart, or process-memory write occurred. The already-running addon may still refresh the cache; this test does not prove addon-independent passive freshness.

## Follow-up trace failures and serialized recovery

Parallel workers attempted bounded, **read-only** current-build extraction, but several Windows terminal invocations stalled for roughly 1,000 seconds without returning results. **The stalled attempts themselves yielded no evidence:** `rr2-child-coordtransform-20261031-01` (helper bytes), `rr2-coord-owner-pdata-20261031-01` (getter function boundaries), plus alternate XYZ and shared-resource ownership requests. No new unit-owner root or stable data offset was found. Native HP/mana/energy/power/charge getters share clock slot `+0x33DC2B0`, but **a common time source is not a common player-owned component**; see [health/resource map](native-current-client-code-map.md).

**Recovery succeeded after serializing the commands:** `rr2-single-serialized-helper-20261031-01` retrieved the exact helper machine code; `rr2-serialized-transform-constants-20261031-01` verified `100.0`, `0.01` and the sign mask; `rr2-serialized-transform-roundconst-20261031-01` verified `0.0` and `0.5` constants. Cloud GNU objdump independently decoded both bounded byte slices. All three retained jobs passed with exact installed SHA `1935A05C...`; they accessed no game process. This resolves the ordinary finite XYZ rounding pipeline, **not** the owner chain, full rounding edge semantics, or a live player pointer.

Concurrent host extraction is a suspected but **unproven** cause of the stalls. Use one heavy Workbridge/REA job at a time, reusing retained evidence and exact job IDs. The ignored Ghidra project remains available. Do not promote the returned three-lane pointer into production telemetry until ownership and cross-lab changed-state evidence are verified independently.

## Field meaning and validation gates

- The original RIFT `Inspect.Unit.Detail` API documents `coordX`, `coordY`, and `coordZ`, and `Event.Unit.Detail.Coord` provides changed-coordinate values keyed by unit ID. Original ArtifactTracker source describes X as east, Y as vertical, Z as south. Those are independent validation references, not native locator proofs.
- Travel bearing computed from changing XYZ is **not** player facing while stationary; RIFT addon authors report facing is unavailable through those coordinate APIs. Treat native rotation/heading as a separate investigation.
- The old verified module `+0x32E0200` → player owner → XYZ `+0x320/+0x324/+0x328` recipe applies to executable SHA `7C356C9D...`, **not** this build. See [XYZ field catalog](xyz-field-catalog.md).
- Both labs already passed the bounded native self-key/entity probe; next correlate the player-owned XYZ and rotation-matrix candidates with fresh independent same-unit observations and a controlled state change. Getter offsets and ownership lookup code are now decoded; they are not by themselves production telemetry. Reject UI/cache copies and require independent changed-state and full-restart tests before promoting a locator.
- Lab1's historical eight-minute source-freshness gate failed. A later Lab2 current-game-epoch 480.057-second strict observer PASSED (684 advancing samples, max gap 4.21128 seconds), documented in `docs/status.md`, but its reader nonce expired at 16:14:53 UTC on 2026-11-01. Do not use stale source pins for input; reacquire a fresh, qualified reader and enforce exact controller/foreground/screenshot/lease gates.

See [current health/resource code map](native-current-client-code-map.md) for the companion static fields and the distinct no-live-pointer limitation.
