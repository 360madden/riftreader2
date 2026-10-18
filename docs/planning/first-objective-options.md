# First objective: options for discussion

Status: proposal, not adopted. No architecture or implementation is specified.

## Recommended starting objective

**Make one existing motion conclusion reproducible from saved evidence, with a
compact result and measured local/AI effort.**

The suggested case is the recorded rejection of a projected vector as actual
velocity during wall sliding. It already has a saved capture, a small report,
input identity, and a clear incorrect interpretation to reject. The
[reference review](../research/motion-evidence-review-2026-10-18.md) records both
the evidence and the missing verified replay entry point.

This directly tests whether prior investigation can become reusable local work.
It does not require finding a new field to demonstrate value.

## Three practical options

| Option | First useful outcome | Existing basis | Main unresolved issue |
|---|---|---|---|
| A — Reproduce a saved finding | A repeatable report correctly rejects projected velocity and preserves relevant uncertainty. | Batch 6, wall-trial artifacts, classification report, and existing offline analysis tools. | Locate and validate the original analysis entry point, or determine the smallest missing part. |
| B — Measure restart reacquisition | An existing qualified field is reacquired and behaviorally checked in a fresh process, with elapsed time and failures recorded. | V1 coordinate/body-yaw and component-chain restart evidence. | Decide the live environment, exact cases, and measurement method. |
| C — Investigate one new native motion field | A candidate for actual velocity, speed, or signed turn rate is either qualified or rejected by meaningful evidence. | Known component relationships, static clues, and negative motion examples. | Greater uncertainty and live/static investigation cost; these fields remain unresolved. |

A is the current recommendation because it provides fixed inputs and a known
counterexample for measuring reproducibility and offloading. B addresses restart
speed more directly. C pursues additional game knowledge. Joey's chosen priority
can change this order.

## Proposed acceptance evidence for A

- Identify exact inputs, build/session applicability, and missing evidence.
- Preserve or locate a saved analysis procedure and its invocation.
- Reproduce the important direction disagreement in both decisive wall trials,
  while also explaining why free travel initially appeared convincing.
- Distinguish recorded field values, derived motion, and semantic hypotheses.
- Report sample timing, gaps, and any limits of stimulus/sample alignment.
- Record elapsed local work, output size, and required AI interactions.
- Repeat against the same fixed inputs and retain the result plus source identity.

These are proposed checks, not adopted numeric thresholds. A passing result
would establish a reproducible analysis of this dataset; it would not establish
a native velocity field, lossless capture, or future-update recovery.

## What needs a decision first

1. Is reproducibility, restart speed, or discovery of a new field the most useful
   first result?
2. Is the saved wall-motion case a suitable first evidence bundle?
3. Which existing source and artifacts should be used as references or reused?
4. What result and effort measurement would make the first increment worthwhile?

After those choices, discuss the smallest implementation that produces that
result. Language, storage engine, project layout, process boundaries, and
consumer interfaces remain open.

## Work already completed

The repository contains a [source-backed reuse inventory](../reference/reuse-inventory.md),
a dated evidence review, and [tool workflows](../README.md). This preparation did
not run V1 analysis, create a replay tool, analyze a RIFT binary, or send game input.
