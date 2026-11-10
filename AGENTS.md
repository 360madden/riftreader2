# RiftReader2 repository instructions

## Active RIFT target: physical Windows hosts only (Joey, 2026-11-10)

For new RR2 live discovery, observation, telemetry, and supervised input work, use
**physical RIFT on AMD-DESKTOP or LEGION**, whichever verified host actually owns
the selected `rift_x64` process. VMware RIFT-Lab-1/2 are **retired as active RR2
targets**. Do not start/restart VMs, deploy to guests, use vmrun/VNC/guest login,
or fall back to a lab on failure. Keep old lab code, test fixtures and evidence
intact as historical reference; their workflows are opt-in archival diagnostics,
not the current operational default.

On every run verify `[Environment]::MachineName` against the requested host,
then obtain fresh local RIFT PID, process start, executable path/hash, and window
identity as applicable. Fail closed on wrong host, absent/ambiguous processes,
changed identity, stale sources or unavailable control ownership. With physical
multibox, require explicit PID binding; never silently choose another instance.
Reuse `scripts/observe_target.py` physical routes, `scripts/observe_physical.py`,
and the local .NET 10 live reader/control agent. Maintain addon nonce/freshness,
exclusive input controller, reviewed actions and STOP/key-release safeguards.
This decision supersedes the older two-lab and three-target scheduling below.
Do not infer permission to operate the physical desktop from target availability.

## Default: results-first development (Joey, 2026-11-08)

Build a functional RR2 capability, not a process around it. Use this short loop:

1. Pick one working outcome; reuse existing tools and code.
2. Make the smallest coherent change; run its focused checks.
3. Try the real RIFT workflow when authorized and ready; label offline or
   candidate results honestly.
4. Commit verified files, push when authorized, and move to the next result.

For ordinary changes, a one-sentence goal and brief outcome are enough.
Do **not** require per-batch plans, broad test sweeps, repeated reviews,
new frameworks, manifests, handoffs, or status artifacts. Create a handoff
only at a genuine stopping point or ownership transition. Use parallel work
only for useful independent tasks, never to fill slots. Preserve concurrent edits.

This fast path retains fresh process/build/session identity, source freshness,
candidate labels, existing action authority, exclusive live-input ownership,
STOP/key release, and verified cleanup. Broader validation is for changes
that need it or claims of full-repository validation.

## Purpose and current scope

RiftReader2 is a practical discovery and retrieval framework for wide-ranging
RIFT data, serving other programs. Its purpose includes discovering information
and reliably retrieving it again on demand. Optimize for discovery speed,
usable retrieval, efficiency, durable knowledge, restart recovery, update recovery,
and less repetitive AI work. Movement and turning support controlled tests.
Dedicated navigation, combat, and player automation belong to a future program.

**Discovery framework — Joey's clarification, 2026-11-07:** A useful finding
should feed a practical repeatable retrieval capability: resolve the current
source/owner, acquire the requested data under fresh identity and applicable
freshness checks, and return structured values or an honest unavailable reason.
Reuse existing readers, commands and contracts; do not build a new generalized
framework before useful retrieval works. Reports distinguish what was discovered,
what can be retrieved on demand, and what remains unqualified (including changed
state, freshness and restart recovery). Discovery-first means prioritizing useful
findings AND working retrieval paths; refinement remains optional, later or never.

**Parallel RRE effort — Joey's clarification, 2026-11-07:** RR2 and RRE are
parallel, complementary efforts: similar subject matter, distinct approaches
and owners. The RRE repository is a valuable information source for this
framework, including findings, readers, artifacts and retrieval techniques.
Consult and reuse useful peer results rather than repeating completed discovery.
Preserve source/build/capture provenance and distinguish imported findings,
historical observations and freshly acquired data. RRE evidence can inform
discovery and retrieval immediately; it does not by itself qualify a current
RR2 live field. Preserve separate repository ownership and serialize any shared
lab access. Do not assume either project replaces the other or must duplicate it.

**Practical-results policy — user decision, 2026-10-25:** This is a personal
tool, not an enterprise compliance program. Prefer the shortest reliable route
to a working result. Reuse existing tools, make small changes, and move to actual
use once the relevant checks pass. Add safeguards for concrete failure risks;
do not keep adding frameworks, review layers, manifests, or documentation as an
end in itself. Keep notes concise and checks proportional to the change; a
documentation-only update does not need the full code-validation suite. Retain
the essential exact-build, stale-data, restart and single-controller protections.

