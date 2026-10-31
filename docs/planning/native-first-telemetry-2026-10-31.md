# Native-first player telemetry roadmap — October 31, 2026

Joey prefers direct read-only RIFT acquisition for routine telemetry. The Lua
addon is a temporary reference and optional fallback, not the target dependency
for HP/resources/abilities. Preserve the current working addon source until an
independent native field is qualified; do not silently alter game or UI state.

| Stage | Work | Gate to advance |
|---|---|---|
| 1. Seed current-build native candidates | Use independent player HP and exact PID/start/build with the existing bounded native scout on each lab. | Provenance, read coverage and context hashes; explicitly candidate-only. |
| 2. Identify player-owned HP and maximum | Compare candidate copies, owner/root references, and passive/authorized changing-state observations. | Current vs max distinguished; wrong copies rejected; same owner revalidated twice. |
| 3. Recover class resources | Resolve Power, Mana, Energy, Charge, Spirit, Planar/combo only when present for the character. | Type and current/max/regen/cap semantics match independent changes; no guessed zeroes. |
| 4. Recover ability and cast state | Investigate internal ability ownership, IDs, catalog, cooldown timers, current cast and selected target. Explore on-disk client data where suitable. | Ability IDs/names and live cooldowns match observed use; absent data is unavailable. |
| 5. Integrate native observations | Extend the independent native block of the .NET live reader, with per-field status, exact-build gate, identity and monotonic expiry. | Both labs show advancing, provenance-labelled native values without Lua binding; no HP/XYZ regression. |
| 6. Prove durability | Resolve pointers from new process epochs after a normal full game exit and relaunch. | Values and semantics requalify on each lab; no hardcoded heap addresses. |

## Baseline and first execution

- Current executable SHA256 for both labs:
  1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.
- The previously successful native Power recipe is gated to a different SHA.
  Do **not** recycle its relative offsets, vtables or type assignments.
- Live source at the start: Lab 1 (PID 8164, player HP 18208, level 45),
  Lab 2 (PID 7012, player HP 10635, level 43). The independent HP and level
  references are time-scoped observations, not an atomic native comparison.
- The new read-only helper scripts/scout_current_native_health.py uses the
  existing Windows guest credential and RiftReader2.Live.exe native scout,
  pins the game PID/start/SHA, bounds bytes/time/matches, and retains host-side
  hash-verified evidence under ignored artifacts/native-current-health/.
- The October 31 high-address 1 GiB Lab 1 scan found 128 candidates before its
  match limit; 39 unique neighborhoods contained three int32 HP copies, the
  independently observed level 45 and an adjacent 65536 marker. Lab 2 found
  115 candidates before its byte limit; 26 neighborhoods contained analogous
  HP/level-43 layouts. Those repeated structures are promising but **not
  authoritative**. No changing-state/owner/pointer/restart qualification exists
  for the current build.
- Scanning did not cast, move, inject, click, reload addons, change controller
  state, restart RIFT, or modify game memory.

## Stage 2 persistence checkpoint — October 31, ~15:12 EDT

The new `scripts/reread_current_native_hp.py` verifies each saved scout candidate
snapshot SHA256, original read bytes, exact process PID/start/build and the native
reader binary (by running PID or the pinned deployed executable path). It makes
only a bounded `snapshot-native` read, retains the raw JSON and SHA256, and
reports both layout retention and byte changes. It never binds the addon,
injects, casts, moves, restarts RIFT or writes process memory. Eight offline
contract tests and four preceding scout tests pass.

| Read-only check | Lab 1 | Lab 2 |
|---|---:|---:|
| Initial HP/level structural neighborhoods | 39 | 26 |
| Distinct full 100-byte context ranges eligible for reread | 37 | 24 |
| Contexts still retaining level, 65536 marker and HP triplet | **2** | **14** |
| Contexts now overwritten / layout lost | 35 | 10 |
| HP triplet in surviving regions | 18208 / 18208 / 18208 | 10635 / 10635 / 10635 |

The retained bytes have a repeated 64-bit record prefix
(`0, 15, -1, (65536 << 32) | level, HP, HP, HP, ...`), indicating a
structured copy rather than a demonstrated live owner field. Many of these
copies disappeared within minutes; stability of the remainder does not
distinguish a player-owned root from caches/serialization or prove HP maximum.
All results remain **candidate-only**, and no new native HP is exposed.
Ignored source and live evidence paths are recorded in `docs/status.md`.

## Extended-context and non-addon source checkpoint — ~15:22 EDT

