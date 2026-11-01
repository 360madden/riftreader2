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

The adjacent code also calls `+0x6983F0` on the unit-associated object and `+0x1144B70` with stack buffers. Their ownership and spatial roles are not yet decompiled. **The observed three-lane layout is a code-access fact**, but it does not by itself prove the address is stable, player-owned, a raw world position record, or the same pointer in both VMs.

## Field meaning and validation gates

- The original RIFT `Inspect.Unit.Detail` API documents `coordX`, `coordY`, and `coordZ`, and `Event.Unit.Detail.Coord` provides changed-coordinate values keyed by unit ID. Original ArtifactTracker source describes X as east, Y as vertical, Z as south. Those are independent validation references, not native locator proofs.
- Travel bearing computed from changing XYZ is **not** player facing while stationary; RIFT addon authors report facing is unavailable through those coordinate APIs. Treat native rotation/heading as a separate investigation.
- The old verified module `+0x32E0200` → player owner → XYZ `+0x320/+0x324/+0x328` recipe applies to executable SHA `7C356C9D...`, **not** this build. See [XYZ field catalog](xyz-field-catalog.md).
- Next offline step: decompile `+0x698460` and related helper functions to find a current-build unit-owner path. Then use the existing exact-build/PID/start-gated native reader for **read-only** same-unit observations in both labs. Reject UI/cache copies and require independent changed-state and full-restart tests before promoting a locator.
- Lab 1's last eight-minute source-freshness gate failed and Lab 2's earlier passing gate is from a prior epoch. No supervised movement pulse should occur until current-epoch freshness and exclusive controller/screenshot/lease checks pass; reuse the existing workflow.

See [current health/resource code map](native-current-client-code-map.md) for the companion static fields and the distinct no-live-pointer limitation.
