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

## Three-target discovery scheduling

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

Apply Joey's 2026-11-06 worker strategy to minimize elapsed time to an accepted,
verified result while preserving final product quality, including the cost of
review, correction and rework:

1. Choose the model and effort for each bounded task. Start routine implementation
   with `gpt-6.1-sol` or `gpt-6.1-terra` at low/medium reasoning. Use `gpt-6-luna`
   for mechanical work with unambiguous acceptance checks. With explicit
   model/effort overrides, spawn using `fork_turns: "none"` and provide the task,
   relevant source context, owned files, constraints and validation commands.
2. Engage `gpt-6-astra` at high reasoning early for difficult architecture or
   consequential review: build/session identity, evidence meaning, compatibility,
   hashes/atomic I/O, concurrency, native access, unsafe code, experiment controls
   and module boundaries. Resolve consequential design questions before dependent
   implementation; require elevated review of substantive code in small batches
   as they become ready. Keep independent work moving while those decisions or
   reviews are pending. Keep review proportional; trivial docs do not require
   an expensive review worker.
3. Verify each implementation promptly with the relevant focused checks and
   correct failures before building on it. Escalate effort/model or reduce scope
   after repeated failure or unresolved ambiguity. Judge the route by time to
   accepted, verified output, not initial generation speed alone. Documentation
   changes need scoped content/link checks; use the full gate when applicable.
4. Have the root reconcile findings and integrate changes. Keep file ownership
   explicit, serialize shared-host heavy work, and retain the root as sole
   live-input owner per lab under all existing identity and input guards.

Terra is a preferred candidate for suitable coding and authorized computer-use/UI
tasks based on Joey's reported guidance, not a measured model benchmark. The
direct ChatGPT Computer Use restriction inside VMware remains in force; model
selection grants no new live-input or lab authorization.

Record what changed, what was actually verified, limitations, and the next
authorized task in `docs/status.md`. Commit only coherent explicit files with
the repository-local author identity.

## Timely evidence checkpoints

Joey authorized local checkpoint commits for significant research and recovery
findings on 2026-10-24, using the implementer's judgment. Preserve a finding
promptly when it resolves or diagnoses a meaningful blocker, establishes a
reproducible method or failure, changes a roadmap decision, or would be costly
to reconstruct after a timeout. A small evidence-only commit is worthwhile even
when no product code changes. Do not delay every such checkpoint until a large
implementation milestone or mix unrelated work merely to make a commit.

Before committing, retain a concise tracked evidence note with source/time,
exact test or observation, relevant process/build/session identity, retained
artifact references and hashes, uncertainty, known limitations, and the next
reproducible step. Use terms such as candidate, blocked, or negative result when
the evidence does not qualify a capability. Validate the scoped document and
links for documentation-only changes; code changes require their appropriate
focused checks and the full repository gate before claiming full validation.
Use explicit Git paths, preserve other work, and do not commit credentials,
private settings, or large generated captures. These commits are local; they
do not imply permission to push, deploy, or alter Git history.
