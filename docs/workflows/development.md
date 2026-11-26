# Development workflow

Use this as a reference when needed, not a mandatory checklist for every edit.
The default is a short path to a working RR2 feature.

## Proactive discovery and efficient live sessions

Choose the next useful capability with its dependencies and likely follow-on
discoveries in view. Prefer a small probe that can unlock several consumers over
repeated isolated checks with high setup cost. Read retained RR2/RRE findings
first, including unavailable results and their scope. Record a promising lead
with the next discriminating observation and the capability it could unlock;
it remains a lead until evidence supports it.

Before live access, finish useful offline implementation and focused checks.
Group compatible live questions sharing the same build/session, target, route
or state change. Use existing captures/receipts and telemetry together so one
fight can inform action effects, resource/timing observations, target ending,
recovery and route return. Reuse observations for later analysis; keep native
and API clocks, source identities and availability distinct. Co-occurrence is
not causation and a shared capture does not make every field qualified.

Reuse the setup, not stale action admission: keep current identity, freshness,
ownership, readiness and release checks on each action. A STOP exercise ends its
run until explicit Resume/new-run authority; do not merge incompatible tests or
expand live scope to fill a batch. Do not add every possible measurement as a
prerequisite to the useful result. After a failure, retain the capture and narrow
the next probe instead of rerunning the whole sequence without a new hypothesis.

Keep independent workers preparing the next needed code, profiles, targeted
checks or evidence analysis while the single live owner operates. Material
discoveries and blockers should change priorities promptly. Use short notes in
the current workflow/roadmap; this is an operating habit, not a new framework or
a mandatory checklist for routine edits.

## CLI-first application interfaces

Joey's November 14 direction applies to all apps: **CLI first, GUI second, both
preferred**. A useful operation should be callable through shared application
code and a scriptable CLI; the GUI presents and controls the same operation and
state. Important workflows should not require automation to click through UI.
Support headless operational paths where applicable; visualization can still
require a window, with CLI launch/configuration/control where useful.

Use discoverable command groups/help, structured JSON when needed, meaningful
exit/refusal states and consistent status/start/stop/resume behavior where those
operations exist. Preserve identity, ownership, STOP/release and availability
checks equally through both interfaces. Prefer CLI for AI scaffolding and
automation when it supplies the required capability; GUI interaction remains a
useful fallback for a genuine interface gap.

Implement CLI support with the next useful feature and align the corresponding
GUI behavior. Choose routine command details without requiring Joey to specify
each flag. Reuse existing commands/contracts; do not invent a new generic CLI
framework or retrofit every historical app before delivering useful work.

## Current live workflow on physical Windows

Run read-only native, Telemetry, and NPC survey workflows on the verified local
Windows host running RIFT. Pin one local `rift_x64` PID and recheck its start
time, executable hash and window as applicable. Work on one host per session.
Use PowerShell 7 for these examples. Set the local hostname and choose the
interpreter for the rest of the examples in this section.

```powershell
$rr2Host = [Environment]::MachineName
$rr2Python = $env:RIFTREADER2_PYTHON
if (!$rr2Python) { $rr2Python = 'python' }
```

The read-only selector reports process identity without interacting with the
game window.

```powershell
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host
# With multiple physical RIFT instances, pass --physical-pid with the chosen PID.
```

Use `--check-native-reader` to check that the executable starts and advertises
the native read commands. The check needs no game process. The wrapper defaults
to the checkout's Debug build. Use `--native-reader` with an absolute local path
to select a published build for a dependency check or a `--read-native` command.

```powershell
& $rr2Python -B scripts/physical_rift.py --expected-host $rr2Host --check-native-reader
```

### Publish the local native reader

From the repository root, use the SDK pinned by `global.json`. Set
`RIFTREADER2_DOTNET` to the local SDK's executable path if it is outside `PATH`.
An already published build can use the last command below with its absolute
executable path in `$rr2PublishedReader`. Keep the published folder together
when copying it to a new checkout or workstation.

```powershell
. .\scripts\resolve-validation-dotnet.ps1
$rr2SdkVersion = (Get-Content global.json -Raw | ConvertFrom-Json).sdk.version
$rr2DotNet = Resolve-ValidationDotNet -RepositoryRoot (Get-Location).Path -PinnedSdk $rr2SdkVersion
$rr2LiveProject = 'src/RiftReader2.Live/RiftReader2.Live.csproj'
$rr2Publish = Join-Path (Get-Location).Path 'artifacts/tools/native-published'
& $rr2DotNet restore $rr2LiveProject --locked-mode
if ($LASTEXITCODE -ne 0) { throw 'Native reader restore failed.' }
& $rr2DotNet publish $rr2LiveProject -c Release --no-restore -o $rr2Publish
if ($LASTEXITCODE -ne 0) { throw 'Native reader publish failed.' }
$rr2PublishedReader = Join-Path $rr2Publish 'RiftReader2.Live.exe'
& $rr2Python -B scripts/physical_rift.py --expected-host $rr2Host --check-native-reader --native-reader $rr2PublishedReader
```

Add `--native-reader $rr2PublishedReader` to use that build in the following
native read commands. Set `$env:RR2_NATIVE_READER = $rr2PublishedReader` to use
it as the default for physical reads and Waypoints in this shell and its child
processes. An explicit `--native-reader` takes precedence where supported.

### Publish both physical tools for local use

`publish-physical-tools.ps1` uses the pinned SDK to publish the native reader
and the WGC probe with their .NET runtimes. It checks the reader's help output
and runs the probe's offline self-test. The command creates a new directory
under `artifacts/tools/physical/` by default. Use `-OutputDirectory` to choose
a new local directory, and keep both tool folders intact when copying them.

```powershell
$rr2Host = [Environment]::MachineName
.\scripts\publish-physical-tools.ps1 -ExpectedHost $rr2Host -UseForCheckout
.\rr2-check-dependencies.cmd --expected-host $rr2Host --workflow wgc
```

`-UseForCheckout` records the verified bundle as the checkout's selection for
later launches, including from Explorer. To reuse a copied bundle, run
`publish-physical-tools.ps1 -ExpectedHost $rr2Host -RegisterBundle PATH` with
its local path. Registration checks the reader, the WGC runtime files listed
by the probe, and its offline self-test. It uses the current host's checkout
settings and needs PowerShell 7 and the published bundle.

Readers that advertise the position panel require its default profile beside
the executable. If the reader supports `position-panel --check-profile`,
registration also validates the profile and compares the reported file hash.

`RR2_PHYSICAL_TOOLS_ROOT` selects a different local bundle for the current shell
or selects the checkout's Debug builds with the value `debug`.
`RR2_NATIVE_READER` and `RR2_WGC_PROBE` take precedence for their respective tools.
The WGC probe uses the requested output path to find the checkout's `artifacts`
directory. Republish older bundles if the dependency check reports
`gpu-probe-relocation-update-required`.

### Prepare local physical Python environments

With 64-bit Windows Python and Tcl/Tk installed, create a new environment for
Waypoints and WGC. `--extra overlay` adds Qt and DXcam, `--extra rerun` adds
Rerun, and `--extra validation` adds the development test dependencies with
the pinned Lua 5.1 runtime. Each environment uses its own pinned requirements
and is created at its final path on the local host.

