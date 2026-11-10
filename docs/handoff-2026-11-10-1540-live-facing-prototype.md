# RR2 handoff — two-lab live turning to a working facing prototype

**2026-11-10, 15:40 EST.** Authoritative host verified by Workbridge `computerName=AMD-DESKTOP`; source `C:\work\riftreader2`, branch `codex/modular-foundation`. No RIFT input, VM/controller changes, or new live capture were made while writing this handoff. Latest known Git HEAD before this handoff: `1c276c2`.

## Result worth carrying forward

- **Historical body facing is real on the October 18 V1 executable build**, not just a guess. Camera-only rotation left body yaw unchanged; A/D caused opposite signed turns of roughly 34°; forward X/Z travel agreed within 0.0014° and 0.0248°; two full game restarts retained the locator. Historical read: `owner = QWORD(moduleBase + 0x32E0200)`, `rawRadians = float32(owner + 0x304)`, `facingDegrees = wrap180(90 - degrees(rawRadians))`. Source: `C:\rift modding\RiftReader\docs\workflow\player-yaw-recovery-result-2026-10-18.md`; historical game SHA starts `7C356C9D`. The old address fails on the current SHA `1935A05C...`; **reuse the method and behavior controls, never the stale absolute locator**.
- **Current-build Lab 2 live correlation:** an A pulse was inserted and released, followed by actor-matrix angle candidate **84.853° -> 72.072° (−12.781°)** with **zero X/Z displacement**, matching the expected left-turn direction. But the requested 100 ms pulse was held for only **51.75 ms**; the guest returned `TimeoutException: The bounded hold elapsed during input delivery`. The pre-action baseline was minutes earlier. This is useful changed-state evidence, **not qualified body facing or a successful 100 ms input trial**. After that attempt the reported state was disarmed, no keys held, and queue clean.
- **Two-lab stationary baseline** collected on November 10: both labs returned native XYZ, vitals, actor pose and four smoothed-scalar candidates; a roughly 20-second no-input comparison showed zero X/Z travel and zero pose/scalar change on both. Live addon/native Lab 2 XYZ were also observed agreeing within ~0.005 units per axis. Source: commit `9295487` and the November 10 continuation transcript.
- **Last reported two-lab readiness at ~13:00 EST**, not a current guarantee: Lab 1 RIFT PID 10212; Lab 2 PID 7956; both managed controllers and guest agents ready, no held keys, native retrieval successful. Lab 2 was the easier UI target; Lab 1 had LuaPad obstructing part of the scene. **Reacquire process/start/build/agent and queue identities now; do not reuse these PIDs as pins.**

## Code already landed

- `b46496b`: `scripts/assess_native_facing_signature.py` implements the V1-style five-phase baseline/camera-only/A/D/W behavior assessment using saved current-build native position/actor-pose readouts. Its output remains **candidate-only**; labels alone are not independently verified input receipts.
- `5bf45c1`: rejects nonadjacent source-report replay across those five captures.
- `1c276c2`: bounds single-key insertion slack so slow native insertion does not automatically truncate every 100 ms turn, while retaining an absolute timeout and key-release checks. **Code commit is not evidence that this binary has been deployed or live-qualified on either guest.**
- Existing `scripts/read_native_telemetry.py` supports `--lab lab1|lab2`, `--fields position actor-pose smoothed-scalar`, `--output-json`, and `--compare-readout-before`. The native position + actor-pose comparison can be gathered without the Lua reader.
- Source-aligned testing was done in the contributing development sessions. **This handoff turn ran no tests and no live turn**; do not claim a fresh full-suite or guest-binary pass from it.

## Shortest path to a functional prototype

