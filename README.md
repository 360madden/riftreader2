# RiftReader2

Modular RIFT research tools focused on reliable information, durable evidence,
restart/update recovery, and less repetitive AI work. V1 supplies reference
evidence and lessons; V2 is independently developed around these goals.

The product architecture is **hybrid: an in-game Lua addon plus an external .NET
application**. The addon and C# decoder share executable contracts. A minimal
Windows reader now acquires nonce-bound live observations with freshness and
reload checks, validated through an ordinary RIFT restart and graceful RIFT-Lab
VM restart with manual relaunch and rebinding. See
[the hybrid decision](docs/decisions/0002-hybrid-addon-and-reader.md).

The current foundation validates saved captures and computes **derived** motion
with explicit gaps and provenance. The included replay data is synthetic.
Live observations come from the addon API; native game fields and restart-stable
offsets remain unqualified. See the [restart validation record](docs/validation/restart-recovery-2026-10-18.md).

The [memory discovery tools](docs/reference/memory-discovery.md) add read-only
memory maps/snapshots, typed and pattern searches, comparisons, and RVA-rooted
pointer-chain discovery and resolution. [Supervised experiments](docs/reference/guarded-experiments.md)
provide one reviewed movement/turning pulse with stop and release evidence.
No new services or frameworks are required.

## Run

Requires the .NET SDK pinned in `global.json` (10.0.302) and PowerShell 7.
The full gate also requires the pinned Lua 5.1 test runtime; follow the
[one-time setup](docs/workflows/development.md).

```powershell
pwsh -NoProfile -File scripts/validate.ps1
dotnet run --project src/RiftReader2.Cli -- analyze --manifest samples/demo/capture.json --config config/default.json
dotnet run --project src/RiftReader2.Cli -- validate-capture --manifest samples/demo/capture.json
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame artifacts/example.wire
```

Add `--output artifacts/my-analysis.json` to save a new report. Existing files
are preserved. Capture/configuration schemas are versioned; invalid identities,
unsupported schemas, malformed rows, and ambiguous configuration fail explicitly.
The addon command requires an exact saved frame (no trailing newline); it reports
the frame hash with source binding and freshness explicitly unverified. See
[the addon guide](addon/README.md) and [wire contract](contracts/addon/README.md).

The Lua addon installed in RIFT is separate from the Git checkout. Compare,
synchronize, and independently verify the main PC and both VM installations:

```powershell
C:\Python314\python.exe scripts\addon_sync.py check --target all
C:\Python314\python.exe scripts\addon_sync.py sync --target all
C:\Python314\python.exe scripts\addon_sync.py verify --target all
```

See the [addon-sync workflow](docs/workflows/addon-sync.md). File consistency
does not replace an in-game addon reload and functional check.

## On-demand controller prerequisite

The standard `scripts/control_client.py` commands now check the matching
Lab-1/Lab-2 main-PC controller and recover it on demand when the authenticated
local endpoint is absent. They use the pre-existing Workbridge managed-helper
lifecycle to register and start one **Limited, interactive, persistent** Windows
Task Scheduler task per lab. The task has **no boot/logon trigger**; an operation
starts it only when necessary, and a healthy instance is reused. The task itself
runs the controller with fresh VM identity, source/config evidence, a preserved
SQLite coordination queue, console ownership, and disarmed defaults. No VM/game
startup or gameplay input is sent. This works even when the requesting Workbridge
job is bounded because the controller runs directly as the managed task, rather
than as a detached child of the job. An authenticated guest-agent connection and
independently fresh telemetry are **separate** prerequisites for live player data
or movement. For an inert diagnostic, pass `--no-auto-start` before the command.
See the [operational dependencies guide](docs/workflows/operation-dependencies.md).

For full authenticated controller **and guest-agent** readiness on the two labs:

```powershell
C:\Python314\python.exe scripts\ensure_guest_agent.py --lab all
```

This reuses connected, idle agents and recovers missing ones through each guest's
current cached VMware login and a separate on-demand, triggerless task. The
standard `control_client.py` live `capture`, reviewed `arm`, and `action` commands
also check this prerequisite; inert `status` and cleanup commands do not start
an absent guest agent. No game input is part of dependency startup.

## Fast known-build native XYZ sampling

The Windows Live executable can repeatedly read the previously discovered,
build-pinned native XYZ **candidate** without scanning for Lua frames or heap values:

```powershell
RiftReader2.Live.exe sample-position --profile position-candidate-profile.json --samples 3 --interval-ms 500 --output position-samples-new.json
```

Run on the same Windows machine as RIFT using the profile in
`config/position-candidate-profile.json`. Reacquisition is per current PID/module
and each read is identity-checked; another game build is rejected. Full semantics,
motion, and update survival remain separate [validation tasks](docs/reference/known-position-sampling.md).

## Offline discovery explorer

The [discovery compiler](docs/reference/discovery-compilation.md) combines
explicit, SHA-pinned field catalogs, Lua/native review reports and recorded
research into a queryable view without accessing RIFT or VMware. Export
JSON, CSV or JSON Lines; existing files are never replaced.

```powershell
dotnet run --project src/RiftReader2.Cli -- export-discoveries --manifest samples/discovery-sources.json --build-sha256 ('A' * 64) --session-id synthetic-session-a --as-of 2026-10-21T00:00:00Z --format json --output artifacts/discoveries-example.json
```

Open `scripts/discovery_explorer.html` in a browser and select the output JSON
to filter, sort, inspect and download records locally. The sample is synthetic;
compiling a discovery does not qualify native game memory semantics.

## Modules

| Project | Responsibility |
|---|---|
| Lua addon | Separate encoding, bounded API sampling, reader binding, and RIFT event modules. |
| Domain | Samples, typed addon observations, analysis options, and result semantics. |
| Application | Streaming numerical analysis and monotonic freshness rules independent of files and UI. |
| Infrastructure | Verified captures, strict addon decoding/configuration, atomic result publication. |
| Cli | Commands, explicit composition, output, and cancellation. |
| Live | Isolated Windows read-only acquisition, process identity, bounded delivery, and latest snapshot. |
| Tests | C# behavior checks, Lua lifecycle checks, and shared cross-language fixtures. |

Start with [status](docs/status.md), [architecture](docs/architecture.md), and
[development](docs/workflows/development.md). The [roadmap](docs/planning/implementation-roadmap.md)
defines small next increments; the [documentation index](docs/README.md) links
goals, research evidence, decisions, and historical setup records.
