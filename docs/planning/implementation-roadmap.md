# RR2 roadmap

Updated **November 14, 2026 (America/New_York)** from checkout
`C:\work\riftreader2`, branch `codex/modular-foundation`, implementation through
`a394022` (Waypoints v1.2.0 movement milestone; longer routes in `b91e2b4`,
composite-source guard in `570414c`).
Review host: **AMD-DESKTOP**. This is the current overall roadmap;
older discovery dispatch plans and the foundation history below are references.
Existing uncommitted native research is work in progress, not a delivered result.

The latest native integrity fix verifies each vitals burst's source digest,
build, process epoch, self key and sample count before composite publication.
Its focused checks and retained-source replay passed; it adds no new live field
semantics or game observation. See the Nov 13 23:54 entry in the
[RRE intake record](../workflows/rre-discovery-intake.md).

RR2's intended product is a **local automated player**, supported by useful RIFT
discovery and repeatable retrieval. Waypoints is an existing consumer and control
tool; its manual/supervised workflow is not the final player-control model.
**Joey's November 14 correction:
route travel must account for combat and survival; reaching a destination is not
useful if the character dies on the way.** Combat is now a first-class roadmap
priority, rather than merely a source of telemetry or deferred future work.
The route follower and combat response must share the existing input ownership
and STOP controls. Their final module/product placement is an implementation
choice, not a reason to omit the capability.

**Progression clarification, November 14:** Joey also wants leveling along the
way. A low-level character must not blindly fight a stronger hostile just because
it is on the route. The product goal is to arrive alive while making useful,
appropriate XP/level progress: assess encounters before engagement, choose
suitable fights, avoid excessive danger, and level in a suitable area first if
the destination cannot yet be reached through a known safe route.

**Build and ability-selection clarification, November 14:** Joey wants future
skills chosen as the character levels, and combat actions chosen in an effective
order using damage, cooldowns, resource costs, downtime and related constraints.
Build progression and combat decisions must use the same current character
state. A leveling loop that leaves skill points/abilities unmanaged or repeats
a fixed attack sequence does not satisfy this goal.

**Autonomous decisions and compute efficiency, November 14:** The automated
player chooses its own ordinary movement, targets, combat actions, recovery and
skill/progression steps locally. AI/humans develop, configure and tune the system
or bridge capability gaps. The completed local runtime should not depend on
per-action LLM calls or human approvals for supported routine behavior. Effective
decisions and low compute/token overhead are product requirements.

