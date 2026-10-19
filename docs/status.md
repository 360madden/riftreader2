# Current status

Updated: 2026-10-18 (America/New_York).

## Phase and direction

Modular architecture and offline foundation implementation, explicitly
authorized by Joey. RiftReader2 is independently developed around its own goals;
V1 remains reference evidence and lessons. See [ADR 0001](decisions/0001-modular-offline-foundation.md).

## Implemented

- .NET 10 solution with Domain, Application, Infrastructure, CLI, and tests.
- Strict versioned config and capture manifests; bounded UTF-8 JSONL replay with
  SHA-256 verification, same-session checks, and explicit gaps.
- Streaming derived motion analysis, cancellation, deterministic JSON reports,
  and publication that preserves existing evidence.
- Central build/package settings, exact SDK pin, package locks, and one local
  validation command enforcing module boundaries and behavior.
- Git initialized; local author `360madden <360madden@gmail.com>`; implementation
  branch `codex/modular-foundation`. Use Git for current commit/working-tree state.

## Verified

The [foundation validation record](validation/foundation-2026-10-18.md) records
75 passing tests, clean Release build, locked restore, formatting, dependency
checks, link checks, and deterministic CLI replay against independently
calculated synthetic results. No live game or V1 tests were run.

## Next work

The architecture/foundation request is implemented. Follow the
[roadmap](planning/implementation-roadmap.md) for new increments. Recommended
next capability: independently reproduce the saved V1 wall-motion conclusion,
including free-travel and both wall trials, with an identified importer and
compact output. This is not yet implemented or qualified by the synthetic demo.

The durable field catalog, read-only native adapter, restart/update measurement,
and experiment runner remain future increments. Start with one bounded task;
use [development guidance](workflows/development.md) to hand routine work to
cheaper models while retaining the same validation. Strong review remains
appropriate for semantics, provenance, schemas, native access, and concurrency.
