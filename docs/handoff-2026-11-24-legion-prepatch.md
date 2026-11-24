# LEGION pre-patch checkpoint — November 24, 2026

Recorded 2026-11-23 23:54 EST, before the possible November 24 04:00 EST patch. Patch timing is an assumption, not a publisher confirmation. This checkpoint uses physical LEGION only; AMD-DESKTOP is unavailable. No input or game changes performed.

## Preserved evidence

- Repo `C:\work\riftreader2`, branch `codex/modular-foundation`. Verified clean and synchronized with GitHub at `3b4de6969cf690a3e996ec52d46508b5c12608a5` before this documentation commit. The preceding push published 195 accumulated commits, then the two-file Python view-tool repair (9/9 focused tests).
- Current installed RIFT build 1179, executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.
- Shared Update Helper baseline: `C:\work\Update Helper\before-20261124-legion.json`, SHA-256 `6612CAB5AD31162CC0EAB21266ED3839C4A2EF1E12E3A2AA82536D5B195C983E`; verified 266 files / 26,754,214,661 bytes. Archived executable at `C:\work\Update Helper\.local\prepatch\df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01\rift_x64.exe` independently matches installed SHA. Do not execute or replace the installation with the copy.
- RR2 selected-file baseline: `artifacts/prepatch-20261124-legion-rr2.json`, SHA-256 `23FA92E2B6B9793D018C26996DE94289E783A7562444B08918534627239F3D0C`. Includes game executable, repository addon, config and local Waypoints calibration. Rehearsal comparison `artifacts/prepatch-20261124-legion-rr2-rehearsal-diff.json`: 65/65 unchanged. This is selected coverage, not the full installation or installed OneDrive addon inventory. All raw artifacts are local, ignored by Git.
- Update Analyzer built with the actual pinned SDK, 10.0.302, zero warnings/errors; 8/8 black-box tests passed. PATH selects 10.0.403, so use the explicit local SDK.

### Passive 1179 reader baseline

The following reports are in `artifacts/prepatch-20261124-legion-live/`, from physical PID 5300, identical process epoch and build. Never reuse this PID or heap address after restart. Candidate results, not independent changed-state/restart qualification.

| File | Result | SHA-256 |
| --- | --- | --- |
| position.json | Two-sample acquisition succeeded | 796E1688BFF4F32354B473C1C0E5877060713156C16FD0F52E41629EFFE76E46 |
| vitals.json | Two samples; health 18208/18208; kind 1 correctly refused Mana/Energy | 1147CAE6A3635C633366E86C2FE2F19F2C2F4EACAEC6F5698378FCB84AF2EF91 |
| player-context.json | Two samples; level 45, Warrior candidates | F604D5E45EF88AB7278BC47F82CF041BBD88B1284AAEB5DA663BD9B875D3CA48 |
| zone-context.json | Single sample, zone candidate available; world instance unavailable | 3C063FC6F226B350B32A6897A1F154B3D42A260B3D907EDA1BA295D63C8B5C4B |

Zone-context does not accept burst sampling; the initial two-sample invocation was correctly refused before the successful single acquisition.

## After Glyph finishes

Use PowerShell 7 on LEGION. After Glyph has finished updating and the installation is stable, the new launcher coordinates the existing shared Update Helper and RR2 analyzer:

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
python -B scripts/patch_recovery.py --checkpoint docs/validation/patch-recovery-legion-20261124.json --attempt patch-20261124-01
```

If another repo has already completed the **same post-patch** shared capture using Update Helper's pinned-baseline workflow, reuse its exact prefix with `--reuse-shared-prefix <completed-prefix>` and a new RR2 attempt name. The launcher replays the shared reports with Update Helper, checks the current installation inventory and metadata against the captured manifest, and independently hashes the current executable. Metadata checks do not constitute a second full-content rehash. Use a fresh shared scan if there is any doubt. Never reuse the pre-patch rehearsal as post-patch evidence.

All attempts write new receipts and command logs under `artifacts/patch-recovery/<attempt>/`, with `summary.json` published after completion. A missing summary means the workflow did not complete. The selected-file comparison may legitimately report changes; the launcher handles analyzer exit code 1. It never launches RIFT, deploys an addon, or grants runtime compatibility.

The installed-addon baseline is separately preserved at `artifacts/prepatch-20261124-legion-installed-addon/`: seven exact startup file copies plus a check receipt (SHA-256 `7DF4996E1080B32317625CCA00B3791FE5674208DF1765374057B56C1ECBFAAF`). All seven files were present, pinned and readable; four had line-ending-only differences from the repository (`RiftAddon.toc`, `reference.lua`, `live.lua`, `main.lua`). No addon was redeployed. The launcher distinguishes a subsequent installed-file change from the already-known repository byte mismatch.

The original RR2 baseline remains immutable. The independently pinned shared baseline SHA is supplied to Update Helper by the launcher, as required by its updated CLI.

## Recovery order

1. Establish whether the installation changed, including data-only changes, and preserve a verified new-build executable copy for offline evidence. Compare source hashes; do not overwrite historical profiles or relax exact-build admission.
2. Reacquire the current physical process identity. Check the installed addon package and independent API/telemetry freshness; test read-only acquisition and compare to independent references. A new build invalidates old native candidate assumptions even if an offset is unchanged.
3. Prioritize core position, vitals, player/target and zone observations; compare each result and failure class to retained evidence. Reuse complementary RRE findings with provenance. Restore only separately validated reader paths; retain unavailable/candidate labels.
4. Validate relevant offline contracts, then separately requalify current runtime behavior. Do not promote old movement or camera calibration, map/route evidence, or live-input permissions across changed builds. Workbridge capture remains a known separate dependency issue (missing three runner files); do not treat it as patch damage.
5. Commit tested scoped changes and push; preserve concurrent edits and local baseline receipts. No new gameplay automation is needed for this recovery preparation.

No actual post-patch compatibility has yet been established.

## 2026-11-24 00:15 EST — recovery launcher rehearsal

- Seven focused launcher regression tests passed on LEGION. The earlier hardened analyzer passed 13/13 tests.
- A fresh full-install rehearsal (`artifacts/patch-recovery/rehearsal-20261124-01/summary.json`) completed in 167.5 seconds, with two consistent full captures, 266/266 installation files unchanged, and no selected RR2 changes.
- A second rehearsal using the same shared prefix (`artifacts/patch-recovery/rehearsal-20261124-02/summary.json`) completed in 4.7 seconds. It replayed the shared comparison, rechecked current inventory and metadata, independently hashed the executable, and captured two consistent current RR2 selections. All seven installed addon startup files matched their independently preserved pre-patch copies, with four known line-ending-only differences versus the repository.
- The second rehearsal used the final checkpoint and launcher including the installed-addon baseline and metadata guards. Both are pre-patch rehearsals, not post-patch evidence or proof of live compatibility. The new-build copy path remains unexercised against an actual changed game executable.
- Shared evidence prefix `rr2-rehearsal-20261124-01`, report SHA-256 `ea4101a2e0418ab8052da7818920d7efe930523e101ed7e89114e10e884f9a48`. Reused RR2 report SHA-256 `74613994425fa9e895f5744cb17335f76b9c491b9fc5d7950cbba0009e4683c0`.
