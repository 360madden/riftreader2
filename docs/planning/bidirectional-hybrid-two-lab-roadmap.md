# Bidirectional hybrid system — prompt and two-lab roadmap

Saved: October 28, 2026 (America/New_York), at Joey's request.

This document preserves the combined implementation prompt and roadmap discussed
with Joey. The two-lab scope below is an accepted user decision, superseding the
earlier Lab-2-only restriction for this work. Later capabilities are roadmap
targets, not claims of implementation or blanket authorization for game input.
Read [repository instructions](../../AGENTS.md), [current status](../status.md),
and the [Casting handoff](../workflows/casting-handoff-2026-10-28.md) on resumption.

**November 6 scheduling update:** Both labs remain the preferred controlled live-test
targets; the physical RIFT installation is also available for complementary
discovery. Use the current [three-target workflow](../workflows/development.md#three-target-discovery-scheduling)
for target selection, bounded failover, separate evidence and user-interference
handling. The historical two-lab plan below does not require waiting on one
unavailable lab.

## Implementation prompt

Develop RiftReader2 into a practical, bidirectional hybrid system in which the
in-game Lua addon and external application share information and contribute
their respective strengths. **Use both RIFT-Lab-1 and RIFT-Lab-2 to accelerate
discovery and validation through coordinated parallel work.**

The addon supplies game information available through the RIFT API. The external
application consumes those observations, supplements them with validated
native-memory telemetry, performs calculations, and sends useful results back to
the in-game experience. Together, they should provide better information, visual
guidance, diagnostics, and a foundation for future coordinated automation.

Start by reviewing the existing architecture, transports, research, and accepted
project decisions. Reuse working components and preserve the distinction between
implemented functionality, research candidates, and future capabilities.

## Scope and authorization

RIFT-Lab-1 and RIFT-Lab-2 are both available for this work. **This explicitly
supersedes the earlier Lab-2-only restriction for the work described here.**

Use both labs for repository-supported read-only discovery, API collection,
communication experiments, addon validation, and previously authorized
supervised, bounded experiments. Reacquire each lab's current identity before
using it; historical VM paths, ports, PIDs, addresses, and executable hashes are
reference information until verified.

This expansion permits parallel use of both labs. It does not automatically
authorize unrestricted gameplay automation, arbitrary input, process
writes/injection, or previously deferred research. Retain other existing
restrictions unless explicitly changed. Original RiftReader/V1 stays reference-only.

## Core feedback loop

1. The addon gathers relevant API observations and exposes them externally.
2. The external application combines them with validated native telemetry.
3. It calculates results such as destination distance, direction, arrival state,
   or screen-space positions.
4. It returns results, status, guidance, or supported requests to the addon.
5. The addon displays the results and performs only operations permitted by the
   current RIFT API and its protected-action rules.
6. Both sides report progress, completion, cancellation, unavailable data, and
   failures clearly.

Separate information exchange from action execution. Receiving a request does
not establish that the addon can perform it. Distinguish ordinary addon
operations, protected actions requiring a physical click, and actions needing a
separately authorized external controller.

## Use the two labs deliberately

Assign complementary work so parallel activity produces useful evidence:

- **Discovery lab:** Investigate uncertain transport mechanisms, collect API
  observations, examine native-memory candidates, and run small isolated experiments.
- **Validation lab:** Preserve a known working baseline, reproduce promising
  findings independently, test integration, and check restart behavior.

Choose assignments after inspecting both labs. Swap roles when useful; neither
lab must permanently own one role.

Use different builds, classes, characters, or configurations as comparative
evidence when they answer a specific question. Do not update or reconfigure a
lab merely to make the environments identical. If replication requires matching
conditions, identify the minimum necessary changes first.

Parallel work must follow these rules:

- Give each lab an independent session identity, output directory, transport
  endpoint, and controller ownership.
- Allow only one input controller per lab. Read-only workers may share collected
  artifacts when the underlying tools support it.
- Assign workers distinct questions and explicit file ownership. Avoid concurrent
  edits to shared contracts, root configuration, or the same source files.
- Keep separate raw evidence per lab. Record VM, executable build,
  process/session, addon version, unit identity, and relevant timestamps.
- A result from one lab is a candidate for the other until reproduced or otherwise
  substantiated. Never transfer absolute addresses or remove build checks.
- Coordinate host resources. Stagger expensive scans and other resource-heavy
  operations when simultaneous execution would slow the game, distort timing,
  or reduce evidence quality.
- Use useful parallel workers and an independent reviewer for substantial
  changes. Keep integration and shared contracts under one coordinator.
- Do not interact with a lab the user is actively controlling without establishing
  ownership. Continue independent work on the other lab where possible.

## Working principles

Use live RIFT API observations as the primary reference wherever the API exposes
the required facts. Validate native-memory candidates through aligned values,
changes, unit identities, and controlled trials.

Use native telemetry and external calculations to fill demonstrated API gaps.
Keep observed values, calculated estimates, and unknown states distinct.

Verify current-client communication capabilities. Do not assume Lua can read
arbitrary files, receive network messages, access the clipboard programmatically,
or execute externally supplied commands. SavedVariables are persisted evidence,
not a live inbound channel.

Prefer existing transports, OS/framework capabilities, small changes, and real
end-to-end tests. Add infrastructure only for a concrete limitation. Bound
collection and message processing; measure responsiveness and transport latency.

## Roadmap

Each phase ends with a demonstrated result, concise verification notes, and the
smallest next step. Saving this plan does not execute its phases.

| Phase | Primary work | Parallel use of the second lab | Completion evidence |
| --- | --- | --- | --- |
| **0. Establish both baselines** | Inspect builds, processes, addons, transports, readers, and control availability. | Inspect the other lab independently and identify useful differences. | Capability map and explicit assignments with fresh identities and known limits. |
| **1. Prove external-to-addon feedback** | Test the smallest supported inbound mechanism using a harmless externally generated value. | Investigate an alternative mechanism or reproduce the leading candidate. | Correct delivery to the intended addon, measured latency, stale/disconnected behavior, and documented manual steps. |
| **2. Complete one useful round trip** | Send addon coordinates externally, calculate destination distance/direction, and return the result to the addon display. | Check calculations, transfer behavior, and failure cases independently. | Correct guidance during an authorized manual movement test; unavailable data is not shown as current. |
| **3. Support ordered destinations** | Add active waypoint, arrival tolerance, progress, and start/pause/cancel/reset controls. Keep movement manual initially. | Test boundary cases, different starting positions, and interrupted delivery. | A two-destination route advances without skipped destinations or arrivals caused by stale data. |
| **4. Research missing telemetry** | Investigate one field at a time: player facing, camera position/orientation, field of view, or visibility information. | Study a separate field or validate a promising candidate independently. | Each accepted field has meaning, locating method, build applicability, evidence, and limits. |
| **5. Demonstrate world-to-screen projection** | Project a known world point using sufficiently validated camera/world data. | Test camera angles, viewport conditions, and points behind the camera. | Markers track known points with recorded error and correct invalid/behind-camera handling. |
| **6. Add visual aids** | Evaluate an addon display, external overlay, or combination; implement the smallest useful aid. | Check alignment, readability, performance, and input behavior independently. | Useful markers and status indicators that remain honest about freshness and uncertainty. |
| **7. Trial coordinated actions, if authorized** | Define requests/results and test one supervised bounded action before a sequence. | Review cancellation, timeout, duplicate handling, and ownership; reproduce after initial success. | Acceptance, progress, completion, cancellation, failure, and input-release evidence. |
| **8. Establish durability** | Test reconnect, addon reload, external restart, and full-game restart separately. | Reproduce supported cases and compare configuration/build differences. | Recovery in tested cases and rejection of stale requests/incompatible builds, with operating instructions. |

Parallelize independent work across phases when dependencies allow. For example,
one lab can test feedback transport while the other collects API references or
validates calculations offline. Do not advance dependent features before their
required evidence exists. Existing patch-recovery deferral still governs native
field recovery; phase 4 does not silently resume deferred work.

## Communication and state

Introduce only the message structure needed by the current phase. As capabilities
grow, distinguish:

- **Observations:** API/native values with source, identity, and observation time.
- **Calculated results:** Derived values linked to their input observations.
- **Requests:** Named operations with validated parameters, identifiers, and
  expiry where needed.
- **Results/status:** Accepted, running, completed, cancelled, failed,
  unsupported, or unavailable, with a useful reason.

Include enough lab/session identity to prevent cross-lab delivery. A result or
request intended for Lab-1 must never be consumed by Lab-2.

Do not execute arbitrary Lua received externally. Prevent duplicate or expired
requests from repeating actions. Add acknowledgments, retries, and persistence
only when the chosen transport requires them.

## Research distinctions

Keep the following separate:

- Destination bearing, player facing, and camera orientation.
- World-to-screen projection and actual line of sight.
- A documented API property and observed runtime behavior.
- A native candidate matching an API value and a durable locating method.
- Success in one lab, independent reproduction in the second, and compatibility
  across different executable builds.

Use the second lab to strengthen evidence, investigate differences, and expose
assumptions, not to turn two weak observations into an unsupported claim.

## First deliverable and execution

First produce a concise feasibility assessment and practical two-lab plan:

1. Fresh capability/build summaries for both labs.
2. Existing components and transports that can be reused.
3. Candidate external-to-addon mechanisms and their verified limits.
4. Recommended first mechanism and acceptance criteria.
5. Lab/worker assignments, shared-file ownership, and resource constraints.
6. First demonstration: **addon coordinates -> external distance/direction
   calculation -> addon display**.
7. Specific missing information or authorization blocking dependent work.

Then implement and test portions already within the accepted scope. Continue
ordinary reversible work without repeated confirmation. When one lab is blocked,
continue useful independent work in the other.

If a step requires new gameplay-input authority or changes an existing deferral,
finish independent preparation first and ask only for the specific decision needed.

Report what changed, which lab produced each result, what was independently
reproduced, what remains unverified, and the next useful increment. Keep
documentation proportional and preserve significant findings in timely,
coherent local commits.
