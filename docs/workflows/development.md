# Development workflow

Use this workflow for the RiftReader2 foundation. It is designed to give Joey
and future coding agents one reproducible path from a clean checkout to a
reviewable result.

## Prerequisites

- PowerShell 7 (`pwsh`).
- The exact .NET SDK selected by `global.json` (`10.0.302`); SDK roll-forward is
  disabled.
- Python with `lupa==2.8` and its Lua 5.1 module for addon and cross-language
  contract tests.
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
Use live RIFT or V1 lab tooling only for an explicitly authorized, bounded gate;
record that evidence separately from offline repository validation.

## Restore, build, and test

The Lua suite is mandatory. A repository-local environment keeps its dependency
isolated and reproducible:

```powershell
python -m venv artifacts/tools/lua-python
artifacts/tools/lua-python/Scripts/python.exe -m pip install -r requirements-lua-tests.txt
```

The validation script resolves Lua Python in this order: explicit
`-LuaPython PATH`, environment variable `RIFTREADER2_LUA_PYTHON`,
`artifacts/tools/lua-python/Scripts/python.exe`, then `python` on `PATH`.
Examples:

```powershell
pwsh -NoProfile -File .\scripts\validate.ps1 -LuaPython artifacts/tools/lua-python/Scripts/python.exe
$env:RIFTREADER2_LUA_PYTHON = 'C:\path\to\python.exe'
pwsh -NoProfile -File .\scripts\validate.ps1
```

The repository does not depend on or hardcode a V1 addon or Python path.

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
