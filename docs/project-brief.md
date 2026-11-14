# Project brief

Status: goals and modular foundation implementation authorized on 2026-10-18.

## Purpose

**Current product target — Joey's November 14 clarification:** a local automated
player that makes its own movement, encounter, combat, recovery, leveling and
skill/build decisions. RR2's discovery/retrieval work supplies its observations
and durable knowledge. AI/humans build, configure, diagnose and tune the software;
the completed runtime should handle supported routine gameplay without model
calls or human decisions per action, reducing latency, compute and tokens.
This states the intended product, not completed autonomous-player capability.

**AI scaffolding clarification:** ChatGPT/AI may temporarily control the player
when there are gaps, blockers or insufficient local decisions, and can be the
preferred approach when it provides better overall benefits. Compare useful
progress, reliability, latency, compute and token costs. Local autonomy remains
the target; it is not a reason to refuse effective assistance during development.
Use the existing authorized controls and one input owner, with a clear handoff
and preserved STOP/identity/freshness/release behavior. No live run is initiated
by recording this requirement.

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
8. Operate an automated player with local outcome-driven decisions and minimal
   repeated AI/human involvement during ordinary travel, combat and progression.

Reliable validation matters alongside acquisition speed. A faster scan that
promotes incorrect fields does not meet the goal.

## Movement and downstream programs

Movement, turning, and similar actions are relevant as controlled experimental
stimuli: they help distinguish what a candidate value represents and whether
a reader remains correct while the game changes.

The original October scope placed dedicated player automation, navigation and
combat in a separate future program, outside the initial project preparation.

**Planning correction — November 14, 2026:** Joey identified combat and survival
as essential to useful route travel. The current roadmap therefore includes a
defensive combat system and travel/combat/recovery integration as near-term
product priorities. The earlier separation of RR2 discovery from downstream
automation does not exclude those requirements from planning. Final module or
program placement remains an implementation decision; no new live combat or
health-change experiment is started by this clarification.

Joey further clarified that low-level characters need to avoid high-level
hostiles and should level along the way. Travel planning therefore includes
pre-engagement threat assessment, suitable XP encounters, recovery, measured
XP/level progress and reassessment after leveling. An unsafe destination may
require a safer known route or leveling in an appropriate area first. Survival
comes before taking an optional fight; a trip retains its objective and limits.

Skill/build progression is also part of this goal: choose future skills in a
valid per-level plan, reconcile actual learned state after leveling, and use a
matching conditional combat policy. Ability/spell choices and ordering must
account for damage/healing, costs, cooldown/GCD/cast timing, defensive needs,
useful combinations and downtime. Useful progress is measured across travel,
fights and recovery, rather than maximizing isolated damage numbers. No live
point spending, training or respec is performed by documenting that requirement.

The runtime observes, chooses legal actions, executes through one input owner,
checks outcomes and replans locally. Normal combat/recovery can return to travel
automatically within an authorized run when all required checks pass. Operator
STOP and safety faults halt every mode and require explicit Resume/new run.
Existing manual/supervised tools remain useful for development and acceptance;
their control model does not define the automated-player goal.

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
are historical. Current priorities include encounter assessment, useful combat
and recovery, bounded leveling, travel/progression integration, longer routes
and dependable route context. Live qualification is
specific to each field/build/session and does not follow from offline tests.

Source: Joey's requests in the RiftReader v2 conversation on 2026-10-18.
