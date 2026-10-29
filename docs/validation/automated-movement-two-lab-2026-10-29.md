# Automated movement on both labs — October 29, 2026

**Authorized window:** through 2026-10-29 22:04:30Z. **Goal:** demonstrate
bounded, reliable **closed-loop** player movement on both labs. Repeated key
delivery alone is not success: every decision must use a newer exact-identity
addon/API position, and each trial must stop safely on stale or contrary data.

## Starting evidence and constraints

The immediately preceding hour closed at 19:57Z with both final native hosts
connected and ready: Lab-1 PID 13240 and Lab-2 PID 51968, both disarmed/idle,
no sampled inputs down, and both queues unblocked with no holder. Their game
PIDs were 6876 and 4200 respectively on executable SHA `1935A05C...0A4BE8`.
Those retained facts come from
`artifacts/two-lab-hour-20261029/final-host-verification.json` and
`final-idle-status.json`; they are a baseline, not authority to skip a fresh
preflight.

Useful live capability already proved on both labs:

- exact-build addon/API XYZ feeds and bounded native W/S pulses with clean
  release and independently newer positions;
- W/S translate along the current body direction; A/D are visually consistent
  with turn left/right, but **no numerical body-facing field is qualified**;
- the guidance bearing is coordinate-axis bearing, not facing or steering;
- this objective uses isolated receiver ports 49813/49923, distinct tokens and
  pinned source addresses. `cadence-soak-01` proved simultaneous, correctly
  routed delivery; each movement run must still verify its live source identity.

No ability is needed for this objective. Light's Balm/Power and the casting
readout are useful separate evidence paths, but the current executable rejects
the old native-Power recipe and facing/LOS remain unverified. Avoid combat,
targets and ability activation during movement qualification.

## Smallest useful closed loop

Use **separate calibration and goal runs** with empirically measured key vectors,
avoiding an invented facing angle or a new pathfinder. Durable component names
are `movement_feedback` (fresh observation producer), `movement_controller`
(bounded feedback decisions), and `run_movement_session` (reviewed transport):

1. Freshly verify VM/game/host identity, foreground in-world state, closed chat,
   clear ground in both travel directions, idle inputs and free queue. Start one
   exact-lab reader/feed and freeze a fresh position.
2. In a calibration run, take one root-reviewed screenshot and one 15-second
   arm grant; never auto-rearm. Measure W and Q independently, requiring clean
   release and a newer same-game/nonce/player/epoch position after each action.
   S or E may be added only when separately measured. Reject displacement below
   0.05 units or an implausibly large/cross-map change. Do not infer S from W,
   E from Q, or yaw from any translation.
3. Derive only the observed horizontal action vectors. Choose one concrete
   nearby target inside the reviewed clear corridor and reachable by a bounded
   combination of the measured vectors. This is not arbitrary 2-D navigation.
4. Start a separate goal run with a new root-reviewed screenshot and exactly one
   15-second arm grant. After **every** action, require an advancing fresh API
   observation, recompute the feedback decision, and retain action/release/source
   evidence. The goal run must include at least two post-goal feedback decisions;
   open-loop replay of the calibrated sequence is insufficient.
5. Stop only after two in-tolerance observations total: the final action's fresh
   feedback plus one strictly advancing no-input settle sample. Finish with
   explicit STOP, idle/disarmed/no-input status and free queue cleanup. Repeat
   independently on the other lab; the two distinct receivers may run
   concurrently only with exact endpoint/token/source identities verified.

Fail closed on changed identity, stale/unavailable source, failed release,
recovery requirement, focus loss, dialog/text-entry uncertainty, combat, queue
loss, two consecutive non-progress pulses, distance growth on two decisions,
cross-track error over 0.50 units, more than six actions, more than 900 ms total
key hold, more than six units from the run origin, or more than 12 seconds for
the armed run. Never cache an old position as current, silently rearm after the
arm grant expires, or compensate by lengthening a blind key hold.

## Acceptance matrix

| Evidence | Lab-1 | Lab-2 |
| --- | --- | --- |
| Distinct receiver endpoint/token/source isolation | Proved by concurrent cadence soak | Proved by concurrent cadence soak |
| Fresh reader and exact-identity movement preflight | Rollover reader launched; rebind pending | Rollover reader launched; rebind pending |
| Reviewed measured-key calibration with release and advancing positions | Blocked twice: no accepted after-feedback | Rejected: S measured, but Q was exactly zero; E remains unknown |
| Separate one-arm goal run with at least two feedback decisions | Pending | Pending |
| Final-action feedback plus advancing no-input settle within tolerance | Pending | Pending |
| Per-attempt STOP/disarm/no-input/free-queue cleanup | Proved for failed attempts | Proved for failed attempts |

Success requires both columns through cleanup. A single pulse, endpoint-only
comparison, visible scene change, or one lab completing does not qualify the
two-lab goal. The bounded straight-line controller would establish practical
position-feedback movement only—not numerical facing, inverse-key equivalence,
obstacle avoidance, arbitrary routing, autonomous combat, or unattended
long-distance navigation.

## Live progress

At 20:15Z the native lab Codex chats independently reconfirmed the expected
identities: Lab-1 RIFT PID 6876 / start ticks 639288974836522510 with control
agent PID 7676; Lab-2 RIFT PID 4200 / start ticks 639288974754421524 with agent
PID 8536. Both addon reloads completed at approximately 20:28Z. Reload reopened
the readiness/casting panels, so the existing separately reviewed `hide-addon`
helper is being used before new nonce binding; panel closure must not be inferred
from reload success alone.

Implementation checkpoint `0e2af08` added the bounded feedback controller,
pinned observation producer and reviewed session transport. Its gate artifact
is `artifacts/validation/20261029T203202Z-260733df`: 1,053 Python tests run,
1,051 passed and two skipped.

The first-reader calibration attempts produced only fail-closed results:

- Lab-1 runs 01 and 02 encountered only feedback barriers and obtained no
  accepted after-observation, ending in bounded feedback timeouts at 3.0 and
  4.5 seconds. No Lab-1 calibration is accepted.
- Lab-2 run 01 accepted an S response of approximately 0.890 planar units with
  -0.400 vertical change, then accepted exactly zero displacement for Q. The
  required independent action basis was correctly rejected.
- Lab-2 run 02 accepted an S response of approximately 0.402 planar units with
  -0.240 vertical change. The E step encountered a barrier and then freshness
  timeout before accepted feedback. E is **unknown**, not proved blocked or
  stationary.

All attempts stopped and cleaned up normally. They are not closed-loop goal
runs. Checkpoint `d382173` adds bounded scanner retry, a 4.5-second feedback
window and 250 ms reader polling. Clean gate
`artifacts/validation/20261029T204440Z-7fbc01a3` passed 545 .NET tests (362 core
+ 183 Live), ran 1,055 Python tests (1,053 passed, two skipped), and passed the
native/Lua checks and 770 documentation links.

Both replacement readers now run published executable SHA
`A5B0D60DBB09CC1F2BE5DB0A9535F0EFB3A2CCE8D65765B3FAE6D68AF150C2E7`:
Lab-1 PID 7120 and Lab-2 PID 4708, with distinct instances and nonces recorded
in `receiver-ownership-rollover-02.json`. The old readers stopped cleanly.
Reload/rebind and a new exact-identity preflight are in progress; no prior
observation or arm grant carries into the replacement-reader trials.
