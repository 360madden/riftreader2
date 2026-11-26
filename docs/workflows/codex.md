# Codex workflow

Current project state changes as live capabilities are validated; use
[the status handoff](../status.md) rather than this workflow as the capability
record. To delegate bounded read-only analysis to the existing Codex CLI in a
RIFT guest, use the [Lab Codex jobs workflow](lab-codex.md).

## OpenAI cloud development (November 27, 2026)

Use a hybrid workflow: OpenAI-managed repository-only coding workers, GitHub
as the shared handoff, and LEGION for physical Windows integration and any
separately authorized live acceptance. Cloud tasks must not connect to the
physical desktop or require installed game assets, private captures, or secrets.
The root AGENTS.md contains the narrow cloud-work exception.

### One-time environment setup

Open [Codex web](https://chatgpt.com/codex), connect only the RR2 repository
(`360madden/riftreader2`), and create/publish a reusable cloud environment.
Select the current development branch `codex/modular-foundation` for tasks;
do not assume `main` contains the latest implementation. Prefer Python 3.14
to match the local toolchain, with no extra packages needed for the initial
allowlisted navigation tests if the cloud environment supports their imports.
Run the checks below as the environment test, and record actual OS, interpreter
and failure/skip results. Linux compatibility is not assumed. If needed, fix
portable test fixtures in a separate branch, not production identity checks.

```sh
python -B scripts/validate_cloud_navigation.py --lane all --jobs 3
```

Use `--lane planning`, `--lane adoption`, or `--lane progress` for focused
worker acceptance. The runner isolates native-reader overrides and invokes
only explicitly selected repository tests. It is not the full Windows gate.
Use `--jobs 1` for serial diagnostics; concurrent lanes report in fixed order.
The progress lane includes deterministic unfinished-leg feedback diagnostics.

### Continuous integration

GitHub Actions runs the `RR2 CI` workflow on worker pull requests targeting
`codex/modular-foundation` and pushes to that integration branch. It runs
three independent hosted checks: fast Windows navigation lanes, Linux
progress/link/commit-whitespace checks, and the full Windows offline gate
(`scripts/validate.ps1`, pinned SDK, locked NuGet restore, build, .NET and Python
tests, formatting, synthetic native/Lua smoke and deterministic replay).
All jobs are read-only repository checkouts; no RIFT or physical host access.

Open worker PRs against the integration branch, not the historical `main`.
Run your focused lane before opening a PR. Review the stable `RR2 required gate`
check, which succeeds only when all three jobs succeed. Cancel superseded
runs rather than queueing stale results. Do not integrate failed, skipped,
cancelled or pending checks; a green hosted run is not live acceptance.

Enable branch protection requiring `RR2 required gate` after the initial
hosted run is green. Preserve the existing integration branch; do not force
push or change the default branch. Until enforcement is confirmed, the
coordinator must check CI manually before merging worker work.

### Initial independent worker assignments

| Worker | Outcome | Exclusive files and validation |
| --- | --- | --- |
| P1 — local planner | Improve bounded coordinate-route selection, input validation and deterministic ranking for standalone synthetic geometry. | `scripts/waypoint_local_plan.py`, `tests/test_waypoint_local_plan.py`; planning lane. |
| P2 — route evidence | Improve portable receipt and candidate-validation fixtures; preserve scoped adoption and rejection of unqualified routes. | `scripts/waypoint_navigation_candidate.py`, `tests/test_waypoint_navigation_candidate.py`; planning lane. |
| P3 — progress and simulation | Improve offline progress projection and synthetic route regression coverage, including loop/floor ambiguity. | `scripts/waypoint_progress.py`, `tests/test_waypoint_progress.py`, `tests/test_waypoint_marker_progress.py`; progress lane. |

Start with three independent tasks, each from the same verified base SHA in
a separate cloud workspace and branch; expand only when useful independent
work exists. Keep interface changes coordinated. Workers must not change the
same files or silently merge a sibling's unreviewed work.

Suggested task prompt: Read AGENTS.md, this workflow, and only the files
assigned to your lane. Work from the current development branch and report
the starting SHA. Implement one coherent outcome with tests, run its lane,
record any failures/skips and limitations, and return a diff or PR for
coordinator review. No native/game access, deployment, or automatic merge.

### Integration and cost

Use ChatGPT Work for coordination, review and cross-repository research;
Codex Cloud for independent implementations and tests. The coordinator reviews
each diff, resolves conflicts, runs the relevant lanes, and then uses the
verified physical host for Windows-specific tests. The full local gate stays
authoritative for physical acceptance. Publish or merge only reviewed work;
retain base SHA, final commit, test result, and changed files.

Start with the ChatGPT plan's available cloud capacity. Do not create API
keys, chargeable API agents, additional billed runners, recurring tasks, or
upload raw game installations automatically. A paid Agents API coordinator
is a later option if measured throughput justifies the additional cost.

Official sources (checked November 27, 2026):

- [Using Codex Cloud](https://help.openai.com/en/articles/20001545-using-codex-cloud)
- [ChatGPT Work and Codex](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)
- [Agents API multi-agent orchestration](https://developers.openai.com/api/docs/guides/agents-api/multi-agent)

## Open and orient

Open your local RiftReader2 checkout as the project folder in Codex. Read root
`AGENTS.md`, current status, and only the topic relevant to the task. Use
[the architecture](../architecture.md) for module boundaries and
[the development workflow](development.md) for the authoritative validation
command.

Suggested resumption prompt:

> Work in this RiftReader2 checkout. Read AGENTS.md and docs/status.md, then the
> documents relevant to my request. Preserve the modular boundaries in
> docs/architecture.md and use scripts/validate.ps1 for the full gate. Treat V1
> as evidence and reference material, not an architecture to copy. State what
> the change proves and what remains unverified.

## Keep context useful

Use status for current progress, the brief for outcomes, and the decision
register for accepted choices. Read detailed research only when it affects the
task. Update durable documents when a material fact changes.

Give a coding agent one bounded outcome, relevant file paths, acceptance
criteria, and the exact validation command. Routine documentation,
unchanged-schema configuration, and narrow tests for specified behavior can use
a cheaper model. Identity, provenance, schema, I/O, concurrency, native access,
or module-boundary changes need stronger reasoning or review; this guidance does
not force a model setting change.

Use existing local tools for bounded searches and numerical work. For relevant
binary research, use the existing REA registration described in
[the REA guide](rea.md); confirm actual tool availability in the active session.

## Git and checks

Inspect current status and preserve unrelated edits. Read the actual branch with
`git branch --show-current`; do not infer it from an older handoff. Use
small coherent commits and explicit paths. Push verified milestones when authorized;
cloud branches are reviewed and integrated by the coordinator.

Run the full repository gate from PowerShell 7:

```powershell
pwsh -NoProfile -File .\scripts\validate.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

The gate performs dependency checks, locked restore, Release build, tests,
format verification, deterministic synthetic replay, relative-link checks, and
Git whitespace review. Inspect new untracked files separately because
`git diff --check` does not cover them.

## Official references

Reviewed on 2026-10-18:

- [OpenAI: Iterating Development Workflows with Codex](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
  documents AGENTS.md as repository guidance; other planning files are optional
  workflow conventions.
- [OpenAI: Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
  recommends concise, task-relevant context.

These references informed the repository guidance. The selected application
foundation is recorded separately in
[ADR 0001](../decisions/0001-modular-offline-foundation.md).
