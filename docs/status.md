# Current status

Updated: 2026-10-20 (America/New_York).

## Native wheel zoom fixed and verified

The [zoom validation record](validation/native-zoom-2026-10-20.md) closes the
remaining wheel-control gap in the identified RIFT-Lab-1 windowed session.
Joey confirmed physical-wheel zoom works. The old native insertion path still
produced no visible zoom; targeted `WM_MOUSEWHEEL` dispatch produced reversible
zoom out/in on the final deployed binary. Four static ground patches returned
to their original pixel positions after the opposite notch.

The native agent checks exact process/window/foreground/client geometry,
dispatches once with a 100 ms timeout, and never retries an unknown result.
The panel reports dispatch separately from observed zoom. Existing movement,
camera drag, review/arm, and release behavior remain intact.

Full gate passed: **358 C# tests**, **173 Python tests**, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native smoke, locked restore,
deterministic replay, formatting and module checks. Evidence:
`artifacts/validation/20261020T131932Z-22b4af08`. The deployed executable is the
exact full-gate published binary. Native host/guest remain connected, disarmed,
idle, with no pending release or sampled input down; bootstrap server stopped.

Next useful work is sustained human panel usability and further information
discovery. Numerical camera calibration, other builds/fullscreen, optional
Pointer Lock outside Codex, and hard-crash cleanup remain unqualified. Do not
repeat completed S/A/D or wheel baselines without a new reason.

## Earlier native control follow-up: browser drag and timing

The [follow-up record](validation/native-vm-controls-followup-2026-10-20.md)
documents the latest improvement set. The Codex browser rejected Pointer Lock;
the panel now defaults to bounded click-and-drag camera input, which reached
the guest and visibly changed the view. Pointer release cancelled the final
pulse, released the button, and left its result visible alongside release
feedback. Camera modes, review countdown, expiry feedback, and mode-change
stops are explicit.

The hold budget now includes setup after the first press. Completed 100 ms
trials measured 101.97–113.96 ms button intervals in this small sample.
Cursor preparation avoids unnecessary warps, rejects existing button-down
state or insufficient client space, and never restores the cursor after input.
Status includes read-only Windows input-state diagnostics.

Final full gate: **336 C# tests** (274 portable, 62 Windows), **172 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting and module checks.
Evidence: `artifacts/validation/20261020T125211Z-934ab6e9`; 251 links checked.
The final deployed executable matches the full-gate published binary.
Native host/guest remain connected and disarmed, with no pending release or
sampled input down. Temporary bootstrap service is stopped.

At this earlier checkpoint, wheel zoom was unresolved. The subsequent physical
baseline and native message-path fix are recorded above. The historical
follow-up record preserves the earlier negative observations.

## Initial native supervised movement and camera controls

The [native control roadmap](planning/native-vm-control-roadmap.md) is
implemented with recorded validation limits. The repository now owns its
guest-local input agent, persistent host connection, operator panel, CLI,
bounded executor, and VM bootstrap/capture helper. The recommended control path
does not import or run original RiftReader source. See
[usage](reference/native-vm-controls.md) and the
[live record](validation/native-vm-controls-2026-10-20.md).

On RIFT-Lab-1, reviewed trials demonstrated S/A/D, W+Q, left camera orbit, and
right yaw/pitch; an earlier native trial demonstrated W. Emergency stop
interrupted a 250 ms action, acknowledged in 39.19 ms, and released the key.
Idle host reconnect cleared an armed session. The final host/guest remain
available, disarmed, with no pending release. The panel was opened for review.
V1 receiver/observer and the temporary bootstrap server are stopped.

Wheel zoom remains unverified despite successful insertion in both directions.
One camera-button interval missed the proposed ±20 ms timing target.
Numerical camera calibration, fullscreen capture, sustained human Pointer Lock
usability, and hard-crash cleanup are unqualified. Next priority is a human
panel usability pass and binding-aware wheel diagnosis, then further field
discovery. Do not repeat the completed S/A/D baselines as discovery.

Final full gate passed: **315 C# tests** (271 portable, 44 Windows), **168 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting/module checks, and
246 relative links. Evidence: `artifacts/validation/20261020T121433Z-4e11a754`.
The final published hash matches the guest timeout-fix binary. A 35-second idle
review and brief panel keyboard/release test passed after deployment.

## Earlier supervised movement-control parity work

