# RiftReader2 repository instructions

## Purpose and current scope

RiftReader2 gathers reliable RIFT information for other programs. Optimize for
discovery speed, efficiency, durable knowledge, restart recovery, update recovery,
and less repetitive AI work. Movement and turning support controlled tests.
Dedicated navigation, combat, and player automation belong to a future program.

**Current phase: documentation and repository preparation.** Authorized work
includes documentation, planning records, repository instructions, Git
initialization, and nonfunctional repository housekeeping. Do not create
application code, solution or project files, package manifests, executable
scaffolding, or an application architecture during this phase. Record design
ideas as proposals and unresolved choices as questions. Begin implementation
when Joey authorizes the next phase; apply later instructions without adding
confirmation steps for work they already authorize.

## Orientation and durable context

- Work in `C:\work\riftreader2`.
- For substantive project work, read [current status](docs/status.md) and the
  relevant topic from [the index](docs/README.md). Read only what the task needs.
- [The brief](docs/project-brief.md) owns goals;
  [decisions](docs/decisions/README.md) own accepted choices;
  [proposals](docs/planning/top-20-proposals.md) remain ideas.
- Treat `C:\rift modding\RiftReader` as reference. Do not modify or import it
  as part of this setup. Reuse decisions remain open.
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
- There are no application build or test commands yet. Verify documentation
  through content review, link checks, and Git checks as appropriate. Do not
  invent a test suite or run unrelated V1 tests.

## Tool and Git workflow

- Codex uses its local tools. Browser ChatGPT uses Workbridge; see
  [its guide](docs/workflows/workbridge.md) for hashes, operation IDs, and jobs.
- Inspect current Git status before edits. Preserve unrelated work.
- Use explicit paths and literal argument arrays for Workbridge terminal jobs.
  Poll to a terminal state and inspect actual exit code and output.
- Reuse the installed REA for relevant binary research; follow
  [the REA guide](docs/workflows/rea.md) and installed provider capabilities.
- This preparation task does not include running RIFT, live inputs, debugger
  attachment, native target analysis, or changes to other projects.
- Keep settings repository-local. Do not change global Git/Codex settings,
  Workbridge runtime settings, or REA installation as incidental setup.
- Commit coherent, verified local changes using explicit files. A remote, push,
  destructive history change, or deployment requires applicable user
  authorization; carry forward authorization already given.
- Report results and material limitations clearly. Continue routine authorized
  documentation work without repeated permission requests.
