# RR2 roadmap

Updated **November 14, 2026 (America/New_York)** from checkout
`C:\work\riftreader2`, branch `codex/modular-foundation`, implementation through
`6fe3f29` (longer routes in `b91e2b4`, composite-source guard in `570414c`).
Review host: **AMD-DESKTOP**. This is the current overall roadmap;
older discovery dispatch plans and the foundation history below are references.
Existing uncommitted native research is work in progress, not a delivered result.

The latest native integrity fix verifies each vitals burst's source digest,
build, process epoch, self key and sample count before composite publication.
Its focused checks and retained-source replay passed; it adds no new live field
semantics or game observation. See the Nov 13 23:54 entry in the
[RRE intake record](../workflows/rre-discovery-intake.md).

RR2's purpose remains useful RIFT discovery and repeatable retrieval for other
programs. Waypoints is a working consumer. **Joey's November 14 correction:
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
| Longer routes | Shared 1,000-unit / 500-waypoint envelope, 30,000 recording samples, 30-minute trip budget, larger CLI transport, preview Fit to 1,500 units and bounded display annotations. | **Implemented and offline verified**, including simulated 1,000-unit/500-point execution and long STOP/Resume; no long-route live trip was performed. Existing files/checkpoints are compatible. [Longer routes](../workflows/physical-waypoints.md#longer-routes). |
| Other native research | Ability/catalog/name, stats/XP, target/unit, buff and cost/cooldown/cast candidates and locating tools exist. | Field-specific partial readers/static findings and historical samples; not a fully qualified live combat/telemetry API. [Earlier discovery packages](discovery-roadmap-2026-11-06.md). |
| Casting diagnostics | Casting addon readout, ability selection, API checks, outcome recording and protected manual Cast/Stop controls exist, with historical dummy-test evidence. | **No working route-integrated combat system.** Manual addon controls and native ability catalogs do not establish external ability execution, defensive decisions or current physical-host combat acceptance. [Casting readout](../reference/casting-readout.md). |
| Level/XP research | Native player/target level branches and experience seed/value readers exist, including accumulated/needed XP and explicit unavailable states. | No demonstrated current physical kill-to-XP correlation or working leveling loop. Hostility, attacker/aggro and elite/rank classification are missing; a combat byte or target level is insufficient. [Player/target/experience findings](../reference/native-player-context-candidates.md). |

## Remaining work, ranked

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
| **1** | **Combat essentials and encounter assessment** | Reuse player/vitals, target/unit, ability and casting work for alive/dead state, usable HP/resource/combat state, player/enemy levels, relevant enemy identity/health/range and a small ability set. Before voluntarily engaging, consider level difference, ordinary/elite/group status where known, nearby additional enemies, current readiness and observed fight outcomes. Initially prefer isolated ordinary enemies near the player's level; avoid stronger, elite, grouped or unknown-risk targets. Choose a safer known route or appropriate leveling area when needed. Establish a bounded normal-input action path with actual target/cast feedback. Missing/stale/unqualified decision data is not permission to assume a fight is safe. |
| **2** | **A small working combat and recovery loop** | Start with the current character/build and a limited attack/defensive/recovery set against one suitable enemy. Support deliberate engagement for XP as well as defense when attacked. Observe outcomes, health loss, resource/cooldown state, target death and disengagement. Stop blind retries on wrong target, range/facing/LOS failure or no progress. Define bounded retreat/help behavior for a losing fight. Useful completion is winning and recovering from one real suitable encounter, not a rotation engine for every class. |
| **3** | **A bounded leveling loop with observed progress** | Select suitable reachable XP targets; fight, verify any XP gain, recover, then choose another target only while health/resource/readiness and the trip's limits permit. Track player level and XP-to-next-level using valid field semantics; do not assume every kill rewards XP or that XP remains monotonic across a level-up. Detect level-up, refresh stats/resources/available ability state and reassess suitable enemies. Use a travel objective, XP/level objective, detour/time budget or explicit stop condition; do not turn a trip into indefinite grinding. |
| **4** | **Connect travel, threat avoidance, leveling and Resume** | Share one input owner across movement, combat and recovery. Preserve the genuine unfinished route checkpoint while fighting or taking a bounded XP detour. Skipping dangerous encounters requires a known traversable alternative; no planner/escape path is assumed to exist. Return from a detour to a valid route admission point through known traversable ground rather than loosening Resume checks or advancing the cursor for kills. After recovery, recheck alive/out-of-combat state, health/resource and route context, then offer explicit Resume. STOP overrides every mode; death or failed recovery stops without automatic retrials. |
| **5** | **Prove useful longer travel and progression** | Use a recorded known-traversable 50–100-unit route with corners: record/save/load, travel, reject a clearly unsuitable encounter, win a suitable one, observe XP, recover and Resume. Success means arriving alive with valid progress and released input, with actual XP reported separately from any level-up. Retain STOP-mid-leg, Reverse and same-build restart/Resume cases as useful. Fix actual failures, then extend distance/complexity; 1,000 units is capacity, not a mandatory first trial. Clear-ground distance-only tests do not establish safe leveling travel. |
| **6** | **Make route location and height context dependable** | Zone tags and measured/estimated height cues already work. Cover actual floors/elevation and zone/world/instance changes; preserve measured path corners and refuse inappropriate route/Resume. Move a specific context check earlier if an XP detour requires it. Combat/level advantage does not establish walkability or obstacle clearance. |
| **7** | **Broaden retrieval and expose useful data to consumers** | Extend beyond the survival/progression essentials with coherent nearby-unit detail, additional stats, ability costs, cooldown/cast/buff outputs and consistent source/time/identity/availability contracts. Reuse physical commands, the composite reader, catalog and exports. Prove useful consumer requests before adding a service/SDK/framework. |
| **8** | **Finish physical-host addon reference acceptance where useful** | Establish the loaded RR2R1 producer, nonce/session binding and advancing same-player observations when needed as independent reference/fallback. Disk hashes and old lab success are insufficient. Move this earlier for a concrete combat/XP-data need; native work need not wait for unrelated addon completion. |

For ranks 1–5, current input/health-change deferrals and action authority must be
resolved for the specific live experiment before it runs. The roadmap correction
does not itself initiate an attack, health-change test or uncontrolled run.

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
  every class/build, automatic build/gear allocation, quests or indefinite
  unattended farming is not the first progression milestone. Threat-based
  avoidance must use known traversable routes until useful path data exists.
- **VMware labs:** retired as active RR2 targets. Their code/evidence remains
  historical; this roadmap does not restart them or authorize another physical
  host. A session operates only its verified local host.
- **SQLite, broad refactoring, more dashboards, extra process/frameworks and
  cosmetic polish:** optional only when a concrete use or failure justifies them.

## Keeping this roadmap current

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
