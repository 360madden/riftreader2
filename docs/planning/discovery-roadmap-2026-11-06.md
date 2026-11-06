# Parallel discovery backlog — November 6, 2026

Deliver useful native readers now; refine semantics, continuity and restart evidence
as separate work. This backlog replaces the sequential discovery plan. Packages
can finish independently; an unavailable live reference must not idle implementation
or static research. Planning describes intended work, not demonstrated capability
or additional live-action authority.

## Known baseline

Exact-build research applies to SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Reacquire actual build and PID/start identity for each live operation.

| Area | Useful starting result | Remaining uncertainty |
| --- | --- | --- |
| XYZ | Both labs re-resolved self-key/entity/component; Lab2 Nov 6 sampled 30/30 unchanged values over 61.08 s | Same-unit changed-state meaning, passive freshness, continuity and restart |
| HP / Energy | Type-checked Lab2 raw records; ordinary HP math and offline Energy 100/100 candidate | Synchronized correlation, changed values, passive freshness and restart; Mana kind3 type unresolved |
| Ability / cooldown / cast | Static cost, cooldown lookup and unit-key cast paths mapped | Live ownership, IDs, timer meanings and changed-state correspondence |
| Orientation | Player-owned matrix/upstream/cache candidates traced | Stationary body-facing meaning, freshness and angular convention |

Old SHA `7C356C9D...` XYZ/Warrior Power changed-state and one full-game restart
results remain historical; reuse methods, not offsets or qualification.
`Inspect.Unit.Detail` calls the refresh path for cached XYZ at component `+0x48`
through RVA `0x6996C0`; API-active agreement cannot prove passive native freshness.
A labeled API-dependent candidate can still be useful. Never call game getters,
initializers or refcount-changing functions to obtain a supposedly passive read.

Starting evidence: [status](../status.md), [Nov 6 sampler](../validation/native-current-sampler-2026-11-06.md),
[coordinate map](../reference/native-current-coordinate-code-map.md),
[HP/resource/ability map](../reference/native-current-client-code-map.md).

## Small architecture, concurrent delivery

Keep existing Domain/Application/Infrastructure/Live/CLI boundaries and versioned
reader/catalog contracts. Share only the proven exact-build unit lookup, memory
session and identity checks; keep XYZ, health/resource, ability, cooldown and cast
interpretation in separately owned modules. Do not introduce a universal discovery
framework, scheduler or mandatory new Lua contract. New shared extraction needs a
short early design check so concurrent workers do not fork ownership logic.

Every output identifies source, exact build/process epoch, acquisition time,
qualification and unavailable reason using existing sample/JSON/catalog patterns.
Raw candidate output is a supported research deliverable before full semantics;
consumers choose the qualifications they require. Memory, addon and derived values
remain distinguishable. An advancing host counter or repeated number is not proof
that the game source advanced. Promote meaning, freshness and restart separately.

Default allocation: root plus up to six workers: five implementation/research
workers and one elevated reviewer. Root integrates, reviews routine changes and
alone operates live controls. Sol/Terra low/medium fit bounded implementation;
Astra high handles early consequential architecture/ownership decisions and focused
review of substantive risky batches. Routine patches use focused checks and root
review; do not require an expensive review cycle for every patch. Keep independent
workers moving during review; escalate repeated ambiguity or rework.

## First dispatch: five independent packages

Start P1–P5 together with explicit file ownership. Root checks eligible live targets
and reference readiness concurrently; the reviewer first checks shared lookup versus
field boundaries and candidate output compatibility. Agree any necessary shared-file
edit once, then let workers deliver independently. Root owns shared registration,
command runners and shared lookup edits; workers own separate field modules and
fixtures, and consult the common probe read-only. Build/publish and heavy PE/Ghidra
work share host resources and are scheduled one at a time, not all research work.

### P1 — Ship useful XYZ candidate consumption

- **Own/start:** `src/RiftReader2.Live/CurrentBuildPositionSampleCommand.cs`,
  `scripts/sample_current_native_xyz.py`; `sample-current-position` already works.
