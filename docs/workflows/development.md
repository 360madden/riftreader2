# Development workflow

Use this workflow for the RiftReader2 foundation. It is designed to give Joey
and future coding agents one reproducible path from a clean checkout to a
reviewable result.

## Prerequisites

- PowerShell 7 (`pwsh`).
- The exact .NET SDK selected by `global.json` (`10.0.302`); SDK roll-forward is
  disabled.
- Repository root `C:\work\riftreader2`.

Keep Git identity repository-local. The intended author is `360madden` with
email `360madden@gmail.com`; do not change global Git configuration.

## Start safely

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
git status --short --branch
dotnet --version
```

Preserve unrelated changes. Generated analysis belongs under `artifacts/`.
Do not use a live RIFT process or V1 tests to validate this offline foundation.

## Restore, build, and test

The authoritative repository check is:

```powershell
pwsh -NoProfile -File .\scripts\validate.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

The script performs a locked restore, Release build, tests, formatting
verification, architecture dependency and documentation-link checks, and the
CLI demo smoke test. Check `$LASTEXITCODE` because PowerShell does not turn a
failing native command into a terminating error automatically.

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
verification, streaming analysis, and result writing; it does not validate a
RIFT field or reproduce the V1 wall-motion result.

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

When adding an adapter, keep external access in Infrastructure and compose it in
CLI. Extract a shared interface only when the new adapter creates a real seam.
Keep Domain free of JSON, files, processes, and platform APIs.

## Efficient model handoff

Give a coding model one bounded change, the relevant file paths, acceptance
criteria, and the exact validation command. Point it to
[the architecture](../architecture.md), current status, and one relevant topic;
avoid loading the entire repository history.

Routine documentation edits, sample/config value changes within an unchanged
schema, formatting fixes, and narrow tests for already specified behavior are
usually suitable for a cheaper model with the validation script required.

Use stronger reasoning and review for changes involving build or session
identity, evidence meaning, schemas and compatibility, hashes or atomic I/O,
streaming and concurrency, native process access, unsafe code, experiment
controls, or module boundaries. These areas can silently invalidate evidence
even when code compiles. This guidance does not require changing model settings
mid-task; it identifies work that should receive capable review.

Record what changed, what was actually verified, limitations, and the next
authorized task in `docs/status.md`. Commit only coherent explicit files with
the repository-local author identity.
