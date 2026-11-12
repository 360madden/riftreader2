# RR2 handoff — settled physical A/D turns and working WGC capture

Recorded November 11, 2026, Eastern time.

## Checkout and host

Actual machine verified AMD-DESKTOP. Repository C:\work\riftreader2, branch codex/modular-foundation, HEAD cacdf91e8dac3ba68c926eccc401815b6167d867. Follow AGENTS.md and reacquire process/build/window/player identity before live work. Physical hosts only. This session operated AMD-DESKTOP.

Concurrent modified files at final check were scripts/fresh_native_actor_pose.py, scripts/observe_physical.py, tests/test_fresh_native_actor_pose.py, tests/test_observe_physical.py, and Application/Domain/Infrastructure packages.lock.json. Untracked energy/anchor scripts and test also remain. Preserve all peer work and index. This session made no implementation changes or commits.

## Workbridge recovery and operational caveat

User explicitly authorized investigation, shutdown/restart, archival of the old quarantine, and one capture. PID 32516 was the main Workbridge dist/server.js child of tunnel-client PID 32444 and scheduled wrapper PID 28196. The recorded quarantine was for request rr2navposebeforeA20261111b, lease d85dd9f0-93e8-4e09-a8ca-ab996efb8586.

Read-only reconciliation found no post-lease descendant candidates but still-present historical owner. Manual archive dry-run originally refused HISTORICAL_OWNER_PID_PRESENT. With user approval, scripts/Restart-Workbridge.ps1 stopped the old task/process tree. Scheduled startup exited 1 and readiness timed out. The configured Start-BackgroundTunnel.ps1 wrapper was then launched directly, hidden, with the scheduled action's existing arguments. Tunnel health subsequently reported ready. A later final health check also returned ready, but Workbridge MCP scheduled task remained Ready, and the final process query returned no tunnel-client.exe row. Therefore service durability and current process ownership need fresh investigation. Do not assume a normal scheduled-task restart or lasting startup recovery.

Archive dry-run subsequently passed review, and scripts/Archive-DesktopQuarantine.ps1 -Execute archived the exact SHA-pinned guard and sidecar to:
C:\work\workbridge-mcp\.tools\desktop-evidence\recovery-archives\rr2capture-recovery-20261112b

The original capture outcome remains unknown. At final check no top-level input-turn lock, admission lock or quarantine sidecar matched the capture gate. Recheck before future operations.

## WGC capture now works on physical RIFT

Used existing tools/physical-wgc-probe Debug executable, backend wgc, one explicit capture per invocation, exact PID/start/SHA/HWND, new PNG paths and JSON receipts.

Historical target this session:
- PID 18092, process start UTC ticks 639300391441133615
- HWND 919618 (0xE0842)
- Executable C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe
- SHA256 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8
- Player key 239816685251645959, character Atank
- User placed RIFT on physical display 3. Win32 Screen reported DISPLAY5 with window at approximately (-1928,-2) to (8,1046). Mapping to Settings display number was not verified.

First usable frame artifacts/rift-visible-20261111-1958.png (actual capture 19:57:36 EST), 1920x1032, capture call ~425.65 ms. Visually shows Atank, practice dummies, Thedeor's Circle, RR2 CASTING v0.4.0. Window was background and uncloaked. Probe reported no input or focus change. Filename minute differs from actual capture timestamp; use JSON receipt timestamps.

## First A/D pair

Existing Debug RiftReader2.Live.exe move-key, explicit PID, --hold-ms 250 --measure-actor-pose --execute --json. Only one pulse each.

A evidence artifacts/physical-a-20261111-195847/
- Original before actor angle -40.1964036699 degrees.
- Immediate after A -79.9534604367, delta -39.7570567668.
- Hold bounds 256.0542–259.6560 ms, midpoint 257.8551.

D evidence artifacts/physical-d-20261111-200003/
- Before D -83.9642711796, immediate after D -44.5975738554, delta +39.3666973243.
- Hold bounds 255.59–258.81 ms.
- Subsequent read-only settled check artifacts/settled-d-pose-20261111-200215.json returned three identical samples -39.9626068287.
- Settled final difference from original +0.2337968412 degrees, right by angle convention.
- Prior A settled magnitude inferred from later pre-D sample 43.7678675097 degrees. Prior D settled magnitude 44.0016643509 degrees. These observations have different delays, so they are a limited repeatability comparison.

Screenshots visibly confirm viewpoint rotation. scripts/physical_turn_visual_pair.py returned visibleViewChangeCandidate=false for obvious turn images because sampled threshold fraction was low (~9–10%). Original-before-A versus after-D comparison was rejected for time gap. Treat comparator output accordingly. Visual evidence alone does not measure body yaw.

## Repeated pair with explicit settling

Evidence directory artifacts/physical-ad-settled-20261111-201818/ contains summary.json, baseline/a/d PNGs and probe receipts, pulse receipts, and raw pose bursts.

Procedure chose a 500 ms wait after each pulse, then five read-only pose samples at 100 ms intervals. Settled criterion was angle span below 0.01 degrees across all five; all sets passed on first attempt. Same player/build/start ownership checked. A fresh stable baseline preceded input.

| Stage | Actor angle degrees |
| --- | --- |
| Fresh baseline | -39.962606828701084 |
| Immediate after A | -79.34399650306521 |
| Settled after A | -83.84288455706586 |
| Immediate after D | -42.53124919561343 |
| Settled after D | -37.88266044091037 |

- Settled A delta -43.8802777284 degrees.
- Settled D delta +45.9602241162 degrees.
- Final residual from this run baseline +2.0799463878 degrees.
- Final residual from original pre-A +2.3137432290 degrees.
- A hold 256.0862–259.6996 ms, midpoint 257.8929.
- D hold 263.7355–266.8802 ms, midpoint 265.30785.
- Longer D hold is consistent with the larger D turn, but two pairs do not establish a calibrated control model.
- Compared to prior delayed settled observations, A magnitude differs ~0.1124 degrees and D ~1.9586 degrees.

Screenshots baseline.png, a.png and d.png were visually inspected. Dummies shift right after A and return near baseline after D with a small remaining offset.

## Interpretation and next work

WGC now provides usable physical game pixels. Immediate actor-matrix readings undercount these settled changes by roughly 4–5 degrees. Wait and measure stability for future comparisons. Angles remain native actor-matrix candidates; body/camera separation and independently calibrated body yaw are outstanding. Same-process repeatability is supported only by these two pairs. No restart qualification or general navigation readiness established.

User authorized the specific short A/D trials and read-only follow-ups. Further live input needs task-appropriate authorization. No more input was sent after the repeated D pulse.

Useful next steps when requested:
1. Recheck Workbridge process ownership/startup health and scheduled task durability.
2. Reuse the existing probe and native pose sampler with fresh pins.
3. For repeatability experiments, retain settled readings and actual SendInput hold bounds, and account for hold-duration variability.
4. Investigate why the offline visual comparator misses these obvious scene shifts if improving that tool is requested.
