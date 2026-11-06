# Implementation roadmap

Status: prioritized plan adopted for the authorized foundation; later increments
remain subject to their evidence and safety gates.

This roadmap grows a hybrid Lua-addon/.NET product through measurable vertical
slices. Each external operation remains a standalone process: CLI for offline
work or the isolated Windows Live executable for live acquisition. Each
increment should leave a useful artifact and a compact handoff so a
later model does not need to rediscover the reasoning.

**November 6 parallel development priorities:** Use the [current discovery roadmap](discovery-roadmap-2026-11-06.md)
for present-build research priorities and three-target work allocation. The
October qualification results below retain their original build and evidence
scope; they do not qualify the current executable automatically. Existing
authorization and restart/update boundaries still apply.

## Current priority override — October 25, 2026

Joey prioritizes durable collection across **fully exiting RIFT and launching it
again**. Confirm the old process has ended, acquire the new process/start identity,
and resolve the preserved build-specific recipe afresh. Addon reload, character
relog or reader restart alone is insufficient; VM/host restarts are separate.

**Patch/update recovery is deferred until Joey explicitly resumes it.** Later
update-recovery references remain future work and do not select the next task.
Do not weaken exact-build guards: changed executable SHA still fails closed.
The [accepted policy](../decisions/0008-full-game-restart-durability.md) controls
this priority. The [October 25 XYZ trial](../validation/native-xyz-restart-2026-10-25.md)
establishes one observed normal full game exit/relaunch; it does not qualify all
future restarts or other fields.

## Remaining practical goals — refreshed October 25, 2026

The original [Start / Read / Stop milestone](position-panel-roadmap.md) is
complete, including corrected same-build full-game exit/relaunch. Native/Lua
displacement also passed through both manual movement and the
[guarded helper](../validation/xyz-guarded-displacement-2026-10-25.md).
Do not repeat these completed milestones as though they were still missing.
Goals 1–2 have since passed live; see the
[implementation evidence](../validation/xyz-goals-implementation-2026-10-25.md).
Joey deferred the health-change test on October 25. Continue resource work while
health meaning/locator/restart qualification remains unfinished. The roadmap is:

1. **Make the proven XYZ run easy to repeat.** Consolidate the working CLI
   collection and guarded-helper steps into a small reusable entry point. Reuse
   the installed reader and existing tools; authenticate once per run, capture
   before, apply one reviewed bounded pulse, capture after, compare, export and
   clean up. Done when a fresh run works without editing dated artifact scripts
   or asking Joey to press movement keys. Keep credentials out of logs; persistent
   credential caching was subsequently authorized and demonstrated without a
   prompt on run 04.
2. **Record XYZ as durable field knowledge.** Add a real catalog definition and
   scoped assessments linking the locating recipe, Lua/native comparison,
   movement and full-game restart evidence. Preserve startup failures and the
   corrected result. Done when the existing catalog command rebuilds a clear
   exact-build qualification report without AI interpreting scattered notes.
   State untested claims explicitly; do not claim patch survival.
3. **Health — changed-state test deferred.** Use Lua health and
   maximum health as the reference, gather controlled changed-state observations,
   and inspect only relevant native candidates. Done when actual changes
   distinguish the field from constant values and cached copies, a reusable
   locating recipe is retained, and normal full-game exit/relaunch reacquires it.
   Capture failures instead of repeatedly widening unchanged searches.
