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
| P03 Live verification | COMPLETE WITH LIMITS | Native S/A/D, W+Q, orbit, yaw/pitch, 39 ms stop, host restart while armed/action-idle, 35-second review and panel input/release. Follow-ups verified bounded browser drag and reversible wheel zoom; numerical calibration and sustained usability remain open. |
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

The [October 20 follow-up](../validation/native-vm-controls-followup-2026-10-20.md)
implemented bounded browser drag after Codex rejected Pointer Lock, explicit
camera modes, countdowns, preserved release/action feedback, and a safer cursor
policy. The hold budget now includes setup after the first press. Three completed
100 ms button trials measured 101.97–113.96 ms; the final browser drag also
demonstrated cancellation on pointer release. These are small samples.

The [native zoom fix](../validation/native-zoom-2026-10-20.md) now passes
both-direction visual checks on the final binary. The agent uses one targeted
wheel message with a 100 ms timeout and no retry; the old native insertion path
showed no zoom despite the user's working physical-wheel baseline.

Remaining priorities are:

1. The [bounded usability pass](../validation/native-control-usability-2026-10-20.md)
   completed binding inspection, drag/zoom/release checks, and panel/native
   authorization fixes. Live page-exit STOP now passes. Longer human sessions,
   smooth continuous camera tracking, and live window-blur behavior outside
   the in-app tab-switch environment remain open. Optional Pointer Lock needs
   a compatible browser. Avoid repeating basic S/A/D.
2. Measure timing across a larger sample only when needed for further tuning;
   the small passing follow-up sample does not establish a distribution.
3. Resume information discovery using the new bounded native controls.
   Numerical camera fields and dedicated gameplay automation remain separate.

These are explicit remaining improvements, not claims that the current
implementation already satisfies them.
