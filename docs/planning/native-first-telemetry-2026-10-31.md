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

## Next bounded experiment

Narrow the **two Lab-1 and fourteen Lab-2 surviving structures** by read-only
extended context and references toward a game/player-owned root; verify the
source hierarchy, and compare against an independently observed change in
current HP (passive if possible). Do not promote a field merely because HP
appears three times or stays unchanged. Any reviewed controlled change needs
separate input authorization and the existing screenshot/lease workflow;
otherwise wait for passive change. Then qualify a restart-stable locator
before emitting trusted live HP or attempting native resource/ability fields.