4. **Repeat for the player's resource/power field — active.** Lua identified
   Warrior / tank and Power; tooltips corroborated the resource name. A
   [clean Light's Balm test](../validation/power-test-2026-10-25.md) demonstrated
   consumption/recovery and one responding memory candidate. Establish its
   owner/provenance and reusable locator next; it may be an addon copy.
   Compare the native changes with Lua. Done when meaning, units,
   availability, locator, invalidation conditions and same-build restart evidence
   are recorded. Historical `power=100` matches are candidates, not completion.

**Confidence follow-up, not a blocker for the completed XYZ milestone:** collect
another full-game exit/relaunch during normal use, including absent-process
handling, fresh PID/start identity, fresh coordinates and old-process rejection.
Do not require endless repeat trials before moving to the next field.

**Deferred or conditional:** patch/update recovery; VM/host reboot, crash and
snapshot-restore qualification; precise velocity/input timing; other fields such
as casting/cooldowns/abilities after health/resource; SQLite only after a
measured need. Guest credential caching is already authorized and verified.
The optional new Courier need not
be guest-deployed while the proven VMware CLI transfer route suffices. Dedicated
navigation/combat automation remains outside this project. Direct ChatGPT
Computer Use stays deferred; separately authorized guarded helpers remain usable.

The numbered sections below retain the original implementation history and
acceptance criteria; this refreshed list determines the next practical work.

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

Completed for the selected batch-6 evidence. The tracked replay manifest pins a
100,187,956-byte, 9,598-sample V1 capture and three trial artifacts. The V2
command independently reproduces one plausible free-travel comparison and two
decisive wall disagreements; see the
[validation record](../validation/wall-replay-2026-10-19.md). The first wall
contact, V1 native-field scan, current-build behavior, and update
recovery remain outside this fixed-input increment.

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

Completed for bounded raw acquisition. The native adapter preserves exact
request, tool, process/build, timing, bytes, and failure provenance behind an
Application-owned port. The [native runtime record](../validation/native-capture-2026-10-19.md)
qualifies the final bundle in two process epochs: ordinary capture, unavailable
memory, wrong identity, no overwrite, and rejection of the actual old request
after a RIFT restart. Reacquisition requires a new explicit request; no native
field meaning or stable locator is promoted.

The earlier addon gate separately qualified ordinary game-process reacquisition
by a surviving reader and a graceful VM power cycle with manual reader/game
relaunch. Those results identify their own executable. The native bundle has
not passed a VM-restart gate. Automatic startup, crash, snapshot restore, and
update recovery remain unqualified. Continue with step 5's durable catalog.

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

Implemented as an offline file-based catalog under
[ADR 0005](../decisions/0005-durable-field-catalog.md). `qualify-fields` verifies
content-pinned assessments/artifacts and evaluates all four claims at an exact
build/session/time. Definition changes invalidate prior assessments; contrary,
expired, and out-of-scope records remain visible. The tracked synthetic bundle
rebuilds the same report and does not promote any real RIFT field. See the
[workflow](../reference/field-catalog.md) and
[validation record](../validation/field-catalog-2026-10-19.md).

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

Implemented as a small Python runner plus adapter to the unchanged original
lab console/readback tools. It performs one 20–250 ms reviewed pulse, retains
before/after evidence, and supports persistent stop and release recovery.
The [live record](../validation/experiments-2026-10-19.md) covers a RIFT pulse,
new API readback, identity/duplicate rejection, and stop-before-input. Timing
alignment remains coarse with unmeasured clock skew; mid-hold stop and crash
recovery have not been qualified in RIFT. See [usage](../reference/guarded-experiments.md).

## 6a. Read-only memory discovery

Joey additionally authorized stronger memory reading and RVA pointer discovery
on 2026-10-19, for investigating navigation, combat, casting, stats, and abilities.
Keep these as discovery features in the existing modules. Provide bounded
memory maps/snapshots, typed value/pattern searches, snapshot comparisons,
reverse pointer-chain candidates, and exact-target live resolution. Preserve
raw failures, coverage limits, build/session identity, and candidate semantics.

Implemented without new projects or dependencies. See
[commands and limits](../reference/memory-discovery.md) and the
[runtime record](../validation/memory-discovery-2026-10-19.md). Real game fields
still need API comparison, semantic experiments, and separate restart/update
evidence before catalog qualification.

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

## 8. Discovery compilation, query and export

Joey authorized an optimal plan and its execution on October 24, 2026.
The [finalized discovery roadmap](discovery-compilation-roadmap.md) owns D0–D4
milestones: strict hash-pinned source manifests, non-promoting typed/native and
catalog importers, deterministic filtering/sorting and JSON/CSV/JSONL export,
then a standalone offline browser explorer with downloads.

Reuse the existing .NET projects and field-catalog semantics. Do not touch
V16/V17 VM console ownership or add a service/database. Retain the complete
rebuildable manifest and original evidence; exports are scoped views, not
semantic qualifications. The [usage contract](../reference/discovery-compilation.md)
specifies bounds, exact CLI options and statuses. Automatic indexing,
cross-build semantic merge and live data feeds remain separately gated.

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