```powershell
$rr2Host = [Environment]::MachineName
.\rr2-setup-python.cmd --expected-host $rr2Host --extra overlay --extra rerun --extra validation
```

After setup succeeds, Waypoints, dependency checks, and development validation
find the prepared interpreters under `.local/physical-python`, including from
a new shell or when Waypoints starts from Explorer. Interpreter-specific
overrides still take precedence. For a shared Python installation
outside this checkout, run with `--output-root` and apply the returned settings.

```powershell
$rr2Host = [Environment]::MachineName
$rr2PythonRoot = 'C:\path\to\new-rr2-python-environments'
$rr2Setup = .\rr2-setup-python.cmd --expected-host $rr2Host --output-root $rr2PythonRoot --extra overlay --extra rerun | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw $rr2Setup.reason }
foreach ($setting in $rr2Setup.environment.PSObject.Properties) {
    Set-Item -LiteralPath "Env:$($setting.Name)" -Value $setting.Value
}
```

If pip reports a Windows path-length error while installing Qt in a deeply
nested checkout, use `--output-root` with a shorter local path. Then register
that completed setup so a new shell or Explorer can find it.

```powershell
.\rr2-setup-python.cmd --expected-host $rr2Host --use-existing $rr2PythonRoot
```

Registration creates `.local/physical-python-link` as a Windows directory
junction after it runs the startup checks for the core interpreter and each
installed optional environment. For the overlay environment, it checks the
Qt Windows platform plugin and the installed DXcam wheel's runtime files.
For Rerun, it checks the viewer version and writes a temporary synthetic recording.
Use an environment prepared at its current location on this host. The
interpreters stay at their installed path. The core launchers honor an explicit
`RIFTREADER2_PYTHON` setting. With automatic discovery, they try the registered
setup, the checkout's default setup, its `.venv`, and system Python. They skip
interpreters that fail to start, including copied virtual environments whose
base Python is missing. Workflow checks report required packages separately.

To replace the checkout's Python junction with a verified local setup, run
`--use-existing` with `--replace-link`. The setup launcher uses the same
interpreter discovery when bootstrapping a repair.

```powershell
.\rr2-setup-python.cmd --expected-host $rr2Host --use-existing $rr2PythonRoot --replace-link
```

The command verifies the replacement before changing the junction and preserves
both environment directories.

### Reuse local tools from a fresh checkout

Set the paths you want to override in the shell that runs RR2. Keep the complete
published folders and Python environments at their installed locations. Use a
movement calibration measured on the Windows host that will run Waypoints.

