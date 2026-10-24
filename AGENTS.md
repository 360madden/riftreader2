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
telemetry. The Lua producer and offline C# decoder have shared contract tests;
live transport must establish freshness and reload/session identity. See the
[addon contract](contracts/addon/README.md).

**Current phase: modular hybrid foundation, native capture, and field qualification.**
Joey authorized this phase on 2026-10-18. Implement and verify the architecture,
configuration, offline evidence workflows, and developer foundations. Follow
[the architecture](docs/architecture.md) and [development guide](docs/workflows/development.md).
Keep later features in the roadmap until their implementation is requested.
Joey subsequently authorized roadmap step 4's remaining bounded read-only
native capture work and its RIFT validation. Follow the
[native capture contract](docs/reference/native-capture.md); preserve raw
acquisition evidence without promoting native-field meanings.
Joey authorized step 5's durable field catalog and qualification workflow on
2026-10-19. Preserve exact evidence and build/session identity; evaluate recorded
assessments without treating raw capture success as field qualification.
Joey authorized step 6's supervised, bounded movement/turning experiments and
read-only memory discovery (RVA pointer chains, value/pattern searches, and
candidate fields for navigation, combat, casting, stats, and abilities) on
2026-10-19. These discover information; dedicated gameplay automation remains
outside this repository. Keep this a practical personal tool: reuse existing
modules and selected lab tools, avoid new frameworks and unnecessary process.

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
- Joey subsequently authorized installing/validating the addon in RIFT and
  building a minimal live transport with reliable freshness and reload/session
  checks. This permits addon deployment and bounded read-only acquisition for
  that task. Joey also authorized operational reuse of the original VM console
  and receiver tools; keep their source unchanged. See the
  [live validation record](docs/validation/addon-live-client-2026-10-18.md).
  Check the actual VMware process/guest before asking Joey to launch RIFT.
  Supervised experiment pulses are authorized under step 6. Dedicated automation,
  debugger attachment, process writes/injection, and changes to V1 remain outside
  this scope. Live verification must precede claims of transport readiness.
- Keep settings repository-local. Do not change global Git/Codex settings,
  Workbridge runtime settings, or REA installation as incidental setup.
- Commit coherent, verified local changes using explicit files. Joey also
  authorized judgment-based **timely local commits for significant findings** on
  2026-10-24, even when a research or recovery checkpoint changes no code. Do
  not wait for an entire roadmap milestone when a consequential result is already
  reproducible and worth preserving. Record exact evidence, source/build/session
  identity when relevant, limitations, and the next action; label tentative,
  negative, or blocked findings honestly. Preserve unrelated work and avoid
  committing credentials, private configuration, and bulky generated artifacts.
  A remote, push, destructive history change, or deployment still requires
  applicable user authorization; carry forward authorization already given.
- Report results and material limitations clearly. Continue routine authorized
  documentation work without repeated permission requests.
