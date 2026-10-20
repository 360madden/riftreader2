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
| P01 Native execution/guest | IN PROGRESS | Independent bounded core and Windows adapter tests underway. |
| P02 Host/operator workflow | IN PROGRESS | Outbound private guest connection, loopback operator UI, no new service. |
| P03 Live verification | TODO | Exact bundle, fresh target, individually reviewed actions. |
| P04 Gate/docs/commits | TODO | Full gate, no V1 imports in native path, concrete limitations. |

Completion means a practical bounded supervised interface with demonstrated
movement/camera behavior. It does not mean numerical camera qualification,
unattended navigation or guaranteed cleanup after OS/hypervisor hard failure.
Any unavailable behavior remains explicit rather than being silently claimed.
