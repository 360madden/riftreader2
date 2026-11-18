# RR2 post-patch recovery handoff — 2026-11-18

**Checkpoint:** Wednesday 2026-11-18, approximately 08:45 EST (America/New_York)  
**Repository:** `C:\work\riftreader2` on **AMD-DESKTOP** only  
**Branch / verified remote HEAD before handoff:** `codex/modular-foundation` / `0d5b63be57e30bbe5e4fd303a441d77f21d85938` (synced with origin)  
**Priority:** P0 recovery following the RIFT 1177 → 1179 update. This handoff records completed work, remaining limits, and the smallest next useful tasks. Canonical detailed chronological evidence is in `docs/status.md`.

## Machine, target, and patch identity

- Local Windows PowerShell `[Environment]::MachineName` returned **AMD-DESKTOP**, exit 0 on November 18. Workbridge was **0.16.5-dev** with root `C:\work`.
- Physical RIFT only (no VMware, no LEGION): `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe`.
- Verified physical target during observations: PID **77980**, process start ticks **639305214834918403**, player self key **239816685251645959**. **Refresh all process/window/build identity before each future acquisition**; these are retained evidence, not permanent endpoints.
- Installed build **STABLE-1-1179-a-1256672**, exact executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`. Historical build **1177** SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- `C:\work\Update Helper\PATCH_EVIDENCE_2026-11-17.md` documented seven modified game files (including `rift_x64.exe`), two removed download records and no added files; it did **not** qualify RR2 addresses. Both archive PEs were SHA-verified for targeted offline comparisons.

## Completed November 18 recovery

| Capability | Actual result | Remaining qualification |
| --- | --- | --- |
| Python build admission/replay | **45/45** focused tests passed; exact build gating preserved | Not a substitute for live field semantics |
| Physical native readers | Position, HP/vitals, facing, selected-position, player context, and **20 selectors / 40 stat candidates** all completed on 1179 | Results remain owner/build/session-bound candidates |
| Warrior Power | Fresh C# `sample-power` **2/2** at **100/100**, advancing clock; recipe `player-power-DF954B79-v1` | No induced resource-change/Lua agreement or full restart proof |
| Cross-day composite replay | New four-source physical capture replayed against November 17: planar delta **6400.5173** native units, same process/build/self key; HP and 40 stat values unchanged | Demonstrates differing recorded XYZ, not independently timed movement causality |
| Facing + target projection | Repaired 1179 selected-target leg with independent self/owner/selection/timing/camera brackets; **87/87 .NET + 4/4 Python** focused tests | Full-game restart, screen-pixel independent match, and target-switch freshness still pending |
| Live facing positive | **2/2** read-only samples succeeded on a selected target: key `9223372039555954076`, distance **14.83123** native units, normalized pixel **(0.5984174201, 0.4330309884)**, stable camera | `movementEligible=false`; no input or independently verified game-screen match |
| Mana candidate | Exact-1179 **kind-3** getter/record/type guarded implementation; fake-memory **2071/3980**, **66/66** .NET focused tests | Live kind-3 character and Lua agreement untested |
| Energy candidate | Exact-1179 **kind-4** getter/record/type guarded implementation; fake-memory **73/100**, **77/77** .NET focused tests | Live kind-4 character and Lua agreement untested |
| Physical wrong-kind vitals | On Atank raw kind **1**, HP **18208/18208** persisted **2/2**; Mana refused `not-mana-kind-three`; Energy refused `not-energy-kind-four` | Correct refusal, not a positive Mana/Energy measurement |
| Target/unit raw template names | Restored exact-1179 C# name-cache path (**16/16** .NET); Python admission (**18/18**); Debug Live build **0 warnings/errors**; physical `target-name` and `unit-names` both exit 0 and returned **Olivia Heln** with the same target/template/localization keys | Raw fallback cache only; localized dictionary not acquired, independent UI/Lua name semantics and restart unverified |

**Important interpretation:** A value produced by a native reader is not automatically a qualified gameplay fact. Preserve exact process start, executable SHA, unit owner, source freshness, candidate labels, and false-positive refusals. The two name commands reuse the same cache logic; agreement is repeatability, not independent semantic confirmation.

## Important saved evidence (ignored local artifacts)

- `artifacts/physical-state-6ea6873023f548c18c674900357d4dc9/summary.json` — fresh 1179 four-source composite; previous comparison `artifacts/physical-state-d1e24e267cc544b58dc437828467c9df/summary.json`.
- `artifacts/physical-native-facing-348d50f8c9734843affd17677e7ab9da.json` — positive target projection; SHA `2B26840C817CAD52555666BBB8B4D63C885A8898420265A9713C6165F3D6563E`.
- `artifacts/physical-native-vitals-0bedc620ab1c4ee7a56f1705ba6364ff.json` — Energy/Mana wrong-kind and HP, SHA `8F2F1D20DBEF3C27FCD3F6109E6F1EABADD17FE0731B01E073B136C02C5FBBA1`.
- `artifacts/physical-native-target-name-dcdbffa57acf49618501569dd978a045.json` — raw target name, SHA `3E4F6C15C6AB87EFE9CC774A0047395A2E1C3767200152D979C949CDD99E80B9`.
- `artifacts/physical-native-unit-names-1f79908c5c6c4e078c28ca239b3f1a61.json` — explicit-unit raw name, SHA `84344B89F7F3035398A33D9432E2C3022155C122BDC5A7558483B60A1044477F`.

## Commits completed and pushed today

In chronological order, all on `codex/modular-foundation`:

1. `6ccd451` — physical postpatch checks and cross-day replay.
2. `d1111a4` — guarded 1179 facing/selected-target pairing.
3. `4c82cce` — type-guarded 1179 Mana candidate.
4. `6b3cc1e` — facing/Mana status evidence.
5. `39a70cc` — positive physical target-projection evidence.
6. `6b00fcf` — type-guarded 1179 Energy candidate.
7. `dc9276f` — Energy physical wrong-kind evidence.
8. `f3a8b45` — 1179 raw selected-target / explicit-unit template-name readers.
9. `0d5b63b` — Python/native CLI gating, focused tests, real raw-name evidence.

The repository was synchronized with `origin/codex/modular-foundation` at `0d5b63b` before this handoff. **Do not assume the branch has not advanced; check before writing/committing.**

## Still blocked and highest-value next steps

1. **P0 — Complete zone-context native recovery.** The old zone reader is 1177-only and must not simply have its SHA gate removed. Bounded, dual-SHA offline research found 1179 provider candidate RVA `0x33803B8`, supported by four matching RIP-relative references; downstream registry candidate `0x33843D8`, selector at provider `+0x40`. The matched producer RVA is `0x135A410` (old `0x135A440`); uniqueness was only checked in a ±64 KiB window. Next: independently identify 1179 outer/child type descriptors, owner+0x150 route, and full getter/producer semantic compatibility. Then add a separate exact-1179 candidate profile with focused fake-memory tests and a no-input physical sample. **These RVAs are source-pinned candidates, not live qualified fields.**
2. **P1 — Controlled positive/repeated-state qualification.** On a user-selected target, gather fresh target-name, target-position, facing and optional screenshot evidence in one bounded session with the same PID/start/build/self; test a *user-performed* target change if available. Do not silently drive the game or claim screenshot correspondence without pixels.
3. **P1 — Mana/Energy positive live sample.** Read a suitable kind-3/kind-4 character without changing Atank's gameplay. Match native values to an independent same-player UI/Lua source under fresh identity. A kind-1 Warrior refusal is already verified, not evidence that the value is unavailable for all characters.
4. **P1 — Whole-game restart durability.** Only when a restart is specifically authorized and the physical game can safely exit, reacquire a **new PID and start identity** and rerun relevant paths. An addon reload or reader restart does not count.
5. **P2 — Remaining older native paths.** `smoothed-scalar`, historical `selected-target`, and other excluded 1177-only readers still need individual exact-build provenance. Do not turn them on en masse.

## Operating constraints / preservation

- Machine boundary: **AMD-DESKTOP only** for this session; no LEGION or VMware fallback. Verify local `[Environment]::MachineName` at session start and exact RIFT process/build/epoch at each live read. With multibox require explicit PID.
- Keep live game input untouched unless a separately reviewed, narrow experiment requires it. All November 18 recovery reads in this handoff were read-only and sent **no game input or desktop focus change**.
- Exclusive live input ownership, STOP/key release, source freshness, nonce/owner and exact-build checks remain mandatory wherever input is used. A candidate is not evidence of movement eligibility.
- The shared Git worktree contains unrelated pre-existing dirty edits: `docs/reference/third-party-workflow-tools-2026-11-12.md`, `scripts/fresh_native_actor_pose.py`, `scripts/hunt_mission.py`, `scripts/waypoint_navigation_candidate.py`, `tests/test_fresh_native_actor_pose.py`, `tests/test_hunt_mission.py`, plus `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, target acquisition/cycle/selection helpers and tests, `.playwright-cli/`, and `output/`. **Preserve all of them.** Never stage, reset, delete, or clean the whole worktree.
- Work in small independently verifiable slices; commit only owned and validated files, push when authorized, and update `docs/status.md` for consequential results. Consult the latest source-hashed RRE evidence but do not modify RRE from this RR2 lane.

