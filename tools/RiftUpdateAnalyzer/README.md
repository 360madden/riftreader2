# RIFT Update Analyzer (.NET 10)

Standalone **read-only file comparison** for RR2 game-update preparation. It never launches RIFT, sends keys, modifies game files, reads process memory, or installs patches.

## Build and verify on Windows

From PowerShell in the RiftReader2 checkout:

```powershell
dotnet build tools\RiftUpdateAnalyzer\RiftUpdateAnalyzer.csproj -c Release -p:RestoreLockedMode=true
python -m unittest tests.test_rift_update_analyzer -v
```

Use the SDK pinned in `global.json`. When it is outside `PATH`, set
`RIFTREADER2_DOTNET` to its executable for the Python tests and invoke that
executable for the build. The full repository validation builds this tool
and passes its selected .NET executable to the tests.

## One-command comparison after the patch

Run on the verified Windows host after Glyph finishes and game files are settled.
Set `$rrBaseline`, `$rrGameExe`, `$rrInterface`, `$rrRoutes` and `$rrOutput` to
the local paths for this comparison.

```powershell
$rrHost = [Environment]::MachineName
dotnet tools\RiftUpdateAnalyzer\bin\Release\net10.0\RiftUpdateAnalyzer.dll run --expected-host $rrHost --baseline-dir $rrBaseline --game-exe $rrGameExe --interface-dir $rrInterface --routes-dir $rrRoutes --out-dir $rrOutput
```

Choose a **new, not-yet-existing** output directory each time. Four immutable artifacts are written there:

- `before.json`: baseline hashes + root/host provenance.
- `after.json`: current hashes + root/host provenance.
- `changes.json`: added, removed and modified selected files; executable-change and requalification flags.
- `REPORT.md`: readable summary, SHA-256 changes and source coverage.

The exit code is `0` when the selected content is unchanged, `1` when any selected file changes, `2` for bad arguments and `3` when a scan is incomplete, unsafe or inaccessible. **Exit 1 is an expected comparison result, not a crash.**

## Reusable three-step CLI

Create snapshots from arbitrary explicit sources (use a new output filename for every capture):

```powershell
$rrHost = [Environment]::MachineName
dotnet tools\RiftUpdateAnalyzer\bin\Release\net10.0\RiftUpdateAnalyzer.dll capture --expected-host $rrHost --source "game=$rrGameExe" --source "routes=$rrRoutes" --out artifacts\example-current.json
dotnet tools\RiftUpdateAnalyzer\bin\Release\net10.0\RiftUpdateAnalyzer.dll compare --before C:\path\baseline.json --after C:\path\current.json --out C:\path\changes.json
dotnet tools\RiftUpdateAnalyzer\bin\Release\net10.0\RiftUpdateAnalyzer.dll report --comparison C:\path\changes.json --out C:\path\changes.md
```

Source groups create stable logical keys (such as `game/rift_x64.exe` or `routes/silverwood.json`) independent of absolute machine path. SHA-256 + byte length decides change, not timestamps.

The scan rejects the wrong computer, traversal or reparse links, duplicate groups/keys, malformed manifests, incomplete concurrent source writes, inaccessible files and exceeded file/byte limits (default 5,000 files / 512 MiB per snapshot). File handles are closed promptly.

## Coverage and qualification limits

The November 17 prepatch backup is **selected**, not a complete RIFT installation. The automatic `run` command covers:

- The single game executable `rift_x64.exe`
- The saved addon variables within `Interface\Saved`
- Only the **15 addon directory names** preserved under the baseline's `interface-addons` directory
- The saved RR2 `artifacts\waypoint-routes` directory

It does **not** diff RIFT's complete game assets or archives. A data-only game patch can leave all selected hashes unchanged. File hashes alone cannot validate live RIFT offsets, pointer chains, collision data, movement or addon semantics. If the game was updated, **reacquire exact process/executable identity and independently requalify affected live readers** before relying on them. An unchanged report is a statement about selected files, not proof of game version or navigation safety.

Latest implementation verified independently of live gameplay; **no RIFT patch installation was initiated by this tool**.
