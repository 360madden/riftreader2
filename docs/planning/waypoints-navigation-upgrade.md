# Waypoints navigation upgrade execution plan

Active host: **AMD-DESKTOP**. Requested November 14, 2026.

Deliver dependable local path following, reuse existing RiftWorld/Recast4j,
and preserve STOP, explicit Resume, identity, height and input ownership.
This plan authorizes offline development; it does not resume live gameplay.

## Dependency order and completion

| Milestone | Deliverable | Focused evidence |
|---|---|---|
| A | Ordered path/distance progress; raw recordings retained separately from derived paths | Legacy hashes, reverse, current-leg projection, loops/hairpins/floors, compact preview and sidecar integrity |
| B | Automatic corner control pauses only where running geometry is infeasible; one shared continuous-span interface | Dense straights stay continuous, feasible curves flow, sharp corners continue after controlled pause, STOP prevents restart |
| C | Survival, retreat and rejoin use shared spans with existing lease/deadline | Released passage prefix and actual walked trail survive interruption; auxiliary moves cannot advance forward progress; ambiguous rejoin refused |
| D | Existing Recast candidate review adapter and explicit clearance/context evidence | Current persisted build/query verified; malformed/partial/unqualified context never becomes movement authority or asserted clearance |
| E | Integrate, build, reload idle app preserving user work; qualified live acceptance when authorized | Focused component/integration checks; physical results reported separately from offline simulations |

A progress and recording work can proceed independently. B's span interface
must be agreed before C integration. D inventories/reuses existing artifacts in
parallel and must not block recorded-route improvements. Integrate coherent
milestones; reassess priority on meaningful evidence or blockers.

## Current assignments

- Architecture: GPT-6 Astra, **ultra** reasoning; contracts and control review.
- Progress/playback: Terra high, exclusive progress/playback files and tests.
- Corner/span bridge: Terra high, exclusive continuous movement bridge/tests.
- Survival integration: Terra medium, exclusive survival files/tests; preserve prior dirt.
- Recording retention: Sol medium, recorder/sidecar code and focused tests.
- Recast reuse: Terra medium, review-only adapter and focused tests.
- Coordinator: integration, docs, verification, commits, and sole live-input owner.

Keep useful dependency-ready tasks queued. Research must answer a current
implementation question or upcoming blocker; do not create speculative filler.
Use CLI/library interfaces first, minimal shared contracts and defensive input
validation. Preserve unrelated work. No additional robotics/AI framework or
Recast engine migration without demonstrated need.

## Verified starting evidence

Waypoints baseline commit: `5288ebc`. Existing RiftWorld courtyard build validates
and a fresh query produced 21 points over 29.2678 units. Alignment remains
candidate-only; the Sanctum build with unknown RR2 transform cannot be adopted.
Prior reported 11-point/29.2039 results are historical. Render geometry and
configured agent radius do not establish authoritative collision or safe width.

## Offline integration result

Implemented A's ordered projection/raw retention, B's automatic control pauses,
C's shared survival spans/frontier rejoin, and D's review-only candidate adapter.
The final combined focused gate passed 223 tests. Architecture review caught and
closed STOP-prefix loss and reversal-erasing retreat simplification. The idle
GUI was reloaded as 1.4.0 with the saved 24-point route preserved; no game input.

Remaining order: (1) scoped physical dense-route/corner/STOP and survival rejoin
acceptance when authorized; (2) actual per-run delay/coast calibration and further
curve tuning from retained traces; (3) qualify geometry/alignment and integrate
explicit sampled clearance evidence. The review adapter always disables movement
and automatic rejoin. Full clearance and live acceptance are not complete.

## Continued implementation

Response planning now consumes same-run validated key/pose receipts in normal
and survival spans. Onset includes sampling delay; release displacement remains
censored evidence, not a certified stopping bound. Standalone survival run and
resume now explicitly enable pass-through guides and measured heights.

The candidate inspector accepts explicitly supplied finite-cast evidence, patch
and geometry inputs and binds hashes, ordered segments, settings and hit records.
The actual short courtyard query has eight segments and forty unique sampled
casts without hits; two vertical segments have collapsed lateral coverage.
Usable width, full body sweep, floor authority and live traversal stay separate.

Scoped candidate publication/admission is being integrated using original
outbound/return receipts and independently queried directions. It must survive
GUI normalization, retain its marker on edits, and guard direct-Go subsections
and approach origins before it is accepted as finished.

Survival acceptance remains unavailable: the old admitted 16 MiB currently
contains marker-prefix collisions and no decoded baseline frame. A bounded
four-snapshot diagnostic established this without input; it did not establish
producer state or the cause of missing frames. Do not repeat that same scan
without a changed hypothesis or acquisition window.

Hypothesis, Ruff, Pyright, py-spy, dotnet-trace and PerfView were installed locally
at the user's request. They must remain unused until the user authorizes running
them. Existing unittest checks remain available.
