# RiftReader2 repository instructions

## Purpose and current scope

RiftReader2 gathers reliable RIFT information for other programs. Optimize for
discovery speed, efficiency, durable knowledge, restart recovery, update recovery,
and less repetitive AI work. Movement and turning support controlled tests.
Dedicated navigation, combat, and player automation belong to a future program.

The product is hybrid: a first-class RIFT Lua addon plus the modular external
.NET application. Preserve addon API, native memory, and derived evidence as
distinct sources. See [the hybrid decision](docs/decisions/0002-hybrid-addon-and-reader.md).
Do not assume general Lua file/network access or treat SavedVariables as live
telemetry. The current implemented pipeline is offline; addon/transport work
must establish producer compatibility, freshness, and reload/session identity.

**Current phase: modular architecture and offline foundation implementation.**
Joey authorized this phase on 2026-10-18. Implement and verify the architecture,
configuration, offline evidence workflows, and developer foundations. Follow
[the architecture](docs/architecture.md) and [development guide](docs/workflows/development.md).
Keep later features in the roadmap until their implementation is requested.

## Orientation and durable context

- Work in `C:\work\riftreader2`.
- For substantive project work, read [current status](docs/status.md) and the
  relevant topic from [the index](docs/README.md). Read only what the task needs.
- [The brief](docs/project-brief.md) owns goals;
  [decisions](docs/decisions/README.md) own accepted choices;
  [proposals](docs/planning/top-20-proposals.md) remain ideas.
- Treat `C:\rift modding\RiftReader` as reference. Do not modify or import it
  wholesale. Evaluate any selective reuse explicitly.
- Build an improved RiftReader2 guided by this repository's goals and decisions.
  Do not copy the original application or inherit its architecture by default.
  Evaluate selective reuse against V2's goals and validation needs.
- Keep a compact handoff in `docs/status.md`: what changed, what was actually
  verified, unresolved questions, and the next authorized task.

## Evidence and efficiency

- Distinguish user decisions, proposals, observed evidence, and assumptions.
- Record sources, dates, build/session identity, and limitations where relevant.
  V1 observations do not establish V2 capabilities.
- A saved address is session state. Durable knowledge includes the field meaning,
  a locating method, applicability, and validation evidence.
- Prefer bounded local searches and analysis to dumping large files into chat.
  Use `rg`/`rg --files` when available or Workbridge's scoped search.
- Keep generated captures, binaries, logs, and caches under `artifacts/`.
  Keep small useful findings and provenance in tracked documentation.
- Run `pwsh -NoProfile -File scripts/validate.ps1` for the full local gate.
  For focused iteration, use the development guide. Keep module dependencies
  acyclic and preserve versioned input/output contracts.
- Keep AI context bounded: read this file, status, and the task's module only.
  Delegate disjoint work with explicit ownership. Routine docs, fixtures, and
  narrowly specified changes can use cheaper models with the same checks;
  identity, native access, concurrency, schema changes, and integration need
  stronger review. See the roadmap for concrete handoff criteria.

## Tool and Git workflow

- Codex uses its local tools. Browser ChatGPT uses Workbridge; see
  [its guide](docs/workflows/workbridge.md) for hashes, operation IDs, and jobs.
- Inspect current Git status before edits. Preserve unrelated work.
- Use explicit paths and literal argument arrays for Workbridge terminal jobs.
  Poll to a terminal state and inspect actual exit code and output.
- Reuse the installed REA for relevant binary research; follow
  [the REA guide](docs/workflows/rea.md) and installed provider capabilities.
- This foundation task does not include running RIFT, live inputs, debugger
  attachment, native target analysis, or changes to other projects.
- Keep settings repository-local. Do not change global Git/Codex settings,
  Workbridge runtime settings, or REA installation as incidental setup.
- Commit coherent, verified local changes using explicit files. A remote, push,
  destructive history change, or deployment requires applicable user
  authorization; carry forward authorization already given.
- Report results and material limitations clearly. Continue routine authorized
  documentation work without repeated permission requests.
