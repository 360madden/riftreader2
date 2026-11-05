# Current-build native XYZ reacquisition on both RIFT labs — 2026-11-05

## Verdict and scope

**Both existing exact-build native player/component probes completed successfully against the currently running guest RIFT processes.** Their point-in-time XYZ results are **cached candidates** — **not** verified continuously advancing or independently changed-state player telemetry. The Lua/receiver channel is still unbound and a strict 480-second current-epoch observer has **not** passed. No RIFT game input, VM/game restart, installed addon change, source memory write, or cross-project modification occurred in these probes.

This checkpoint follows the [Nov 5 full-vs-fast feedback forensic correction](lab2-fast-vs-full-forensics-2026-11-05.md) and [Nov 4 guarded addon-bind attempt](lab2-automatic-bind-attempt-2026-11-04.md). Per the RR2 stale-data policy, the earlier RRE and REA-Lab1 evidence was consulted before changing recovery strategy; neither is substituted for fresh RR2 source evidence.

## Current original runtime receipts

| Field | RIFT-Lab-1 | RIFT-Lab-2 |
| --- | --- | --- |
| Workbridge job | `rr2_fresh_20261105_current_native_xyz_lab1_01` | `rr2_fresh_20261105_current_native_xyz_lab2_01` |
| Status | PASS exit0, `complete` | PASS exit0, `complete` |
| Game PID | `1952` | `11572` |
| Game process-start ticks | `639294190379863806` | `639293038821710082` |
| Game executable SHA256 | `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` | Same SHA |
| Native reader SHA256 | `362ECD5A1BE3F10BD3AE9E78B66FA0B56D390E5DD7234B4B5997649926B83A53` | Same SHA |
| X candidate | `7399.28515625` | `7181.80078125` |
| Y candidate | `871.7792358398438` | `820.8821411132812` |
| Z candidate | `3034.239013671875` | `3135.876220703125` |
| Native candidate sampled UTC | `2026-11-05T00:30:59.7831552Z` | `2026-11-05T00:29:20.7414970Z` |
| Report complete UTC | `2026-11-05T00:31:07.6870259Z` | `2026-11-05T00:29:28.9258555Z` |
| Position/health component indexes | `34 / 6` | `34 / 6` |
| Cached XYZ input anchors | Stable within sequential capture | Stable within sequential capture |

Raw, SHA-pinned original probe reports (ignored artifacts, **not** Git-tracked):

- Lab1 `artifacts/native-unit-manager/lab1/c9721a02c9674b1cb02e074956c8745e/review.json`, SHA256 `5436246ac9595d645e3330f2f93a411f360a97e3b2282f827b71b8cfe890be66`.
- Lab2 `artifacts/native-unit-manager/lab2/7bfc25891d184bc4add4079f6c3a25dd/review.json`, SHA256 `fbcd466229513439536593edc4bd6147d450bc17fe7fe2b7969f1d0334637ab5`.

Each invocation independently qualified exact-build source files, the RIFT PID/start, manager-to-player hash lookup, position owner/component index and reread anchors. Native transform calculation remains `structural-rotation-candidate`. Source tests: `C:\Python314\python.exe -m unittest discover -s tests -p test_probe_native_unit_manager.py`, **46/46 PASS**, Workbridge job `rr2_fresh_20261105_native_probe_regressions_01`.

## Critical interpretation

The previously known `sample-position` executable profile at `config/position-candidate-profile.json` is pinned to an **older executable SHA `7C356C9D...`** and root RVA `0x32E0200`; it is **incompatible** with the current `1935A05C...` build. Do not reuse or silently relabel this historical profile. The current probe uses the current-build manager RVA `0x33624A8`, entity/position-component lookup and exact process-epoch gates, described in `docs/reference/native-current-coordinate-code-map.md`.

Both reports retain these explicit caveats: sequential reads are non-atomic (ABA changes not excluded); native self-key not independently correlated with Lua during these runs; no Lua query was made; cached position **passive freshness** was not verified; no independent HP/API changed-state or complete game restart qualification was performed. Two successful snapshots in different labs are not equivalent to a four-second live player feed.

## Next practical gate

1. **Separate native source continuity from Lua binding.** If pursuing native-first XYZ, build a bounded rapid sampler around the already qualified manager/component owner path, with short scan/access timing, fresh process/owner reread, explicit state and per-sample monotonic timestamps. The complete orchestration probe takes ~50 seconds and must **not** be advertised as a 4.5-second feedback loop.
2. Qualify **same-player changed-state and freshness** against independent RIFT UI/API or an appropriately reviewed controlled movement observation. Do not make a source-byte/position match alone into semantic proof. Compare native-before / independent game-state observation / native-after, without invoking Lua to refresh native cache before the baseline.
3. Restore the normal nonce-bound RR2 addon reader only through an input channel that is permitted and still checks current screenshot/controller ownership, never by circumventing the previously blocked tool execution. The last Nov4 reader nonce expired at 00:12:24Z and cannot be reused.
4. Preserve each source as its own source with honest qualification. Do not restart VMs/games, replace native RVA profiles, loosen the 12-second movement cap or 4.5-second freshness bound merely to get a green result.

This is an independently verified **current-process native-candidate reacquisition** milestone, not accepted live motion or full source freshness.
