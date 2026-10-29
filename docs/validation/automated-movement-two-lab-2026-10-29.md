# Automated movement on both labs — October 29, 2026

**Authorized window:** through 2026-10-29 22:04:30Z. **Goal:** demonstrate
bounded, reliable **closed-loop** player movement on both labs. Repeated key
delivery alone is not success: every decision must use a newer exact-identity
addon/API position, and each trial must stop safely on stale or contrary data.

**Current result:** Lab-1 has one accepted bounded 2-D arrival. Repeatability
and any accepted Lab-2 arrival remain unproved; Lab-2 is not reliably ready, so
the two-lab goal is not yet met. Primary evidence is the current-identity
[Lab-1 calibration](../../artifacts/two-lab-movement-20261029/lab1-calibration-run-06/result.json),
[accepted goal result](../../artifacts/two-lab-movement-20261029/lab1-goal-run-05/result.json),
and [final input status](../../artifacts/two-lab-movement-20261029/lab1-goal-run-05/final-status.json).

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
5. Once the final action's fresh feedback is in tolerance, issue explicit STOP
   and disarm within the 12-second motion budget. Then allow one separate,
   bounded no-input confirmation of at most three seconds. It must strictly
   advance and remain in tolerance; it cannot extend the arm or permit another
   action. Finish with idle/no-input status and free queue cleanup. Repeat
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
| Fresh reader and exact-identity movement preflight | Third reader reliable in matched sample: 95/95 fresh | Bound/fresh observed, but unreliable: 40/56 fresh in three-minute sample |
| Reviewed measured-key calibration with release and advancing positions | [Proved in run 06](../../artifacts/two-lab-movement-20261029/lab1-calibration-run-06/result.json): W 0.927, Q 0.934, cross 0.999969 | [Proved 1-D in run 07](../../artifacts/two-lab-movement-20261029/lab2-calibration-run-07/result.json): S 0.662 planar; exact profile `A0FCD163...` |
| Separate one-arm goal run with at least two feedback decisions | [Proved by run 05](../../artifacts/two-lab-movement-20261029/lab1-goal-run-05/result.json): Q 74 ms + W 73 ms, two fresh feedback iterations | Goal runs 01 and 02 failed pre-ARM stale/no input |
| Final-action feedback plus advancing no-input settle within tolerance | [Proved by run 05](../../artifacts/two-lab-movement-20261029/lab1-goal-run-05/feedback/next-734-735-receipt.json): final distance 0.118824, advancing same-position settle | Not reached |
| Session STOP/disarm/no-input/free-queue cleanup | Run 05 and final system cleanup proved | Failed-attempt and final system cleanup proved |
| Independent successful repeat for reliability | Run 06 failed post-Q stale; not proved | No accepted arrival to repeat |

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
  4.5 seconds. At that stage, no Lab-1 calibration was accepted.
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

The rollover used published executable SHA
`A5B0D60DBB09CC1F2BE5DB0A9535F0EFB3A2CCE8D65765B3FAE6D68AF150C2E7`.
Lab-1 calibration run 05 then succeeded under reader PID 7120 and its pinned
instance/nonce: a 150 ms W pulse displaced 1.019 planar units and a separately
observed 150 ms Q pulse displaced 0.863, with normalized cross 0.99996, clean
release and advancing exact-identity receipts. Its nonce later rotated before
goal planning; the cause of that rotation was not retained. This is
valid historical calibration evidence but not authority to act under a
successor identity. Offline waypoint replay is reference-only.

Lab-2's rollover challenge did not stay matched, and the Lab-1 reader continued
streaming under a newly rotated nonce. That challenge change invalidated the
historical calibration profile; it is not evidence that guest PID 7120 exited.
Both feeds continued delivering receipts, but unbound delivery is not a usable
position source. A third reader, fresh bind/preflight and new same-identity
calibration are therefore required before either remaining goal run; no prior
arm grant or position may carry over.

Checkpoint `369303c` corrects the scan acquisition-interval clock. The prior
timestamp defect is proved; treating it as the cause of every earlier binding
loss would be inference. Clean gate
`artifacts/validation/20261029T211217Z-4bd9b2b1` passed 549 .NET tests (366 core
+ 183 Live), ran 1,055 Python tests (1,053 passed, two skipped), and passed the
native/Lua checks and 772 documentation links. Third-reader rollover is
authorized with executable SHA
`33A21D0B32BD1C3978CABDFE7EC9C43A0413DB3B4B0654C3BBF8516EAD07F71B`.
The receipt journal retains each byte-distinct receipt it observes from both
feeds; sequence gaps mean it is not proof that every producer receipt was
captured. At that checkpoint, third readers were running as Lab-1 guest PID 6424 / nonce
`906b999c...` and Lab-2 guest PID 7132 / nonce `5c65d5c6...`; both feeds reached
bound/fresh state on their pinned source and expected game identity. Lab-2
still needed a qualifying current-identity calibration and goal run; subsequent
results and terminal cleanup are recorded below.

Lab-1 calibration run 06 is the first current-identity calibration accepted for
goal use: under guest reader PID 6424 / nonce `906b999c...`, independent 150 ms
W and Q actions displaced 0.927 and 0.934 planar units respectively, with
normalized cross 0.999969, clean release and advancing pinned receipts. Lab-2
run 03 has not yet produced a qualifying calibration result artifact. Lab-1
goal preparation may use run 06 only while that exact reader identity remains
current; the historical run-05 vectors remain excluded.

