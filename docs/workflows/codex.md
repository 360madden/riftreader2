# Codex workflow

Current project state changes as live capabilities are validated; use
[the status handoff](../status.md) rather than this workflow as the capability
record. To delegate bounded read-only analysis to the existing Codex CLI in a
RIFT guest, use the [Lab Codex jobs workflow](lab-codex.md).

## Open and orient

Open `C:\work\riftreader2` as the project folder in Codex. Read root
`AGENTS.md`, current status, and only the topic relevant to the task. Use
[the architecture](../architecture.md) for module boundaries and
[the development workflow](development.md) for the authoritative validation
command.

Suggested resumption prompt:

> Work in C:\work\riftreader2. Read AGENTS.md and docs/status.md, then the
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
small coherent local commits and explicit paths. Remote publishing is not part
of the current local foundation work.

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
