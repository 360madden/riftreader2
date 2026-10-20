# Native supervised VM control roadmap

Authorized October 20, 2026: Joey requested the optimized proposal, then
implementation through completion with coherent local commits. This supersedes
the attached prompt's design-only phase; process writes/injection, autonomous
gameplay, V1 modification and incidental global/VM changes remain excluded.

The [machine-readable proposal](native-vm-control-proposal.json) owns the
design and acceptance scope. Existing S/A/D evidence is retained, not replayed
as discovery. The new transport needs its own live validation.

| Phase | State | Checkpoint |
|---|---|---|
| P01 Native execution/guest | COMPLETE | Bounded core, exact Windows target, scan codes, relative mouse, durable release intent, and per-input timing. |
| P02 Host/operator workflow | COMPLETE | Authenticated outbound guest connection, loopback panel, CLI, and repository-owned bootstrap helper. |
| P03 Live verification | COMPLETE WITH LIMITS | Native S/A/D, W+Q, orbit, yaw/pitch, 39 ms stop, host restart while armed/action-idle, 35-second review and panel key/release; zoom unverified and one mouse timing target missed. |
| P04 Gate/docs/commits | COMPLETE | Full gate includes native control tests; usage, live record, source dependency audit, and local commits. See status for the final gate. |

Completion means a practical bounded supervised interface with demonstrated
movement/camera behavior. It does not mean numerical camera qualification,
unattended navigation or guaranteed cleanup after OS/hypervisor hard failure.
Any unavailable behavior remains explicit rather than being silently claimed.

## Evidence and next priorities

The [dated live record](../validation/native-vm-controls-2026-10-20.md) owns
observations and limits. The [usage guide](../reference/native-vm-controls.md)
owns setup and operation; [status](../status.md) owns the final gate and handoff.
The native workflow has zero V1 runtime source imports. The old experiment
adapter remains available for its historical evidence workflows.

Follow-up priorities are:

1. Human usability pass with the panel beside VMware: sustained keyboard
   control, Pointer Lock drag, blur, expiry, and clear feedback. CLI actions
   already exercise the same guest executor; avoid repeating basic S/A/D.
2. Inspect actual zoom bindings/input consumption and resolve wheel behavior.
   Both directions inserted successfully but produced no clear visual zoom.
3. Measure camera-button timing across a larger sample before tuning it.
   Current 100 ms samples were 115.83 and 127.60 ms from insertion to release;
   the latter missed the proposed ±20 ms target.
4. Resume information discovery using the new bounded native controls.
   Numerical camera fields and dedicated gameplay automation remain separate.

These are explicit remaining improvements, not claims that the current
implementation already satisfies them.
