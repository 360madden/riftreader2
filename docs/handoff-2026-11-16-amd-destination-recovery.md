# RR2 handoff — verified destination recovery planning (AMD-DESKTOP)

**Checkpoint:** 2026-11-16, approximately 08:08 EST (America/New_York)
**Project:** `C:\work\riftreader2`
**Verified machine:** **AMD-DESKTOP**, independently confirmed by local `hostname.exe` through AMD-DESKTOP Workbridge on this checkpoint. **Do not use LEGION or VMware labs in this session.**
**Branch:** `codex/modular-foundation`
**HEAD observed:** `6615c278090ba47259c2e0b312341615b4d1766d` (tracking `origin/codex/modular-foundation`, no ahead/behind indication).
**Connector:** AMD-DESKTOP Workbridge `0.16.5-dev`, root `C:\work`.

## Outcome: real code delivered, not live destination acceptance

The destination planner now handles a failed/stopped journey as three distinct steps, each preserving the current Waypoints route and STOP controls:

1. **Verify arrival after execution** — After a worker reports completion, independently refresh a same-process/same-player native pose and check actual destination approach tolerances. A route receipt alone cannot prove arrival.
2. **Record a recovery start after halt/STOP** — For a trusted `halted` or `stopped` run, check release/key-up and acquire a new read-only native player pose, recording `recoveryObservation` and `recovery.startNativeXYZ` in the original `plan.json`. The original terminal failure remains intact.
3. **Make a fresh replacement candidate** — `--from-recovery-plan PATH` consumes the earlier halted `plan.json`, then verifies old route/receipt hashes and release, original destination/map sources, exact session/process/player, unchanged STOP epoch/latch, and a fresh position within 0.30 planar / 0.50 height units of the recovery handoff. Only then does it query RiftWorld into a *new* output directory. It never starts gameplay input, clears STOP, automatically adopts a route, or starts a retry.

### Commits for the current destination/recovery chain

| Commit | Delivered |
| --- | --- |
| `49eecc0` | Independent fresh post-route native destination arrival verification |
| `b1c9bef` | Do not retain arrived substatus when post-run pose is unverified |
| `b30c9b1` | Fresh, read-only recovery start after trusted halted/stopped run |
| `cabeca4` | CLI/plan-only replacement candidate from a verified recovery plan |

These four commits were pushed successfully to GitHub. The branch subsequently advanced through **other developers' survival/HP commits**, including `2f5247d`, `7095d66`, `fa0634f` and `6615c27`. Their commit presence is confirmed; this handoff does **not** claim independent validation of those later HP changes.

### Verification actually performed

On **AMD-DESKTOP**, for commit `cabeca4`:

- `C:\Python314\python.exe -m unittest tests.test_waypoint_destination_plan -v` → **65/65 PASS**.
- `C:\Python314\python.exe -m unittest tests.test_waypoint_candidate_adoption tests.test_waypoint_external_route tests.test_waypoint_destination_plan` → **79/79 PASS**.
- `git diff --check` for the three changed waypoint files → **PASS**.
- `python scripts\waypoint_destination_plan.py --help` → **PASS**, with `--from-recovery-plan` advertised.
- All above are **offline/fake-runner validation**. **No new live RIFT movement or physical end-to-end destination arrival was tested by this workstream.**

## Resuming the actual CLI flow

Start in `C:\work\riftreader2` on freshly verified **AMD-DESKTOP**, and follow the prepared-map example in `docs/workflows/physical-waypoints.md`. For a newly halted run that actually recorded `recovery.status=fresh-native-start`, repeat the same catalog/patch/build/destination selection, using:

```powershell
.\.venv\Scripts\python.exe scripts\waypoint_destination_plan.py `
  --catalog PATH_TO_DESTINATIONS_JSON `
  --destination SAME_DESTINATION_ID `
  --patch PATH_TO_EXACT_PATCH_JSON `
  --build PATH_TO_EXACT_NAVIGATION_JSON `
  --from-recovery-plan PATH_TO_HALTED_PLAN_JSON `
  --session EXACT_EXISTING_WAYPOINTS_SESSION `
  --out-dir NEW_UNUSED_OUTPUT_DIRECTORY