The [movement-control parity roadmap](planning/movement-control-parity-roadmap.md)
now has separate successful 100 ms S/A/D trials on Joey's selected RIFT-Lab-1,
with fresh receiver/observer identity, reviewed screenshots, release delivery,
and advancing independent API samples. S changed position; A/D produced opposite
visual viewpoint rotations with unchanged XYZ and confirmed turn bindings.
Heading/angle remains unmeasured. The controller is stopped with no pending
release. See the [October 20 record](validation/movement-parity-2026-10-20.md).
Do not repeat these baselines on resumption; reacquire current identity for any
new experiment. Next useful discovery remains changed-state health/resource
capture using the completed targeted-audit tools.

October 20 full gate passed: 273 C# tests, 121 Python tests, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native synthetic smoke, locked
restore, replay, formatting/module checks and 229 links. Evidence:
`artifacts/validation/20261020T105058Z-83f84b40`. Older verification sections
below describe their own earlier milestones.

## Direction and completed scope

RiftReader2 is an independently developed hybrid Lua addon plus modular .NET
application. Keep it a practical personal research tool. V1 remains unchanged
reference material and selected lab infrastructure. See [architecture](architecture.md)
and [roadmap](planning/implementation-roadmap.md).

Steps 0–6 and the additionally requested memory-discovery feature are implemented
within their recorded limits:

- Five production modules, pinned .NET 10, strict configuration, and one validation gate.
- Content-pinned replay, motion analysis with explicit gaps, and durable output.
- First-class Lua producer/C# decoder with shared executable contracts.
- Nonce-bound addon transport with freshness and session/reload invalidation.
- Bounded read-only native capture and a durable field catalog/qualification workflow.
- One supervised movement/turning pulse with reviewed screenshots, exact VM/game
  binding, stop/release recovery, and before/after API evidence. See
  [experiment usage](reference/guarded-experiments.md).
- Read-only memory maps and bounded snapshots, typed value/pattern searches,
  snapshot comparisons, RVA-rooted reverse pointer discovery, and live chain
  resolution. Uses existing modules, no new projects or packages. See
  [memory discovery](reference/memory-discovery.md).

Git author remains repository-local `360madden <360madden@gmail.com>`; branch
`codex/modular-foundation`. Use Git for current commit/worktree state.

## Latest verification

The earlier native-player-field discovery pass was **incomplete at Joey's
handoff request**; a subsequent live restart and field sweep is recorded below. One bounded live capture resolved `[rift_x64+0x32E0200]` and found
float32 XYZ at owner offsets `0x320/0x324/0x328`, within 0.004 of fresh typed Lua
values in one stationary sample. The historical nearby health offsets failed.
A supervised 100 ms forward pulse completed with release and newer API
coordinates, but no post-movement native capture or game restart was performed.
No gameplay field was qualified. See the [resumption record](validation/native-player-fields-2026-10-19.md)
for exact identities, evidence, candidate paths, and the next steps.

This pass changed documentation only; the temporary capture helper and raw
evidence remain under ignored `artifacts/field-discovery/`. The original DVD is
restored and connected; the temporary GuestObserver, host receiver, and watcher
were stopped. RIFT remains logged in. Documentation/link/Git checks apply to
this handoff; the full application gate below belongs to the preceding build.

The final combined gate passed **238 C# tests** (225 portable, 13 Windows),
**21 Python tests**, 108 Lua assertions, 22 actual Lua-to-C# cases, locked restore,
zero-warning Release build, formatting/module checks, deterministic motion and
catalog replay, the published native smoke, and 198 relative links before final
handoff edits. Evidence: `artifacts/validation/20261019T052736Z-c7039e2e` and
`artifacts/memory-validation/full-gate.log`.
All 196 links in the final documentation passed a separate check.

The [memory runtime record](validation/memory-discovery-2026-10-19.md) covers the
same exact published bundle as the full gate, SHA-256
`17A1C90E5EB5864F314DE9B6218DA6FB685A15E910E020B3CCE8029EBF63B9EC`.
In RIFT PID 11620 it mapped 8,281 readable regions, captured/repeated the header,
retained unreadable-memory failures, rejected wrong epoch/build and overwrite,
and followed the PE ImageBase pointer at RVA `0x1B8` back to `MZ`. All four
portable discovery commands processed these exact runtime snapshots. This is a
real RIFT acquisition/pointer check, not a player-object or gameplay-field claim.

