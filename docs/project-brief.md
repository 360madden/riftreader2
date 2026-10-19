# Project brief

Status: user goals recorded on 2026-10-18. Technical design is open.

## Purpose

RiftReader2 should collect information about RIFT so that future programs can
build on dependable, reusable findings. Joey's priorities are speed, efficiency,
reliability, persistence across restarts, and quick recovery when updates change
where useful information can be found.

RiftReader2 is an improved version developed around the goals and decisions in
this repository. The original RiftReader is a reference for evidence, lessons,
and useful techniques, not an application to copy or an architecture to inherit.
Any selective reuse must be justified against V2's goals and validation needs.
Joey explicitly reaffirmed this direction on 2026-10-18.

## Agreed outcomes

1. Gather useful information more quickly, with fewer repeated manual or AI steps.
2. Make live collection and verification dependable enough to support discovery.
3. Preserve findings and supporting evidence so sessions can resume without
   repeating completed investigation.
4. Reacquire applicable data after a restart using preserved knowledge.
5. Use previous findings to narrow recovery work after game updates.
6. Move time-consuming, repetitive, and numerical work into local tools where
   that produces measurable benefit.
7. Make the resulting knowledge useful to other programs.

Reliable validation matters alongside acquisition speed. A faster scan that
promotes incorrect fields does not meet the goal.

## Movement and downstream programs

Movement, turning, and similar actions are relevant as controlled experimental
stimuli: they help distinguish what a candidate value represents and whether
a reader remains correct while the game changes.

Dedicated player automation, navigation, and combat are intended for a separate
future program. Their implementation is outside the current project preparation.

## What should survive

The durable result should identify a field's meaning and units, how to locate
it, which build and conditions it applies to, how it was validated, and what
evidence supports it. Current process addresses alone are insufficient.

Fast restart recovery and fast update recovery are separate objectives.
A method proven across restarts of one build is not thereby proven against
future game updates. Recovery speed and validity need separate measurements.

## Current authorized work

Create this repository, its documentation structure, Git baseline, and concise
Codex/Workbridge guidance. Preserve useful context from existing RiftReader and
the installed REA.

Application architecture, source skeletons, solution/project files, dependencies,
storage schemas, and runtime interfaces await discussion. C#/.NET experience
and existing V1 tools are useful context; no V2 stack is adopted here.

## Next discussion

Choose a small first discovery objective and its observable success criteria.
Then evaluate reuse, environment, evidence retention, and tooling choices against
that objective. See [open questions](planning/open-questions.md) and
[proposed measures](validation/success-measures.md).

Source: Joey's requests in the RiftReader v2 conversation on 2026-10-18.