**Discovery first — Joey's durable correction, 2026-11-07:** Prioritize useful
discoveries and working results NOW. Refinement is optional: later, or never.
Do not make cleanup, refactoring, generalization, polish, extra documentation,
broader testing or another review cycle a default follow-up or completion gate.
Do that work only when it is needed for the next useful observation/capability
or fixes a concrete demonstrated failure. Reuse what works, check the relevant
risk, use it, and move to the next discovery. Keep ownership, exact identity,
freshness, STOP/release and honest candidate/qualification labels intact.

The product is hybrid: a first-class RIFT Lua addon plus the modular external
.NET application. Preserve addon API, native memory, and derived evidence as
distinct sources. See [the hybrid decision](docs/decisions/0002-hybrid-addon-and-reader.md).
Do not assume general Lua file/network access or treat SavedVariables as live
telemetry. The Lua producer and offline C# decoder have shared contract tests;
live transport must establish freshness and reload/session identity. See the
[addon contract](contracts/addon/README.md).

**Self-contained runtime — Joey's decision, 2026-11-06:** Current tools and
applications must use RiftReader2-owned implementations and observations. The
older RiftReader checkout and RiftReaderApiProbe are historical/reference
material only, never operational prerequisites. Preserve explicit historical
replay without silently falling back to legacy producers. The RR2R1 migration
and pending installed-addon acceptance are recorded in
[the migration note](docs/reference/self-contained-api-reference.md).

**Native-first telemetry priority — Joey's decision, 2026-10-31:** For new
player health, resources, abilities, cooldown and cast-state telemetry, prefer
direct, read-only RIFT process-memory or other independently verified game data
when practical. The Lua addon is scaffolding, an independent validation reference,
or a fallback—not the default runtime prerequisite. Do not make a new Lua
contract/deployment dependency before assessing native feasibility. Native
numeric matches are candidates until changed-state and ownership evidence proves
their meaning; bind every live locator to its exact build and process epoch.

**Dual-method executable research — Joey's decision, 2026-11-01:** To
learn the RIFT executable and qualify native fields, use **both** bounded,
exact-build static analysis (REA/Ghidra/disassembly/retained PE evidence)
and practical controlled live experiments that deliberately change the
relevant game state. Do not impose a blanket "no game input" default on
executable research. Static owner/offset candidates, unchanged numeric
matches, and screenshots alone are not changed-state verification; compare
native before/after observations with independent UI/API evidence, then test
freshness and full-game restart recovery as applicable. The coordinator
owns live game actions and serializes them per lab under fresh PID/start/SHA,
reviewed foreground state, exclusive queue/controller lease, bounded input,
STOP/key release and independently verified cleanup. Other research agents
can analyze distinct static artifacts in parallel without taking live input
ownership. Reuse existing supervised movement/turning and reviewed console
authorizations; use new action classes (such as casting/combat) only within
an expressly authorized, narrow experiment. No game-memory writes,
injection, debugger attachment, uncontrolled automation, or bypass of
existing input/freshness gates is implied. Prefer useful measurements and
small reproducible experiments over prolonged planning.

**Practical parallel development — Joey's correction, 2026-11-06:**
Prioritize speed and useful results; preserve existing module boundaries and
leave refinement optional, including never. For narrow tasks, state the outcome
in one sentence and begin implementation. When parallel work is genuinely useful,
briefly establish file ownership, shared interfaces and focused checks. Run
independent goals in parallel, keeping useful work
moving while a decision or review is pending. Do not invent work to fill slots.

Use `gpt-6.1-sol` or `gpt-6.1-terra` at low/medium reasoning for routine workers;
`gpt-6-luna` suits mechanical tasks with clear checks. The root reviews routine
changes. Use `gpt-6-astra` at high reasoning for targeted difficult architecture
and high-consequence native identity, concurrency or control reviews, not every
substantive patch. Escalate after repeated failure or consequential uncertainty.
For overrides, use `fork_turns: "none"` with explicit task context, owned files,
shared interfaces, constraints and checks. Terra's preference for suitable coding
and authorized UI work is Joey's guidance, not a measured benchmark or new
Computer Use authority.