**CLI-first applications, November 14:** All apps should expose core workflows
through a discoverable, scriptable CLI first, with a GUI over shared operations
and state second; both are preferred. This applies across the runtime, build,
combat, discovery and Waypoints work rather than being a separate late polish
task. Avoid GUI-click dependencies for important operations; provide headless
paths where applicable and consistent status/control, errors and structured
output. Existing Waypoints CLI support is a starting pattern, not proof that
every app already meets this requirement. Apply incrementally to useful work;
see the [development guide](../workflows/development.md#cli-first-application-interfaces).

**Temporary AI-control scaffolding:** ChatGPT/AI can directly control the player
when local behavior is missing, blocked or insufficient, and may be preferred
when the overall benefit is better. Compare useful progress, reliability,
latency, compute and tokens; zero model calls is a target for mature local
behavior, not a reason to leave useful work blocked. Assisted operation uses the
same authorized action scope, input owner, STOP and identity/freshness/release
checks. Build reusable local behavior from recurring assisted cases when useful.

This updates planning direction; it does not start combat implementation or
grant new game-input, casting, restart or cross-host authority. Live work still
requires its applicable authority and fresh identity/ownership checks.

## Completed capabilities

| Area | What is delivered | Evidence boundary |
| --- | --- | --- |
| Foundation and retained knowledge | Modular .NET core/CLI/Windows reader, bounded native capture, field catalog, pointer/value searches, deterministic replay, source-hashed compilation, JSON/CSV/JSONL exports and offline Discovery Explorer. | Implemented and tested; old captures preserve their original build/session, not current live qualification. [Compilation milestone](discovery-compilation-roadmap.md). |
| Hybrid addon | RR2-owned Lua producer, strict C# decoder, typed frames, nonce/freshness lifecycle and shared contract checks. | Historical Lab 1 RR2R1 acceptance passed 64/64 advancing comparisons. Physical RR2R1 loaded/bound producer and advancing-reference acceptance remain separate. [Standalone reference](../reference/self-contained-api-reference.md). |
| Physical acquisition | Exact-host/PID native commands, position/body-facing/camera readers and reusable same-build movement calibration. | AMD physical movement/turning, feedback and specific full-game restart recovery cases are recorded; other fields retain their own limits. [Waypoints workflow](../workflows/physical-waypoints.md). |
| Native player-state retrieval | Composite context/XYZ/vitals acquisition, SHA-verified replay, same-epoch histories and explicit cross-epoch comparisons; raw stat/vitals comparison tools. | Latest Nov 13 AMD composite observed XYZ and HP candidates; target, Mana and Energy were unavailable. Unchanged HP is not changed-state proof. [Composite record](../workflows/rre-discovery-intake.md), [stat comparison](../handoff-2026-11-10-player-stats-offline.md). |
| Waypoints core | Actual-path recording, save/load, Forward/Reverse, STOP/F8, persistent progress, explicit Resume and idle reconnect. | Short-route live trials and specific same-build restart/Resume cases passed. [Recorded-route evidence](../handoff-2026-11-12-recorded-routes.md). |
| Waypoints daily use | Six-tab GUI and CLI controls, draft-safe editing/Undo, route Library, zone tags, live-pose status, Activity/error diagnostics, scene capture, beacons, compact radar, manual guidance and breadcrumb export. | Local live cases and native normal/compact UI checks recorded; zone/floor identity and universal display continuity remain limited. [Waypoints capability inventory](five-hour-recorded-routes-2026-11-12.md#what-is-done). |
| Longer routes | Shared 1,000-unit / 500-waypoint envelope, 30,000 recording samples, 30-minute trip budget, larger CLI transport, preview Fit to 1,500 units and bounded display annotations. | **Implemented and full-envelope offline verified.** One live nine-point STOP/Resume case covered 23.10184156 total planned units on a repeated 2.89-unit clear segment. A separate ten-unit clear-path out-and-back used one W hold per leg (1.601/1.560 seconds), ended 0.243274/0.252260 units from its goals, released all input and settled with zero drift. These cases do not qualify obstacle travel, arbitrary longer routes or the 1,000-unit envelope. Existing files/checkpoints are compatible. [Longer routes](../workflows/physical-waypoints.md#longer-routes). |
| Continuous movement helper and owned map destinations | **Waypoints v1.2.0 implements** continuous held-W travel as the GUI/headless default, legacy pulse fallback, an RR2-owned flat-X/Z Click-to-move mode and CLI projection/movement controls. Existing identity, progress, foreground, STOP/release and explicit playback Resume checks remain in the path. | **Scoped live acceptance passed for continuous clear-path route/STOP/Resume plus CLI and physical-GUI owned-map movement.** The resumed route reached nine of nine over 23.10184156 planned units; a separate ten-unit out-and-back used one W hold per leg, arrived within 0.253 units, released input and settled with zero drift. CLI `preview project`/`move pick` used the actual mapped 411×182 rendered map and arrived within 0.203314 units. In the physical GUI test, the first stale-origin click was refused before input; after an explicit new click at screen pixel 879,390, shared `map-go` arrived within 0.2644456 units. Both map cases left the original six-point route, revision 1, selection 6 and clean state unchanged; final restoration returned within 0.166 units of the original position with STOP latched and no release fault. These are clear-path controls, not obstacle navigation or NumLock autorun; the flat X/Z map supplies no terrain, height, obstacle or clearance knowledge. [Route result](../../artifacts/movement-upgrade/long-route-resumed.json); [ten-unit result](../../artifacts/movement-upgrade/10-unit-out-and-back.json); [CLI map result](../../artifacts/movement-upgrade/map-click-move.json); [GUI status](../../artifacts/movement-upgrade/gui-click-status.json); [usage and limits](../workflows/physical-waypoints.md#movement-modes-and-map-destinations). |
| Other native research | Ability/catalog/name, stats/XP, target/unit, buff and cost/cooldown/cast candidates and locating tools exist. | Field-specific partial readers/static findings and historical samples; not a fully qualified live combat/telemetry API. [Earlier discovery packages](discovery-roadmap-2026-11-06.md). |
| Casting diagnostics | Casting addon readout, ability selection, API checks, outcome recording and protected manual Cast/Stop controls exist, with historical dummy-test evidence. | **No working route-integrated combat system.** Manual addon controls and native ability catalogs do not establish external ability execution, defensive decisions or current physical-host combat acceptance. [Casting readout](../reference/casting-readout.md). |
| Level/XP research | Native player/target level branches and experience seed/value readers exist, including accumulated/needed XP and explicit unavailable states. | No demonstrated current physical kill-to-XP correlation or working leveling loop. Hostility, attacker/aggro and elite/rank classification are missing; a combat byte or target level is insufficient. [Player/target/experience findings](../reference/native-player-context-candidates.md). |

## Remaining work, ranked

**Reassessed after the completed movement milestone, November 14:** Combat and
survival are next. The first integrated outcome is one suitable encounter,
verified recovery and continuation of the saved route. Reuse the accepted
continuous helper; further movement polish and optional autorun come after this
unless an observed movement failure blocks it. Establish the actual current
build/learned actions for the first fight, then expand to the per-level plan.
A full future build planner must not delay the first useful defensive response.

The subsequently reported camera-shake defect was brought forward under that
failure-driven rule. Sparse travel steering and settled initial alignment now
have a complete live 72.802-unit courtyard loop with eight legs/corners, zero
moving A/D corrections and verified arrival/release/stationarity. Same-read
camera candidates and recorded frame sequences show steady straight-leg follow
in this case; broader camera smoothness remains unqualified. The combat and
survival ranking below resumes after this targeted movement correction.

Ranks 1–2 are now in implementation: source-verified survival assessment and the
local action handoff model have focused tests. Fresh composite and decoded
ReaderBridge packets supply scoped observations, including API-published Power;
they do not establish a complete threat model or engagement readiness. The next
useful gap is current learned abilities/bindings and verified action/readiness
feedback, alongside reliable survival observations and the live owner adapter.

The first working survival intake commands are:

```powershell
python scripts/survival_state.py --summary PATH_TO_COMPOSITE_SUMMARY
python scripts/readerbridge_v3.py --packet PATH_TO_RETAINED_PACKET
python scripts/capture_readerbridge_v3.py --expected-host AMD-DESKTOP --physical-pid PID --seed-index PATH_TO_CURRENT_EPOCH_SCOUT_INDEX --output NEW_DIRECTORY
```

The acquisition command reacquires packet addresses in a bounded scope from a
fresh same-process scout; a seed from another process epoch is refused. A live
pair matched two advancing packet generations to exact same-generation player
identity companions and exposed HP 18208/18208 and Power 100. Producer defaults,
changed-state qualification, learned abilities and action readiness remain gaps;
the result deliberately reports `ready: false`. The local action coordinator is
an offline-tested handoff component, not yet a live travel/combat runtime.

The next product outcome is a character that can judge encounters, win suitable
fights, gain useful experience and preserve its route. Avoiding a fight can be
the correct decision; a reactive fight loop alone cannot make an over-levelled
route safe. Combat prerequisites should deliver only the data/actions needed
for the first useful encounter, not wait for every stat,
ability, buff or cooldown to be discovered. Native research can proceed in
parallel without competing for the live reader or input owner. Useful scoped
candidate output remains acceptable for research; gameplay decisions need the
specific freshness/meaning and action feedback they depend on.

| Rank | Work | Current gap and useful completion point |
| --- | --- | --- |
| **1** | **Usable survival state and encounter assessment** | Establish fresh same-player alive/dead, HP/max-HP, required resources, combat state, level, target identity and action readiness for the first supported encounter. Reuse current readers; baseline candidate values need the independent meaning/change evidence required by decisions. Compare enemy level, known hostility/elite/group status, nearby danger and character readiness. Unknown critical danger is grounds to avoid/refuse engagement. Deliver only the data and bounded normal-input action feedback needed for the first suitable encounter; acquire additional fields as actual decisions require them. |
| **2** | **One shared local runtime and input owner** | Put route travel, combat, recovery and later progression behind one local coordinator and the existing exclusive action owner. Treat the continuous helper as a bounded clear-path travel actuator, not a second controller or a terrain planner. One STOP/safety latch must halt every mode and stay latched until explicit Resume/new run; no subsystem may silently clear it or advance another subsystem's checkpoint. |
| **3** | **One working defensive encounter and recovery** | Bind the actual current class/soul/role and learned abilities/ranks. Implement a small local conditional policy: emergency defense/heal or retreat, useful interrupt/setup, suitable damage and sustainable fallback. Respect target identity, range, resources, cooldown/GCD/cast/channel occupancy and verify outcomes. Survive and finish one suitable isolated encounter, recover to readiness, and stop/retreat when losing or evidence is unavailable. Use current learned actions; the full future build plan is rank 5. Tune useful damage, costs and downtime from observed results rather than requiring every mechanic before this works. |
| **4** | **Travel/combat/recovery handoff and continuation** | Interrupt an owned movement leg, verify key release and retain the pending waypoint before combat takes input. Avoid unsuitable fights using known traversable alternatives or halt when no safe option is known. After an ordinary supported encounter, automatically continue only after alive/out-of-combat, recovery, identity, freshness, path/context and budget checks pass. Death, failed recovery, unavailable critical state and operator STOP remain latched until explicit Resume/new run. Fights and later XP detours never advance a route checkpoint. |
| **5** | **Plan skills and build progression for the actual character** | Establish the current class/soul/role/build, learned abilities/ranks, unspent points and applicable prerequisites. Start with one solo-leveling/survival build and a per-level plan for skill/talent choices, passives, unlocks and training where applicable. Balance useful damage, sustain, defense and synergy; a future unlock is not currently usable. Detect level-up/build changes, reconcile the plan with actual learned state and refresh action choices. Applying a plan requires a supported, verified game interaction; proposing an allocation does not prove allocation automation exists. |
| **6** | **A bounded leveling loop with observed progress** | Select suitable reachable XP targets; fight, verify XP, recover and continue while ready and within the trip objective/limits. Detect level-up, reconcile skill/build progression and newly available abilities, refresh stats/resources and reassess suitable enemies. Do not assume every kill rewards XP or that accumulated XP is monotonic across a level-up. Track whole-cycle progress and downtime rather than kills or peak damage alone. |
| **7** | **Prove useful longer travel and progression** | Use a recorded known-traversable 50–100-unit route with corners: record/save/load, reject an unsuitable encounter, win a suitable one using the build's action policy, observe XP, recover and Resume. Success means arriving alive with valid progress and released input, with actual XP reported separately from level-up. Include level-up/build reconciliation when one occurs. Retain STOP-mid-leg, Reverse and same-build restart/Resume as useful. Fix real failures, then expand; full 1,000-unit capacity is not a mandatory first trial. |
| **8** | **Make route location and height context dependable** | Zone tags and measured/estimated height cues already work. Cover actual floors/elevation and zone/world/instance changes; preserve measured corners and refuse inappropriate route/Resume. Move a specific context check earlier when an XP detour requires it. Combat/level advantage does not establish walkability. |
| **9** | **Broaden retrieval and expose useful data to consumers** | Extend beyond the survival/build/progression essentials with coherent nearby-unit detail, more stats and ability/cooldown/cast/buff outputs, retaining consistent source/time/identity/availability contracts. Reuse physical commands, the composite reader, catalog and exports. Prove useful requests before adding a service/SDK/framework. |
| **10** | **Finish physical-host addon reference acceptance where useful** | Establish the loaded RR2R1 producer, nonce/session binding and advancing same-player observations when needed as independent reference/fallback. Disk hashes and old lab success are insufficient. Move this earlier for concrete build/combat/XP data; native work need not wait for unrelated addon completion. |

For ranks 1–7, current input/health-change deferrals and action authority must be
resolved for the specific live experiment before it runs. The roadmap correction
does not itself initiate an attack, health-change test or uncontrolled run.

## Autonomous runtime and compute requirements

Use a small local state machine with conditional priorities/scoring over the
existing readers, build profiles and one input owner. Each cycle acquires or
updates the needed state, checks the objective and threats, selects a legal
action, executes it, verifies the result and updates the next decision. Movement,
combat and recovery decisions normally belong to this runtime. The temporary
AI-assisted mode below can bridge behavior it cannot yet handle effectively.

Cache build plans and stable mechanics; refresh them on relevant changes.
Recompute choices when observations, readiness or objectives change, using
bounded local polling/timers for time-dependent state. Separate fast combat
reactions from slower route/build planning so unchanged data does not trigger
expensive work. Begin with explicit local rules and measured action values;
bounded look-ahead is useful only when it improves actual decisions. A generic
agent framework or online model training is not a prerequisite.

Developers can use AI for research, code, offline log analysis and policy tuning.
Use compact summaries for assistance when sufficient; direct ChatGPT control is
also valid scaffolding when needed. A gap in local decisions can hand control to
AI after the current action releases and its state/checkpoint are retained; the
two controllers must not act concurrently. AI uses fresh observations and the
existing authorized controls, then can return ownership once local operation is
ready. Missing telemetry needed by both controllers remains a real blocker;
AI assistance must not invent it or bypass its checks.

Choose AI assistance when its practical benefit exceeds the extra latency,
compute/token cost and development effort of alternatives. Do not insist on
finishing an entire local subsystem before a useful assisted experiment. Record
the missing local capability and useful outcomes concisely; implement repeatable
local policies for recurring cases rather than requiring the same model work
indefinitely. Measure decision latency, CPU/memory/read overhead, model calls/
tokens, intervention count and gameplay outcomes. Mature routine local action
selection targets zero model calls/operator decisions; incomplete cases may
legitimately use AI until a local implementation is more beneficial.

Optimize actions for the configured survival/progression/travel objective using
reliable available data. Validate improvements against whole-cycle results;
"optimal" is the design aim under that model and constraints, not a claim of a
globally proven perfect policy. Revalidate after level/build changes locally.

Keep the current Waypoints explicit-Resume tool separate from future autonomous
continuation semantics. Normal completion of a fight and recovery need not ask
the operator to resume each time. Operator STOP and safety latches always take
precedence, remain latched, and require explicit Resume/new run after fresh
admission. Supervised development trials can test the automated runtime without
the supervisor making its routine decisions. None of this asserts that the
autonomous runtime or its combat/progression features is implemented today.

## Skill progression and combat decision requirements

These are required parts of ranks 3, 5 and 6, not delivered capabilities. Implement the
first useful character/build profile with existing readers and input controls;
do not wait for a universal simulator or an AI training system.

**A shared character/ability model.** Bind the active class/souls/role, level,
learned ability IDs/ranks, relevant passive choices, stats and resources to the
actual character. Separate future unlocks, definitions and cached catalog entries
from learned usable abilities. Record prerequisites, cost/resource generation,
cast/channel time, GCD/shared cooldown, remaining cooldown/charges, range/target
rules, damage/healing/effects and important combinations when available. Unknown
mechanics remain unknown; tooltip costs or raw native records do not establish
the current player's effective values or a command for learning/spending points.

**A per-level build plan.** Choose skills/points in a valid prerequisite order
for the solo-travel/leveling goal. Consider damage, survivability, resource
efficiency, recovery and useful ability combinations; a passive improvement can
be more valuable than another attack. Keep planned versus actually applied and
learned state separate. On level-up, inspect actual point/unlock/training changes,
reconcile the plan and rebind any action mapping before using a new ability.
Never assume a rank or skill was learned from the intended plan alone. A build
change invalidates decisions based on its old ability/cost/cooldown profile.

**Conditional action priorities.** First reject invalid targets/actions and
respect STOP, identity, availability, freshness and input ownership. Select among
currently legal actions according to the situation: emergency defense/heal or
retreat; a useful interrupt; setup/buff/debuff where its benefit will apply;
efficient damage; a finisher; then sustainable fallback or a justified wait.
Only enable action types verified for the chosen build. Re-evaluate after each
confirmed action/state change, including a proc or defensive trigger during a
cast. Respect cast/channel/GCD occupancy; interrupt the player's own action only
under an explicit useful emergency/interrupt policy.

**Damage, cooldowns and resource trade-offs.** Compare useful expected effects
over the relevant time horizon, including remaining enemy health, cast/channel
and GCD occupancy, cooldown availability, resource costs/generation and the
value of preserving a defensive resource. Account for damage-over-time duration
before target death, refresh/clipping, buff/debuff combinations, overkill and
observed misses/resistance where measurable. A higher total-damage spell may
lose value if it delays a better action, exhausts resources or increases the
recovery needed before the next fight. Area damage needs an explicit suitable
multi-target policy; it must not silently pull additional enemies. A cooldown
being ready alone does not mean spending it now is best.

**Measure whole-cycle results.** Retain action selection/rejection reasons,
expected versus observed exact-target damage/healing, time to kill, resource
spent/generated, health loss, useful cooldown uptime, failed actions and
recovery time. Separate exact-target results from collateral damage. Assess
damage per effective action time and resource alongside **survival and XP per
total elapsed travel + combat + recovery time**. Report deaths/failures and
time lost rather than hiding them behind good combat-only DPS. Keep sample size,
target/build context and uncertainty; a single critical hit is not expected
damage. Start with an explicit build priority profile, tune from relevant
observations, and avoid unsafe trial actions merely to gather optimization data.

**A useful first demonstration.** For one actual character/build, show the next
planned skill choices, the current learned ability set and why the policy chose
each action. Demonstrate a suitable encounter and recovery, report its XP and
elapsed cost, and reconcile skill/ability priorities after an actual level-up
when available. This verifies a useful profile; it does not claim the globally
optimal build/rotation or reliable behavior across every class and enemy.

## Conditional work and deferred scope

- **Reliability and performance:** fix a concrete failure or measured bottleneck
  when encountered. Large-route display work is implemented; longer live sessions,
  camera/window changes and mixed-DPI cases remain partially untested. These are
  targeted follow-ups, not a compulsory stress/review program before every result.
- **Same-build restart durability:** retain/reacquire locating recipes as each
  useful field is delivered. Waypoints restart evidence does not qualify all
  stats/target/resource fields. Reuse normal game restarts for additional evidence
  instead of repeating completed baselines without a reason.
- **Patch/update recovery:** explicitly deferred. Exact-build checks continue;
  another executable hash requires new evidence.
- **Terrain/navmesh, obstacle avoidance and automatic stuck detours:** not
  implemented. Longer routes still require a known clear taught path. Dedicated
  terrain routing, indefinite patrol and quest automation remain future work.
  Combat, level-appropriate encounters and bounded XP/level progression during
  travel are ranked above. Leveling is part of the goal; a general engine for
  every class/build, automatic gear allocation, quests or indefinite
  unattended farming is not the first progression milestone. Threat-based
  avoidance must use known traversable routes until useful path data exists.
- **Skill/build progression:** explicitly included above. Automated point
  spending/training must follow an established valid plan and supported game
  interactions; this roadmap has not spent points, changed a build or claimed
  that an allocation mechanism is already implemented.
- **VMware labs:** retired as active RR2 targets. Their code/evidence remains
  historical; this roadmap does not restart them or authorize another physical
  host. A session operates only its verified local host.
- **SQLite, broad refactoring, more dashboards, extra process/frameworks and
  cosmetic polish:** optional only when a concrete use or failure justifies them.

## Keeping this roadmap current

**Re-evaluate priorities after every major milestone**, and earlier when new
evidence or a material blocker changes the best next step. This ranked list is
an adaptive plan, not a fixed sequence to follow despite changing conditions.

At each such checkpoint, mark what actually finished and reassess the remaining
outcomes by usefulness, dependencies, feasibility, effort and newly exposed gaps.
Keep the order when it still makes sense; reorder when a different outcome now
offers better progress. A completed milestone may unlock a previously blocked
path or make an earlier proposal unnecessary.

For a blocked item, identify the concrete missing dependency and a productive
next step. Use an existing alternative or beneficial temporary AI scaffolding
where applicable. If no practical route through the blocker is available, move
the highest-value independent work forward. Keep the blocked item visible with
its reason and an unblock condition; revisit when new evidence, tools or a
completed dependency changes that condition. Do not stall unrelated work or
repeat the same unsuccessful approach without a new hypothesis.

Reprioritize autonomously within the authorized scope. Record a short reason
for material ranking changes here and name the next useful outcome. This is a
brief milestone decision, not a new process/framework, mandatory broad test
sweep or approval round for every edit. A workaround must preserve existing
host/action authority, input ownership, STOP and evidence/qualification limits.

Update this document when a useful capability ships or its remaining gap changes.
Keep detailed receipts in [status](../status.md) and the owning workflow/reference.
Use **implemented**, **observed live in stated cases**, **candidate/partial**, and
**deferred** accurately. A ranked item is a recommendation; completed work and
user scope decisions take precedence over this list.

The detailed [Waypoints roadmap](five-hour-recorded-routes-2026-11-12.md) owns that
app's capability inventory. The [November 6 discovery backlog](discovery-roadmap-2026-11-06.md)
retains field-specific research leads; its multi-lab dispatch order is historical.

<details>
<summary>Historical foundation plan and acceptance record (October–November 6)</summary>

The original implementation plan is preserved below for evidence and old links.
Its priority lists, target allocations and pending descriptions are historical;
the ranked roadmap above governs current planning.

Status: prioritized plan adopted for the authorized foundation; later increments
remain subject to their evidence and safety gates.

This roadmap grows a hybrid Lua-addon/.NET product through measurable vertical
slices. Each external operation remains a standalone process: CLI for offline
work or the isolated Windows Live executable for live acquisition. Each
increment should leave a useful artifact and a compact handoff so a
later model does not need to rediscover the reasoning.

**November 6 parallel development priorities:** Use the [current discovery roadmap](discovery-roadmap-2026-11-06.md)
for present-build research priorities and three-target work allocation. The
October qualification results below retain their original build and evidence
scope; they do not qualify the current executable automatically. Existing
authorization and restart/update boundaries still apply.

## Current priority override — October 25, 2026

Joey prioritizes durable collection across **fully exiting RIFT and launching it
again**. Confirm the old process has ended, acquire the new process/start identity,
and resolve the preserved build-specific recipe afresh. Addon reload, character
relog or reader restart alone is insufficient; VM/host restarts are separate.

**Patch/update recovery is deferred until Joey explicitly resumes it.** Later
update-recovery references remain future work and do not select the next task.
Do not weaken exact-build guards: changed executable SHA still fails closed.
The [accepted policy](../decisions/0008-full-game-restart-durability.md) controls
this priority. The [October 25 XYZ trial](../validation/native-xyz-restart-2026-10-25.md)
establishes one observed normal full game exit/relaunch; it does not qualify all
future restarts or other fields.

## Remaining practical goals — refreshed October 25, 2026

The original [Start / Read / Stop milestone](position-panel-roadmap.md) is
complete, including corrected same-build full-game exit/relaunch. Native/Lua
displacement also passed through both manual movement and the
[guarded helper](../validation/xyz-guarded-displacement-2026-10-25.md).
Do not repeat these completed milestones as though they were still missing.
Goals 1–2 have since passed live; see the
[implementation evidence](../validation/xyz-goals-implementation-2026-10-25.md).
Joey deferred the health-change test on October 25. Continue resource work while
health meaning/locator/restart qualification remains unfinished. The roadmap is:

1. **Make the proven XYZ run easy to repeat.** Consolidate the working CLI
   collection and guarded-helper steps into a small reusable entry point. Reuse
   the installed reader and existing tools; authenticate once per run, capture
   before, apply one reviewed bounded pulse, capture after, compare, export and
   clean up. Done when a fresh run works without editing dated artifact scripts
   or asking Joey to press movement keys. Keep credentials out of logs; persistent
   credential caching was subsequently authorized and demonstrated without a
   prompt on run 04.
2. **Record XYZ as durable field knowledge.** Add a real catalog definition and
   scoped assessments linking the locating recipe, Lua/native comparison,
   movement and full-game restart evidence. Preserve startup failures and the
   corrected result. Done when the existing catalog command rebuilds a clear
   exact-build qualification report without AI interpreting scattered notes.
   State untested claims explicitly; do not claim patch survival.
3. **Health — changed-state test deferred.** Use Lua health and
   maximum health as the reference, gather controlled changed-state observations,
   and inspect only relevant native candidates. Done when actual changes
   distinguish the field from constant values and cached copies, a reusable
   locating recipe is retained, and normal full-game exit/relaunch reacquires it.
   Capture failures instead of repeatedly widening unchanged searches.
4. **Repeat for the player's resource/power field — active.** Lua identified
   Warrior / tank and Power; tooltips corroborated the resource name. A
   [clean Light's Balm test](../validation/power-test-2026-10-25.md) demonstrated
   consumption/recovery and one responding memory candidate. Establish its
   owner/provenance and reusable locator next; it may be an addon copy.
   Compare the native changes with Lua. Done when meaning, units,
   availability, locator, invalidation conditions and same-build restart evidence
   are recorded. Historical `power=100` matches are candidates, not completion.

**Confidence follow-up, not a blocker for the completed XYZ milestone:** collect
another full-game exit/relaunch during normal use, including absent-process
handling, fresh PID/start identity, fresh coordinates and old-process rejection.
Do not require endless repeat trials before moving to the next field.

**Deferred or conditional:** patch/update recovery; VM/host reboot, crash and
snapshot-restore qualification; precise velocity/input timing; other fields such
as casting/cooldowns/abilities after health/resource; SQLite only after a
measured need. Guest credential caching is already authorized and verified.
The optional new Courier need not
be guest-deployed while the proven VMware CLI transfer route suffices. Dedicated
navigation/combat automation remains outside this project. Direct ChatGPT
Computer Use stays deferred; separately authorized guarded helpers remain usable.

The numbered sections below retain the original implementation history and
acceptance criteria; this refreshed list determines the next practical work.

## 0. Reproducible repository foundation

Deliver the pinned .NET 10 solution, five production modules, two test projects,
central build and package settings, lock files, repository-local Git identity,
and one validation script.

Acceptance evidence:

- the locked restore, Release build, tests, formatting, module-boundary checks,
  link checks, and demo smoke test complete successfully;
- Git reports only intended files;
- documentation distinguishes Joey's direction from implementer-selected stack.

## 1. Deterministic offline analysis slice

Deliver strict version-1 configuration and manifest parsing, bounded capture
size and line length, same-handle SHA-256 verification and streaming JSON Lines
input, derived-motion analysis, optional atomic no-overwrite JSON output,
`analyze`, `validate-capture`, and help. Track a small synthetic dataset whose
illustrative status is explicit.

Acceptance evidence:

- repeated analysis of identical inputs produces equivalent content;
- invalid versions, missing/unknown/duplicate properties, identity, sequence,
  timestamps, values, size, line length, count, and digest fail with useful
  diagnostics;
- gap limits and yaw wrapping have focused tests;
- no V1 or live-game conclusion is claimed.

## 2. Hybrid addon contract and producer foundation

Implement the required Lua producer and C# boundary from
[ADR 0002](../decisions/0002-hybrid-addon-and-reader.md). Start with one small
typed reference observation, capability states, producer/schema versions, and
reload/session/freshness rules. Preserve separate API/native/derived provenance.

Acceptance evidence:

- actual Lua output and C# decoding agree on shared valid/invalid fixtures;
- zero/false, missing/invalid fields, unsupported versions, stale observations,
  sequence reset, conflicting copies, and size limits have meaningful checks;
- addon work is bounded; heavy processing and retention remain external;
- transport capabilities are verified rather than assumed from general Lua;
- live deployment/readiness is reported separately from mocked producer tests.

The minimal producer, strict decoder, and shared offline contract tests are now
implemented; see [ADR 0003](../decisions/0003-addon-observation-contract.md).
The bare producer passed one identified actual-client source gate after
`/reloadui`, with advancing RR2A1 sequence and clock. This establishes that
package/API path in that session only. The nonce-bound RR2L1 increment selected
by [ADR 0004](../decisions/0004-nonce-bound-addon-transport.md) is implemented.
The fifth production project is a Windows-only Live adapter and composition
executable referencing Domain, Application, and Infrastructure.

The full gate passed 173 C# tests, 108 Lua assertions, 11 RR2A1 plus 11 RR2L1
actual-Lua-to-C# cases, 9 Python host-gate tests, and a zero-warning Release
build. One RIFT-Lab runtime gate established advancement, stale rejection,
reload invalidation, reader restart with a new nonce, and rebinding in the same
RIFT process. See the
[live record](../validation/live-transport-2026-10-18.md). A later
[recovery gate](../validation/restart-recovery-2026-10-18.md) exercised the final
executable through an ordinary RIFT process restart and a graceful VM power
cycle with manual relaunch and nonce rebinding. Hard-crash, VM snapshot restore,
update recovery, loaded-module verification, and production remote consumption
remain separate qualifications. Existing saved replay can proceed independently.

## 3. Reproduce one saved evidence conclusion

Choose and identify an immutable V1 evidence bundle, starting with the proposed
wall-motion case if it remains the best fixed input. Implement the smallest
independent importer or replay adapter needed to express that evidence through
V2 contracts. Do not import V1 application architecture.

Acceptance evidence:

- exact source path, size, hash, build/session applicability, and known
  limitations are recorded;
- the procedure is invokable without AI interpretation and gives a compact,
  repeatable result;
- free-travel plausibility and decisive wall disagreement are both represented;
- elapsed local work, output size, and remaining manual/AI steps are measured.

This increment establishes reproducibility of one saved conclusion. It does not
qualify a native velocity field.

Completed for the selected batch-6 evidence. The tracked replay manifest pins a
100,187,956-byte, 9,598-sample V1 capture and three trial artifacts. The V2
command independently reproduces one plausible free-travel comparison and two
decisive wall disagreements; see the
[validation record](../validation/wall-replay-2026-10-19.md). The first wall
contact, V1 native-field scan, current-build behavior, and update
recovery remain outside this fixed-input increment.

## 4. Read-only Windows capture adapter

Develop a bounded V2 process scanner and read-only capture adapter independently
behind the external I/O boundary. Preserve executable/build identity, process
and session identity, capture timing, failures, and exact output identity. The
unchanged V1 receiver/console may be reused operationally in the controlled lab,
but its application architecture and claims do not become V2 contracts. No
generic scanner offset or native-field readiness is established yet.

Acceptance evidence:

- offline tests cover platform-independent contracts;
- a controlled live session records provenance and failure behavior;
- no write, input, debugger, or automation capability is introduced;
- restart reacquisition is measured separately from update recovery.

Completed for bounded raw acquisition. The native adapter preserves exact
request, tool, process/build, timing, bytes, and failure provenance behind an
Application-owned port. The [native runtime record](../validation/native-capture-2026-10-19.md)
qualifies the final bundle in two process epochs: ordinary capture, unavailable
memory, wrong identity, no overwrite, and rejection of the actual old request
after a RIFT restart. Reacquisition requires a new explicit request; no native
field meaning or stable locator is promoted.

The earlier addon gate separately qualified ordinary game-process reacquisition
by a surviving reader and a graceful VM power cycle with manual reader/game
relaunch. Those results identify their own executable. The native bundle has
not passed a VM-restart gate. Automatic startup, crash, snapshot restore, and
update recovery remain unqualified. Continue with step 5's durable catalog.

Native identity, platform I/O, timing, and concurrency require strong-model
implementation or review.

## 5. Durable field catalog and qualification workflow

Represent a field as meaning, units, locator method, applicability, validation
evidence, confidence, and invalidation conditions. Link observations and results
by content, build, and session identity. Generate a compact qualification report
that another program can consume without interpreting raw notes.

Acceptance evidence:

- a saved address alone cannot be promoted as durable knowledge;
- contradictory and expired evidence remains visible;
- restart and update claims require their own recorded validation;
- the catalog can be rebuilt or checked from retained artifacts.

Schema and semantic changes require strong review. Routine entries with complete
provenance can use a cheaper model plus mechanical validation.

Implemented as an offline file-based catalog under
[ADR 0005](../decisions/0005-durable-field-catalog.md). `qualify-fields` verifies
content-pinned assessments/artifacts and evaluates all four claims at an exact
build/session/time. Definition changes invalidate prior assessments; contrary,
expired, and out-of-scope records remain visible. The tracked synthetic bundle
rebuilds the same report and does not promote any real RIFT field. See the
[workflow](../reference/field-catalog.md) and
[validation record](../validation/field-catalog-2026-10-19.md).

## 6. Guarded experiment support

Add explicit plans and safety gates for controlled movement and turning tests
that collect evidence for RiftReader2. Keep dedicated navigation, combat, and
player automation in a future program.

Acceptance evidence:

- every action is bounded, attributable to an experiment, and stoppable;
- stimuli and samples share a usable time basis with recorded uncertainty;
- runs cannot silently target an unverified build or session;
- analysis reports gaps and alignment limitations.

Experiment control, timing, and live integration require strong-model design and
review.

Implemented as a small Python runner plus adapter to the unchanged original
lab console/readback tools. It performs one 20–250 ms reviewed pulse, retains
before/after evidence, and supports persistent stop and release recovery.
The [live record](../validation/experiments-2026-10-19.md) covers a RIFT pulse,
new API readback, identity/duplicate rejection, and stop-before-input. Timing
alignment remains coarse with unmeasured clock skew; mid-hold stop and crash
recovery have not been qualified in RIFT. See [usage](../reference/guarded-experiments.md).

## 6a. Read-only memory discovery

Joey additionally authorized stronger memory reading and RVA pointer discovery
on 2026-10-19, for investigating navigation, combat, casting, stats, and abilities.
Keep these as discovery features in the existing modules. Provide bounded
memory maps/snapshots, typed value/pattern searches, snapshot comparisons,
reverse pointer-chain candidates, and exact-target live resolution. Preserve
raw failures, coverage limits, build/session identity, and candidate semantics.

Implemented without new projects or dependencies. See
[commands and limits](../reference/memory-discovery.md) and the
[runtime record](../validation/memory-discovery-2026-10-19.md). Real game fields
still need API comparison, semantic experiments, and separate restart/update
evidence before catalog qualification.

## 7. Indexing only when measured

Continue with versioned files until a retained-data query, scale, integrity, or
concurrency requirement is measured. If proven, add SQLite as an Infrastructure
index over durable artifacts, with rebuild and migration behavior specified
before adoption.

Acceptance evidence:

- the motivating workload and current limitation are measured;
- source artifacts remain identifiable and recoverable;
- migrations, backup/rebuild, and compatibility are tested;
- Domain and Application remain storage-independent.

## 8. Discovery compilation, query and export

Joey authorized an optimal plan and its execution on October 24, 2026.
The [finalized discovery roadmap](discovery-compilation-roadmap.md) owns D0–D4
milestones: strict hash-pinned source manifests, non-promoting typed/native and
catalog importers, deterministic filtering/sorting and JSON/CSV/JSONL export,
then a standalone offline browser explorer with downloads.

Reuse the existing .NET projects and field-catalog semantics. Do not touch
V16/V17 VM console ownership or add a service/database. Retain the complete
rebuildable manifest and original evidence; exports are scoped views, not
semantic qualifications. The [usage contract](../reference/discovery-compilation.md)
specifies bounds, exact CLI options and statuses. Automatic indexing,
cross-build semantic merge and live data feeds remain separately gated.

## Handoff size and model allocation

Split work at the increments above, then subdivide into one contract or adapter
change per task. A good handoff names the exact inputs, output, invariants, file
scope, and command that proves completion.

Use cheaper models for routine documentation, unchanged-schema configuration,
mechanical fixture maintenance, formatting, and narrow tests after behavior is
specified. Require stronger reasoning or review for evidence semantics,
identity/provenance, schema compatibility, I/O durability, streaming or
concurrency, native access, unsafe code, module boundaries, and experiment
controls. Always prefer a local deterministic check over spending tokens to
re-evaluate the same artifact.

</details>
