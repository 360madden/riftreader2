# First objective: options for discussion

Status: dated planning comparison from 2026-10-18, retained for rationale. Since
then, the [modular offline foundation](../architecture.md) and deterministic
synthetic analysis slice were implemented and validated. The first V1 evidence
objective remains future work; see [current status](../status.md) and
[the roadmap](implementation-roadmap.md).

## Recommended evidence objective

**Make one existing motion conclusion reproducible from saved evidence, with a
compact result and measured local/AI effort.**

The suggested case is the recorded rejection of a projected vector as actual
velocity during wall sliding. It already has a saved capture, a small report,
input identity, and a clear incorrect interpretation to reject. The
[reference review](../research/motion-evidence-review-2026-10-18.md) records both
the evidence and the missing verified replay entry point.

This tests whether prior investigation can become reusable local work. The
synthetic foundation proves the pipeline, but it does not answer this evidence
question.

## Three practical options

| Option | First useful outcome | Existing basis | Main unresolved issue |
|---|---|---|---|
| A — Reproduce a saved finding | A repeatable report correctly rejects projected velocity and preserves relevant uncertainty. | Batch 6, wall-trial artifacts, classification report, and existing offline analysis tools. | Locate and validate the original analysis entry point, or determine the smallest missing part. |
| B — Measure restart reacquisition | An existing qualified field is reacquired and behaviorally checked in a fresh process, with elapsed time and failures recorded. | V1 coordinate/body-yaw and component-chain restart evidence. | Decide the live environment, exact cases, and measurement method. |
| C — Investigate one new native motion field | A candidate for actual velocity, speed, or signed turn rate is either qualified or rejected by meaningful evidence. | Known component relationships, static clues, and negative motion examples. | Greater uncertainty and live/static investigation cost; these fields remain unresolved. |

A remains the next recommended evidence increment because it provides fixed
inputs and a known counterexample for measuring reproducibility and offloading.
B addresses restart speed more directly. C pursues additional game knowledge.

## Proposed acceptance evidence for A

- Identify exact inputs, declared build/session applicability, content hashes,
  and missing provenance.
- Preserve or locate a saved analysis procedure and its invocation.
- Reproduce the important direction disagreement in both decisive wall trials,
  while also explaining why free travel initially appeared convincing.
- Distinguish recorded field values, derived motion, and semantic hypotheses.
- Report sample timing, gaps, and limits of stimulus/sample alignment.
- Record elapsed local work, output size, and required AI interactions.
- Repeat against the same fixed inputs and retain the result plus source identity.

These checks remain proposed, not adopted numeric thresholds. A passing result
would establish reproducible analysis of this dataset; it would not establish a
native velocity field, lossless capture, executable provenance, or future-update
recovery.

## Questions before importing V1 evidence

1. Is reproducibility, restart speed, or discovery of a new field the most useful
   next result?
2. Is the saved wall-motion case a suitable first immutable evidence bundle?
3. Which existing source and artifacts should be referenced or selectively
   adapted?
4. What result and effort measurement would make the increment worthwhile?

The language, module layout, and initial file-based boundaries are now selected.
Implement the smallest adapter and analysis change that produces the chosen
result without importing V1 application structure. A database and new process
boundary remain evidence-driven later choices.

## Work already completed

The repository contains a [source-backed reuse inventory](../reference/reuse-inventory.md),
a dated evidence review, [tool workflows](../README.md), and a verified offline
analysis foundation. That foundation replays only a synthetic illustrative
capture. It has not reproduced the V1 wall-motion conclusion, analyzed a RIFT
binary, read a live process, or sent game input.