The [experiment record](validation/experiments-2026-10-19.md) covers a supervised
100 ms `w` pulse with key-up, matching identity, and newer ReaderBridge API
coordinates, plus identity/duplicate rejection and stop-before-input. The final
adapter also has tested retry handling for transient post-release unavailability;
the successful live trial's retained hashes identify the preceding adapter revision.

Independent review checked native rights, identity/failure provenance, strict IO,
bounds, pointer/work limits, and stop/release behavior. The original DVD is
restored, temporary observer/receiver processes are stopped, and RIFT remains
logged in. No V1 source or global configuration changed.

Earlier records separately cover [addon recovery](validation/restart-recovery-2026-10-18.md),
[native process restart](validation/native-capture-2026-10-19.md),
[fixed wall replay](validation/wall-replay-2026-10-19.md), and
[catalog semantics](validation/field-catalog-2026-10-19.md). They identify their
own inputs/builds and do not requalify this new bundle for every recovery scenario.

## October 19 resumed evidence review

Two later **previously retained** native reports (05:57 and 06:00 UTC) were found
in ignored `artifacts/field-discovery/runs/`, after the earlier 05:45 capture.
Both independently reread the root and show post-movement XYZ within 0.004 of
fresh typed Lua values in the same RIFT process/build as the original capture.
A fresh 08:22 UTC host receipt confirmed the same live game process and Lua
coordinates, but did not include a fresh native capture. No new movement or
RIFT restart was performed in this review. The VMware CD/DVD configuration
currently selected the field-lab ISO; this was observed, not changed.

The new [native position evidence reviewer](reference/native-field-evidence.md)
replays all three reports, pins source bytes/hashes, checks exact game/observer
identities and root-owner bytes, measures XYZ agreement, and distinguishes the
first capture's **unrecorded** root stability reread from the later verified
ones. Its output is `movement-consistent-stability-unverified` with exactly one
process epoch, `candidate-only`, and no restart/update qualification. Local
review: `artifacts/field-discovery/candidate-review-20261019.json` (ignored).
The reviewer has a dedicated regression suite and is included in the full
`validate.ps1` gate. See the [updated live handoff](validation/native-player-fields-2026-10-19.md).

The resumed full repository gate passed on October 19: 238 C# tests,
40 Python tests (including 19 for the new reviewer), 108 Lua assertions,
22 Lua-to-C# cases, zero-warning Release build, locked restore, native
smoke, deterministic replay, formatting checks, and 208 relative links.
Evidence: `artifacts/validation/20261019T083341Z-16701712` (ignored).

## October 19 live restart and health candidate sweep

An additional bounded guest capture at 08:54 UTC used the existing read-only
field-lab executable and fresh typed Lua in game PID `11620`. The report at
`artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json`
(SHA-256 `2D2120DCC8E2986BB284F3401B6EBBB7E49BBC0790E3B4AD1E3A144910B676B9`)
scanned 1,073,741,824 bytes with zero read failures and 126 matches for health
18,208 (119 int32, 7 float64). It hit the byte limit and is not exhaustive.

The guest game then exited via its ordinary in-game Exit Game menu; a fresh
GuestObserver report showed zero game processes and foreground Glyph. Glyph
restarted the same RIFT build without sign-in, and Atank re-entered the world.
The new game PID `8356` started `2026-10-19T09:11:06.5141458Z`
(UTC ticks `639279978665141458`), replacing PID `11620`
(UTC ticks `639279813293755454`). The Lua observer stayed alive and its
typed generation reset from 1 to 2, with fresh advancing values.

A second independently bounded read-only native capture at 09:13 UTC resolved
the same root RVA `0x32E0200` with a successful root reread, now to a
**different** session owner `0x220BF9406A0` instead of `0x216ECFE06A0`.
The resulting XYZ `(7296.40381, 876.31891, 3054.37769)` matched fresh
Lua `(7296.39990, 876.32001, 3054.37988)` within 0.004. The source is
`artifacts/field-discovery/runs/4ebbe9ee91c148c4a05466ebb9049d25/report.json`,
SHA-256 `07DB7E70D98EA102FE0939A9CD89C1153FA8A0D0318B5E431B90D3BC3766415F`.
This is **observed same-build cross-process-epoch locator recovery**, not
semantic qualification or update survival. A separate invalid-old-epoch
request was not run in this session.