| Workflow | Setting | Local prerequisite |
| --- | --- | --- |
| Full development validation | `RIFTREADER2_DOTNET`, `RIFTREADER2_LUA_PYTHON` or `RIFTREADER2_PYTHON` | [Pinned SDK and prepared Python](#restore-build-and-test) |
| Physical workflows and Waypoints | `RIFTREADER2_PYTHON` | Python with Tcl/Tk for Waypoints and Pillow for WGC |
| Waypoints prepared maps | `RR2_RIFTWORLD_ROOT`, `RR2_RIFTWORLD_PYTHON`, `RR2_RIFTWORLD_UPSTREAM`, `JAVA_HOME` | Git on `PATH` and [local RiftWorld, JPype, Java and pinned navigation dependencies](physical-waypoints.md#prepared-map-destinations) |
| Both native physical tools | `RR2_PHYSICAL_TOOLS_ROOT` | [Published or copied tools bundle](#publish-both-physical-tools-for-local-use) |
| Native physical reads and Waypoints | `RR2_NATIVE_READER` | [Published Live reader](#publish-the-local-native-reader) |
| Installed physical addons | `RR2_RIFT_ADDONS_ROOT` | [Register a custom local AddOns directory](addon-sync.md#check-the-local-windows-installation), or use Windows Documents |
| Waypoints calibration | `RR2_WAYPOINTS_BASIS` | [Verified calibration folder](physical-waypoints.md#local-calibration-and-dependency-checks) |
| WGC capture | `RR2_WGC_PROBE` | [Published WGC probe](#publish-both-physical-tools-for-local-use), Python with Pillow, and the active deployment's desktop-evidence directory |
| Qt waypoint markers | `RR2_OVERLAY_PYTHON` | Python with [overlay requirements](../../requirements-overlay.txt) |
| DXcam capture | `RR2_DXCAM_PYTHON` | Python with [capture requirements](../../requirements-capture.txt) |
| Rerun export and viewer | `RR2_RERUN_PYTHON` | Python with [visualization requirements](../../requirements-visualization.txt) |
| Shared desktop evidence and Workbridge capture | `RR2_WORKBRIDGE_ROOT`, `RR2_WORKBRIDGE_CLI_ROOT`, `RR2_WORKBRIDGE_NODE` | [Register an active local deployment, matching CLI, and Node.js 24+](target-observation.md#active-workflow-on-the-local-windows-host) |

Run the startup checks on the computer where you will use RR2. The command
reports each workflow in JSON and exits with code 2 if a selected check is
blocked. It uses the same Python selection as the Waypoints launchers. Repeat
`--workflow` to check a subset. Qt imports the marker presenter and checks that
its Windows platform plugin can load. Rerun reports viewer and exporter
readiness separately. The exporter check writes and removes a temporary
synthetic recording. These checks open no windows. Game process identity and
live addon publishers are verified separately during acquisition.

The ReaderBridge check looks for `ReaderBridge/RiftAddon.toc` and
`ReaderBridge/ReaderBridge.lua` under the configured AddOns root. It reports
missing or unreadable files and compares readable files with the decoder's
ReaderBridge 0.3.2 reference. A local variant is reported by hash. Its packet
decoding is checked during capture.

```powershell
$rr2Host = [Environment]::MachineName
.\rr2-check-dependencies.cmd --expected-host $rr2Host
# Check only WGC and prepared maps
.\rr2-check-dependencies.cmd --expected-host $rr2Host --workflow wgc --workflow prepared-maps
# Check the SDK and Python used by the development gate
.\scripts\validate.ps1 -CheckPrerequisites
```

### Read native telemetry

```powershell
$rr2Python = $env:RIFTREADER2_PYTHON
if (!$rr2Python) { $rr2Python = 'python' }
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native vitals
# Also: position, orientation, actor-pose, smoothed-scalar, player-context, selected-target, stats.
# For read-only actor/model/render matrix candidates (NOT qualified body heading):
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native actor-pose
# Facing matrix plus direct player-system yaw and camera/aim-point candidates:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native facing --samples 5 --interval-ms 60
# Bounded loaded-unit positions, distances from self and candidate screen points:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --physical-pid CURRENT_PID --read-native unit-positions --unit-limit 512
# For a bounded passive actor/model/render pose time series under one native lease:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native actor-pose --samples 10 --interval-ms 100
# For four native entity-owned, unqualified smooth-state scalar candidates:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native smoothed-scalar --samples 5 --interval-ms 100
# For a short read-only movement-observation burst:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native position --samples 10 --interval-ms 0
# For repeated HP/resource observations under one native session:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native vitals --samples 10 --interval-ms 0
# Exact-build Warrior Power candidate, using the existing native C# reader:
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --read-native power --samples 5 --interval-ms 200
# Add --physical-pid PID if more than one local RIFT instance is running.
```

For two candidate native positions across a 1–30 second observation window,
use the manual motion probe. It keeps the PID, process epoch, build, window
identity and sampled player key consistent. Use a fresh output directory to
retain both raw reports and replay the candidate displacement offline.

```powershell
& $rr2Python -B scripts/physical_manual_motion_probe.py --host $rr2Host --pid CURRENT_PID --seconds 2 --native-reader $rr2PublishedReader --output artifacts/NEW_MANUAL_MOTION
& $rr2Python -B scripts/physical_manual_motion_probe.py --replay artifacts/NEW_MANUAL_MOTION/manual-motion.json
```

The report records both sample times and the XYZ delta. The observer sends no
keys and leaves focus alone. Replay can run on another analysis machine after
copying the directory. It checks both raw report hashes and recomputes the delta.

Before selecting RIFT for a Telemetry target series, check the local 64-bit
Windows Python, both native reader commands, and the installed Telemetry files.

```powershell
& $rr2Python -B scripts/capture_physical_telemetry_target_series.py --check-dependencies --expected-host $rr2Host --native-reader $rr2PublishedReader
```

The check reads the metadata of `RiftAddon.toc`, `main.lua`, and `telemetry.lua`
in the Telemetry folder under the local Windows Documents addon directory.
Use `--installed-telemetry-dir` to check a custom installation. The
[addon inventory](addon-sync.md#inspect-addon-metadata) reports residency details.
The dependency check requires no PID. Capture verifies the current process,
build and advancing Lua publisher.

Add `--include-native-target-levels` to the dependency check and capture to
compare the selected unit's exact ID and level in each window. Copy the full
series directory to replay from its `result.json`. The replayer verifies the
original window summaries by hash, including any window that required a scope
rediscovery.

```powershell
& $rr2Python -B scripts/capture_physical_telemetry_target_series.py --expected-host $rr2Host --physical-pid CURRENT_PID --include-native-target-levels --output-dir artifacts/NEW_TARGET_LEVEL_SERIES
& $rr2Python -B scripts/replay_physical_telemetry_target_series.py --series artifacts/NEW_TARGET_LEVEL_SERIES/result.json
```

With the freshly verified `CURRENT_PID`, use a new output directory for each
command. NPC survey preparation verifies the installed addon files and prints
the bind and capture commands. It looks under the current user's Windows
Documents folder. Pass `--installed-casting-dir` for a custom installation.
Run the capture command after the operator binds the nonce in RIFT.

```powershell
& $rr2Python -B scripts/physical_nearby_units.py --expected-host $rr2Host --physical-pid CURRENT_PID --include-levels --output-dir artifacts/NEW_NEARBY
& $rr2Python -B scripts/collect_physical_player_state.py --expected-host $rr2Host --physical-pid CURRENT_PID --include-stats --include-zone --output-dir artifacts/NEW_PLAYER_STATE
# Optional exact-build Warrior Power plus a second player-context check:
& $rr2Python -B scripts/collect_physical_player_state.py --expected-host $rr2Host --physical-pid CURRENT_PID --include-stats --include-zone --include-power --output-dir artifacts/NEW_POWER_STATE
& $rr2Python -B scripts/capture_physical_telemetry_target_series.py --expected-host $rr2Host --physical-pid CURRENT_PID --native-reader $rr2PublishedReader --output-dir artifacts/NEW_TARGET_SERIES
& $rr2Python -B scripts/prepare_physical_npc_survey.py --check-dependencies --expected-host $rr2Host --include-levels
& $rr2Python -B scripts/prepare_physical_npc_survey.py --expected-host $rr2Host --physical-pid CURRENT_PID --include-levels --output-dir artifacts/NEW_NPC_PLAN
```

For a published build, pass `--native-reader $rr2PublishedReader` to
`physical_nearby_units.py`, `physical_selected_target_profile.py`, or
`collect_physical_player_state.py`. Each collector uses the selected executable
for all of its native samples. The Telemetry zone and target-series captures
use the selected reader for the survey and both sides of every bracket,
including a stale-scope retry. The NPC dependency check verifies the installed
addon files and reader startup without selecting RIFT. The generated capture
command uses the verified bind plan and selected reader. Use `--bind-plan` with
the copied plan and a local reader path to run from another checkout on the
capture host.

Copy the player-state directory with its `summary.json` and native source files
to replay it offline. Replay locates the sources beside the summary and checks
each SHA-256, executable path and process identity recorded at capture. Pair
and history reports retain the capture host, process identity and sample times.
The opt-in Power source is process-scoped: matching Warrior context before
and after the burst is required, but its native unit key remains unavailable.
Power-enabled bundles must pass source replay before summary publication.
Unsupported builds or unavailable Power refuse the opt-in collection.
`--after` compares two ordered captures from the same process on the same host.
Power comparisons distinguish the last-to-last difference from the gap between
the earlier burst's last sample and the later burst's first sample. History
preserves within-burst extrema and reports missing Power captures explicitly;
these differences are not measured spending, regeneration or continuous traces.

```powershell
& $rr2Python -B scripts/replay_physical_player_state.py --summary artifacts/NEW_PLAYER_STATE/summary.json
& $rr2Python -B scripts/replay_physical_player_state.py --summary artifacts/EARLIER_PLAYER_STATE/summary.json --after artifacts/NEW_PLAYER_STATE/summary.json
& $rr2Python -B scripts/replay_physical_player_state.py --summary artifacts/EARLIER_PLAYER_STATE/summary.json --history artifacts/NEW_PLAYER_STATE/summary.json
```

For captures from distinct RIFT processes on the same host and executable
build, use the cross-epoch comparator. It compares positions, HP and optional
zone candidates after replaying both source bundles. Raw stat slots are compared
when both bundles include stats and their player-key candidates and selector
layouts agree. The report describes numeric agreement across separate epochs.
Optional Power endpoints are compared only for matching self-key and recipe
candidates. These are uncorrelated numeric differences, not resource changes.
Player continuity, action causation and independent Lua agreement remain unverified.

```powershell
& $rr2Python -B scripts/compare_physical_player_state_epochs.py --before artifacts/BEFORE_RESTART/summary.json --after artifacts/AFTER_RESTART/summary.json
```

For an existing RRE saved-snapshot JSON export, the progression-only mode
reuses the export SHA-256 and player-ID checks without requiring a stat capture.
It reports saved API Experience fields and native/saved level candidates. A
missing or empty Experience map does not prove a level cap; the normal-domain
fraction is historical only. Native XP is not captured by this workflow.

```powershell
& $rr2Python -B scripts/compare_saved_api_stats.py --state-summary artifacts/NEW_PLAYER_STATE/summary.json --reference EXPORTED_RRE_JSON --reference-sha256 EXPORT_SHA --progression-only --output artifacts/NEW_PROGRESSION.json
```

On the two supported executable hashes, the raw Experience seed can also be
retrieved without input. Use a newly built native reader that supports the
updated command (the older published bundle may not). Its raw progression
record, record level and float are not calculated accumulated/needed/rested XP.

```powershell
& $rr2Python -B scripts/physical_rift.py --expected-host $rr2Host --physical-pid CURRENT_PID --read-native experience-seed --native-reader $rr2PublishedReader --output artifacts/NEW_XP_SEED.json
```

Use `experience-values` with the same freshly built reader for typed value
candidates. Both supported builds can return the initialized baseline, level
limit, required XP, calculated accumulated XP and raw rested candidate. The
wrapper derives a progression fraction only for a valid normal-domain result.
Missing providers, cache misses, sentinels and invalid types do not establish
zero experience or a level cap. All values remain candidates; independent API
agreement and changed-state/restart qualification are separate checks.

```powershell
& $rr2Python -B scripts/physical_rift.py --expected-host $rr2Host --physical-pid CURRENT_PID --read-native experience-values --native-reader $rr2PublishedReader --output artifacts/NEW_XP_VALUES.json
```

The RR2A1 collector compares advancing unbound addon coordinates with native
position brackets. The RR2R1 probe can retain potential reference frames for
offline replay. A strict RR2R1 assessment requires the exact active addon nonce.
Both capture commands accept `--native-reader $rr2PublishedReader`. RR2A1 uses
the selected binary for every scan and native bracket. For a nonce-bound RR2R1
assessment during capture or offline replay, `--cli` selects a published
`RiftReader2.Cli.dll` and `--dotnet` selects the local .NET host.
Use the same SDK to publish the decoder when needed.

```powershell
$rr2DecoderProject = 'src/RiftReader2.Cli/RiftReader2.Cli.csproj'
$rr2DecoderFolder = Join-Path (Get-Location).Path 'artifacts/tools/decoder-published'
& $rr2DotNet restore $rr2DecoderProject --locked-mode
if ($LASTEXITCODE -ne 0) { throw 'Decoder restore failed.' }
& $rr2DotNet publish $rr2DecoderProject -c Release --no-restore -o $rr2DecoderFolder
if ($LASTEXITCODE -ne 0) { throw 'Decoder publish failed.' }
$rr2DecoderCli = Join-Path $rr2DecoderFolder 'RiftReader2.Cli.dll'
```

```powershell
& $rr2Python -B scripts/collect_physical_rr2a1_pair.py --expected-host $rr2Host --physical-pid CURRENT_PID --native-reader $rr2PublishedReader --output-dir artifacts/NEW_RR2A1_PAIR
& $rr2Python -B scripts/probe_physical_rr2r1.py --expected-host $rr2Host --physical-pid CURRENT_PID --native-reader $rr2PublishedReader --max-scans 1 --output-dir artifacts/NEW_RR2R1_SCAN
& $rr2Python -B scripts/probe_physical_rr2r1.py --replay-summary artifacts/NEW_RR2R1_SCAN/summary.json --output-dir artifacts/NEW_RR2R1_REPLAY
# For nonce-bound replay, also pass --session-id ACTIVE_NONCE --cli $rr2DecoderCli --dotnet $rr2DotNet.
```

For a resumed RR2R1 capture, keep the previous capture folder together with the
resumed capture folder. Use `--resume-source-summary` to supply the immediate
predecessor. Replay checks the saved summary hash, the original requests and
receipts, the recorded host and process identity, the reader hash, and the
resume cursor. These are offline checks and can run from a different checkout.

```powershell
& $rr2Python -B scripts/probe_physical_rr2r1.py --replay-summary artifacts/RESUMED_RR2R1_SCAN/summary.json --resume-source-summary artifacts/PREVIOUS_RR2R1_SCAN/summary.json --output-dir artifacts/NEW_RESUME_REPLAY
```

The facing result includes `nativeValues.opticalCamera` for the supported selected
view mode. It reports optical yaw/pitch and world eye position, or a camera-specific
unavailable reason. The gameplay camera/aim-point snapshot is retained separately.
`nativeValues.positionXYZCandidate` now uses the existing entity-owned position
reader at component `+0x48`, with `positionSource` identifying that source. The
downstream player-system copy remains in `playerSystemPositionXYZCandidate`.
Raw `positionCandidate` retains its historical player-system meaning; raw
`entityPositionCandidate` and `entityPositionRawBits` retain the independent read.
Older reports without the entity fields use an explicitly labeled legacy snapshot.
Projection and target-relative arithmetic use entity XYZ when present.

`unit-positions` reuses the exact-build unit-manager topology and typed position
reader. It examines at most 512 entries under a 2 MiB read budget and retains
unit keys as text. `nativeValues.units` is sorted by horizontal distance from
the captured self position and includes normalized screen points when the camera
matches before/after the scan. `--start-bucket N` selects the starting bucket;
the report exposes scan limits, buckets examined, absent position components and
unavailable rows/chains. This is a loaded-manager subset with sequential samples,
not a complete world inventory, unit classification, occlusion or freshness proof.
Camera changes withhold screen points while retaining the position candidates.
`nativeValues.playerScreenPointCandidate` projects the captured facing XYZ into
top-left normalized client coordinates. To project another supplied world point,
add `--project-world X Y Z` to the facing command. The result appears under
`projectedWorldPointCandidate`. The raw report retains projection matrix, viewport
and float32 bits. `insideViewportCandidate` checks screen bounds only and cannot
establish occlusion. Multiply normalized coordinates by the current client size;
window borders and the title bar are outside that coordinate system.
Add `--include-target` to the facing command to reacquire the existing gated
target-position candidate in the same native session. The compact
`selectedTargetProjectionCandidate` retains target key, world XYZ, guard status
and screen point. Camera reads bracket the target acquisition. A changed camera
withholds the screen point; a changed player owner or position rejects the combined
sample. The fallback target-key branch remains explicitly labeled. Target freshness,
hover independence, occlusion and restart recovery are separate qualifications.
The target result also includes `relativeToPlayerCandidate`, with the XYZ delta,
horizontal/3D distance, world bearing and signed angles from primary/body facing.
Distances use native coordinate units; bearings use positive Z toward positive X.
Coincident X/Z and exactly opposite directions withhold a signed turn angle.
This arithmetic does not establish matching world identity or movement eligibility.

For one reviewed screenshot with a matching native position, facing and target
snapshot, use the observation entry point on the verified local host.

```powershell
.\rr2-observe.cmd --target physical --expected-host $rr2Host --physical-pid CURRENT_PID --native-facing
```

This selects the WGC probe and brackets the image with native reads. It never
focuses RIFT or sends input. `nativeFacing.status` is `stable-bracket-candidate`
only when process/window identity, player sources, orientation, camera and target
match across the frame within five seconds and acquisition timestamps are ordered.
Then `nativeFacing.values` contains the native values associated with that image.
Otherwise the screenshot remains available and `nativeFacing` gives an unavailable
reason plus any completed raw report paths. These sequential reads cannot exclude
ABA changes or establish frame freshness, occlusion or restart recovery.
The WGC receipt optionally records physical window geometry and a validated
`clientFrameMapping`. The combined result adds `playerFramePointCandidate` and
target `framePointCandidate`, expressed in full-size screenshot pixels. The probe
uses its own temporary DPI context and read-only client/DWM geometry; the visible
frame size must match the bitmap. Unavailable or old geometry withholds pixel
points while retaining the image and normalized candidates. `insideClientCandidate`
distinguishes gameplay-client coordinates from title-bar/border coordinates that
can still satisfy `insideFrameCandidate`. These remain coordinate candidates.

For a **single-command, read-only** distance/progress preview against an existing
named anchor (replace the example catalog and ID with actual saved values):

```powershell
& $rr2Python scripts/physical_rift.py --expected-host $rr2Host --physical-pid CURRENT_PID --read-native position --samples 10 --interval-ms 100 --anchor-catalog config/my-anchors.json --anchor-id North_Gate
```

The `offlineAnchorPreview` is candidate X/Z arithmetic only. It never authorizes
movement or proves source freshness, world-instance compatibility or arrival.
Use `scripts/analyze_physical_turn_pair.py --help` for an independent offline
before/after orientation comparison; its deltas also remain unqualified candidates.

It rechecks local process/build identity, passes exact PID/start epoch to the .NET
reader and writes a new unique JSON artifact; no game input, screenshot, guest,
or foreground change. Build `src/RiftReader2.Live` with the pinned .NET 10 SDK
first if `native-reader-not-built` is returned. Native `vitals`, `position`,
and `actor-pose` receipts include compact `nativeValues` (HP/resources, last XYZ,
or actor/model/render planar-angle candidates) for programmatic use; the full raw
candidate report is retained at `nativeOutput`. The actor-pose report is a new
read-only physical route using the existing exact-build actor reader; it does
not qualify body or camera facing. On AMD-DESKTOP (November 10), one physical
RIFT read returned actor planar candidate **111.8823°**, model candidate **0°**,
and `alternate-reference-branch-not-followed`, with no game input.
For 2-30 actor-pose samples, the separate
`native-current-actor-pose-candidate-burst/1` report retains every raw sample
under one lease and process session. Each read revalidates the exact game epoch;
missing, changed-player or invalidated bursts produce **no completed report**.
The compact receipt projects the last sample and count, never qualified heading.
It also exposes `planarAngleSeriesDegreesCandidate` for actor/model/render
and wrap-aware `planarSignedTravelDegreesCandidate` plus the actor's largest
adjacent angle step. Missing angle values or an exactly 180° step produce
unavailable signed travel, not a guessed direction. These are readout aids,
**not** proof of body-facing response to a turn.
Use `python scripts/physical_rift.py --expected-host ([Environment]::MachineName) --read-native actor-pose --samples 10 --interval-ms 100 --include-position` for opt-in, read-only before/after XYZ brackets around each actor pose (explicit `--physical-pid N` when multiboxed). The compact receipt adds `positionBracketSeriesCandidate`, `positionNetPlanarDisplacementCandidate` and `positionMaxWithinSamplePlanarChangeCandidate`; every bracket is checked against the same player key. Brackets are sequential, not atomic or proof of body-facing, motion freshness or turn response. The receipt also provides `positionObservedPlanarPathLengthCandidate` and `positionMaxAdjacentPlanarStepCandidate` across all successive before/after X/Z anchors. Unlike net displacement, observed path length can reveal an out-and-back excursion; zero is not proof of no movement between samples. No game input or foreground changes are made.
Actor and render world-translation candidates are now exposed from the matrix payloads
already read. With `--include-position`, `actorPositionPlanarResidualSeriesCandidate`
measures each actor X/Z's distance to its same-owner before/after position segment;
`actorPositionVerticalOffsetSeriesCandidate` compares Y to the segment's projected
height. `actorPositionMaxPlanarResidualCandidate` is null if any actor translation is
unavailable. These are structural consistency scores, not proof of freshness or facing.
The raw bracket also includes `secondaryBeforeCandidate` and `secondaryAfterCandidate`
from the existing position-component `+0x88` bytes when finite. A read-only physical
sample on November 10 found both secondary XYZs identical to primary XYZ; actor Y
was 0.060 lower, so secondary-vs-primary did not explain the vertical offset.

Opt in to the exact-build transform-source comparison with
`python scripts/physical_rift.py --expected-host ([Environment]::MachineName) --read-native actor-pose --samples 1 --include-position --include-transform-sources`.
It adds three owner-bracketed native triplets only when requested:
`position+0x88`, `actor+0x4F8`, `actor+0x770`, and reports their reconstructed
actor translation and maximum deviation from the stored `actor+0x3BC` XYZ.
The **2026-11-11 01:12:29 UTC read-only physical capture** on AMD-DESKTOP,
PID 44888 (exact build SHA pinned), measured primary and secondary Y `863.5872`,
first actor Y offset `0`, second actor Y offset `-0.06`, and stored/reconstructed
actor Y `863.5272`, with **0 maximum X/Y/Z difference**. This resolves the
observed static -0.06 Y discrepancy to actor offset `+0x774` (the Y member
of the `+0x770` triplet), not primary-vs-secondary position. Raw evidence:
`artifacts/physical-native-actor-pose-70c4746cabe04dde958b50cad58148d7.json`
(SHA256 `0593221e66264455e2c31f83860aa7d243fe681efec42a9b6e10d898f62dca85`).
The arithmetic is verified for this stationary snapshot; source freshness,
body heading, movement response and restart stability remain unqualified.
The capture performed no game input, casting or foreground changes.

The physical `--read-native orientation` route now returns validated primary and
secondary matrix angles, the two refresh indicators, and maximum matrix-element
difference in `nativeValues`; raw float32 bits remain in its artifact. A **2026-11-11
02:08-02:10 UTC** AMD-DESKTOP passive comparison (PID 44888, exact pinned SHA)
found the nine actor-matrix raw float bits at `actor+0x398` **identical** to the
position secondary matrix at `position+0x94` across two sequential, separate
owner-pinned captures. Both decoded to `111.8823333629°`; the position primary
at `position+0x60` decoded to `111.8816776312°`. Refresh handle/flag were zero.
This is empirical confirmation of the existing `0x687320` copy path on this
stationary process, **not independent or changed-state body-heading proof**.
Evidence: `artifacts/physical-native-orientation-fec7abee8bf046aeb5aa3e983572526b.json`
(SHA256 `c103b3301152d97448f37ae28c776988bac1c7a73b40eb4ccee6f07eaf916912`),
and `artifacts/physical-native-actor-pose-823b891c15ed46798ca5b1b43d644791.json`
(SHA256 `b375211022dc3c16897a4c59584db6bdf570988839936f601b4f51badf088958`).
There was no game input or focus change; the samples were not atomic.

The physical-only `smoothed-scalar` route reuses the existing exact-build
native scalar reader; it never invokes in-game getter functions or controls the
character. Its four float candidates are reported with exact raw bits and the
same PID/start epoch and owner checks as other physical reads. A 2-30-sample
burst acquires one native lease/session, revalidates each observation, rejects
changed-player/invalidated bursts, and publishes only a complete series. The
**2026-11-11 01:31 UTC AMD-DESKTOP five-sample passive capture**, PID 44888,
returned current/source/target `0/0/0` and factor `15` in all five observations
for owner key `239816685251645959`. Raw evidence:
`artifacts/physical-native-smoothed-scalar-818b2a1bb1904e2ca84a8c727791e30e.json`.
The preceding single sample yielded the same values. These scalars are not
qualified as body heading, camera yaw or turn speed; stationary consistency
cannot establish movement response, source freshness, or post-restart stability.
No input, memory write, screen capture or foreground change occurred.

A verified AMD-DESKTOP physical ten-sample, zero-delay read on November 10
captured in **395.6 ms** (~39.6 ms per observation, excluding process startup):
all ten samples kept one player key and the same 111.8823° actor candidate,
0° model candidate, and unobserved alternate render branch. This static series
proves capture mechanics, **not** angle response to turning.
Before every native launch, the reader also checks the **current physical PC's**
hostname against the selection owner and selected process host. A cached selection
from the other PC (or a malformed target) is blocked before launching the reader.
The tool checks native receipt type and returned process/build epoch before
reporting success. A position burst checks that the requested, completed, and
actual observation counts agree, and rejects missing, mixed or invalid player
keys and nonfinite XYZ; a truncated run or character switch cannot silently
produce a completed movement-observation summary. The results remain **native
candidates**, not passive-freshness, changed-state or restart-qualified values. Vitals without `--samples` keeps
its original single-observation contract; with 2-30 samples it emits a separate
`native-current-vitals-candidate-burst/1` report containing the samples and the
last observation, refusing mixed player keys. An AMD-DESKTOP physical 10-sample
zero-delay run on November 10 measured **363.1 ms** for native capture (36.3 ms
per observation; roughly 2.2 s including launch), with unchanged candidate HP
18,208/18,208. These timings are observations, not guaranteed polling rates.

The lower-level .NET `inspect-native` command also works with physical multibox
when **both** `--pid` and `--start-ticks` are supplied from a fresh local
selection. With neither option, inspection still requires exactly one RIFT
process; supplying only one option or a wrong start epoch is rejected before
any report is published:

```powershell
dotnet run --no-build --no-restore --project src/RiftReader2.Live -- inspect-native --output artifacts/my-new-native-inspection.json --pid CURRENT_PID --start-ticks CURRENT_START_TICKS
```

For the reviewed Workbridge visual backend, use `--target physical` and the
verified local name in `--expected-host`. The explicit
`--allow-foreground-change` flag permits focus changes after desktop ownership
is established. [Visual observation workflow](target-observation.md#active-workflow-on-the-local-windows-host)

Use local .NET 10 `RiftReader2.Live` for native reads and the host-local control
agent only after its exact process/config prerequisites are met. On the owning
Windows machine, verify the local hostname and select the current RIFT PID
before checking reservation availability or preparing paired configs:

```powershell
$rrHost = [Environment]::MachineName
Get-Process -Name rift_x64 | Select-Object Id, MainWindowHandle
$rrPid = <verified RIFT PID>
& $rr2Python scripts/physical_reservation_preflight.py --host $rrHost --pid $rrPid
```

The preflight samples the exact host, PID, start ticks and executable SHA. It
acquires, rechecks and releases the Windows client reservation. To prepare
paired session configs, use `python scripts/physical_control_config.py --host
$rrHost --pid $rrPid --local-ip <local-private-IPv4> --agent-port <agent-port>
--ui-port <operator-port>`. Choose an IPv4 address assigned to an eligible local
interface and two distinct ports. The command writes credentials into a new
session directory under `artifacts`. Keep those files local. Both checks work
on AMD-DESKTOP, LEGION and other verified local Windows hosts. Service startup,
movement calibration and supervised input have their own prerequisites.

For a physical multibox control agent, set **both** optional config fields
`boundProcessId` and `boundProcessStartUtcTicks` to the same freshly verified
local RIFT process. Missing or mismatched bindings fail closed; leaving both
absent retains the original exactly-one-process rule. The five native control-agent
readers (HP/resources, XYZ, orientation, actor pose, smoothed scalar) now use
this same explicit PID/start-epoch selection gate; unbound readers still reject
multiple running instances. This is offline-tested, **not yet live-qualified
for physical multibox input**. Screenshots
are not telemetry qualification; the `--native-vitals` physical route currently
remains blocked until independently tested. Any physical input additionally
needs exclusive foreground ownership, action-specific review, STOP and release.
The **historical** Lab-1/Lab-2 workflow below is retained for research evidence,
not for active scheduling. Preserve it without deploying to VMware. The old
`run_movement_session.py` live CLI, `run_targeted_click.py` action path, and
`run_xyz_workflow.py --run` are now disabled by default because their hosts are
VMware-bound. Their offline analysis functions remain available. Physical
movement/control is not yet live-qualified; use the physical selector and native
reader development path until that milestone passes independent testing.

## Default fast path

1. **Choose an outcome:** one usable discovery, retrieval, or controlled
   navigation capability. Prefer the existing reader, addon, and helpers.
2. **Implement a vertical slice:** change the fewest necessary files.
   Skip new infrastructure, planning artifacts, and speculative refactors.
3. **Check what changed:** run focused tests and exercise the real workflow
   when it is relevant and already authorized. Escalate to broad tests only
   for cross-cutting risk or a full-repository validation claim.
4. **Ship and continue:** commit only the verified files, push when authorized,
   and take the next useful task. A short result/blocker note replaces routine
   reports. Write a handoff only for a real session stop or ownership transfer.

Live input still requires fresh exact identity, source/freshness gates,
exclusive controller ownership, bounded action and verified STOP/key release.
These checks are implemented by existing helpers; do not duplicate them as
new forms, reviews or process layers.

## Discovery priority

Joey's durable November7 correction: **practical discovery results come first;
refinement can happen later, or never.** Use the shortest reliable route to the
next useful observation or working capability. Reuse existing tools and move
to actual use after the relevant focused checks pass. Cleanup, abstractions,
polish, extra reporting, broad test runs and repeated reviews are not default
work or completion requirements; do them only for a concrete blocker or failure.
Preserve exact identity/freshness, ownership and STOP/release gates, and label
candidate data honestly. A concise evidence note is enough for a useful finding.

## Prerequisites

- PowerShell 7 (`pwsh`).
- The exact .NET SDK selected by `global.json` (`10.0.302`). The SDK pin disables
  roll-forward. For a custom location outside automatic discovery, pass `-DotNet`
  or set `RIFTREADER2_DOTNET` to the pinned executable.
- 64-bit Python 3.14 with Tcl/Tk for the full host suite. The Lua contract tests
  use `lupa==2.8` and its Lua 5.1 module.
- A local RiftReader2 checkout. Run the commands from its root.

Keep Git identity repository-local. The intended author is `360madden` with
email `360madden@gmail.com`; do not change global Git configuration.

## Start safely

```powershell
git status --short --branch
$rr2Host = [Environment]::MachineName
$rr2Host
dotnet --version  # Use the pinned SDK's executable path when it is outside PATH.
```

Preserve unrelated changes. Generated analysis belongs under `artifacts/`.
Use live RIFT or V1 lab tooling only for an explicitly authorized, bounded gate;
record that evidence separately from offline repository validation.

## Historical three-target discovery scheduling (superseded 2026-11-10)

Joey's 2026-11-06 decision makes both labs and physical-PC RIFT available for
authorized discovery. Prefer isolated labs to reduce inadvertent human input;
these are starting roles, not fixed assignments or evidence of readiness.

| Target | Starting role | Conditions |
| --- | --- | --- |
| RIFT-Lab-1 | Discovery | Fresh target preflight; swap with Lab-2 when useful. |
| RIFT-Lab-2 | Independent validation | Reproduce with its own identity and evidence; swap with Lab-1 when useful. |
| Physical-PC RIFT | Supplemental read-only/reference | Default while Joey uses the PC; controlled input requires existing target-specific authority and exclusive foreground/controller ownership. |

1. State the bounded evidence goal, target assignments, verification and retry
   limit. Independently check each selected target's process/start/build and the
   player, source freshness, tool and controller prerequisites applicable to the
   chosen operation. Unresolved player semantics remain candidate evidence; they
   need not block an otherwise authorized raw discovery read. Keep artifacts
   separate by target and epoch; resolve addresses afresh rather than copying
   session addresses between targets.
2. Run eligible complementary work, serializing heavy scans on the shared host.
   Reuse existing tools and brief coordination notes; this policy does not call
   for a persistent scheduler or framework.
3. After bounded retry, record the blocker and classify it as target-specific
   or shared. Switch to another eligible target for a target-specific blocker;
   use safe independent/offline work when a shared prerequisite blocks the goal.
   Never use a switch to bypass a denied action or shared gate.
4. Before leaving active input, obtain clean STOP/key release and independently
   verified controller cleanup. If cleanup is unknown, quarantine that target:
   issue no further experimental input or start a competing controller; preserve
   safe STOP/release and authorized recovery. Continue nonconflicting independent
   work. Recheck authority and readiness on the replacement target before use.
5. Record which target produced each result, what was actually verified and what
   remains blocked. Availability does not grant blanket input, addon reload,
   game/VM restart or patch-recovery authority; existing target-specific guards
   and the direct ChatGPT Computer Use deferral remain in force.

## Restore, build, and test

Use [the setup command](#prepare-local-physical-python-environments) with
`--extra validation`. For a custom output root, register the completed setup
with `--use-existing` or apply the returned `RIFTREADER2_LUA_PYTHON` setting
in the shell that runs validation. You can also prepare a repository-local
environment manually.

```powershell
python -m venv artifacts/tools/lua-python
artifacts/tools/lua-python/Scripts/python.exe -m pip install -r requirements-validation.txt
pwsh -NoProfile -File .\scripts\validate.ps1 -CheckPrerequisites
```

The manifest includes the Lua, control and overlay requirements plus NumPy and
pytest. The prerequisites check verifies the selected SDK, Python imports,
Tcl initialization and the Lua 5.1 runtime without starting a game or window.
It prints the selected .NET and Python executable paths.
The Python test step runs both unittest cases and pytest functions with Qt set
to offscreen. It uses the Release build of the standalone RIFT Update Analyzer
and the .NET executable selected by validation. For Lua-only changes,
`requirements-lua-tests.txt` is sufficient for the focused Lua tests. The local
PowerShell cache checks import their inbox modules using the child PowerShell's
installation directory.

Validation checks .NET installations on `PATH`, `DOTNET_ROOT_X64`, `DOTNET_ROOT`,
the repository's `artifacts/tools/dotnet` directory and standard Windows
installation locations. It also checks the pinned sibling when a discovered
installation directory is named for its SDK version. A match must report the
exact SDK from this checkout. An explicit `-DotNet PATH` or
`RIFTREADER2_DOTNET` selects only that executable, so an incompatible override
fails directly.

Validation checks the registered setup, the completed `.local/physical-python` setup,
`artifacts/tools/lua-python/Scripts/python.exe`, the checkout's `.venv`,
the absolute executable in `RIFTREADER2_PYTHON`, Python
installations on `PATH`, then installations listed by the Windows `py` launcher.
It selects the first interpreter that passes the Python package, Tcl and pinned
Lua checks. Use `-LuaPython PATH` or `RIFTREADER2_LUA_PYTHON` to check and use one
specific interpreter. If it fails, validation reports the missing dependencies
for that interpreter.

```powershell
pwsh -NoProfile -File .\scripts\validate.ps1 -LuaPython artifacts/tools/lua-python/Scripts/python.exe
$env:RIFTREADER2_LUA_PYTHON = 'C:\path\to\python.exe'
$env:RIFTREADER2_DOTNET = 'C:\path\to\pinned-sdk\dotnet.exe'
pwsh -NoProfile -File .\scripts\validate.ps1 -CheckPrerequisites
```

The repository does not depend on or hardcode a V1 addon or Python path.

Run `python -B scripts/check_repository_links.py` to check Markdown links
independently. Missing links to Git-ignored evidence under `artifacts/` are
counted separately because a fresh checkout only includes tracked files.
Links to missing repository files, including tracked artifacts, fail the check.

The authoritative repository check is:

```powershell
pwsh -NoProfile -File .\scripts\validate.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

The script performs Lua producer tests, shared producer-to-decoder fixtures,
locked restore, Release build, .NET tests, formatting verification, architecture
dependency and documentation-link checks, and CLI smoke tests. Check
`$LASTEXITCODE` because PowerShell does not turn a failing native command into a
terminating error automatically.

For focused development, run only the narrow command needed while iterating,
then run the authoritative script before claiming repository validation:

```powershell
dotnet restore --locked-mode
dotnet build --configuration Release --no-restore
dotnet test --configuration Release --no-build --no-restore
dotnet format --verify-no-changes --no-restore
```

Do not refresh lock files casually. An intentional package change should update
`Directory.Packages.props` and the lock files together and receive
dependency-aware review.

## Exercise the offline slice

For finite read-only Windows native captures, use the published Live executable
and the [native capture guide](../reference/native-capture.md). This path has
its own exact process/build request and preserves raw bytes and failures;
the no-argument Live executable continues to run the addon transport.

Replay the selected saved V1 wall-motion evidence:

```powershell
dotnet run --project src/RiftReader2.Cli --configuration Release -- replay-wall-motion --manifest evidence/v1-wall-motion-20261018.json
dotnet run --project src/RiftReader2.Cli --configuration Release -- replay-wall-motion --manifest evidence/v1-wall-motion-20261018.json --output artifacts/wall-motion-replay.json
```

The tracked manifest points to the exact retained V1 capture and its sibling run
artifacts under `C:\rift modding\RiftReader`. The command fails closed if their
size, SHA-256, observer/process/build identity, ordering, timing, or selected
trial evidence disagrees. It streams the capture and reports one free-travel
control plus two decisive wall-contact trials. A successful replay rejects the
saved projection as realized velocity for that fixed evidence; it does not
identify a positive projection meaning or a native velocity field. The named
output must not already exist.

Decode one exact saved addon frame. The input must be ASCII, at most 4096 bytes,
with no BOM, bytes outside the markers (including a trailing newline), or
concatenated frame. JSON whitespace inside the markers is accepted:

```powershell
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame PATH
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame PATH --output artifacts/addon-observation.json
```

Decoded reports remain source-unbound and freshness-unverified. This command
does not read RIFT or turn `RiftReader2_Frame` into a transport.

Decode one saved nonce-wrapped frame against the expected reader nonce:

```powershell
dotnet run --project src/RiftReader2.Cli -- decode-live-addon --frame PATH --session-id HEX
dotnet run --project src/RiftReader2.Cli -- decode-live-addon --frame PATH --session-id HEX --output artifacts/live-addon-observation.json
```

This is also offline validation. It checks RR2L1 framing, nonce equality, and
the inner RR2A1 contract, but its result remains source-unbound and
freshness-unverified.

## Exercise the live reader

`RiftReader2.Live` is a Windows x64 standalone process. It reads the strict
`riftreader2-live.json` beside its executable, generates a new nonce on every
launch, and prints the `/rr2bind` command. For a local development run:

```powershell
dotnet run --project src/RiftReader2.Live --configuration Release
```

The tracked configuration disables network delivery. Its default atomic output
is `%LOCALAPPDATA%\RiftReader2\Live\latest.json`. A lab delivery configuration
may target only a literal private IPv4 `/observation` endpoint and requires a
token; keep that private configuration and token out of Git, logs, and command
arguments. The current V1 host receiver is delivery-only and reports
`gameReady: false`.

Evaluate one delivered receipt with the fail-closed host snapshot gate:

```powershell
python scripts/read-live-receipt.py --receipt PATH --expected-nonce NONCE
python scripts/read-live-receipt.py --receipt PATH --expected-nonce NONCE --expected-receiver RECEIVER_ID
```

The gate requires a receipt no older than two seconds, exact reader/nonce
identity, a complete guest scan, and a bound/fresh selected observation whose
effective last-advance age is below its timeout. Its cross-machine result assumes
guest and host UTC differ by at most 250 ms. Success is conditional snapshot
freshness, not a continuing feed, remote production-consumer guarantee, or game
readiness.

The reader scans only readable, committed `MEM_PRIVATE` regions and reports
complete only when the declared domain finishes within all budgets. Read or
budget failures are unavailable/incomplete. The target SHA-256 is for the file
at the MainModule path after identity rechecks; it is not proof of loaded module
bytes. Stop with Ctrl+C; a stopped reader makes prior receipts historical.

Validate input identity without producing an analysis result:

```powershell
dotnet run --project src/RiftReader2.Cli -- validate-capture --manifest samples/demo/capture.json
```

Run the deterministic demo analysis and write a new report:

```powershell
dotnet run --project src/RiftReader2.Cli -- analyze --manifest samples/demo/capture.json --config config/default.json --output artifacts/demo-analysis.json
```

Omit `--output` when only console reporting is needed. A named output must not
already exist; preserving an existing report takes precedence over convenience.

Review help when adding or changing an option:

```powershell
dotnet run --project src/RiftReader2.Cli -- --help
```

The demo data is synthetic. A passing demo confirms configuration, hash
verification, streaming analysis, and result writing; the demo command does not
validate a RIFT field or reproduce the V1 wall-motion result. Use the separate
content-pinned wall replay above for that saved conclusion.

## Change discipline

When changing analysis, keep observations, derived values, and semantic claims
separate. Test boundary conditions that could change a conclusion, including
identity mismatch, invalid ordering or time, gaps, limits, non-finite values,
and angle wrapping where relevant.

When changing configuration or capture JSON:

1. Decide whether the meaning is backward compatible.
2. Reject unknown future versions and missing, duplicate, or unknown properties
   rather than guessing.
3. Update examples, strict parsing, validation, tests, and documentation in one
   coherent change.
4. Recompute sample hashes after intentional sample-byte changes.

Keep capture bundles flat: `samplesFile` is a plain filename beside the
manifest. Preserve the configured capture-size bound, the 16,384-character
JSONL line bound, and the same-handle verify-then-read behavior when changing
input code. Treat `sourceKind`, build identity, units, coordinate frame, clock
basis, and timing uncertainty as source declarations. A verified samples hash
binds saved bytes; it does not prove those declarations or a live collection
path.

Keep the configuration DTO in Infrastructure so external JSON stays separate
from Domain analysis options. Reports must record the effective mapped options,
tool version, product-assembly hashes, and machine-readable sample/build
verification status.

When adding an adapter, keep external access in Infrastructure or an isolated
platform project such as Live. Compose it in the appropriate CLI host.
Extract a shared interface only when the new adapter creates a real seam.
Keep Domain free of JSON, files, processes, and platform APIs.

When changing the addon contract, update Lua encoding/acquisition, strict C#
decoding, shared accepted/rejected fixtures, the contract document, and both
language test paths together. Mocked API tests prove behavior against the mock,
not current-client RIFT compatibility. Do not add deployment, SavedVariables,
or network/file transport as incidental contract work. The only current inbound
command is the explicitly selected one-load `/rr2bind` nonce lifecycle; changing
it requires the RR2L1 contract, lifecycle tests, and live evidence to agree.

## Efficient model handoff

For catalog changes, use the [catalog contract](../reference/field-catalog.md)
and synthetic bundle under `samples/catalog/`. Keep definitions, assessments,
and observation artifacts content-bound; preserve contradictory/expired records.
Run `qualify-fields` twice at the same explicit context/time and compare report
bytes. The full test gate includes that replay plus tamper and publication checks.
No live RIFT session is required for the catalog's offline validation.

Give a coding model one bounded change, the relevant file paths, acceptance
criteria, and the exact validation command. Point it to
[the architecture](../architecture.md), current status, and one relevant topic;
avoid loading the entire repository history.

Apply Joey's 2026-11-06 correction: prioritize practical development speed,
retain good architecture, and refine after actual use.

1. Before each batch, give a short plan (3–5 bullets is enough) covering the
   outcome, independent goals, file ownership/shared interfaces and focused
   checks. Decide core ownership and contracts early; defer optional polish.
   Run independent segmented goals in parallel and keep them moving while
   another slice needs a decision or review. Use existing tools, not a new
   scheduler or framework.
2. Start routine workers with `gpt-6.1-sol` or `gpt-6.1-terra` at low/medium
   reasoning; use `gpt-6-luna` for mechanical tasks with clear checks. For model
   overrides, use `fork_turns: "none"` and provide task context, owned files,
   shared interfaces, constraints and checks. The root handles routine review.
   Use `gpt-6-astra` at high reasoning for targeted difficult architecture and
   high-consequence native identity, concurrency or control review, not every
   substantive patch. Escalate when repeated failures or consequential ambiguity
   make the fast route slower.
3. Run focused checks, correct failures and integrate useful slices promptly.
   Broaden checks when scope warrants; run the authoritative script before
   claiming full repository validation. Ship useful candidate output with honest
   labels, refine after actual use. Live qualification governs live capability
   claims; it does not block implementing raw candidate output. Retain module
   boundaries and versioned contracts.
4. Record concise evidence for meaningful results, material limitations and the
   next useful step; no per-edit report or new manifest is needed. Keep file
   ownership explicit, serialize shared-host heavy work, and retain the root as
   sole live-input owner per lab under existing authority, identity, freshness
   and input guards. Preserve unrelated work and integrate explicit files.

Terra's preference for suitable coding and authorized UI work is Joey's guidance,
not a measured benchmark. The direct ChatGPT Computer Use restriction inside
VMware remains in force; model selection grants no new lab or input authority.

## Timely evidence checkpoints

Joey authorized local checkpoint commits for significant research and recovery
findings on 2026-10-24, using the implementer's judgment. Preserve a finding
promptly when it resolves or diagnoses a meaningful blocker, establishes a
reproducible method or failure, changes a roadmap decision, or would be costly
to reconstruct after a timeout. A small evidence-only commit is worthwhile even
when no product code changes. Do not delay every such checkpoint until a large
implementation milestone or mix unrelated work merely to make a commit.

For a meaningful result, retain a concise evidence note with the observation or
check, relevant source/build/session identity, useful artifact references and
material limitations. Include hashes when they bind the evidence; do not create
per-edit reports or manifests. Label candidate, blocked and negative findings
honestly. Documentation changes need scoped content/link checks; code changes
need focused checks, with broader checks when scope warrants and the full gate
before claiming full repository validation.
Use explicit Git paths, preserve other work, and do not commit credentials,
private settings, or large generated captures. These commits are local; they
do not imply permission to push, deploy, or alter Git history.