1. **Fresh admission on each lab:** verify AMD-DESKTOP, VM/game PID+start+executable SHA, managed controller and guest-agent generation/binary SHA, ready/disarmed/no held keys, queue/lease clear, and independent cleanup. Recover only through the existing owner-aware lifecycle; do not overwrite a peer's active experiment. Recheck addon sync/binding if using Lua as the second channel.
2. **Lab 2 first: clean turn delivery.** Ensure the newly committed hold fix is actually in the guest release and managed updater has activated it before evaluating its effect. Capture a fresh, image-reviewed bounded 100 ms `A` turn using the existing authorized controller/lease/STOP path. Record actual down/up timestamps and rejection reason, not only the requested duration. Verify release, disarm, zero keys, and queue cleanup. Do **not** increase review/arm deadlines or bypass input ownership to make it pass.
3. **Tight native before/after on the same Lab 2 game epoch:** acquire baseline via the existing `read_native_telemetry` JSON route immediately before the action, then capture again immediately after. Compare actor/model/render angle candidates and X/Z displacement; pair screenshots if review is timely. A stationary negative-delta turn with qualified input timing is the first prototype milestone.
4. **Independent Lab 1 experiment:** use Lab 1 for `D` opposite-turn and, when the interface is reviewable, camera-only rotation negative control. It has separate game addresses and source hashes. Serialize input ownership per lab and shared desktop resources; Lab 1 offline/read-only analysis can proceed while Lab 2 is being reviewed.
5. **Complete the five-phase facing signature on one controlled game epoch:** `python -m scripts.assess_native_facing_signature --baseline <json> --camera-only <json> --turn-left <json> --turn-right <json> --forward <json>`. Use five separately sampled readouts with independent action receipts. The tool can find a behavior-consistent matrix but **cannot by itself prove absolute facing**; repeat W at a second heading and verify camera-only invariance, then full RIFT restart with fresh locator resolution before marking the field durable.
6. **Expose the smallest usable .NET-facing read path** once correlation holds: current-build owner locator -> radians/angle conversion -> structured `playerFacingDegrees` with build/process/source freshness, plus explicit `unavailable` on mismatch. Keep Lua as an independent real-time reference until C# is sufficiently proven. Stop short of generalized pathfinding or a new architecture.

Minimal capture example, from `C:\work\riftreader2` on verified AMD-DESKTOP:

```powershell
C:\Python314\python.exe -m scripts.read_native_telemetry --lab lab2 --expected-host AMD-DESKTOP --fields position actor-pose smoothed-scalar --output-json artifacts\facing-lab2-before.json
# Perform one separately reviewed, bounded turn with the existing control helper.
C:\Python314\python.exe -m scripts.read_native_telemetry --lab lab2 --expected-host AMD-DESKTOP --fields position actor-pose smoothed-scalar --output-json artifacts\facing-lab2-after.json --compare-readout-before artifacts\facing-lab2-before.json
```

Use new output names if those paths exist; `--output-json` intentionally refuses overwrite.

## Ownership, blockers, and completion criterion

- **Current blocker:** live-qualified 100 ms turn duration plus tightly paired input/native orientation evidence. Current-build body-facing semantics and restart recovery still pending. The historical V1 locator is invalid on this build.
- **Working prototype criterion:** a reviewed turn is delivered at measured acceptable duration; fresh same-epoch native heading changes in the correct direction while stationary; opposite turn and camera-only control distinguish body yaw from camera yaw; the C# reader returns a repeatable value or honest unavailable reason. W-bearing + second-heading and full restart raise confidence toward production.
- **Concurrent files preserved:** 5 pre-existing modified tracked files (`scripts/fresh_native_actor_pose.py`, its test, and three `packages.lock.json` files) and 3 untracked peer research/test files (`scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `tests/test_rank_native_anchor_candidates.py`). Do not stage or overwrite them without their owners' coordination.
- Keep work practical: one controlled input, one changed-state observation, one focused check, one commit. Lab 1 and Lab 2 share the Windows host but have different current game processes; no old PID, nonce, screenshot review or arm plan survives a new session.

Useful continuation references: `docs/planning/turn-heading-2026-11-10.md`; `docs/handoff-2026-11-10-0351-turn-heading.md`; `docs/handoff-2026-11-10-0453-controller-turn-evidence.md`; `scripts/assess_native_facing_signature.py`; `docs/validation/lab2-100ms-turn-live-2026-11-09.md`.
