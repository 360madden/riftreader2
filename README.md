# RiftReader2

Modular RIFT research tools focused on reliable information, durable evidence,
restart/update recovery, and less repetitive AI work. V1 supplies reference
evidence and lessons; V2 is independently developed around these goals.

The current foundation validates saved captures and computes **derived** motion
with explicit gaps and provenance. It runs offline. The included data is
synthetic; no V2 native field or live-game capability has been qualified.

## Run

Requires the .NET SDK pinned in `global.json` (10.0.302) and PowerShell 7.

```powershell
pwsh -NoProfile -File scripts/validate.ps1
dotnet run --project src/RiftReader2.Cli -- analyze --manifest samples/demo/capture.json --config config/default.json
dotnet run --project src/RiftReader2.Cli -- validate-capture --manifest samples/demo/capture.json
```

Add `--output artifacts/my-analysis.json` to save a new report. Existing files
are preserved. Capture/configuration schemas are versioned; invalid identities,
unsupported schemas, malformed rows, and ambiguous configuration fail explicitly.

## Modules

| Project | Responsibility |
|---|---|
| Domain | Samples, analysis options, and result semantics. |
| Application | Streaming numerical analysis independent of files and UI. |
| Infrastructure | Verified capture files, strict configuration, atomic result publication. |
| Cli | Commands, explicit composition, output, and cancellation. |
| Tests | Behavioral checks across modules and failure paths. |

Start with [status](docs/status.md), [architecture](docs/architecture.md), and
[development](docs/workflows/development.md). The [roadmap](docs/planning/implementation-roadmap.md)
defines small next increments; the [documentation index](docs/README.md) links
goals, research evidence, decisions, and historical setup records.
