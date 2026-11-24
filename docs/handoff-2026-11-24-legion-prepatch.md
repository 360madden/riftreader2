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

Use PowerShell 7 on LEGION. Do not run while the installer is changing files.

```powershell
Set-Location -LiteralPath 'C:\work\Update Helper'
python -B post_patch.py --expected-host LEGION --before before-20261124-legion.json --prefix patch-20261124-attempt-01
if ($LASTEXITCODE -ne 0) { throw 'Shared patch capture incomplete; inspect and use a new attempt prefix' }

Set-Location -LiteralPath 'C:\work\riftreader2'
$sdk = 'C:\work\tools\dotnet\10.0.302\dotnet.exe'
$dll = Join-Path $PWD 'tools\RiftUpdateAnalyzer\bin\Release\net10.0\RiftUpdateAnalyzer.dll'
& $sdk build tools/RiftUpdateAnalyzer/RiftUpdateAnalyzer.csproj -c Release -p:RestoreLockedMode=true
if ($LASTEXITCODE -ne 0) { throw 'Analyzer build failed' }
$sources = @('--source','game=C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe','--source',"rr2-addon=$PWD\addon",'--source',"rr2-config=$PWD\config",'--source',"rr2-calibration=$PWD\.local\waypoints-calibration")
$before = Join-Path $PWD 'artifacts\prepatch-20261124-legion-rr2.json'
$after = Join-Path $PWD 'artifacts\postpatch-20261124-legion-rr2-attempt-01.json'
$diff = Join-Path $PWD 'artifacts\postpatch-20261124-legion-rr2-attempt-01-diff.json'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $before).Hash -ne '23FA92E2B6B9793D018C26996DE94289E783A7562444B08918534627239F3D0C') { throw 'Unexpected baseline hash' }
& $sdk $dll capture --expected-host LEGION @sources --out $after
if ($LASTEXITCODE -ne 0) { throw 'RR2 capture failed' }
& $sdk $dll compare --before $before --after $after --out $diff
if ($LASTEXITCODE -notin @(0,1)) { throw 'RR2 comparison failed' }
Get-Content -LiteralPath $diff
```

Use a new output suffix for retries, never overwrite the baseline. Exit 1 from the analyzer compare means a detected change, not a tool failure.

## Recovery order

1. Establish whether the installation changed, including data-only changes, and preserve a verified new-build executable copy for offline evidence. Compare source hashes; do not overwrite historical profiles or relax exact-build admission.
2. Reacquire the current physical process identity. Check the installed addon package and independent API/telemetry freshness; test read-only acquisition and compare to independent references. A new build invalidates old native candidate assumptions even if an offset is unchanged.
3. Prioritize core position, vitals, player/target and zone observations; compare each result and failure class to retained evidence. Reuse complementary RRE findings with provenance. Restore only separately validated reader paths; retain unavailable/candidate labels.
4. Validate relevant offline contracts, then separately requalify current runtime behavior. Do not promote old movement or camera calibration, map/route evidence, or live-input permissions across changed builds. Workbridge capture remains a known separate dependency issue (missing three runner files); do not treat it as patch damage.
5. Commit tested scoped changes and push; preserve concurrent edits and local baseline receipts. No new gameplay automation is needed for this recovery preparation.

No actual post-patch compatibility has yet been established.
