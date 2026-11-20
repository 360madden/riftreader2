# RR2 build-1179 post-restart recovery: new physical process epoch

**November 19, 2026, ~22:35 EST · AMD-DESKTOP · read-only validation**

## Process provenance

The previous November 18 physical RIFT session was PID **77980**, start ticks **639305214834918403**, exact executable SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**. Machine-local process enumeration on November 19 found a **different running RIFT process**, PID **42656**, started **20:56:09 EST**, and no previous PID 77980 in the enumerated RIFT processes. A fresh `physical_rift.py --expected-host AMD-DESKTOP` selection validated PID **42656**, start ticks **639307365692952544**, HWND **18551026**, the same exact installed game SHA, and owner host **AMD-DESKTOP**. This is a distinct process epoch, not a claim that RR2 initiated or controlled a restart.

## Fresh post-restart physical acceptance

The existing native composite collector completed exit **0** with the following command (explicit fresh PID; no input):

```powershell
C:\Python314\python.exe -B scripts\collect_physical_player_state.py --physical-pid 42656 --samples 2 --interval-ms 100 --include-stats --include-zone --output-dir C:\work\riftreader2\artifacts\physical-state-postrestart-20261119-2226
```

It acquired six independently saved SHA-256-pinned sources in order: **zone-before**, **player-context**, **position**, **vitals**, **stats**, **zone-after**. Same player numeric key **239816685251645959** (Atank, Level 45 Warrior); native HP **18208/18208**, resource kind **1** with correct unavailable Mana/Energy under wrong-kind guards; 20 selected stat fields each with ordinary/unbuffed candidates; player XYZ **(6032.8154, 832.4444, 3141.68)**. Zone endpoints both yielded raw key **12**, child key **1830661357**, derived candidate **`z0000000CB7B53FD7`**, and `worldInstanceStatus=unavailable`.

Ignored report: `artifacts/physical-state-postrestart-20261119-2226/summary.json`, SHA-256 **86377B46299E1DBBB4BB14B925C698840BBF10FB596B93218713E230B51AFB89**. Each native source path and SHA is retained inside the summary; no source payloads have been added to Git.

A subsequent read-only selected-position burst returned **2/2 `no-target`**, raw fallback key 0 and no target coordinates (ignored source `artifacts/physical-native-selected-position-aab355bfaec34c31949105e7b77993a0.json`, SHA-256 **925A4CDB8853A58DB9FC1A1F9C1B18D7600E990B4FCDF692E538C52F9A0D7955**). A separate facing/target burst returned **2/2 complete** with guarded body/camera candidate data and `selectedTargetProjectionCandidate.status=unavailable`, `targetStatus=no-target`, not a stale target (ignored `artifacts/physical-native-facing-70bd6503e59a41f9b3c2caad71f28e8d.json`, SHA-256 **0160E649C9FFAEF2CEFC3924AA85258175EAB333CCABC3D030DD861DC7659977**).

## Replay compatibility repaired and cross-process comparison

`scripts/replay_physical_player_state.py` now admits optional ordered one-shot `zone-before`/`zone-after` sources alongside the original three-source and optional stat variants. It verifies both original source hashes, strict typed zone projections, player/build/module/epoch ownership, recorded source ordering, child/raw/derived ID agreement and the exact candidate-only bracket summary. Fabricated world-instance qualification, missing zone sources, hash tampering and mismatched epochs are refused. Replay uses only saved files and never attaches to RIFT.

`scripts/compare_physical_player_state_epochs.py` now carries an explicit `crossEpochZoneCandidateComparison` result, preserving `not-comparable` for older reports without both zone brackets.

Actual replay comparison, using:
- before: `artifacts/physical-state-zonebracket-20261118-1629/summary.json` (PID 77980, SHA **4FD29439811D5A0417403260A1E370EF6E29B7D97E97C157AFAFC70A5B1A3E57**)
- after: `artifacts/physical-state-postrestart-20261119-2226/summary.json` (PID 42656, SHA **86377B46299E1DBBB4BB14B925C698840BBF10FB596B93218713E230B51AFB89**)

exited **0** with `different-id-candidates`: yesterday `z487C9102D2EA79BE` versus tonight `z0000000CB7B53FD7`. Same numeric player key and same executable SHA, but separate process epochs; the native numeric planar difference **1422.32** is **not** independently verified travel. There is no continuous cross-restart player identity or public Lua zone agreement from these records.

## Validation and boundaries

**161/161** focused Python tests passed (original collector/physical zone/selection, replay, added zone-bracket replay cases, cross-epoch comparison); `git diff --check` is required before commit. The new replay tests include actual saved-source tamper and identity negatives and skip when ignored local evidence is absent. No .NET native reader implementation was edited, so this session does not claim a new .NET build.

**Proven:** exact-build RIFT memory reader paths returned coherent native candidates on a newly observed process; saved zone-bracket reports are independently replayable; post-restart no-target is handled without stale target position. **Unproven:** same-moment public Lua/API ID, world-instance authority, continuous live freshness, cause/timing of zone changes, controlled A→B→A target switch or navigation clearance. No gameplay input, process-memory writes, UI reload, focus change, or game restart was sent by RR2 in this work.