```

Expected plan-only outcome on a complete, matching map query: `status=planned`, `startSource=verified-halt-recovery`, `recoverySource` recorded, `stages.adoption=native-evidence-required`, `inputSent=false`, `currentRouteChanged=false`. A changed source/owner/STOP/position is a **refusal**, never permission to reuse old evidence or automatically resume.

The new candidate is **not yet a qualified executable route**. Existing `--from-current --session` remains available for an entirely new read-only planning request when an old recovery handoff no longer qualifies; do not silently substitute it inside the recovery mode.

## Highest-value next work

1. **Complete one physical destination loop** on a qualified short safe route: prepared RiftWorld source → independently corresponding walked/native corridor evidence → scoped route adoption → separately authorized bounded execution → fresh post-release native arrival. Inspect the full outcome including survival; do not treat a Detour output or worker completion alone as success.
2. **Close the recovery-to-route qualification gap** for a new segment. Current recovery mode generates a candidate, but cannot automatically assert novel swept clearance or adopt that candidate. Reuse existing RiftWorld/Detour evidence and RR2 adoption validators; keep incomplete or unknown corridor segments non-executable. If collision and terrain evidence are missing, report the precise missing section rather than promoting a guess.
3. **Integrate travel survival before full-autonomy claims.** Avoid unsuitable hostiles; ensure shared movement/combat ownership, STOP, release, health/threat validity, bounded retreat and explicit checkpoint semantics. Peer work exists, but a complete real-world safe-to-destination trial remains unverified.

Keep the next implementation as small as possible. CLI first, GUI over shared behavior later. No speculative framework, broad refactor, or cleanup milestone is needed to resume productive development.

## Exact safety / evidence boundaries

- Operate only the independently verified machine. The historical VM labs are retired for active RR2 work. With physical multibox, bind the exact PID and game process start/build/player; never assume the old PID remains valid.
- STOP is latched until explicit Resume/new run. One input owner. Require trusted release and idle status before any next action. **Creating this handoff does not authorize game input.**
- The current RiftWorld destination pilot is a named historically walked courtyard endpoint, **not** a completed service/NPC interaction, general region navigation, verified world-screen transform or universal collision proof.
- Handoff source hashes/poses only qualify the exact original sources and process/STOP epoch; they are not durable permission to move.
- `docs/planning/implementation-roadmap.md` is the overarching product priority, and `docs/workflows/physical-waypoints.md` documents current destination CLI and evidence semantics. The broader product goal is a local autonomous player with survival/combat/progression, not merely the manual Waypoints GUI.

## Concurrent work to preserve

At the 08:08 EST inspection, Git status was synchronized but **not clean** because other active lanes had uncommitted work, including:

- Modified: `docs/reference/third-party-workflow-tools-2026-11-12.md`, `scripts/fresh_native_actor_pose.py`, `scripts/hunt_mission.py`, `scripts/waypoint_navigation_candidate.py`, `tests/test_fresh_native_actor_pose.py`, `tests/test_hunt_mission.py`.
- Untracked: `.playwright-cli/`, `output/`, `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `scripts/target_acquire.py`, `scripts/target_cycle.py`, `scripts/target_selection.py`, and their corresponding test modules.

**Preserve all of these.** Before any next edit, recheck `git status` and HEAD; do not stage, discard, rebase or overwrite another developer's files. Commit only owned, verified changes and push non-force when authorized.

## One-minute next-session checklist

1. Bind AMD-DESKTOP Workbridge; execute a machine-local hostname check and reject wrong host.
2. Read `AGENTS.md`, this handoff, current `git status/log`, and relevant waypoint guide/roadmap sections.
3. Re-run the 79 related offline tests if touching destination/adoption, then choose the smallest live-qualified route/terrain step.
4. Before any real RIFT run, establish fresh explicit PID, game build/start, player/STOP, controller ownership, requested authority, key release and survival readiness. No automatic retry from a stopped receipt.
5. Preserve distinct source-map candidates, independently walked evidence and actual post-release player observations; report failures and successes by their real evidence level.
