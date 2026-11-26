# LEGION post-patch recovery — November 26, 2026

**Checkpoint:** 2026-11-26 02:43 EST / 15:43 PHT. Physical LEGION; branch `codex/modular-foundation`, starting HEAD `229fb5ba0027196dff1474d9f50463e8a3d34b73`. No gameplay input, focus changes, reload, restart, addon deployment, or process writes.

## Result

- The prepared recovery launcher completed (exit 0), reusing the verified November 26 RiftWorld/Update Helper prefix `riftworld-20261126-01` and original pinned November 24 baseline. All 266 installation files, 26,754,214,661 bytes, were unchanged in the shared content capture at 07:11:12 UTC. The later RR2 check revalidated inventory/metadata and the executable SHA, not a third whole-install content scan.
- Installed executable SHA-256: `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01` (known 1179). Both RR2 selected captures were consistent; no selected baseline changes. Seven installed addon startup files were unchanged; four pre-existing line-ending-only repository mismatches remain. No new offsets or binary profile needed.
- Fresh physical PID 15076, start ticks 639312735157524276: position, vitals, player-context, zone-context, stats, facing, selected-position, selected-target, orientation and actor-pose commands returned exit 0. Position/vitals/context sampled twice. XYZ (7218.107, 873.187, 3026.5872), HP 18208/18208, Warrior level 45 candidates; 20 selectors / 40 ordinary and unbuffed raw stat candidates. Mana and Energy correctly refused wrong resource kinds. No-target candidate from both selection readers; target-name exit 2 (gated target unavailable). A successful command or stable observation is not a qualified live field.
- Fresh read-only independent Telemetry bracket and source-hashed zone replay passed: Sanctum, same player/process/build and publisher generation, 42 + 34 frame occurrences, 69 distinct sequences, 27 new advancing frames, sequences 14102–14179. Target replay passed with Lua none across all 69 unique frames and matching native-zero endpoint candidates. Not atomic, not full field semantics/freshness, not world-instance identity or target transition qualification.

## Regression checks

A real host registration leaked into the simulated AMD-DESKTOP offline admission fixture. Isolated its configured-reader resolver; no production code or guards changed. The focused recovery/admission run passed 13/13. A broader direct run exposed similar host-registration dependencies in other older fixtures (52 failures, 4 errors, 4 skips). Re-running the same 201-test selection with the existing process-local `RR2_PHYSICAL_TOOLS_ROOT=debug` and no `RR2_NATIVE_READER` override passed (197 passed, 4 skipped). This is a valid isolated offline test configuration, not a fix to every older fixture. No persistent machine settings changed.

## Retained local evidence

Under `artifacts/patch-recovery/patch-20261126-01/` (ignored by Git):

| Artifact | SHA-256 |
| --- | --- |
| summary.json | 09be93cdf7822bd02840a23bf555563fd6b5a7d780dba7fcdf3dbc9a64582dcf |
| telemetry-zone/summary.json | e0d4d804abf53c5bf63eff73efbe34edb28d6a45bee9a434ecef1cc439cbf56e |
| telemetry-zone/zone-replay.json | 4b6cc6bd6529080c011da2569696d87fc7b816852005c2a2368ad59087f5d820 |
| telemetry-zone/target-replay.json | 1178bea5532a497a6d09ba252d5c24d8370a80178c11ff90011eccd696d7cd69 |

The runtime subfolder retains the native JSON and wrapper receipts. Reacquire fresh process identity before future live reads. Independent live cross-check was for zone and no-target state only. No positive selected-target/name transition, movement, camera/actor-heading change, full controlled restart, or new resource-kind qualification was performed. Workbridge's previously missing capture runner files are a separate dependency problem, not demonstrated patch damage. Whole-repository validation was not rerun.

**Next:** resume normal discovery on LEGION; qualify positive target/changed-state observations and repair offline fixture isolation as practical. Keep exact-build admission and prior calibration/authority limits intact.