- **Deliver:** improve the smallest demonstrated consumer/sampling gap; expose the
  existing candidate values with honest timing, owner and unavailable status. Reuse
  existing output before inventing another interface; do not claim a stream yet.
- **Done:** focused command/host checks cover valid reads, owner/epoch loss and
  timing; retained sample replays cleanly. No independent Lua prerequisite.
- **Dependencies/fallback:** none for candidate work; replay retained captures if
  live acquisition is blocked. If existing output meets the consumer need, keep it,
  report the verified invocation and move the worker to P6/P7; do not invent a gap. Semantic/live comparison is P7, continuity is P9.

### P2 — HP/Energy candidate reader

- **Own/start:** new field-specific reader beside the existing Live readers;
  `scripts/probe_native_unit_manager.py`, `scripts/reread_current_native_hp.py`,
  `scripts/scout_current_native_health.py` and the client code map supply lookup/type/math evidence.
- **Deliver:** bounded read-only candidate HP and Energy inputs/calculations with
  type/owner/revision checks and explicit unavailable outcomes. Keep Mana unresolved
  until its applicable typed owner is traced; do not generalize Energy to all power.
- **Done:** retained typed records reproduce expected arithmetic; mismatched type,
  changed owner and inconsistent mutable inputs fail explicitly in focused tests.
- **Dependencies/fallback:** none on XYZ qualification or Lua. Use retained records
  for implementation; fresh baseline correlation can follow through P7.

### P3 — Ability ownership and costs

- **Own/start:** ability section/findings in the client code map and an isolated
  ability candidate module when justified; trace existing cost-builder/context and
  cost-child-vector paths rather than broad numeric scans.
- **Deliver:** one bounded player/context-to-ability ID/cost locating recipe, with
  enough retained evidence for a passive reader or a precise missing owner edge.
- **Done:** distinguish live player records from templates; match IDs/cost inputs
  independently where available. Static-only findings remain labeled static.
- **Dependencies/fallback:** none on P1/P2; finish source/type/writer evidence if
  live ownership cannot yet be observed. Root owns any ability activation.

### P4 — Cooldown ownership and timer reconstruction

- **Own/start:** separate cooldown findings/module; conditional lookup `0x129045C`,
  upstream collection/ID mapping and `0x5A7450` table `+0x240/+0x248/+0x250`.
- **Deliver:** bounded ownership recipe and offline timer reconstruction, then a
  candidate reader only when the owner/type route supports passive access.
- **Done:** show collection/key provenance and timer inputs; synthetic/retained
  cases distinguish timer arithmetic from live cooldown/GCD qualification.
- **Dependencies/fallback:** no XYZ/HP dependency. P3 ID findings may help later;
  missing owner means a concrete static finding, not invented live telemetry.

### P5 — Cast-state ownership and reader feasibility

- **Own/start:** separate cast findings/module; unit-key producer `0x91DED0`, dynamic
  selector `0x2F57260`, children `+0x280/+0x290` and downstream timer helpers.
- **Deliver:** unit-owned cast candidate topology, state/timer inputs and a minimal
  passive reader where supported. Current Casting addon omits `uninterruptible`.
- **Done:** absence/idle is explicit; retained logic separates start/progress/stop
  hypotheses and flags. An idle zero does not establish cast semantics.
- **Dependencies/fallback:** none on other initial packages; source tracing and
  fixtures continue while an expressly authorized cast-time trial is unavailable.

## Refill the queue as workers finish

