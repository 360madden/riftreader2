# New-build native XYZ numeric candidates — RIFT-Lab-2, 2026-10-27

**Outcome: candidate-only.** The existing current-reader `scout-values-native` captured **23** bounded read-only contexts for the freshly verified RIFT API player-X reference in Lab-2's new build. Ten contexts contain neighboring float32 Y and Z within the declared tolerance at X+4 and X+8. Multiple copies and unchanged player position prevent promoting any address to authoritative native XYZ or a restart-stable pointer.

## Source and process identity

- Source: the independently verified [four post-patch typed Lua comparisons](lab2-typed-inline-postpatch-2026-10-27.md), player `u035400012DFEB5BC`, API XYZ = **(7160.759765625, 821.2099609375, 3156.1499023438)**. This source was observed about ten minutes before the numeric scan; exact simultaneous equivalence was **not** established.
- Target: **RIFT-Lab-2**, RIFT PID **11900**, process-start ticks **639286946776156559**, new executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; reader SHA `2CC9C42B51394C6B8429E4DFF4BD57FBA321302C01879ED98414859951F888B4`. Both binaries and game PID/start were rechecked before the guest read; RIFT remained alive on that epoch afterward.
- Bounded `native-value-scout-request/1`: high private-region heuristic start `0xDC91D1A000` from the verified new-build map; single `float32` reference X `7160.759765625` with absolute tolerance `0.02`; 32 context bytes before and 40 after; **256 MiB / 20 s**, 32,768 maximum regions, 128 maximum matches. Search only committed readable non-guard `MEM_PRIVATE`, **not** module-image `.data`.

## Original evidence and verification

- Guest saved and ZIP-transferred a published scout result whose `index.json` SHA-256 is **`37624DDFA2E5F28A3E59319600B763F820304EBD25F828EF18BB3B0BC1BB83E9`**. Host original is ignored `artifacts/lab2-xyz-20261027-07.zip`, 40,626 bytes, SHA-256 **`2D0B331A459683A0C96DFA1ED324EB713C9964BC8DD2A2B795A9EE5E55C0D481`**. Guest receipt: `artifacts/lab2-xyz-20261027-07-receipt.json`. Host independently rehashed the ZIP, index, original request, all **23** candidate request/snapshot pairs, decoded byte-lengths and context chunk checksums.
- Index correctly declared `status=partial`, `reason=byte-budget-exceeded`, `examinedBytes=268435456`, `nextAddress=0x257B92C2FF9`. This is a **partial high-region search**, not a full address-space absence or global uniqueness claim.
- **19/23** immediate snapshots still held an X float within tolerance; **four** scan-time X matches had changed or been overwritten before the immediate context copy. Their presence in the index is not a continuing field observation. This is why saved bytes must be inspected independently of the match index.
- **10/23** retained contexts contain float32 X with adjacent Y at `+4` and Z at `+8`, both within ±0.02 of the qualified Lua XYZ. Representative saved context starting at candidate X address `0x257A80DF638`: X ≈ **7160.758789**, Y ≈ **821.214233**, Z ≈ **3156.152832**; differences from earlier API reference are approximately (-0.000977, +0.004272, +0.002930). Several contexts repeat very similar triplets at 16-byte spacing. These could be copies, interpolation/state buffers, UI caches or other actor records; no ownership was established.
- The scout matches **independent scalar X values**, never a complete XYZ tuple as an atomic condition. Y/Z adjacency was tested **offline against the captured original bytes**. Numeric proximity alone cannot decide which of the ten copies is authoritative.

## Source-field availability in one verified API frame

- The verified 2026-10-27 typed wire also contained `player.health=10635`, `healthMax=10635`, `planar=3`, `planarMax=3`, `combo=5`, `coordX/Y/Z` as above, and `player.zone=z0000000CB7B53FD7` with field statuses `ok`.
- `player.power`, mana, combat and mounted values were **unavailable** in that frame; target status was **absent**. Do not treat unavailable as zero or infer new-build native resource fields from it. `autonomousInputReady=false` is a producer field, not a guarantee of game-control readiness.

## Later same-epoch native readback

- An independent, later, **read-only five-range `snapshot-native`** operation pinned to the same game PID/start/SHA returned `status=complete` with **five of five** successful 76-byte contexts. Exact original ignored: `artifacts/lab2-xyz-20261027-09-snapshot.json`, SHA-256 **`43831785A5F442D1C2BA1CA56F4B56D47DEDEB0F08615BD2E4C0C0F848658236`**; guest/host receipt `artifacts/lab2-xyz-20261027-09-receipt.json`. Host verified all per-chunk Base64 lengths/hashes and matching request provenance.
- All five selected contexts (X addresses `0x257A80DF638`, `0x257A897DE40`, `0x257AC9E04D0`, `0x257B8F7D390`, `0x257B8F91050`) were **byte-for-byte identical** to their initial scout contexts and retained approximately (7160.758789, 821.214233, 3156.152832). The guest game PID/start remained unchanged.
- A third independently verified typed API run roughly one minute later continued to advance sequence **14545/14546 → 16731/16732** with the same source player and unchanged Lua XYZ (four of four strict offline pairs). See the [third-run evidence](lab2-typed-inline-postpatch-2026-10-27.md). Temporal persistence is useful evidence, but identical static values **cannot distinguish authoritative native position from stale copies**. A separately observed position change is still essential.

## GUI validation blocker and remaining gates

- A read-only `vmrun runProgramInGuest -interactive -noWait` diagnostic for Lab-2 returned **4294967295** before creating its expected receipt. A separately authenticated noninteractive check confirmed no interactive diagnostic receipt, game still running in Windows session **1**, guest default PowerShell in session **0**. Do not claim interactive console or screenshot support from this failed experiment.
- No player movement, attack, casting, game restart, VM restart, memory write, injection or addon deployment was performed. Old build root RVA `0x32E0200` and offsets `+0x320/+0x324/+0x328` remain barred for this new executable.
- Next: use small exact-epoch `snapshot-native` rereads of independently selected candidate X/Y/Z neighborhoods alongside fresh typed source. Promote only if a separately observed player-position change produces synchronized multi-axis native responses, false-positive copies are rejected, and a new-build locator then survives full game restart.
