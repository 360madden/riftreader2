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

## November 27 — published-reader recovery checkpoint

Host verified LEGION; source branch `codex/modular-foundation`, native release built from `edeb6a85ea4087ecbafdfc114936a68b88d4da68` using .NET SDK 10.0.302. Registered only after published startup/smoke and live nine-source acquisition/replay passed. A subsequent test-only formatting correction does not change the native release source.

- Current registered bundle: `artifacts/tools/physical/20261127-phase20-edeb6a8/`. Native reader SHA-256 `ACB20F67636ECDB019495C504622B65E843494AF9B1D53490E5C4DBEE7F12812`; WGC probe SHA-256 `2CE4ABD4307D66A177C86DB0B73D1DA30DDF60E886DFEC7473D72274B090F59E`.
- Registration `.local/physical-tools.json` SHA-256 `B54E638B2D8C2A9590AD1A6AABA49B65AA6C63A39CBB788898EA10DEB84ABC1C`. Prior bundle `artifacts/tools/physical/20261123T203937Z-cd330b8b/` retained, prior registration backup `artifacts/postpatch-20261127-phase20-registration-before.json` SHA-256 `80EB53271DEB231509E9F89A2D18E332DCC73C417B0F032934A4E423E35250DE`. Roll back only if necessary, on verified LEGION with native helpers idle, using the existing `publish-physical-tools.ps1 -ExpectedHost LEGION -RegisterBundle` command with the prior absolute local bundle path.
- Original immutable file checkpoint `docs/validation/patch-recovery-legion-20261124.json` remains the file baseline. Revalidated its pinned shared and RR2 baseline hashes, archive and installed executable SHA, and current metadata against the retained November 26 shared capture (266 files). This is not a fresh whole-install content hash. A genuinely new patch needs a fresh shared post-patch capture, not reuse of the earlier cycle's prefix.
- Published reader smoke passed synthetic-process identity, PE header, stale epoch and no-overwrite checks; WGC 35/35 offline checks passed. No actual desktop capture.
- Fresh published-reader nine-source state on PID 24992/start ticks 639313044653553067, build 1179: health, XYZ, Power, all 40 raw stat values and XP endpoints match the phase-18 development capture. Experience 158578/337592, raw rested 84398, level 45. These are same-process sequential candidates, not independent API qualification or proof of changed-state behavior.
- Nine of ten dependency checks ready; Workbridge desktop backend alone blocked by missing `dist/desktop-ui.mjs`, `dist/desktop-capture.mjs`, `dist/desktop-turn-admission.mjs`. WGC and DXcam dependency checks ready. `Waypoints.cmd --check` exit 0, same-build historical calibration seed reused; no motion tested.
- Fresh ReaderBridge capture and replay returned advancing sequence candidates 9000 and 9003, matching native/Lua level 45, published Power 100/100 (maximum may be addon default), no target. No independent XP API reference, changed-state or positive-target evidence. ReaderBridge result remains `ready=false`.

Local retained evidence (SHA-256; files are ignored by Git):

| File | SHA-256 |
| --- | --- |
| `artifacts/postpatch-20261127-phase20-release-state/summary.json` | `5DDC0F264ADC24A41ADB121EAE8B84FABFB2BCF1D459991C817606676F810411` |
| `artifacts/postpatch-20261127-phase20-release-state/replay.json` | `C5B8A3D6DAF7AA9F7B63C00F81BAB1C7417EE7707413A66F27F462BC2C27356D` |
| `artifacts/postpatch-20261127-phase20-release-comparison.json` | `BD22C8551932DCBF552EA30BC3A8B477C2C285A07EC36B84EB71CEAB3D8DDC38` |
| `artifacts/postpatch-20261127-phase20-release-readerbridge/result.json` | `C17AFD8E4F76F62454AB2A0D17F82FB793CA97A300B09ADF45CFEC927E8C3FC3` |

Reacquire the actual host/PID/start/build identity for every future live acquisition. Do not treat these retained addresses, snapshots or calibration seed as current movement permission or proof. No gameplay input, game modification, addon deployment or restart was performed in this deployment pass.

Validation checkpoint: initial whole-repository run stopped at a C# test whitespace violation after all 1965 .NET tests passed. Corrected the formatting only. Retry passed Release build (zero warnings/errors), both .NET test projects (445 + 1520), formatting, native publish smoke, synthetic Lua/C# contracts and scheduler/helper mocks. Python suite was still running at the 25% checkpoint, with no failure reported yet. The owned bounded job `rr2-1127-phase20-full-validation-retry` has a 600-second timeout; local log `artifacts/validation-legion-20261127-phase20-format-fix.log`. Check its terminal exit and final validation marker before claiming a full pass. The active log is locked by the writer and is not yet a finalized hash-pinned receipt.
