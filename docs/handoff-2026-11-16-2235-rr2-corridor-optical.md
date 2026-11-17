# RiftReader2 handoff — corridor evidence and optical bounds

Updated: **2026-11-16 22:35 EST** (America/New_York)  
Verified machine: **AMD-DESKTOP** via machine-local `[Environment]::MachineName`; never LEGION.  
Repository: `C:\work\riftreader2`, branch `codex/modular-foundation`, last code HEAD `3ae0590` (pushed).

## Delivered in this continuation

| Commit | Scoped result | Verification |
| --- | --- | --- |
| `1a96a61` | Forward and reverse route adoption capture receipt/zone hashes before native reading and refuse changed bytes before publishing source evidence. | Two red-first mutation regressions; 75/75 adoption/destination offline tests; Git whitespace gate. |
| `71f45ab` | Refuse retained native paths exceeding the cumulative 1,000-unit travel budget, including separately completed/encounter/auxiliary legs. **Post-receipt evidence admission**, not a guarantee that the native mover stops at 1,000 units. | Two red-first over-budget cases; 40/40 runner, 13/13 survival policy, 11/11 CLI; independent reviewer rechecked 40/40. |
| `51cef9c` | Dark-gradient neighbor rows use independent per-row candidate ray projections; unbracketed rows say unavailable. All optical visibility/navigation/movement flags remain false. | Red-first negative control, real pinned second-view reprojected boundaries; 13/13 optical tests. |
| `fa901ca` | Route Library refuses a `rr2.retained-wgc-composite-candidates/1` document dressed up with plausible route fields. | Red-first direct library test; 15/15 library/boundary offline tests. |
| `3ae0590` | Refuse an impossible next survival move **before launching** the mover if the remaining verified cumulative travel budget cannot cover its minimum current→guides→goal planar span. Unpredicted in-leg meander is still caught only after receipt. | Red-first two-leg no-mover assertion; 41/41 runner, 11/11 CLI, 13/13 survival policy. |

All listed commits were selectively committed and pushed to `origin/codex/modular-foundation`. No source from unrelated worktree edits was staged. No live RIFT input, focus change, VM activity, LEGION access, or new collision/navigation qualification.

## Deferred, not left half-applied

A proposed strict native receipt requirement (`pathTruncated is False` and integer `readCount == len(path)`) is supported by current `src/RiftReader2.Live/Control/FollowRouteCommand.cs`:
- `FollowAsync` increments each accepted pose read and appends a path point (approximately lines 534–573), reporting truncation when the buffer loses entries.
- Pause composition increments both totals and marks capped paths truncated (approximately lines 1222–1260).
- Both normal and halt JSON reports emit `ReadCount`, `Path` and `pathTruncated` (approximately lines 1426–1472).

However, many existing **legacy synthetic** survival tests build partial receipts without these fields. A red-first strictness experiment caused 8 failures + 5 errors in 43 tests, primarily from fixture shape. The two uncommitted experimental edits were undone through their Workbridge operation IDs; **no strictness change was committed**. Post-undo runner verification **41/41 passed**, and selected survival source/test Git diffs are clean. Next maintainable slice: migrate explicit physical-receipt fixtures without masking intentionally malformed negative cases, then enable strict acceptance with a focused green gate.

## Collision / navigation status and next actions

1. **P0 collision still STOP**: current-frame contact freshness, physical blocking response and navigation clearance remain unqualified. Independent read-only RiftWorld evidence reports nested triangle dispatch source candidate/index 163 and 531/531 offline P0 tests, but no live nested-dispatch capture or physics-step/contact response proof. Do not import a current live claim from stored manifolds or source render triangles.
2. **P1 physical acceptance**: resume only after current physical PID/start/build, player and input ownership are reverified and Joey separately authorizes the specific supervised movement experiment. Existing historical PID77704 is not reusable authority.
3. **P1 visual evidence**: optical gradients and mesh first-hit layers remain advisory candidates, without depth-buffer fragment identity or independently qualified occlusion. Keep `movementEligible=false`.
4. **Autonomous travel**: the new budget checks protect planned launch and receipt admission, but not every intermediate native step. A true movement-enforced cap requires passing remaining distance to the native follower and testing its halt/release behavior. Preserve STOP, release and shared deadline.
5. Optional broader `test_survival*.py` discovery encountered missing `lupa`; focused required suites passed. Do not imply full-suite coverage.

Current unrelated dirty/untracked work in native actor pose, hunt mission, candidate navigation, target helpers, etc. belongs to other lanes; preserve it.
