# Implementation roadmap

Status: prioritized plan adopted for the authorized foundation; later increments
remain subject to their evidence and safety gates.

This roadmap grows a hybrid Lua-addon/.NET product through measurable vertical
slices. Each external operation remains a standalone process: CLI for offline
work or the isolated Windows Live executable for live acquisition. Each
increment should leave a useful artifact and a compact handoff so a
later model does not need to rediscover the reasoning.

## 0. Reproducible repository foundation

Deliver the pinned .NET 10 solution, five production modules, two test projects,
central build and package settings, lock files, repository-local Git identity,
and one validation script.

Acceptance evidence:

- the locked restore, Release build, tests, formatting, module-boundary checks,
  link checks, and demo smoke test complete successfully;
- Git reports only intended files;
- documentation distinguishes Joey's direction from implementer-selected stack.

## 1. Deterministic offline analysis slice

Deliver strict version-1 configuration and manifest parsing, bounded capture
size and line length, same-handle SHA-256 verification and streaming JSON Lines
input, derived-motion analysis, optional atomic no-overwrite JSON output,
`analyze`, `validate-capture`, and help. Track a small synthetic dataset whose
illustrative status is explicit.

Acceptance evidence:

- repeated analysis of identical inputs produces equivalent content;
- invalid versions, missing/unknown/duplicate properties, identity, sequence,
  timestamps, values, size, line length, count, and digest fail with useful
  diagnostics;
- gap limits and yaw wrapping have focused tests;
- no V1 or live-game conclusion is claimed.

## 2. Hybrid addon contract and producer foundation

Implement the required Lua producer and C# boundary from
[ADR 0002](../decisions/0002-hybrid-addon-and-reader.md). Start with one small
typed reference observation, capability states, producer/schema versions, and
reload/session/freshness rules. Preserve separate API/native/derived provenance.

Acceptance evidence:

- actual Lua output and C# decoding agree on shared valid/invalid fixtures;
- zero/false, missing/invalid fields, unsupported versions, stale observations,
  sequence reset, conflicting copies, and size limits have meaningful checks;
- addon work is bounded; heavy processing and retention remain external;
- transport capabilities are verified rather than assumed from general Lua;
- live deployment/readiness is reported separately from mocked producer tests.

The minimal producer, strict decoder, and shared offline contract tests are now
implemented; see [ADR 0003](../decisions/0003-addon-observation-contract.md).
The bare producer passed one identified actual-client source gate after
`/reloadui`, with advancing RR2A1 sequence and clock. This establishes that
package/API path in that session only. The nonce-bound RR2L1 increment selected
by [ADR 0004](../decisions/0004-nonce-bound-addon-transport.md) is implemented.
The fifth production project is a Windows-only Live adapter and composition
executable referencing Domain, Application, and Infrastructure.

The full gate passed 173 C# tests, 108 Lua assertions, 11 RR2A1 plus 11 RR2L1
actual-Lua-to-C# cases, 9 Python host-gate tests, and a zero-warning Release
build. One RIFT-Lab runtime gate established advancement, stale rejection,
reload invalidation, reader restart with a new nonce, and rebinding in the same
RIFT process. See the
[live record](../validation/live-transport-2026-10-18.md). A later
[recovery gate](../validation/restart-recovery-2026-10-18.md) exercised the final
executable through an ordinary RIFT process restart and a graceful VM power
cycle with manual relaunch and nonce rebinding. Hard-crash, VM snapshot restore,
update recovery, loaded-module verification, and production remote consumption
remain separate qualifications. Existing saved replay can proceed independently.

## 3. Reproduce one saved evidence conclusion

Choose and identify an immutable V1 evidence bundle, starting with the proposed
wall-motion case if it remains the best fixed input. Implement the smallest
independent importer or replay adapter needed to express that evidence through
V2 contracts. Do not import V1 application architecture.

Acceptance evidence:

- exact source path, size, hash, build/session applicability, and known
  limitations are recorded;
- the procedure is invokable without AI interpretation and gives a compact,
  repeatable result;
- free-travel plausibility and decisive wall disagreement are both represented;
- elapsed local work, output size, and remaining manual/AI steps are measured.

This increment establishes reproducibility of one saved conclusion. It does not
qualify a native velocity field.

## 4. Read-only Windows capture adapter

Develop a bounded V2 process scanner and read-only capture adapter independently
behind the external I/O boundary. Preserve executable/build identity, process
and session identity, capture timing, failures, and exact output identity. The
unchanged V1 receiver/console may be reused operationally in the controlled lab,
but its application architecture and claims do not become V2 contracts. No
generic scanner offset or native-field readiness is established yet.

Acceptance evidence:

- offline tests cover platform-independent contracts;
- a controlled live session records provenance and failure behavior;
- no write, input, debugger, or automation capability is introduced;
- restart reacquisition is measured separately from update recovery.

The current gate qualifies ordinary game-process reacquisition by a surviving
reader and a graceful VM power cycle with manual reader/game relaunch. It does
not add automatic startup or qualify crash, snapshot-restore, or update recovery.

Native identity, platform I/O, timing, and concurrency require strong-model
implementation or review.

## 5. Durable field catalog and qualification workflow

Represent a field as meaning, units, locator method, applicability, validation
evidence, confidence, and invalidation conditions. Link observations and results
by content, build, and session identity. Generate a compact qualification report
that another program can consume without interpreting raw notes.

Acceptance evidence:

- a saved address alone cannot be promoted as durable knowledge;
- contradictory and expired evidence remains visible;
- restart and update claims require their own recorded validation;
- the catalog can be rebuilt or checked from retained artifacts.

Schema and semantic changes require strong review. Routine entries with complete
provenance can use a cheaper model plus mechanical validation.

## 6. Guarded experiment support

Add explicit plans and safety gates for controlled movement and turning tests
that collect evidence for RiftReader2. Keep dedicated navigation, combat, and
player automation in a future program.

Acceptance evidence:

- every action is bounded, attributable to an experiment, and stoppable;
- stimuli and samples share a usable time basis with recorded uncertainty;
- runs cannot silently target an unverified build or session;
- analysis reports gaps and alignment limitations.

Experiment control, timing, and live integration require strong-model design and
review.

## 7. Indexing only when measured

Continue with versioned files until a retained-data query, scale, integrity, or
concurrency requirement is measured. If proven, add SQLite as an Infrastructure
index over durable artifacts, with rebuild and migration behavior specified
before adoption.

Acceptance evidence:

- the motivating workload and current limitation are measured;
- source artifacts remain identifiable and recoverable;
- migrations, backup/rebuild, and compatibility are tested;
- Domain and Application remain storage-independent.

## Handoff size and model allocation

Split work at the increments above, then subdivide into one contract or adapter
change per task. A good handoff names the exact inputs, output, invariants, file
scope, and command that proves completion.

Use cheaper models for routine documentation, unchanged-schema configuration,
mechanical fixture maintenance, formatting, and narrow tests after behavior is
specified. Require stronger reasoning or review for evidence semantics,
identity/provenance, schema compatibility, I/O durability, streaming or
concurrency, native access, unsafe code, module boundaries, and experiment
controls. Always prefer a local deterministic check over spending tokens to
re-evaluate the same artifact.