The new capture scanned 977,739,776 bytes with zero read failures and stopped
at 128 exact health matches. The tracked
[native field reviewer](reference/native-field-evidence.md) now also validates
recorded health-hit contexts and clusters and distinguishes same-build
cross-epoch candidate evidence from actual qualification. The health review
produced 111 clusters and no authoritative health/resource locator. Health
was 18,208/18,208 and raw power 100 before and after both scans; there was
no changed-health reference to distinguish cached values. Full raw captures,
reviews and screenshots stay under ignored `artifacts/field-discovery/`.
See [the chronological validation record](validation/native-player-fields-2026-10-19.md).

The full repository validation passed again on October 19, including **238 C#
tests, 58 Python tests** (37 native-field reviewer tests), 108 Lua assertions,
22 actual Lua-to-C# contract cases, locked restore, a zero-warning Release
build, published native synthetic-process smoke, deterministic replay,
formatting/module checks, and 210 relative links. Local gate evidence:
`artifacts/validation/20261019T091919Z-2dba17e0` (ignored). No V1 source or
RIFT executable was modified; the RIFT-Lab game was relaunched normally.

## October 19 offline cross-epoch health structure comparison

The new `--compare-health-hits` replay in
[the field evidence guide](reference/native-field-evidence.md) checks the
existing 08:54 and 09:13 raw reports against each other without touching the
live game. Both reports have different PID/start epochs but the same build,
player, and unchanged typed health/max `18208/18208` and power `100`.
Only validated int32 marker layouts are compared; no absolute heap address
is treated as a portable locator.

Of 104 and 111 recorded health-hit groups, **10 and 7** respectively
contained informative multi-marker layouts. Exactly one layout recurred:
**8 instances before restart and 5 after** with repeated health, power and
independently observed level `45` values at the same relative offsets.
That multiplicity argues against assuming any instance is a unique field.
The ignored replay report is
`artifacts/field-discovery/health-cross-epoch-shapes-20261019.json`
(SHA-256 `6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD`).
It records `candidate-only`, no tested changed-state values, and no
qualified restart or update survival for health. The comparison is bounded,
deterministic, and covered by focused tests. No live game changes occurred.

The full October 19 gate passed with 238 C# tests, **73 Python tests**,
108 Lua assertions, 22 actual Lua-to-C# contract cases, a zero-warning Release
build, native synthetic smoke, locked restore, replay, formatting checks, and
212 relative documentation links. Evidence:
`artifacts/validation/20261019T120612Z-21633586` (ignored).

## Limits and next useful work

No native position, health/resource, combat, cast, cooldown, or ability field is
qualified yet. Memory hits and chains are candidates. Use Lua/API observations
as reference, then record field meaning, units, locator/build applicability,
contrary evidence, and restart/update checks in the [catalog](reference/field-catalog.md).
The next task is to gather controlled **changed-state** health and raw resource
observations, capture only relevant regions, and distinguish true fields from
copied/cached structures. Measure reacquisition over additional restarts and
separately check old-epoch request rejection for the specific field chain.
Always reacquire process/session/build identity; never reuse heap addresses.
Update survival requires a different executable build and independent evidence.
Use the saved replay and catalog rather than repeating completed baselines.

Snapshot reads are sequential, capped at 64 MiB per explicit request, and are
not atomic. Pointer discovery searches selected bytes, 8-byte-aligned x64 slots,
main-module roots, depth up to four, and nonnegative offsets up to 4,096. Results
report truncation. Encoded pointers and other-module roots are not supported.
A process restart requires fresh inspection and explicit requests; build changes
require separate validation. Large scans have not been benchmarked in RIFT.

Experiments retain timing uncertainty: host/guest skew is unmeasured, so their
API samples support coarse before/after comparisons, not precise motion timing.
Mid-hold stop, hard crash, snapshot restore, and update recovery remain unqualified
in RIFT. Sending key-up is not proof of game key state. Dedicated navigation,
combat, and casting automation remain outside this repository.

The foundation implementation is complete; the native position candidate has
same-build restart evidence, but semantic catalog qualification, health/resource
discovery and update recovery remain unfinished. Keep versioned files; there is no
measured reason to add the roadmap's optional SQLite index. Routine fixtures,
field entries, and documentation can use cheaper models with the same gate;
identity, native IO, pointer semantics, and input control still warrant strong review.
