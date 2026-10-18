# RiftReader2

**Current phase: documentation and repository preparation.**

RiftReader2 is intended to gather reliable information about RIFT that other
programs can build upon. The priorities are faster discovery, efficient local
analysis, durable findings, dependable reacquisition after restarts, and faster
recovery when game updates change relevant values.

Movement and turning serve controlled data collection and validation. Dedicated
player automation, navigation, and combat belong to a separate future program.

The repository was started on 2026-10-18 at `C:\work\riftreader2`. Application
architecture, project layout, dependencies, storage, and interfaces remain open
for discussion. There is no application, executable skeleton, or build command.

## Start here

| Document | Purpose |
|---|---|
| [Agent instructions](AGENTS.md) | Scope and working rules for Codex and other assistants. |
| [Current status](docs/status.md) | Compact handoff and next discussion. |
| [Project brief](docs/project-brief.md) | Agreed outcomes and scope. |
| [Proposed top 20](docs/planning/top-20-proposals.md) | Ideas to evaluate; not an approved implementation plan. |
| [Open questions](docs/planning/open-questions.md) | Choices to discuss before implementation. |
| [Documentation index](docs/README.md) | Workflows, research, decisions, and validation. |

## Work locally

Open `C:\work\riftreader2` as the project folder in Codex. Its repository
instructions are in `AGENTS.md`; a short resumption prompt is in the
[Codex guide](docs/workflows/codex.md).

From browser ChatGPT, use Workbridge with project `riftreader2`. See the
[Workbridge guide](docs/workflows/workbridge.md) for paths, reliable edits,
command jobs, and Git operations.

## Repository contents

- `docs/planning/`: proposals and questions.
- `docs/decisions/`: recorded decisions.
- `docs/reference/`: dated context from existing work.
- `docs/research/`: future research notes and evidence references.
- `docs/workflows/`: Codex, Workbridge, and REA usage.
- `docs/validation/`: observed checks and proposed success measures.
- `docs/templates/`: concise decision and research note templates.
- `artifacts/`: documented location for local generated output, excluded from
  Git except for its README.

This is a separate repository. Existing RiftReader work remains at
`C:\rift modding\RiftReader` and is reference material.