Checkpoint `2235569` adds pre-arm waiting, explicit one-dimensional mode and
starts the motion timer only after arming. Gate
`artifacts/validation/20261029T213423Z-c1f112c7` passed 549 .NET tests and ran
1,062 Python tests (1,060 passed, two skipped), plus the native/Lua and link
checks. Lab-1 goal run 03 produced two accepted action-feedback iterations,
ending 0.09578 units from its target, followed by a distinct fresh no-input
same-position receipt. The run nevertheless failed because the settle check
crossed the 12-second elapsed budget; it is **not** an accepted arrival.

The then-required transport correction requires STOP/disarm before the bounded
no-input confirmation and keeps that confirmation outside the 12-second motion
budget without extending or renewing the arm. Lab-2 calibration run 04 failed
before ARM on a 4.5-second stale initial observation and sent no input. Its
calibration was unproved at that stage.

[Lab-2 reader-03 reliability diagnosis](../../artifacts/two-lab-movement-20261029/lab2-reader03-reliability-diagnosis-20261029T214700Z.md)
found a 56.7-second no-fresh outage overlapping calibration run 06, including
two Win32 299 read failures and 6–9.4-second scans beyond the five-second
freshness limit. Across three minutes, Lab-2 was fresh for 40/56 samples
(71.4%), with p90 scan time 5.642 seconds and maximum 9.428; same-window Lab-1
was 95/95 fresh, p90 1.501 seconds, maximum 2.698. The failure recurred after a
short recovery (outer 615 timed out at 10.002 seconds; outer 616 completed in
7.700 seconds but was already expired). A short readiness streak therefore
does not qualify Lab-2. Tracked-range or cached-candidate scanning remains a
future recovery candidate, not a proved fix.

With that transport correction applied, Lab-1 goal run 05 is an accepted
bounded 2-D arrival. It used exactly two feedback-driven actions—Q for 74 ms,
then W for 73 ms—under the calibration's pinned reader/game/player identity.
The final action feedback was 0.118824 units from the goal. A later no-input
receipt strictly advanced outer sequence 734 to 735 and addon sequence 3685 to
3689 while retaining the same XYZ, satisfying the settle condition. Total key
hold was 147 ms. The retained final status proves disarm and no sampled inputs
down; queue receipt sequence 169 succeeded with holder null and blocked count
zero. The host's persistent console reservation is expected ownership, not a
movement-session queue leak. One arrival does not yet establish repeatability;
the final two-lab trial cleanup was still pending at that checkpoint.

Checkpoint `1a07583` corrects the final feedback barrier and released-settle
sequence. Gate `artifacts/validation/20261029T214459Z-fb6d85e6` passed 549 .NET
tests, ran 1,068 Python tests (1,066 passed, two skipped), and passed the
native/Lua checks and 778 documentation links. Lab-2 calibration run 07 then
accepted a bounded 1-D S profile: 150 ms displaced 0.662102 planar units with
-0.419983 vertical change, exact profile SHA `A0FCD163...`, followed by clean
cleanup. Lab-2 goal run 01 failed before ARM on stale data and sent no input.
Lab-1 repeat goal run 06 failed on stale post-action feedback. Neither the
Lab-1 reliability repeat nor a Lab-2 arrival is yet accepted.

Lab-2 goal run 02 also failed before ARM on stale data and sent no actions,
despite two preceding fresh readiness observations. Live input scope is now
closed with no further movement attempts planned. The final outcome is partial:
one Lab-1 2-D arrival, no successful repeat, and no Lab-2 arrival. Reliable
automated movement on both labs is therefore **not proved**.

The [accumulator microbenchmark](../../artifacts/two-lab-movement-20261029/accumulator-microbenchmark/README.md)
supports a lower-risk next candidate: reuse the feed scanner's scratch buffer.
Across 256 MiB, baseline checkpoint `1a07583` allocated 302,575,608 bytes
(73,871 per 64 KiB chunk) and took 61.6–67.2 ms; the isolated reused-scratch
prototype allocated
40 bytes and took 14.1–15.1 ms while producing byte-identical cross-boundary
output. A Lab-2 full scan extrapolates to about 2.71 GiB managed allocation.
This is accumulator-only evidence, not proof of a fourfold whole-scan gain or
that allocation caused Win32 299. The production reuse change and two focused
tests were committed as `2d38866`; final gate
`artifacts/validation/20261029T215649Z-6e2ed889` passed 551 .NET tests (366 core
+ 185 Live), ran 1,068 Python tests (1,066 passed, two skipped), and passed the
native/Lua checks and 781 documentation links. It was **not deployed** to either
lab: all reported live trials used reader SHA `33A21D0B...`, so live scan impact
remains unmeasured. Tracked-range scanning remains a broader, higher-risk
alternative.

## Final cleanup

Cleanup completed at 22:02:53Z. The authoritative
[cleanup summary](../../artifacts/two-lab-movement-20261029/final-cleanup-02/summary.json)
is `trial-cleanup-resumed-complete` and references the exact reader-stop receipts
retained in `final-cleanup-01`; Lab-2's receiver was stopped exactly,
while Lab-1's receiver had already ended for an unobserved reason. Typed listener
count was zero and terminal artifact hashes were retained. Independent
[final host status](../../artifacts/two-lab-movement-20261029/root-final-host-status.json)
confirms both native hosts connected/ready, disarmed, not busy, with no sampled
inputs down, no recovery requirement and free queues. RIFT game PIDs 6876 and
4200 and both control agents were intentionally preserved.
