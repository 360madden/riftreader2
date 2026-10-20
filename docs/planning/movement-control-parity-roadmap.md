# Movement-control parity: durable roadmap (RIFT-Lab)

State: COMPLETE within visual/API evidence limits. Checkpoint: 2026-10-20. This file is the primary resumption record for **backward (S), left (A), right (D)** parity with the prior forward (W) supervised pulse.

## Objective and boundaries

Bring S/A/D to the **same measured evidence level** as the earlier W test: currently bound VM and game, fresh visual review, short key-down/key-up, independent newer before/after readback, and defensible classification of the observed action. Do not confuse key delivery with game response. In RIFT, A/D may be **turn** or **strafe** depending on bindings; test rather than assume. Navigation/pathfinding/combat and persistent unattended input are outside scope.

Use the existing V1 VM console, game-session checks and receiver unmodified, via the small V2 experiment adapter. Preserve other repositories. Only one owner controls VM input and recovery at a time. No long pulses, loops, automatic replays, or input retries with uncertain delivery.

## Phase board (change states only with evidence)

| ID | Work | State | Acceptance / durable evidence |
|---|---|---|---|
| MC-00 | Baseline/inventory | DONE | Clean codex/modular-foundation worktree observed, code and historical W record inspected. V1 controller/guest tool reuse confirmed. |
| MC-01 | Reacquire live readiness | DONE | Current VM PID/start, guest game PID/start/window/build, active observer, host receiver *destination* and fresh sequence, foreground world and release/stop state all verified. Recover expired/stale feed using existing lab infrastructure, not old data. |
| MC-02 | Evidence plan and key semantics | DONE (visual scope) | Decide how XYZ and yaw/rotation will be measured with independent post-release evidence. Verify current game bindings, distinguish turning vs strafing, choose conservative displacement/angle thresholds and capture errors. |
| MC-03 | Offline parity tests/code | DONE (bounded scope below) | W/S/A/D happy paths, invalid key and 20–250 ms bounds, identity mismatch, stale/unreviewed screenshot, duplicated plan, stop/cancel, key-up uncertainty, no advancing sample, wrong epoch, bounded readback. Fix documented V2 issues only, don't refactor working V1 without cause. |
| MC-04 | Supervised live trials | DONE | One separate fresh prepare/review/run for S, A, D (and optionally W as current baseline); verified release and advancing post-sample, saved screenshots and before/after XYZ/heading evidence. 20–100 ms first, no blind sequences. |
| MC-05 | Interpret/remedy | DONE | For each direction classify delivery/release, movement/heading change or inconclusive. Re-test any corrected V2 defect; do not claim A/D turn if only lateral position changes. |
| MC-06 | Full validation and commit | DONE | Run PowerShell 7 full gate, inspect exit codes and logs, write dated validation note, update docs/status.md, commit only validated task files and this roadmap. No push. |

Blocking MC-01 does not block offline MC-02/03 work; document that distinction.

## Historical October 19 checkpoint — superseded below

- 2026-10-19 around 12:27 UTC: host vmware-vmx PID **54820** running. This is **not** proof the guest game is currently responsive.
- Existing V2 example receiver file (artifacts/experiment-validation/receiver/latest.json) was **25,633 seconds old** at 12:27:25 UTC; its target was old game PID **11620**, sequence 1976. This file is **stale** and MUST NOT be used to authorize input or claim current game observations.
- 12:29 UTC: host TCP port 49712 had a listener owned by PID **27028**, while Python PIDs 48380/27028 existed. Listener presence alone does not establish output destination or correct guest-token identity. Inspect those process command lines and confirm receiver output path before any changes; avoid competing listeners.
- Historical later RIFT PID **8356** was documented after a restart at 09:11 UTC. Do not treat historical PIDs as current; reidentify current guest process/window/build.
- V1 vm_console.py accepts w/a/s/d for 20–250 ms and performs keyDown/keyUp; V2 scripts/rift-experiment.py invokes it. Prior October 19 W pulse was recorded in docs/validation/experiments-2026-10-19.md; S/A/D have **no corresponding live V2 evidence yet**.
- No new input, game/VM restart, code edit or receiver restart was done in this task before this roadmap. Original session controller state has a STOP file, so examine the current controller state; never silently clear an existing stop latch.
- Repo baseline clean at time of preflight. Do not presume it remains so on resume.

## Resume protocol (follow in this order)

1. Read AGENTS.md, this roadmap, docs/status.md, and most recent relevant docs/validation note. Inspect actual Git status/HEAD. Never assume this checkpoint represents current running processes.
2. Pick the first ACTIVE/BLOCKED/TODO phase with prerequisites satisfied; reuse verified DONE artifacts rather than rediscovering. Check Workbridge command_status/output for previously recorded request/job IDs; do not duplicate uncertain operations.
3. Reacquire **current** VM/game process identity, build/window/foreground, live observer sequence, receiver/output/token binding, screenshot freshness and any pending release/STOP. A working VMware UI alone is insufficient. Refuse input on stale or incomplete status.
4. For each live direction: prepare one reviewed 20–250 ms pulse with scripts/rift-experiment.py, inspect the **new** screenshot, then run the exact single-use plan **within 45 seconds**. If review expires, prepare a new plan. On unconfirmed release, stop/recover before a new attempt. Do not invoke direct VNC keypresses or bypass guards.
5. Keep outputs in ignored artifacts/experiments or an explicitly unique ignored validation run. Save UTC time, exact VM/game/observer identity, key, hold request/observation, hashes, reviewer note, raw before/after, delivered/released status, result classification and limitations. A failed/rejected run is useful evidence and must remain recorded.
6. Checkpoint after each meaningful phase/substep: update this phase board + the checkpoint below, link any dated validation report, and commit verified coherent slices. Only then do the next live pulse.