Run focused checks, correct failures and integrate useful slices promptly. Use
broader checks when scope warrants or before claiming full repository validation.
Ship useful candidate output with honest labels, refine after actual use; live
qualification is required for live capability claims, not as a prerequisite to
implementing raw candidate output. Keep concise evidence notes for meaningful
results and material limitations, not per-edit reports or new manifests. Give
brief visually clear progress updates at actual milestones or blockers, with
America/New_York timestamps, color markers and emojis when useful. Avoid
repeated SITREPs without a material change. Reuse existing tools; add no scheduler
or process framework. Preserve module boundaries,
versioned contracts and all authority, exact-identity, freshness and control
protections. The root retains sole live-input ownership per lab and coordinates
shared-host heavy work; workers gain no independent game-input authority.

For a screenshot-only request, use `scripts/observe_target.py` with explicit
`--target` and `--expected-host` on that target's owning Windows host; see the
[target observation workflow](docs/workflows/target-observation.md). The default
is capture-only, with no target fallback. Physical capture also requires explicit
foreground-change authority. Keep the Lab 2 native/UI and confirmation behavior
below when those diagnostics are requested.

For Lab 2 read-only native/UI diagnostics, prefer the bounded
`scripts/inspect_lab2_tool.py --output <fresh absolute directory>` delivery entry
point. In ChatGPT/Codex, run it and load its returned image within ONE
`functions.exec` call: await command completion (including any needed session
polling), require successful verified delivery, then await `tools.view_image`
and emit the image. Do not return to the model solely to dispatch a predictable
poll or load that image. See the [one-handoff recipe](docs/workflows/lab2-tool-handoff.md).
The underlying `inspect_lab2_workflow.py run --native-vitals` retains fresh
VM/game/agent admission, candidate labels, queue-owned capture and verified
cleanup. Review the returned pixels after release; image delivery is not visual
approval. Failures must not display an earlier run's image or silently retry.
For an explicitly requested read-only confirmation, add `--confirm-output
<second fresh absolute directory>` and return both verified images in the same
call. Each observation keeps its own complete admission and cleanup. Use separate
calls when the next action depends on interpreting the first image.
For those image-dependent calls, reuse the reviewed helper in
`scripts/lab2_tool_handoff.js` rather than regenerating the command wrapper.
Load it once as described in the one-handoff recipe, inspect the overview, then
choose a focused read-only continuation. Keep the actual visual decision.

**Current phase: modular hybrid foundation, native capture, and field qualification.**
Joey authorized this phase on 2026-10-18. Implement and verify the architecture,
configuration, offline evidence workflows, and developer foundations. Follow
[the architecture](docs/architecture.md) and [development guide](docs/workflows/development.md).
Keep later features in the roadmap until their implementation is requested.
Joey subsequently authorized roadmap step 4's remaining bounded read-only
native capture work and its RIFT validation. Follow the
[native capture contract](docs/reference/native-capture.md); preserve raw
acquisition evidence without promoting native-field meanings.
Joey authorized step 5's durable field catalog and qualification workflow on
2026-10-19. Preserve exact evidence and build/session identity; evaluate recorded
assessments without treating raw capture success as field qualification.
Joey authorized step 6's supervised, bounded movement/turning experiments and
read-only memory discovery (RVA pointer chains, value/pattern searches, and
candidate fields for navigation, combat, casting, stats, and abilities) on
2026-10-19. These discover information; dedicated gameplay automation remains
outside this repository. Keep this a practical personal tool: reuse existing
modules and selected lab tools, avoid new frameworks and unnecessary process.

## On-demand operational dependencies — Joey's correction, 2026-10-31

When Joey requests a RiftReader2 operation, its entry point owns the required
operational dependencies. Do not tell Joey to manually start a controller,
reader, receiver, or helper merely because a previously running process exited.
Discover whether each dependency is necessary, inspect current health and
identity, reuse healthy instances, and safely start or recover missing instances
within the operation's authorized scope. This applies independently to both labs
and to the repo-to-installed-addon sync, telemetry freshness, VM/guest reachability,
receiver and reader sessions, and controller/queue ownership. A working VM or RIFT
process alone never establishes player telemetry readiness.

