# RiftReader2 Casting v0.4.0 handoff — October 28, 2026

This is a durable **resume checkpoint**, not a request to replay earlier VM input.
Read [current status](../status.md), [Casting behavior](../reference/casting-readout.md)
and [repository instructions](../../AGENTS.md) before changing anything.

## Repo, decisions and scope

- **Working tree at handoff preparation:** `C:\work\riftreader2`, branch
  `codex/modular-foundation`, clean after implementation commit
  `9e871d2b17b14d8ec701acc6e66ef59737ae5788`. Recheck fresh Git HEAD/status
  upon resumption; this handoff itself will be a later documentation commit.
- **Source-of-truth tooling:** Workbridge, observed `0.16.4-dev` on the Windows
  host; use exact-file SHA guards, unique operation IDs, terminal command exit
  codes, and explicit Git file/hash lists. Do not assume the ChatGPT container
  can directly see Windows `C:\work`.
- **Scope imposed by Joey:** **RIFT-Lab-2 only for this conversation.**
  Do not touch or use RIFT-Lab-1. Keep original RiftReader/V1 reference-only.
  The RIFT patch-recovery work is deferred by existing repository policy.
- **Input policy:** ChatGPT Computer Use inside VMware remains deferred.
  Separately authorized, guarded native VM-console helpers can still be used
  for supervised bounded tests after fresh identity, capture, ownership, and
  explicit arm/release checks. For this release, **no game input was sent**.
- **Preference:** Practical working result, defensive programming, frequent
  meaningful commits, and disjoint useful parallel reviews when requested.
  Avoid creating orchestration/frameworks just to increase activity.

## What was completed

1. `093d1d59c9d22002cce3075beb98511798306f5e` — **v0.3.0 Casting HUD**
   unified square/flat controls, hierarchy, spacing and protected Cast/Stop
   styling; unverified facing and LOS are clearly marked amber. Joey's later
   screenshot confirmed the **v0.3.0 title rendered** but showed that **Hide**
   was nearly invisible. That screenshot did not verify the colored chat
   message, picker clickability, or protected button dispatch.
2. `9e871d2b17b14d8ec701acc6e66ef59737ae5788` — **v0.4.0**
   implements guarded dragging of both dashboard and picker headers,
   viewport-clamped and character-persisted HUD coordinates, brighter Hide,
   and a first-class diagnostic `/rr2cast` CLI. Main panel, picker and separate
   restricted Cast/Stop frames move together. Combat-protected state and
   invalid/unknown coordinates fail closed; save restoration can defer to a
   safe state. The TOC-derived title and once-per-load teal/green chat notice
   use **v0.4.0**.
3. Six independent review lanes examined drag/event contracts, CLI,
   screenshot/UI, security, tests and deployment/doc limits. Their useful
   findings were incorporated. The earlier repository-wide October 28
   bug-hunt and its residual risks are documented in
   [the codebase review](../validation/rr2-bughunt-2026-10-28.md).

### New in-game commands

`/rr2cast` or `/rr2cast show` opens the HUD.
`/rr2cast help` prints colored instructions and diagnostic limits.
`/rr2cast status` reports target, selected ability, API-based readiness,
range/cast/channel/cooldown/Power, trial and HUD position.
`/rr2cast info` explains version, status meaning and feature limits.
`/rr2cast abilities` opens the 20-choice-per-page picker.
`/rr2cast record` begins **observation only** (up to 60 seconds).
`/rr2cast hide` and `/rr2cast toggle` control visibility.
`/rr2cast position` prints the current coordinates.
`/rr2cast move 360 96` moves/clamps the HUD; `/rr2cast reset` restores
default placement. Unknown or extra arguments get a usage hint.
**No CLI command casts, moves the character or starts autoattack**; manual
restricted Cast and Stop macros remain on real mouse-click frames.

## Source gates actually observed

- **71/71 focused Casting Lua 5.1 mock tests pass**, including CLI, defensive
  drag/restore, and failed protected reposition rollback.
- **904 repository-wide Python tests pass; 2 skipped**, full unittest discovery,
  exit 0. Negative-test stderr is intentional and was not treated as failure.
- Lua 5.1 source parsed successfully and `git diff --check` returned exit 0.
- This v0.4.0 slice did **not** change C# files or rerun the full .NET 10
  gate; earlier codebase-bughunt evidence includes those separate results.
  Mocked UI tests cannot establish real RIFT mouse hit testing or secure
  button click dispatch.

Relevant source:
`addon/RiftReader2Casting/main.lua`,
`addon/RiftReader2Casting/RiftAddon.toc`,
`addon/RiftReader2Casting/model.lua` (unchanged),
`tests/test_casting_addon.py`.

