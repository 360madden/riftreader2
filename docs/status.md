# Current status

Updated: 2026-10-19 (America/New_York).

## Direction and completed scope

RiftReader2 is an independently developed hybrid Lua addon plus modular .NET
application. V1 remains read-only reference material and selected lab tooling.
See [architecture](architecture.md), [decisions](decisions/README.md), and the
[implementation roadmap](planning/implementation-roadmap.md).

Steps 0–5 are complete within their recorded evidence gates:

- Pinned .NET 10 solution: Domain, Application, Infrastructure, CLI, Windows Live,
  separate portable/Windows tests, strict configuration, and module checks.
- Content-pinned JSONL replay, streaming motion analysis, explicit gaps, and
  deterministic reports with publication that preserves existing evidence.
- First-class Lua 5.1 producer and strict C# decoder with shared contracts.
- Nonce-bound addon transport with bounded read-only acquisition, freshness,
  reload/session invalidation, private delivery, and a host snapshot gate.
- Independent replay of the selected V1 wall-motion batch; its native field
  meaning remains unqualified.
- Finite `inspect-native` / `capture-native` commands with strict requests,
  exact process/build identity, bounded reads, explicit failures, monotonic
  timing, raw-byte hashes, and report/tool identity. Application owns the port;
  Windows access remains isolated in Live. See the
  [native capture contract](reference/native-capture.md).
- Versioned durable field catalog, content-pinned assessments/artifacts, and
  deterministic qualification at an explicit build/session/time. All four
  claims remain visible, with contrary and expired history retained. See the
  [catalog workflow](reference/field-catalog.md) and
  [ADR 0005](decisions/0005-durable-field-catalog.md).

Git author is repository-local `360madden <360madden@gmail.com>`; branch
`codex/modular-foundation`. Use Git for the current commit and worktree state.

## Latest verification

The step-5 implementation passed the full local gate: 214 C# tests
(205 portable, 9 Windows), 108 Lua assertions, 22 actual Lua-to-C# cases,
9 Python host-gate tests, locked restore, zero-warning Release build,
format/dependency checks, deterministic replay, and the published native smoke.
Evidence: `artifacts/validation/20261019T050044Z-98856eec`.
The gate checked 174 relative links; all 177 final documentation links also passed.

The [catalog validation record](validation/field-catalog-2026-10-19.md) records
two byte-identical 21,738-byte qualification reports from the retained synthetic
bundle. Tests reject tampered evidence, preserve existing output, invalidate
changed definitions, retain contradictory/expired history, and require explicit
restart/update corroboration. Independent review covered schemas, semantics,
provenance, and bounds. No actual game field was promoted; this increment is
offline and did not require a running RIFT session.

The [native runtime record](validation/native-capture-2026-10-19.md) validates
the final published bundle in RIFT-Lab, before and after an ordinary RIFT
restart. Two captures per session each returned 3/3 header samples. Unmapped
memory retained an explicit unavailable range; wrong epoch/build and existing
output were rejected. The exact pre-restart request failed after restart, and
fresh inspection/capture succeeded. PID changed from 11884 to 11620 while the
mapped address stayed unchanged. Raw captures remain semantically unqualified.

The previously runtime-tested native bundle SHA-256 is:
`7D095CCBB8826ACC62F6C788158F278DBF1ED77CE64157272D7D338C11EA6C52`.
The current build's runtime path was not requalified in RIFT by the catalog
task; the host-only published smoke passed. The prior native gate exercised
native commands only. The earlier addon
[live transport](validation/live-transport-2026-10-18.md) and
[game/VM restart](validation/restart-recovery-2026-10-18.md) evidence identifies
its own exact executable. The
[saved replay record](validation/wall-replay-2026-10-19.md) identifies the
separate fixed-input conclusion. See [all validation records](validation/README.md).

The prior native gate stopped its temporary receiver, restored the original
DVD, and left RIFT logged in. This offline increment made no VM or V1 changes.

## Limits and next work

Native capture now preserves acquisition evidence; it does not establish a
native coordinate/velocity field, durable locator, or alignment with addon
observations. Reads are sequential. Disk executable identity is distinct from
loaded-image verification. Delivery remains `gameReady: false`; addon host
freshness is snapshot-only under the documented 250 ms clock-skew bound.

A native process restart requires a fresh explicit request. Native-bundle VM
restart, hard crash, snapshot restore, update recovery, automatic startup, and
production remote consumption remain unqualified. Earlier addon VM recovery
required manual relaunch and binding.

The catalog verifies retained bytes and applies recorded review policy. Reviewer,
origin, semantics, and build/session attribution remain declarations, not live
attestation. Invalidation conditions require review; the tool does not monitor
them automatically. No real RIFT field has been qualified by the synthetic
demonstration.

The next roadmap increment is **step 6: guarded experiment support**. Start
with a bounded experiment-plan contract, stop/release behavior, exact target
identity, and timing uncertainty before adding controlled movement/turning.
Dedicated player automation remains outside RiftReader2. Step 6 needs its own
implementation authorization; the requested step-5 work is complete.

Strong review remains appropriate for catalog semantics, schema, provenance,
and native access. Cheaper models can handle documented entries, fixtures,
formatting, and narrow tests once behavior is specified; retain the same
[validation gate](workflows/development.md). Routine catalog entries can follow
the documented file workflow; native field promotion needs actual evidence.
