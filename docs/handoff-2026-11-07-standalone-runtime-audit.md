---
kind: riftreader2-standalone-audit-handoff
project: RiftReader2
repository: 'C:\work\riftreader2'
branch_at_audit: codex/modular-foundation
checkpoint_date_et: 2026-11-07
priority: standalone-runtime-closure
state: core-rr2-owned-lab1-live-accepted-cross-target-pending
scope: documentation-only-read-only-audit
remote_push: not-requested
resume_from:
  - AGENTS.md
  - docs/status.md
  - docs/reference/self-contained-api-reference.md
  - docs/validation/self-contained-lab1-live-acceptance-2026-11-06.md
  - docs/handoff-2026-11-06-standalone-lab1-accepted.md
---

# HANDOFF — RR2 standalone runtime status (November 7, 2026)

## Executive answer

**RR2's core implementations are RR2-owned; universal, end-to-end standalone
operation is not yet accepted.** The old `C:\rift modding\RiftReader` checkout
and `RiftReaderApiProbe` are historical/reference sources, not intended
live runtime prerequisites. The distinction is **implementation independence**
versus **proven live readiness** on every target and every consumer.

This handoff records a read-only source/documentation audit. No code,
installed addon, reader, receiver, controller, VM or RIFT session was changed.

## Verified baseline

| Area | Evidence | Interpretation |
| --- | --- | --- |
| Offline .NET / CLI / Lua contracts | RR2-owned libraries, strict contracts, independent receiver and addon code recorded in the migration note | Implemented independently; this checkpoint does not rerun tests |
| Lab 1 loaded RR2 addon | One previously reviewed `/reloadui` and `/rr2guide bind`; seven-file v0.2.0 package, old probe disabled | **Accepted on Lab 1 only** on November 6 |
| Lab 1 reference acquisition | Two 8-snapshot RR2 native-memory captures; **64/64 advancing RR2R1 comparisons** in 15 s; same nonce, player and clock epoch, sequence 413→431 | Proven advancing RR2-owned API-reference slice |
| Resource reference | Independent Python inspection: Mana 3980/3980; Power explicitly unavailable | Reference observation, not changed-state native field qualification |
| Host receivers | RR2-owned preflight started/reused Lab 1 and Lab 2 host receivers | Process/ownership readiness only; **feedFreshness: not-verified** |
| Installed packages | Source/install file parity reported for physical, Lab 1 and Lab 2 | Disk parity does not prove a loaded addon or fresh feed |
| Native candidate tooling | November 7 status records RR2-repository-only live catalog commands in both labs | Additional native-candidate evidence, not proof of full standalone telemetry |

Original Lab 1 evidence:
[validation record](validation/self-contained-lab1-live-acceptance-2026-11-06.md),
[migration contract](reference/self-contained-api-reference.md),
[accepted handoff](handoff-2026-11-06-standalone-lab1-accepted.md).
Do not reuse historical PIDs, nonces, hashes or controller readiness as current facts.

## Bounded source audit (November 7)

Read-only Workbridge text searches over the selected RR2 checkout
(`*.cs`, `*.py`, `*.ps1`; **466 files searched** per broad code query):

1. **Zero literal references** to `C:\rift modding\RiftReader` in the
   selected source files. This does not prove every dynamically generated
   path, third-party invocation or packaged runtime has been audited.
2. Remaining `RiftReaderApiProbe` mentions were found in explicit
   historical parsing/fixtures, notably `inspect_typed_resource.py` and
   `TypedWireSnapshotCommand.cs`; these are not by themselves a required
   live process or imported old checkout.
3. `RRAPIVAL2` marker handling remains for explicitly selected historical
   replay and generic parsing/testing. Current typed capture/inspection
   requires RR2R1 session selection; silent fallback to legacy live wire
   is prohibited. A comprehensive call-graph/runtime audit is still due.
4. Literal `workbridge-mcp` paths were confined in the searched code
   to legacy helper registration/migration inspection and its test.
   `scripts/Manage-RR2HelperTask.ps1` exists as RR2's helper manager.
   Development access through Workbridge is distinct from a live RR2
   runtime dependency.

**Conclusion of this bounded search:** no current mandatory use of the
original RiftReader executable/checkout was identified. This is not a
blanket claim that all runtime paths have passed standalone acceptance.

## Outstanding gaps / operational boundaries

| Priority | Gap | Acceptance needed |
| --- | --- | --- |
| P0 | Lab 2 and physical RIFT loaded RR2R1 source | Independently verified loaded source, fresh nonce, advancing same-player captures; requires new target-specific game-input authority |
| P0 | Both receiver feeds | End-to-end packets from current RR2 producer with independently advancing receipt/freshness and exact owner/session identity |
| P0 | Movement | Replace obsolete native movement profile; prove final pre-input nonce/freshness/ownership gates before live use |
| P1 | Telemetry field semantics | Independent changed-state HP/Mana/XYZ or ability observations, not just stable matches |
| P1 | Durability | Sustained ~480 s freshness and full RIFT-process restart recovery; reload is insufficient |
| P1 | Runtime closure | Trace active entry points, dynamic paths/subprocesses, packaging, cached legacy defaults and current consumers |
| P2 | Public README | Clarify that **Lab 1 RR2R1 acceptance passed**; Lab 2/physical acceptance is pending. The public README's unqualified pending statement is stale. |

Do not delete `RiftReaderApiProbe` or retained historical evidence from
other targets until each target has independently passed its disabled-probe
acceptance. Do not run `run_xyz_workflow.py` as a live movement workflow
while the documented obsolete profile and final gating gaps remain.

## Next practical batch

1. Finish the **static and runtime entry-point dependency audit**, tracing
   current scripts/CLI/controller/receiver owners and external invokes.
   Distinguish explicit historical replay from active paths; record only
   concrete blockers or discovered runtime dependencies.
2. Prove **receiver feed freshness** from RR2-owned producer to independent
   consumer on eligible targets, with current identities and no claim based
   solely on process status.
3. Repair/validate the obsolete movement profile and final input gates
   offline before considering supervised movement.
4. When separately authorized, run **target-specific** Lab 2 and physical
   loaded-addon acceptance. Do **not** repeat Lab 1's successful
   `/reloadui` or bind merely because this handoff was reopened.
5. Update public README language once the authoritative status and active
   Git branches are reconciled. Do not force-push or overwrite unrelated
   development work.

## Checkpoint and recovery

- Current Windows working tree had unrelated active edits in three
  `src/RiftReader2.Live` files before this documentation checkpoint.
  They are not part of this handoff commit.
- Public GitHub `main` received README/banner presentation commits
  `2017799` and `041a089` on November 7; the active local
  `codex/modular-foundation` branch is separate and must not be casually
  overwritten or force-pushed.
- For future work: read `AGENTS.md`, `docs/status.md`, this handoff,
  and the latest source-hashed Lab 1 validation. Inspect new `git status`,
  HEAD and VM/game/session identities before using their evidence.
- This checkpoint grants **no game input, reload, restart, install, remote
  push, or controller recovery action**. Existing protections and explicit
  target-specific authority remain in force.
