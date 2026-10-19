# Current status

Updated: 2026-10-19 (America/New_York).

## Direction and completed scope

RiftReader2 is an independently developed hybrid Lua addon plus modular .NET
application. V1 remains read-only reference material and selected lab tooling.
See [architecture](architecture.md), [decisions](decisions/README.md), and the
[implementation roadmap](planning/implementation-roadmap.md).

Steps 0–4 are complete within their recorded evidence gates:

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

Git author is repository-local `360madden <360madden@gmail.com>`; branch
`codex/modular-foundation`. Use Git for the current commit and worktree state.

## Latest verification

The final native implementation passed the full local gate: 196 C# tests
(187 portable, 9 Windows), 108 Lua assertions, 22 actual Lua-to-C# cases,
9 Python host-gate tests, locked restore, zero-warning Release build,
format/dependency checks, deterministic replay, and a published executable
smoke. Evidence: `artifacts/validation/20261019T043104Z-a6f572d3`.
The full gate checked 158 relative links; all 160 final documentation links
also passed. Live validation caught a single-file identity gap; the fix records
the actual bundle hash and the published smoke now provides regression coverage.

The [native runtime record](validation/native-capture-2026-10-19.md) validates
the final published bundle in RIFT-Lab, before and after an ordinary RIFT
restart. Two captures per session each returned 3/3 header samples. Unmapped
memory retained an explicit unavailable range; wrong epoch/build and existing
output were rejected. The exact pre-restart request failed after restart, and
fresh inspection/capture succeeded. PID changed from 11884 to 11620 while the
mapped address stayed unchanged. Raw captures remain semantically unqualified.

Final native bundle SHA-256:
`7D095CCBB8826ACC62F6C788158F278DBF1ED77CE64157272D7D338C11EA6C52`.
The native commands were exercised; the addon transport's full runtime gate
was not repeated for this bundle. Its earlier
[live transport](validation/live-transport-2026-10-18.md) and
[game/VM restart](validation/restart-recovery-2026-10-18.md) evidence identifies
its own exact executable. The
[saved replay record](validation/wall-replay-2026-10-19.md) identifies the
separate fixed-input conclusion. See [all validation records](validation/README.md).

At teardown, the temporary receiver was stopped and the original VM DVD
restored and queried. RIFT was left logged in. V1 source was unchanged.

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

The next roadmap increment is **step 5: durable field catalog and qualification
workflow**. Start with a small versioned contract for meaning, units, locator,
build/session applicability, evidence references, confidence, and invalidation.
A saved address alone must not become qualified knowledge. Retain contradictory
or expired evidence and require distinct restart/update evidence. No live field
promotion or new experiment control is implied by this handoff.

Strong review remains appropriate for catalog semantics, schema, provenance,
and native access. Cheaper models can handle documented entries, fixtures,
formatting, and narrow tests once behavior is specified; retain the same
[validation gate](workflows/development.md). Step 5 is the recommended next
scope; this turn completed the specifically authorized step-4 remainder.
