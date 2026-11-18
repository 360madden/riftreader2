# RIFT 1179 zone ID: independent API comparison status

**2026-11-18, 16:11 EST — AMD-DESKTOP.** Read-only investigation for RR2 P1. No gameplay input, UI reload, game restart, memory writes, or changes to the sibling Telemetry/RRE repositories.

## Source observations

| Source | Game epoch/build | Player | Zone value | Scope |
| --- | --- | --- | --- | --- |
| RR2 physical native zone cache | 2026-11-12 17:45 UTC, PID 69312, SHA 1935A05C... (1177) | 239816685251645959 | `z487C9102D2EA79BE` | Native derived candidate; typed owner/child, no public API agreement in its own session |
| Telemetry 0.5.0 Lua publisher / companion | 2026-11-15 13:09 UTC, distinct PID 37928, SHA 1935A05C... (1177) | `u035400012FA2D207` = 239816685251645959 | `z487C9102D2EA79BE`, API zone name `Sanctum` | Ten accepted live schema-4 observations; `player.unit.attributes.zone` and `player.zone.id` agree |
| RR2 physical native zone cache | 2026-11-18 ~11:07 EST, PID 77980, SHA DF954B79... (1179) | 239816685251645959 | `z0000000CB7B53FD7` | Two consistent native candidate reads in one process epoch; not public API-qualified |

Original RR2 source: `artifacts/physical-zone-context-6df9d3bef69244428a11513f771ecda0.json` (1177). Patched source: `artifacts/physical-native-zone-context-2881c914ecf44a64ab3302c61eb08bea.json` (1179). Sibling sources: `C:\work\Telemetry\artifacts\player-live-validation\report.json` and `...\captures\player-live-10.jsonl`; 0.5.0 validation notes in `C:\work\Telemetry\docs\player-live-contract-validation.md`. Native unit key conversion was checked exactly: `0x035400012FA2D207` is `239816685251645959`.

**Conclusion:** Historical 1177 native and independently produced Lua/API zone strings agree for the same character across different process epochs. This is corroboration, **not a same-session qualification**. The later 1179 candidate differs but cannot be called incorrect, or a proven zone transition, without a fresh independent 1179 API observation for the same player/state.

## Present-day independent-source blocker

At approximately 16:05 EST, `C:\work\Telemetry\telemetry.cmd snapshot --wait 8000` exited **0** but reported `state=unavailable` and `Unsupported RIFT build DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01.` Its `sources.player-api` was unavailable (`No current native player identity to bind.`). This is a **Telemetry companion version gate**, not an API-zone mismatch or proof its Lua publisher stopped. Workbridge command receipt: `rr2_p1_telemetry_live_snapshot_1608`.

RR2 independently reacquired the physical game identity at approximately 16:06 EST: **AMD-DESKTOP**, PID **77980**, start ticks **639305214834918403**, exact SHA **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**. The Telemetry 0.5.0 addon is installed historically, but current loaded publisher freshness was **not** established by this failed companion scan.

## Practical next qualification

1. **Preferred:** Have the separately owned Telemetry project independently qualify/add the 1179 native player/target identity path, keeping its exact-build gate. Do not simply disable the gate. Then compare fresh `player.zone.id` and `player.unit.attributes.zone` with an immediately adjacent RR2 zone-cache report and same player/build/epoch.
2. **Alternative:** Capture a same-session independent `Inspect.Unit.Detail(Inspect.Unit.Lookup("player")).zone` via a reviewed existing Lua console/addon path, with player ID, source time and process epoch; `Inspect.Zone.Detail(zone)` can additionally provide display name/type. Preserve nil/unavailable and separate language/localization. Avoid SavedVariables-only claims of real-time freshness.
3. After an independently checked zone string, separately test user-triggered changed-zone behavior and full-game restart durability only with the required scoped authorization. Do not promote raw zone key or equal candidate strings into world-instance identity/route clearance.

No source code in Telemetry, RRE, or the game client was altered.

## 16:16 EST addendum — positive same-process native change

A **fresh read-only RR2 zone-cache sample at 16:14:42 EST** on the same physical PID **77980**, process-start ticks **639305214834918403**, exact build SHA **DF954B79...** and self key **239816685251645959** returned raw key **1216123138**, child key **650763347**, and derived candidate **`z487C9102D2EA79BE`**. The earlier 1179 physical source captured at **11:06:41 EST** on that *same process epoch and player* returned raw key **12**, child key **1830661357**, and **`z0000000CB7B53FD7`**. The outer type and child guards passed on both samples; returned component addresses differ, as expected for separately resolved ownership observations.

Ignored new source: `artifacts/physical-native-zone-context-387e2412cf954611b7930886a71ee1a2.json`, SHA-256 **37F33626651081FCF0BE6B84F30C3CCEFA22623A33DAC9200E90D820FC8DB33F**. Earlier source: `artifacts/physical-native-zone-context-2881c914ecf44a64ab3302c61eb08bea.json`, SHA-256 **DBE107BC48A9574F6C16232BDA8C6B91B4FA92ABE7B6A7284539E25835670FF9**.

An offline comparison revalidated both source hashes and exact process/start/build/module/player correspondence, then passed both reports through `physical_rift._native_values("zone-context", ...)` and reused `save_physical_route_view._compare_zone_context`. The result was **`changed-candidates`**, reason **`zone-or-player-candidate-changed`**, exit **0** (`rr2_zone_1616_cross_time_replay`). Since the player key did not change, the distinguishing evidence is the zone/cache field change. The later native candidate also equals the independent *historical* Telemetry Lua API ID for Sanctum; that cross-date agreement is suggestive but not an independent **current-1179 same-moment** comparison. The five-hour unobserved interval does not identify transition time, input cause, public zone semantics, world-instance identity, or route clearance. No RR2 game input or focus change occurred.
