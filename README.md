# RiftReader2

Modular RIFT research tools focused on reliable information, durable evidence,
restart/update recovery, and less repetitive AI work. V1 supplies reference
evidence and lessons; V2 is independently developed around these goals.

The product architecture is **hybrid: an in-game Lua addon plus an external .NET
application**. The minimal addon and C# decoder share an executable contract;
live transport and actual client validation remain future work. See
[the hybrid decision](docs/decisions/0002-hybrid-addon-and-reader.md).

The current foundation validates saved captures and computes **derived** motion
with explicit gaps and provenance. It runs offline. The included data is
synthetic; no V2 native field or live-game capability has been qualified.

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

## Modules

| Project | Responsibility |
|---|---|
| Lua addon | Separate encoding, bounded API sampling, and RIFT event modules. |
| Domain | Samples, typed addon observations, analysis options, and result semantics. |
| Application | Streaming numerical analysis independent of files and UI. |
| Infrastructure | Verified captures, strict addon decoding/configuration, atomic result publication. |
| Cli | Commands, explicit composition, output, and cancellation. |
| Tests | C# behavior checks, Lua lifecycle checks, and shared cross-language fixtures. |

Start with [status](docs/status.md), [architecture](docs/architecture.md), and
[development](docs/workflows/development.md). The [roadmap](docs/planning/implementation-roadmap.md)
defines small next increments; the [documentation index](docs/README.md) links
goals, research evidence, decisions, and historical setup records.