## Existing commands (host PowerShell in C:\work\riftreader2)

Use installed Python C:\rift modding\VMs\RIFT-Lab\controller-env\Scripts\python.exe.
- Offline: python -m unittest discover -s tests -p test_experiment_core.py -v
- Live (only after preflight): python scripts/rift-experiment.py --config artifacts/experiment-validation/config.json prepare --key s --hold-ms 100
- Review returned new screenshot; run with EXACT single-use --plan path and an accurate --review-note while fresh.
- Repeat separately for a and d (never automatically).
- Recovery: scripts/rift-experiment.py with same --config, action stop or recover.
- Full gate: pwsh -NoProfile -File scripts/validate.ps1.

The example config is historic. Validate its receiver observation path/guest binding first; create an appropriate per-run config if needed.

## Coordination, reporting, model metadata

Concurrent lanes if subagents are genuinely available: CODE (V2 experiment implementation), TEST (narrow parity regressions), LIVE (sole VM and receiver operator), DOC (this file / validation note / status). Exclusive file ownership, one LIVE actor; coordinator integrates after each phase. Without available subagents, operate these lanes sequentially.

For every result report *observed* model/provider data only: model family GPT-6; exact variant blank; reasoning effort Extra High **as displayed in user's UI screenshot**, not independently backend attested. Future runs leave unknown model/effort fields blank rather than guessing. Git authorship is not model provenance.

## Historical October 19 execution checkpoint

Last completed phase: MC-00 (inventory and read-only preflight).
Currently blocked phase: MC-01 (stale historical receiver receipt, current guest feed unverified).
Next actions: identify PID 27028 command line/destination and current guest observer; use installed receiver only when identity is established. Parallel offline MC-03 regressions can proceed now.
Latest test or live job IDs: rr2-move-host-readiness-20261019-01; rr2-move-receiver-readiness-20261019-01; rr2-move-processes-20261019-01 (all passed; passive checks, no VM input).
Unresolved: current guest PID/focus/build, live observer receipt destination, A/D turn vs strafe, trustworthy heading reference.

## October 20 live resumption

Joey selected RIFT-Lab-1 (display name of the original RIFT-Lab VMX).
The host launcher was rejected for Windows group/admin permissions; Joey started
it manually. Current VM PID 39056, start ticks 134369666367568339.
Fresh receiver be57ffb257e443b0b11b0fac024a4575 writes under
artifacts/movement-parity-20261020/receiver. Fresh GuestReadback observer binds
RIFT PID 3400, start 2026-10-19T20:37:36.4351086Z, historical build hash 7C356C9D...17BD.
Old session controller has pending=null and STOP; preserve it until explicit
new prepare. MC-01 readiness acquired. MC-02 bindings screenshot confirms
S=Move Backward, A=Turn Left, D=Turn Right (Q/E strafe). No heading is exposed
by this receiver. Use before/after XYZ plus visual comparison; do not infer
heading from coordinates. A 0.05 coordinate-unit displacement threshold is an
analysis choice, not calibrated noise. Angular change remains visual/unmeasured.
Start with one reviewed 100 ms pulse each; inconclusive is an allowed result.
MC-03: 19 focused experiment tests pass, including new four-key boundary,
invalid key, stop, post-input epoch, and post-release advancement tests.
Screenshot freshness remains enforced by the unchanged V1 console guard.
MC-04 is next. Retained evidence: artifacts/movement-parity-20261020/.
`MC-04 S`: run 4cac8951b7ad4ee997e4c63c9e788b8b completed, 100.6712 ms hold, release sent, fresh post-sample and matching identities. No repeat input required.
`MC-04 A`: run f2f8a30dae6f46febc57318aab254f7c completed, 100.7244 ms hold, release sent, fresh post-sample and matching identities. XYZ unchanged; screenshot shows viewpoint rotation consistent with verified Turn Left binding, no measured yaw.
`MC-04 D`: run 8a79ca4855264a73a29d87a887790b09 completed, 100.4704 ms hold, release sent, fresh post-sample and matching identities. XYZ unchanged; visual rotation reversed A, consistent with Turn Right binding. All three trials complete; stopped/recovered afterward with no pending release. MC-05 interpretation complete at visual/API scope; MC-06 full gate pending.



## Current checkpoint — October 20 completion

MC-00 through MC-06 are complete within the recorded scope. The full gate
passed (273 C#, 121 Python, 108 Lua assertions, 22 Lua/C# cases, 229 links).
See [the validation record](../validation/movement-parity-2026-10-20.md).
Controller STOP is restored, recovery reports pending=null and paused=true.
Receiver/observer remain active; RIFT remains in-world. Reacquire identity and
freshness before any later input. Do not replay S/A/D just to recreate context.
No measured yaw, game-key-state attestation, hard-crash recovery or field
qualification is claimed. Next discovery is targeted changed-state health and
resource evidence; numerical heading qualification is separate future work.