| ID / owner lane | Starting point and deliverable | Focused done check; true dependency / blocked fallback |
| --- | --- | --- |
| P6 Orientation | Coordinate code map's player matrix/upstream paths; isolated orientation candidate decoder and locating recipe | Static owner/axis evidence plus fixture math first; stationary-turn/body-versus-camera correlation needs root's live gates. Continue static work if blocked; XYZ travel bearing and dimension-item yaw are not body facing |
| P7 Independent reference / pairing | `src/RiftReader2.Live/TypedApiInlineCapturePass.cs`, `src/RiftReader2.Cli/TypedWireSnapshotCommand.cs`; `scout-copy-typed-native`, `inspect-typed-wire` and existing UI/API evidence | Complete advancing same-player/epoch reference and explicit pairing window/tolerance, or precise blocker. Needed for semantic claims and whichever action flow requires it, never for raw read research; prepare offline pair review if blocked |
| P8 XYZ source independence | Coordinate map: refresh `0x6996C0`, upstream `0x612EE0` / `0x612B50`; trace writers and test query-on/query-quiet only through an eligible route | Identify which producers/queries stopped and compare actual motion; report API-dependent or unresolved honestly. Depends on relevant observation/control gates, not on P9; trace upstream statically if isolation is unavailable |
| P9 Stream / consumer integration | Existing Live output and delivery paths, `src/RiftReader2.Domain/FieldCatalogTypes.cs`, `src/RiftReader2.Application/FieldQualificationEvaluator.cs` | Deliver bounded candidate continuity/consumer path with sample span, count, max gap/read duration, owner/identity loss and unavailable behavior. Depends only on a selected reader, not every field's semantics; offline failure/replay checks if live blocked |
| P10 Recovery / independent reproduction | `src/RiftReader2.Live/TargetDiscovery.cs`, `WindowsNativeMemorySession.cs`, existing host sampler and [restart policy](../decisions/0008-full-game-restart-durability.md) | Recover necessary reader dependencies on demand without duplicate owners; fresh process/owner resolution and old-process rejection. Use a useful reader first; implement/replay recovery now, perform full-game exit/relaunch only under applicable authority |

P7 readiness/pairing can be prepared by root immediately and handed to a free worker;
it is not a sixth implementation prerequisite for P1–P5. Hand back one useful result,
focused check outcome, limitation and next action, then refill with P6–P10. Keep shared
code-map edits section-scoped or give root short findings for integration.

## Deliver now; refine when use exposes a need

| Deliver in the first useful slice | Improve afterward |
| --- | --- |
| Bounded candidate reader or precise locating result | Broader field coverage and additional characters/classes |
| Existing JSON output with clear source/status | UI polish, richer exports and convenience wrappers |
| Focused failure checks for actual owner/type/epoch risks | Wider endurance/performance coverage justified by use |
| One concise finding with reusable evidence | Further cross-lab and restart qualification, labeled separately |

Do not defer correct ownership, exact-build checks or honest output contracts;
those prevent expensive rework. Do defer generic abstractions, elaborate dashboards,
automatic scheduling and documentation expansion without a demonstrated need.

## Live scheduling and practical completion

Lab1 discovery and Lab2 independent reproduction are initial roles, freely swappable
when readiness changes. Physical RIFT supplements read-only/reference work while
Joey uses the PC. Root retains sole live-input ownership; workers can concurrently
analyze static artifacts, implement modules and inspect eligible retained/read-only
evidence. Serialize heavy shared-host jobs and conflicting acquisitions/control.

Exact identity, source freshness and existing controller/action gates still apply.
Use [AGENTS](../../AGENTS.md) and [development scheduling](../workflows/development.md#three-target-discovery-scheduling)
for operational rules: stale-source RRE/REA lookup, credential checks, STOP/cleanup,
health-change deferral, narrow casting authority, restart scope, deferred patch
recovery and direct VMware Computer Use. A denied action is not a failover trigger.
The strict addon observer remains required where its control flow requires it;
it is not a universal gate for raw native candidates.

After one diagnosis and bounded recovery, switch an eligible target or continue an
independent package. Stop a scan without a new hypothesis; stop a module at a useful
candidate plus known limitation instead of waiting for universal qualification.
Accept each working reader/finding after its focused checks and proportional review.
Refine correlation, freshness, continuity and restart incrementally. Do not invent
new approval rituals, expand live action classes or restart games as incidental setup.