Implement dependency preflights in reusable code, not only AI instructions or
human runbooks. Check the dependencies of *each* operation rather than eagerly
starting every service for ordinary chat. Avoid duplicate owners and stale plans;
reacquire exact VM, RIFT process, build, addon/session and lease identity after
restarts. Start control hosts disarmed, with no gameplay input or automatic
movement. Do not silently rebind an addon, restart a VM/game, reset a queue,
clear a lease, or bypass reviewed-input gates. If recovery requires these actions
or a new authority, stop and report the exact dependency/blocker; do not claim
an unavailable service is a functioning telemetry source. Validate freshness and
readiness at the end of recovery, not just process existence. Use bounded retries,
clear status, and idempotent ownership. A missing automatic recovery implementation
is a product defect to track and fix, not a routine manual prerequisite for Joey.

## Stale-data research preflight — Joey's decision, 2026-11-04

If a RiftReader2 reader reports stale, expired, unbound, non-advancing or
contradictory player data, first inspect the relevant **RRE** and **REA-Lab1**
source-hashed findings and existing RR2 forensic receipts before choosing
a new recovery action, redesign or additional experiment. Prefer reusing
qualified historical diagnostics and eliminating an already-understood cause
over repeating broad scans or rebuilding tooling. Distinguish full-scan
freshness from candidate-region fast freshness and compare exact source
epochs; a stale full scan is not proof that fast addon production stopped.
RRE and REA historical/static facts never become live RR2 data without fresh
process/build/nonce/player/epoch and independent advancing receipt proof.
Keep their repositories read-only from RR2 work and preserve their owners.
This research lookup must not delay an already-required STOP/key release or
verified cleanup; all live actions still require the usual guards.

## Two-lab scope — user decision, 2026-10-28

Both **RIFT-Lab-1 and RIFT-Lab-2** are available for the bidirectional hybrid
research and validation work. This supersedes the earlier Lab-2-only restriction
for that work. Follow the [saved prompt and roadmap](docs/planning/bidirectional-hybrid-two-lab-roadmap.md).
Assign complementary discovery/validation tasks with explicit file ownership,
separate lab/session identities, endpoints and evidence, and one input controller
per lab. Reacquire current VM/process/build identity; do not copy absolute
addresses or assume matching builds. Coordinate expensive scans on the shared host.
Other input restrictions, patch-recovery deferral, V1 reference-only status and
limits on dedicated gameplay automation remain in force. Roadmap targets are
not implementation evidence or blanket action authorization.

**Three-target scheduling — Joey's decision, 2026-11-06:** Use both labs and
the physical-PC RIFT instance to accelerate authorized discovery; prefer the labs
because they reduce exposure to inadvertent human input; still verify exclusive
control for input experiments. Start with Lab-1
discovery and Lab-2 independent validation, swapping roles as readiness warrants.
Use physical RIFT as a supplemental read-only/reference target by default while
Joey uses the PC. Controlled input requires existing target-specific authority
and exclusive foreground/controller ownership; target availability grants no new
input, reload, restart or patch-recovery authority.

