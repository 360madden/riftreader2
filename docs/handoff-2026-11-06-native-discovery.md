# Native discovery handoff — November 6, 2026

## Resume quickly

Work in `C:\work\riftreader2`. Read [AGENTS.md](../AGENTS.md),
[current status](status.md), and the [parallel backlog](planning/discovery-roadmap-2026-11-06.md).
At handoff the branch is `codex/modular-foundation`, code checkpoint `526e34f`,
and the tree was clean before this handoff. Recheck Git and relevant live identity;
old PIDs, reader nonces, addresses and lab readiness are historical only.

Joey wants a short plan before each batch, rapid practical development, separate
worker ownership and concurrent independent work. Use fast custom workers for
routine implementation, and stronger targeted review for consequential ownership,
architecture or native/control changes. Provide frequent visual progress updates
with America/New_York timestamps, color markers and emojis. Ship useful honestly
labeled candidates; refine later. Avoid unnecessary process or new frameworks.

## What works and what does not

- `sample-current-vitals` is an exact-build read-only HP/Energy **candidate**
  command. The shared `CurrentBuildPlayerLookup` re-resolves the player and
  retains ownership anchors; the command revalidates process identity before
  no-overwrite report publication. [Usage](reference/current-native-vitals.md).
- Both labs returned no-input candidate reports on SHA
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`:
  Lab2 HP 10635/10635 and Energy 100/100; Lab1 HP 9010/9010, Mana kind 3
  explicitly unavailable. These are **not** independently correlated,
  changed-state, passive-freshness or restart-qualified results. Exact process
  identities, reader/report hashes and artifact paths: [vitals evidence](validation/native-vitals-2026-11-06.md).
- Current-build XYZ was acquired on both labs; Lab2's 30 stationary samples
  spanned 61.08 seconds. That establishes acquisition over that interval only.
  [XYZ evidence](validation/native-current-sampler-2026-11-06.md).
- `scripts/native_cast_candidate.py` is an offline raw topology helper, not a
  live identity envelope or qualified cast-state reader. See
  [cast candidate](reference/native-current-cast-candidate.md).
- Static [ability ownership](reference/native-ability-ownership-findings-2026-11-06.md)
  and [cooldown findings](reference/native-cooldown-static-followup-2026-11-06.md)
  narrow the next work. Cooldown may have a context-derived initial timer; the
  correct conditional lookup entry is `0x1290458`, not `0x129045C`.
- The full gate passed build, 603 .NET tests, formatting, native smoke, Lua and
  host Python checks, then failed the final whitespace check on two pre-existing
  files: `docs/validation/lab1-controller-recovery-incident-2026-10-30.md` and
  `docs/workflows/lab1-controller-handoff-2026-10-30.md`. It was **not a full
  gate pass**. Focused tests and scoped elevated review are recorded in the
  [vitals validation](validation/native-vitals-2026-11-06.md).

## Next parallel work

1. **Independent reference:** assess fresh `RiftReaderApiProbe` `RRAPIVAL2`
   frames using existing `scout-copy-typed-native` and `inspect-typed-wire`.
   The probe worked on this SHA historically; current producer availability,
   same-player identity and advancing source time must be established afresh.
   It is independent of the RR2 guidance nonce; do not bypass the prior rejected
   GUI bind. A bounded scan that finds no frame proves only its covered scope.
2. **Mana:** trace kind-3 type/owner and calculate a bounded candidate without
   treating kind-4 Energy as generic Mana. Continue offline or on another eligible
   target if the reference path is blocked.
3. **Ability/cooldown/cast:** use the retained exact-build findings for separate
   ownership/timer work and focused tests. No native getter invocation; cast or
   other new gameplay action requires its own narrow authorization.
4. **Integration:** keep workers on separate files; root owns shared lookup and
   command registration. Deliver candidate output with source and limitations;
   compare with independent data before making stronger claims.

Do **not** use `scripts/run_xyz_workflow.py`, `scripts/xyz_capture.ps1` or
`scripts/review_native_motion_pair.py` as current-build XYZ pairing tools: their
underlying profile/reviewer uses old root `0x32E0200` and offsets
`0x320/0x324/0x328`. Use the current sampler and a suitable bounded comparison.
`Inspect.Unit.Detail` can refresh the coordinate cache: API-active agreement is
not proof of passive freshness.

## Target and action boundaries

Use Lab1 and Lab2 in complementary roles, swapping when unavailable; the physical
RIFT installation is available as a supplemental target. Prefer labs for controlled
tests, but verify exclusive control rather than assuming isolation. Per target,
reacquire applicable VM/process/build/player/source identity; do not copy session
addresses. Serialize heavy shared-host work. On a target-specific blocker, use
another eligible target or independent offline work; never switch to evade a denied
action. The coordinator owns live input and preserves STOP/release and cleanup.
Check each VM's cached credential source before every guest login. Inspect RRE and
REA-Lab1 findings first for stale/non-advancing data, keeping those repos read-only.
Ask before `/reloadui`, game/VM restart or reboot. Direct ChatGPT Computer Use in
VMware and patch recovery remain deferred; no memory writes or injection.

## Checkpoint

Code commits: `c0cf0ba` (shared lookup, vitals, parallel findings) and `526e34f`
(whitespace correction). This handoff is documentation only. No live checks,
input, reload, restart or background worker were started while preparing it.
