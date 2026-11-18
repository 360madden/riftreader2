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
