# RR2 low-latency native pose/orientation burst — physical AMD-DESKTOP

**Date:** November 11, 2026. **Host verified:** AMD-DESKTOP. **Target:** exact physical RIFT PID 44888, process-start UTC ticks 639299470183328173, EXE SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. Historical pins are not future defaults. **No gameplay input, VMware, LEGION or screen-capture operation.**

## Practical performance change

The .NET 10 `CurrentBuildActorPoseSampleCommand` and `CurrentBuildOrientationSampleCommand` previously called the full `WindowsNativeMemorySession.RevalidateAsync()` after **every read**. That routine hashes the on-disk RIFT executable and verifies its process, path and module mapping. In a 30-sample zero-interval burst, the full revalidation was far more expensive than each native sample.

Both samplers now retain one exact-process read lease/session, recheck the player and component during native reads, and run the **full executable/process/module revalidation once at the end of a multi-sample burst before publishing**. Single-sample behavior still performs full revalidation. Any failed final check cancels publication and no partial results are emitted. This optimizes bounded passive burst collection; it does not qualify avatar body yaw, freshness or independent game response.

| Physical 30-sample measurement | Before | After |
| --- | ---: | ---: |
| Actor-pose acquisition window | 1,136.475 ms | 7.857 ms |
| Actor-pose acquisition rate | 25.52 samples/s | 3,690.98 samples/s |
| Actor-pose entire native capture with final revalidation | 1,182.502 ms | 52.762 ms |
| Actor-pose repeat entire capture | — | 51.084 ms |
| Orientation acquisition window | Not measured before code change | 6.615 ms |
| Orientation acquisition rate | Not measured before code change | 4,383.98 samples/s |
| Orientation entire native capture with final revalidation | Not measured before code change | 43.341 ms |

Actor-pose acquisition became **144.7× faster**, and full capture **22.4× faster** in the first before/after test. These are **burst measurements** under `--samples 30 --interval-ms 0`, not guaranteed sustained streaming throughput or proven game-state refresh. After optimization, a 5-sample actor-pose capture and a 5-sample orientation capture with `--interval-ms 100` also succeeded, preserving paced sampling. All accepted samples retained the same player key and unchanged stationary matrix/XYZ candidates.

## Discovered and corrected Python precision bug

The first 30-sample fast orientation capture **wrote a native report but the RR2 Python wrapper rejected it** as `invalid-native-reader-report`. Cause: .NET emits **7 fractional decimal digits (100 ns ticks)** in its UTC timestamps; Python `datetime` stores only 6 digits (microseconds). Several correctly ordered sub-microsecond samples became equal after truncation, causing false overlap rejections.

Updated `scripts/physical_rift.py` to compare the seventh fractional digit explicitly, without relaxing UTC/order rules. Updated `scripts/analyze_physical_turn_pair.py` to use the same exact tick ordering for burst validation. The original 30-sample report, previously rejected, now validates offline, and a fresh 30-sample physical orientation capture passed the full RR2 reader path. Exact replayed samples remain candidate-only.

## Evidence and verification

- Pre-change actor-pose source: `artifacts/physical-native-actor-pose-1e69cb359732412a9265dafe81047b16.json`, SHA-256 `89C9358405D09BFE44DF921E1616A1955028103DDA06E723FEC5D697CA1C1CFC`.
- Post-change actor-pose: `artifacts/physical-native-actor-pose-e3dab1a9e955432c8dde4cc1ea2f8c4e.json`, SHA-256 `588C0C3F6D7FA141E5188BC03BB2AEC2E0160BC2D8C1069CD5544F67BDD850E7`; repeat: `artifacts/physical-native-actor-pose-7f5bb065c7254fccaf237d362deb75a4.json`.
- Rejected-then-revalidated orientation source: `artifacts/physical-native-orientation-bc0306526e0a402282b1d9195732bf21.json`, SHA-256 `6E5725FF4E323F33E8E4E06B6BF06A1485718BBB64584F311C8DDCA4E88EE187`.
- Fully accepted fast orientation: `artifacts/physical-native-orientation-2a4a54fdf1be4535a1481fbd67296957.json`, SHA-256 `5ACC1325532F9F227D69298FDDCFF7B7F35BD0746D31FE067CF6D00EAC51F7E8`.
- Focused automated tests: **46/46 .NET 10** for the actor/position orientation sampler commands, **62/62 Python** for physical reader and turn comparison. Added tests confirming **one final revalidation**, no output on failed post-burst check, and acceptance of valid 100 ns ordering while rejecting replayed timestamps.
- The screenshot desktop-control quarantine remains separate and was not modified or bypassed.

**Remaining qualification:** These are high-speed reads of *potentially cached* matrices. Live A/D actor-turn delta, camera/body separation and independent game-view confirmation must still be measured after reviewed desktop-capture recovery. No automatic navigation was enabled.
