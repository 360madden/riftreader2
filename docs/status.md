# Current status

Updated: 2026-10-18.

## Phase

Documentation and planning. Application architecture and code remain pending
discussion with Joey.

## Current state

- Root: `C:\work\riftreader2`; branch: `main`.
- Initial documentation baseline: `ba857c0`.
- Joey reaffirmed that V2 is an improved version guided by this repository's
  goals, not a copy of V1. The brief, decision register, and agent instructions
  now record that direction; selective technical reuse remains undecided.
- [The brief](project-brief.md) records goals; the
  [top 20](planning/top-20-proposals.md) remains proposed.
- [First objective options](planning/first-objective-options.md) now compares
  reproducing a saved finding, measuring restart reacquisition, and investigating
  one new native motion field.
- [The reuse inventory](reference/reuse-inventory.md) records existing source
  entry points and limitations.
- [The motion review](research/motion-evidence-review-2026-10-18.md) preserves
  newer V1 evidence and the unresolved replay-command question.
- [Workbridge](workflows/workbridge.md) and [REA](workflows/rea.md) guides include
  the newer local .NET helper proof and existing evidence-reuse mechanisms.

## Most useful new findings

V1's projected motion vector was rejected as actual velocity by wall-slide
evidence. The saved report and 100,187,956-byte capture are present; the complete
capture was not reanalyzed or rehashed during this review. A saved command for
reproducing that classification was not identified by the bounded search.

The current recommendation is to make one saved conclusion reproducible and
measure the required local work and AI interactions. This remains a proposal.

V1 progressed independently to `099ddf8` with guarded motion diagnostics.
Observed cadence in its recorded batch differs from the requested interval.
Those findings are reference evidence, not V2 runtime results.

## Verification and continuity

The [initial setup record](validation/repository-setup-2026-10-18.md) describes
the original documentation baseline. The continuation added source-backed
reference and planning documents only. No V1 code or tests, live game input,
binary analysis, or helper build was run during this review.

Use `git log -1 --oneline` and `git status --short --branch` for the current
commit and working-tree state. Keep startup context small and follow the
[documentation index](README.md) for task-specific detail.

The direction clarification changed documentation only. Content review,
relative-link checks, and Git whitespace checks passed before its commit.

## Next discussion

Choose which first result matters most: reproducible saved analysis, faster
restart reacquisition, or new-field discovery. Then discuss the smallest useful
implementation and its success criteria. No option, technical stack, schema,
process layout, or runtime interface has been adopted.
