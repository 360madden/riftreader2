# Project brief

Status: goals and modular foundation implementation authorized on 2026-10-18.

## Purpose

RiftReader2 should collect information about RIFT so that future programs can
build on dependable, reusable findings. Joey's priorities are speed, efficiency,
reliability, and persistence across full game exits and relaunches. Recovery when
updates change where useful information can be found remains a longer-term goal;
Joey explicitly deferred patch recovery on 2026-10-25.

RiftReader2 is an improved version developed around the goals and decisions in
this repository. The original RiftReader is a reference for evidence, lessons,
and useful techniques, not an application to copy or an architecture to inherit.
Any selective reuse must be justified against V2's goals and validation needs.
Joey explicitly reaffirmed this direction on 2026-10-18.

Joey also explicitly requires a hybrid product: a Lua addon inside RIFT and a
modular external .NET application. The addon gathers supported API information
and validation references; the external side performs acquisition, native-field
research where useful, analysis, persistence, and export. Both are first-class
parts of V2. See [the hybrid decision](decisions/0002-hybrid-addon-and-reader.md).

## Agreed outcomes

1. Gather useful information more quickly, with fewer repeated manual or AI steps.
2. Make live collection and verification dependable enough to support discovery.
3. Preserve findings and supporting evidence so sessions can resume without
   repeating completed investigation.
4. Reacquire applicable data after a restart using preserved knowledge.
5. Preserve findings for future update recovery; patch recovery is currently deferred.
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

**Current priority, reaffirmed by Joey on 2026-10-25:** durable collection across
fully exiting RIFT and launching it again. A restart requires the old game
process to end, a fresh process/start identity, and reacquisition through the
preserved locating recipe. Addon reload, character relog, and reader restart
alone do not satisfy this requirement. VM/host restart validation is separate.

Patch/update recovery is deferred until Joey explicitly resumes it; it is not
the automatic next milestone or a condition for accepting observed same-build
restart durability. Exact-build guards remain mandatory: a changed executable
SHA fails closed. A method proven on one build is not thereby proven after an
update. Preserve the number and scope of observed restart cases and keep native
field semantics separately qualified. See [the accepted restart durability
policy](decisions/0008-full-game-restart-durability.md).

## Current authorized work

Joey authorized establishing and building the modular architecture and as much
of its useful foundation as practical, with easy upgrades, explicit
configuration, and efficient AI use. The implementation selects .NET 10 and an
offline evidence workflow as documented in the
[architecture decision](decisions/0001-modular-offline-foundation.md).
Git author identity is repository-local: `360madden <360madden@gmail.com>`.

## Current planning

Use the [ranked RR2 roadmap](planning/implementation-roadmap.md) for completed
capabilities and remaining work. The Lua/C# producer/contract and selected saved
wall-motion replay have been delivered; the original October starting tasks
are historical. Current priorities include useful longer routes, physical
player/resource retrieval and dependable route context. Live qualification is
specific to each field/build/session and does not follow from offline tests.

Source: Joey's requests in the RiftReader v2 conversation on 2026-10-18.