## RIFT-Lab-2 deployment (verified files; no UI reload)

- **Target VMX:** `C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx`; VMware
  monitor port **5906**. No Lab-1 access.
- **Game executable:** guest `C:\RIFT_TRANSFER\RIFT\rift_x64.exe` with
  SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
  At deployment, PID **2700**, UTC process start
  `2026-10-28T18:05:39.4270240Z`. **These are historical IDs; reacquire**.
- **Installed guest addon:** `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2Casting`.
- **Preflight / backup / staging / deployment / independent postflight:** all
  verified with exact process identity and file SHA-256. Runner:
  `artifacts/rr2-lab2-hud-deploy-20261028-02/deploy_v040.py`.
  Immutable ignored evidence under
  `artifacts/rr2-lab2-hud-deploy-20261028-07/`,
  run `7c64061e50024a40be59e655e0f1e908`.
- **Final installed hashes (source/stage/guest/postflight agreement):**
  - `main.lua`:
    `7E24D78EEAF589BF76A7E4D59B4F6BE5242D8C8D4947448995C33A60DA945213`
  - `RiftAddon.toc`:
    `F957E327C793073293FFBFC29D98411D9CF1DED9CEA5738A0CC42CFBD087D6B0`
  - `model.lua`:
    `DBD689B9F47140E95153A583E47A445AE3AC35794D293CF58C5D58E1143CE2BC`
- **Rollback:** Not needed. Verified v0.3.0 backup retained in guest Public
  Documents as `RR2CastBackup-7c64061e50024a40be59e655e0f1e908`.
  Temporary staging cleanup requested. Cached guest credentials were reused
  without prompting or revealing them.
- **No input, UI reload, game restart, or live click** occurred during this
  deployment. File installation proves v0.4.0 is staged for the next UI load;
  it does *not* prove the new UI is running yet.

## Next authorized milestone: live UI and CLI acceptance

1. Check fresh repository status, Lab-2-only VMX, process identity/build,
   controller lease and screenshots. Do **not** act on the historical PID or
   pixel rectangles from older casting handoffs.
2. Ask Joey to type `/reloadui` **in the RIFT-Lab-2 client**. Confirm the
   HUD title **RR2 CASTING v0.4.0** and one teal-green chat initialization
   notification. If missing, preserve screenshot and addon-load errors.
3. Run `/rr2cast help`, `status`, `info`. Confirm colored legible lines,
   sensible blocked/unknown data, and non-misleading facing/LOS warnings.
4. Drag the blank part of the HUD header, then open Abilities and drag the
   picker title. Verify both move their associated panel, and the separate
   protected Cast/Stop row stays aligned without a click being consumed as a
   cast. Check viewport clamping and readable Hide label.
5. Use `/rr2cast position`, `move 360 96`, `reset` as a reliable fallback
   if mouse dragging fails; record exact warnings. After a **second reload**,
   verify the saved position actually persisted. RIFT character SavedVariables
   are saved asynchronously; inspect resulting evidence, not just the code.
6. Only with fresh manual screenshot/target review and a designated training
   dummy, optionally validate protected Cast/Stop click dispatch. Do not
   assume API READY proves a clear shot. The release does not automate spells.
7. Obtain fresh **current-build** `Inspect.Documentation` and relevant API
   evidence through the established saved-evidence pipeline. Investigate
   general facing/yaw and hostile LOS separately; the older documented
   group-member-only `blocked` property is **not** generic hostile LOS.
8. Capture a fresh RIFT screenshot with **Numpad \*** into
   `C:\Users\mrkoo\OneDrive\Documents\RIFT\Screenshots`, now a Workbridge
   readable root. It confirms appearance, not click dispatch.
   If `Inspect.Mouse().Left` is absent/changed on the live build, the drag
   intentionally cancels; use CLI move while reviewing current API evidence.

**Do not claim live v0.4.0 dragging, position persistence, chat notice or
protected-action click success until individually observed.** An addon
`/reloadui` does not qualify full-game restart durability.

## Broader follow-up (separate from release acceptance)

The current dashboard is an improvement, not a final professional design
system. Review it holistically after current-version screenshots: consistent
control states, focus/hover, readable typography, spacing, scalable/clamped
layout, hierarchy, status semantics and the secure-action boundary. Keep
facing/LOS visibly unverified until actual current-game evidence supports
implementation; avoid fabricating clear-shot readiness. Continue RR2's
durable restart-aware native reader and discovery roadmap only after the
short live UI acceptance loop. Patch recovery remains deferred.
