# Current status

Updated: 2026-10-19 (America/New_York).

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

The latest native-player-field discovery pass is **incomplete at Joey's handoff
request**. One bounded live capture resolved `[rift_x64+0x32E0200]` and found
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

## Limits and next useful work

No native position, health/resource, combat, cast, cooldown, or ability field is
qualified yet. Memory hits and chains are candidates. Use Lua/API observations
as reference, then record field meaning, units, locator/build applicability,
contrary evidence, and restart/update checks in the [catalog](reference/field-catalog.md).
The next authorized task is to resume native position and health/resource
discovery: capture the changed position against fresh typed Lua, narrow health
and resource candidates with changed-state observations, then resolve the same
frozen chains after an ordinary RIFT restart. Reacquire all process/session
identities; do not reuse a saved heap address as a locator. Use the resumption
record above to avoid repeating the baseline research.

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

The foundation implementation is complete; native-player-field discovery and
restart qualification remain unfinished. Keep versioned files; there is no
measured reason to add the roadmap's optional SQLite index. Routine fixtures,
field entries, and documentation can use cheaper models with the same gate;
identity, native IO, pointer semantics, and input control still warrant strong review.