## Quick safe restart commands (PowerShell on verified AMD-DESKTOP)

```powershell
Set-Location C:\work\riftreader2
git status --short --branch
git log -3 --oneline
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
```

Then select a **fresh, explicit** physical PID and use `--read-native <kind>` or the exact `.NET 10` native CLI as appropriate. For the current physical session the observed PID was `77980`, **but never use it as a permanent default**.

**Handoff result:** Build-1179 native position/context/stats/HP/Power/facing-target and guarded Mana/Energy/raw-name paths substantially recovered; remaining work is individually pinned zone/legacy readers and independent changed-state/full-restart qualification.

## 2026-11-18 post-handoff addendum — zone recovery through `0509ac0`

The P0 implementation item above is complete for build 1179. Commits `a8637aa`, `99f5fff`, and `0509ac0` restored the raw zone cache, verified the outer type, and restored the guarded zone-ID candidate. Two no-input physical reads in the same process epoch returned `z0000000CB7B53FD7` (raw zone key `12`, child key `1830661357`). This shows repeatability in one state, not agreement with the public zone ID. World-instance identity remains unavailable.

**Next P1:** Compare the candidate with a fresh, independent Lua/UI zone ID for the same player in the same state. Changed-zone behavior, freshness after a user-performed target change, positive kind-3 Mana and kind-4 Energy samples, and durability after a separately authorized full-game restart remain unverified.