After bounded retry, classify a blocker as target-specific or shared and switch
to an eligible target or independent offline work instead of stalling. A switch
cannot bypass a denied action or shared prerequisite. Before abandoning active
input, obtain clean STOP/key release and verified controller cleanup. If cleanup
is unknown, quarantine that target: issue no further experimental input or start
a competing controller, while preserving safe STOP/release and authorized recovery.
Continue nonconflicting independent work. Reacquire each target's process/start/build
and the player, source freshness, tool and controller prerequisites applicable
to the chosen operation; unresolved player semantics remain candidate evidence;
isolate artifacts and never reuse session addresses across targets. Serialize
shared-host heavy scans. Coordinate this with the existing tools and concise
notes, not a persistent scheduler or new framework. See the
[practical scheduling workflow](docs/workflows/development.md#three-target-discovery-scheduling).

**Autonomous information-channel trial — user grant, October 28:** After reserving
idle Lab-2 and manually loading the guidance addon, Joey explicitly authorized
the agent to attempt the command-entry work itself, use or design helper apps,
and work independently while he is away. This covers the bounded addon reload,
guidance bind/status/clear and calculated-result delivery needed for this trial.
Use a narrowly allowlisted repository console helper with fresh VM/game identity,
an agent-reviewed screenshot, exclusive controller ownership and key release.
It does not expand into arbitrary Lua/macros, protected clicks, unrestricted
gameplay automation or previously deferred research. Keep direct ChatGPT Computer
Use deferred; the authorized repository CLI/console-helper route remains available.

## Automated movement trial — user decision, 2026-10-29

After the two-lab guidance hour, Joey explicitly requested another two hours
using both labs toward common goals, with maximum useful subagents, focused on
"automated and reliable player movement." This authorizes implementing and
testing bounded position-feedback movement in this repository; it supersedes
the earlier deferral of that specific automation work for this trial.

Use the existing reviewed capture, exact identity, queue lease, native arm and
release contracts. A reviewed finite arm may contain multiple automatically
chosen pulses driven by new independent position observations. Keep the current
15-second arm boundary; do not silently re-arm. Calibrate actual key responses
before using them, and stop on lost freshness, identity, control, progress or
budget. Nearby waypoint trials do not establish general pathfinding, obstacle
avoidance, combat automation or qualified native facing. The Computer Use and
patch-recovery deferrals below remain in force.

## Current durability policy — user decision, 2026-10-25

Prioritize durable collection that survives **fully exiting RIFT and launching
the game again**. Restart means the old game process has ended and a new
process/start identity is acquired; addon reload, character relog, or reader
restart alone does not satisfy it. Preserve reusable build-specific locating
recipes and evidence, then resolve fresh process/owner addresses on each run.
Reject absent/stale processes and never report cached coordinates as fresh.

**Patch/update recovery is deferred until Joey explicitly resumes it.** Do not
treat it as the next task or a prerequisite for accepting demonstrated same-build
restart durability. Keep exact-build checks: a changed executable SHA still
fails closed; deferral does not authorize carrying offsets to another build.
VM/host restarts are separate scopes. Report observed restart cases honestly;
one successful case does not establish unlimited reliability or field semantics.
See [the accepted policy](docs/decisions/0008-full-game-restart-durability.md).

## Computer Use policy — user decision, 2026-10-25

**Defer ChatGPT Computer Use for direct interaction with RIFT inside VMware
until Joey explicitly resumes it.** Do not make troubleshooting or retesting
that path the next task. Prefer the verified CLI workflow for applicable VMware
management operations. This deferral does not grant new live-input authority;
existing scope, identity checks, console ownership and input guards still apply.

**Clarification — user correction, 2026-10-25:** This deferral concerns the
ChatGPT Computer Use path. Existing separately authorized guarded VM-console
helpers remain available for supervised bounded experiments. Use their normal
capture, identity, exclusive-access, arm and release checks; do not unnecessarily
ask Joey to press movement keys when the authorized helper can perform the test.

## Orientation and durable context

- Work in `C:\work\riftreader2`.
- For substantive project work, read [current status](docs/status.md) and the
  relevant topic from [the index](docs/README.md). Read only what the task needs.
- [The brief](docs/project-brief.md) owns goals;
  [decisions](docs/decisions/README.md) own accepted choices;
  [proposals](docs/planning/top-20-proposals.md) remain ideas.
- Treat `C:\rift modding\RiftReader` as reference. Do not modify or import it
  wholesale. Evaluate any selective reuse explicitly.
- Build an improved RiftReader2 guided by this repository's goals and decisions.
  Do not copy the original application or inherit its architecture by default.
  Evaluate selective reuse against V2's goals and validation needs.
- Keep a compact handoff in `docs/status.md`: what changed, what was actually
  verified, unresolved questions, and the next authorized task.

## Evidence and efficiency

- Distinguish user decisions, proposals, observed evidence, and assumptions.
- Record sources, dates, build/session identity, and limitations where relevant.
  V1 observations do not establish V2 capabilities.
- A saved address is session state. Durable knowledge includes the field meaning,
  a locating method, applicability, and validation evidence.
- Prefer bounded local searches and analysis to dumping large files into chat.
  Use `rg`/`rg --files` when available or Workbridge's scoped search.
- Keep generated captures, binaries, logs, and caches under `artifacts/`.
  Keep small useful findings and provenance in tracked documentation.
- Run `pwsh -NoProfile -File scripts/validate.ps1` for the full local gate.
  For focused iteration, use the development guide. Keep module dependencies
  acyclic and preserve versioned input/output contracts.
- Keep AI context bounded: read this file, status, and the task's module only.
  Delegate disjoint work with explicit ownership. Routine docs, fixtures, and
  narrowly specified changes can use cheaper models with the same checks;
  identity, native access, concurrency, schema changes, and integration need
  stronger review. See the roadmap for concrete handoff criteria.

## Tool and Git workflow

- Guest Codex tasks use [the lab job workflow](docs/workflows/lab-codex.md).
  Keep the main PC repository authoritative; dispatch explicit read-only tasks
  and selected source snapshots with `scripts/lab_codex.py`. Collect reports
  and review their claims before integrating findings. These jobs do not own
  game input or replace the existing per-lab control host. Use the returned
  absolute run path for status, collection or cancellation, never a guessed
  "latest" job. Existing CLI sign-ins and VM-specific cached guest logins are
  reused; do not copy authentication files between machines.
- **Mandatory cached-credential check for every VM logon (Joey, 2026-10-30):**
  Before each and every attempt to log on to either RIFT lab guest, first
  check that VM-specific cached-credential source using the existing approved
  tools. Repeat the check for every attempt, including after reboots, snapshot
  restores, configuration changes, or previous credential failures. No exceptions.
  Never infer that credentials are absent solely from an earlier failure.
  Do not disclose, recreate, or copy credentials between VMs. If genuinely
  unavailable after the fresh check, report the blocker and ask Joey.
- **Addon sync (Joey, 2026-10-31):** `addon/RiftReader2/` is the source of
  truth for the main PC and both VM installations. After Lua changes or VM
  restore/restart, and before live addon tests, use
  `python scripts/addon_sync.py check --target all`, synchronize drift, then
  verify exact hashes and OneDrive Offline/Pinned state on each installation.
  File verification does not prove a live addon reload or binding. See
  [addon-sync](docs/workflows/addon-sync.md); the tool sends no game input.
- Codex uses its local tools. Browser ChatGPT uses Workbridge; see
  [its guide](docs/workflows/workbridge.md) for hashes, operation IDs, and jobs.
  For new sessions, check Workbridge approval settings and verify a small,
  genuinely needed write early before long-running work; follow
  [the approval preflight](docs/workflows/workbridge-approval-preflight.md).
- Inspect current Git status before edits. Preserve unrelated work.
- Use explicit paths and literal argument arrays for Workbridge terminal jobs.
  Poll to a terminal state and inspect actual exit code and output.
- For parallel native research, serialize heavyweight main-PC Workbridge terminal
  extraction/Ghidra jobs; let other agents work on independent references or
  retained outputs. Several simultaneous read-only PE jobs stalled without a
  result for ~1,000 seconds on 2026-10-31; **the root cause is unconfirmed**.
  On a missing/late job handle, record the exact request ID, inspect job status,
  and stop or reschedule before retrying. Never claim code evidence from a
  stalled command or launch many retries to saturate the shared host.
- Reuse the installed REA for relevant binary research; follow
  [the REA guide](docs/workflows/rea.md) and installed provider capabilities.
- Joey subsequently authorized installing/validating the addon in RIFT and
  building a minimal live transport with reliable freshness and reload/session
  checks. This permits addon deployment and bounded read-only acquisition for
  that task. Joey also authorized operational reuse of the original VM console
  and receiver tools; keep their source unchanged. See the
  [live validation record](docs/validation/addon-live-client-2026-10-18.md).
  Check the actual VMware process/guest before asking Joey to launch RIFT.
  Supervised experiment pulses are authorized under step 6. Dedicated automation,
  debugger attachment, process writes/injection, and changes to V1 remain outside
  this scope. Live verification must precede claims of transport readiness.
- Keep settings repository-local. Do not change global Git/Codex settings,
  Workbridge runtime settings, or REA installation as incidental setup.
- Commit coherent, verified local changes using explicit files. Joey also
  authorized judgment-based **timely local commits for significant findings** on
  2026-10-24, even when a research or recovery checkpoint changes no code. Do
  not wait for an entire roadmap milestone when a consequential result is already
  reproducible and worth preserving. Record exact evidence, source/build/session
  identity when relevant, limitations, and the next action; label tentative,
  negative, or blocked findings honestly. Preserve unrelated work and avoid
  committing credentials, private configuration, and bulky generated artifacts.
  A remote, push, destructive history change, or deployment still requires
  applicable user authorization; carry forward authorization already given.
- Report results and material limitations clearly. Continue routine authorized
  documentation work without repeated permission requests.
