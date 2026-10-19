# Current status

Updated: 2026-10-18 (America/New_York).

## Phase and direction

Modular architecture and offline foundation implementation, explicitly
authorized by Joey. RiftReader2 is independently developed around its own goals;
V1 remains reference evidence and lessons. See [ADR 0001](decisions/0001-modular-offline-foundation.md).
Joey explicitly requires a hybrid Lua addon plus external .NET application;
[ADR 0002](decisions/0002-hybrid-addon-and-reader.md) makes that product boundary
explicit. Joey subsequently authorized the minimal Lua addon, C# decoder, and
shared contract tests; that increment is complete offline under
[ADR 0003](decisions/0003-addon-observation-contract.md).

## Implemented

- .NET 10 solution with Domain, Application, Infrastructure, CLI, and tests.
- Strict versioned config and capture manifests; bounded UTF-8 JSONL replay with
  SHA-256 verification, same-session checks, and explicit gaps.
- Streaming derived motion analysis, cancellation, deterministic JSON reports,
  and publication that preserves existing evidence.
- Central build/package settings, exact SDK pin, package locks, and one local
  validation command enforcing module boundaries and behavior.
- Lua 5.1 package with separate encoder, bounded API sampler, and event hookup;
  typed player/position/health/combat observations, clock/lifecycle handling,
  and a strict 4096-byte contract.
- Typed C# decoder and `decode-addon --frame PATH [--output PATH]`, with exact
  frame hash, `unbound` source binding, and `unverified` freshness.
- Shared producer/consumer fixtures and a mandatory actual-Lua-to-C# gate;
  repository-local development runtime under ignored `artifacts/tools/`.
- Git initialized; local author `360madden <360madden@gmail.com>`; implementation
  branch `codex/modular-foundation`. Use Git for current commit/working-tree state.

## Verified

The [addon validation record](validation/addon-contract-2026-10-18.md) records
138 passing C# tests, 85 Lua assertions, and 11 actual Lua-to-C# shared cases.
The full gate passed locked restore, clean Release build, formatting, dependency
checks, links, and the existing deterministic synthetic replay. The 36 rejected
wire fixtures are included in the C# total. No live game, deployment, native
analysis, or V1 tests were run. Earlier evidence remains in the
[foundation record](validation/foundation-2026-10-18.md).

## Next work

The requested minimal producer/decoder increment is complete. Next, validate
the addon against the actual client and establish one bounded acquisition
transport with independent process/load identity, receiver timing, and freshness
rules. These live-facing capabilities remain unimplemented; local counters
alone cannot identify reloads or distinguish stale copies. Follow the
[roadmap](planning/implementation-roadmap.md). Independently reproducing the saved
V1 wall-motion conclusion remains the next saved-evidence case; it can proceed
without a live bridge. Neither capability is implemented by the synthetic demo.

The durable field catalog, read-only native adapter, restart/update measurement,
and experiment runner remain future increments. Start with one bounded task;
use [development guidance](workflows/development.md) to hand routine work to
cheaper models while retaining the same validation. Strong review remains
appropriate for semantics, provenance, schemas, native access, and concurrency.