The reread helper now permits explicit source-validated addresses plus up to
1,024 extra bytes on either side. Both exact game identities survived another
read: **2/2 Lab-1** layouts and **10/14 Lab-2** layouts retained their HP
triplets with 256 prefix/512 suffix bytes. None of the 16 enlarged contexts
contained the earlier known unit ID as raw LE/BE 64-bit, ASCII or UTF-16.
Several surrounding windows contain `<font...>SEQ...`, `LibString`,
`MessageViewer`, zone or other UI text. This is evidence for a **UI/cache
copy lead**, not a qualified engine-owned player field; neither proximity
nor GUID absence settles ownership. Raw snapshots and reports remain ignored
under `artifacts/native-current-health/`.

The independent passive-source inventory confirms both exact game processes
and reads only existing file metadata plus three named config keys. Both labs
have `Rift.cfg` with `LogCombatConsole=False`, 0.5-second configured flush
interval and a OneDrive DocumentsDirectory override. No existing combat log
or standalone `telara.db` was found among the 11 checked candidate paths.
Do not silently turn combat logging on or treat packaged asset absence as
database absence. Four inventory unit tests and ten reread tests pass.
See [online research leads](native-telemetry-online-research-2026-10-31.md).

## Writable main-module scope checkpoint — ~15:32 EDT

`scripts/plan_native_module_scopes.py` parsed only exact-identity-pinned
executable PE headers on both labs after exact game identity validation.
The main image has a single writable section:
`name=.data, RVA=0x2F56000, virtualSize=6903392,
rawSize=4242432, characteristics=0xC0000040`.
Module size is 63,164,416 bytes. Runtime section base is
`0x7FF76C836000` (Lab1) or `0x7FF67B966000` (Lab2); ASLR
makes absolute addresses epoch-specific. This is a 6.9 MB **proposed**
scope, not a memory capture or a proven readable `MEM_IMAGE` region.
The evidence hashes and ignored paths are recorded in `docs/status.md`.

Existing application code already implements `MemoryDiscovery.FindPointerChains`
(aligned 64-bit pointers, bounded depth/offset, module-rooted candidate
chains) and CLI `find-pointers` on retained native memory snapshots.
**Reuse this** after explicitly intersecting `.data` virtual bounds with
committed/readable image pages; retain coverage and holes, cap request
ranges/bytes, and do not silently scan the entire main module, other DLLs
or private heaps. A module-rooted path can still lead to Lua/UI caches.

## Next bounded experiment

Set aside the HP triplets as validation-only until ownership is demonstrated.
Use a fresh independent (time-pinned) two-lab XYZ reference and construct an
exact-build read-only multi-field native float32/float64 coordinate search;
scope and cap bytes/time, preserve holes, compare cross-epoch and never
claim source authority on numeric coincidence. In parallel, inspect only
writable `MEM_IMAGE` sections of the exact RIFT module (PE RVAs + runtime
base) for a scoped 64-bit owner/backreference root, subject to a separate
read-only execution gate. Do not broaden the old MEM_PRIVATE int32 scout
silently or reuse old-build Power offsets. A changed-state correlation,
self-unit relationship and game-restart re-resolution still gate trusted HP.

Combat-log parsing remains a useful **separate non-addon ability-event source**
only after an existing log becomes available or Joey authorizes an explicit
reviewed toggle under the screenshot/lease workflow. Do not edit config,
issue `/combatlog`, trigger combat, move the player or rebind the addon
implicitly.

## Verified live image capture and pointer search — ~17:34 EDT

The existing deployed native reader produced complete, SHA-bound two-lab
snapshots of the writable .data virtual range (6,903,392 bytes each).
Live memory-map intersection gave 43 Lab1 and 41 Lab2 readable MEM_IMAGE
ranges, no holes, and 1,686/1,686 successful bounded reads per lab.
See docs/status.md for exact ignored artifact paths and file SHA256 values.

Existing find-pointers (depth one, max offset 2048) searched both Lab1 and
ten Lab2 old HP-shaped field targets. Only one Lab2 target had two candidate
RVA roots: 0x3363BF8 + 0x688 and 0x3364DE8 + 0x588. Exact-process live
follow-pointer resolved both, but terminal int32 now read 365256408, not the
old HP value 10635. These are pointer paths to an overwritten/cached
candidate, not authoritative current HP; deeper private-memory chains and
player ownership remain untested. Do not promote them into telemetry.

Official current RIFT UI documentation confirms numeric Player Health and
Ability bars when already displayed. The approved controller screenshot
route needs its proper navigation queue lease; both raw VNC and protected
API attempts stopped at ownership/lease gates. Never bypass the gate or
silently reset a lease. Next: capture a fresh independently verified XYZ
and named ability-resource reference, then require changed-state player
identity and full-game-restart re-resolution for a native locator.
