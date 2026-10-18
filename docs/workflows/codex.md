# Codex workflow

## Open and orient

Open `C:\work\riftreader2` as the project folder in Codex. Root
`AGENTS.md` contains persistent repository guidance. The brief and status
documents are ordinary project documents referenced by that guidance.

The repository instructions are already written; no generated application or
additional initialization command is needed for the current documentation phase.
Model choice and account settings remain the user's existing choices.

Suggested resumption prompt:

> Work in C:\work\riftreader2. Read AGENTS.md and docs/status.md, then the
> documents relevant to my request. We are preparing documentation and discussing
> the design. Help me choose the first discovery objective and success criteria.
> Keep architecture proposals provisional and do not create application code or
> a skeleton until I authorize implementation.

## Keep context useful

Use the status file for current progress, the brief for outcomes, and the
decision register for accepted choices. Read detailed research only when it
affects the task. Update those documents when a material fact changes.

Use existing local tools for bounded searches and numerical work. For relevant
binary research, use the existing REA registration described in
[the REA guide](rea.md); confirm actual tool availability in the active session.

## Git and checks

Inspect current status and preserve unrelated edits. The initial branch is
`main`. Use small coherent local commits and explicit paths.
No remote publishing is part of repository preparation.

There are no application build/run/test commands. For documentation changes,
review content, relevant links, and `git diff --check`; review new untracked
files too because that command alone does not inspect them.

## Official references

Reviewed on 2026-10-18:

- [OpenAI: Iterating Development Workflows with Codex](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
  documents AGENTS.md as repository guidance; other planning files are optional
  workflow conventions.
- [OpenAI: Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
  recommends concise, task-relevant context.

These references inform repository guidance. They do not adopt an application
framework or require additional global configuration.
