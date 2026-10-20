# Supervised S/A/D parity — October 20, 2026

## Target and readiness

Joey explicitly selected RIFT-Lab-1. Its display name maps to
`C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, port 5905, not RIFT-Lab-2.
The existing launcher was rejected for Windows group/admin permissions.
Joey started the VM; subsequent console identity was PID 39056, start ticks
134369666367568339, log epoch 2026-10-20T10:43:56.803Z.
RIFT-Lab-2 was left untouched.

The stale host receiver was replaced using the unchanged installed receiver,
same private endpoint/config, and a new output directory under
`artifacts/movement-parity-20261020/receiver`.
Receiver identity: be57ffb257e443b0b11b0fac024a4575.
The existing guest GuestReadback observer was launched through the bound console:
0c10fe6a-d561-4a02-9535-7a107fc5ff0b, machine DESKTOP-8632QPL,
source 192.168.56.128. Fresh in-world readback bound RIFT PID 3400,
start 2026-10-19T20:37:36.4351086Z, window 0x401F2,
`C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, disk SHA-256
7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD.
VM start and game start differ; this is not evidence of a newly launched game
process or fresh restart qualification.

The old experiment controller had no pending release and its STOP latch was
inspected. New explicit preparation cleared that latch as documented.
An initial S preparation showed the options menu and was never executed.
After closing it, a new plan and screenshot were reviewed.

## Individual trials

The in-game bindings screen confirmed W=Move Forward, S=Move Backward,
A=Turn Left, D=Turn Right, Q/E=Strafe Left/Right. No binding was changed.
Each trial used its own prepare, screenshot review, and single-use run.
All requested 100 ms; all reported input and release sent, retained game focus,
matching VM/game/receiver identities and an advancing independent API sample
whose acquisition began after release (subject to unmeasured clock skew).

| Key | Run ID | Observed hold ms | Result |
|---|---|---:|---|
| S | 4cac8951b7ad4ee997e4c63c9e788b8b | 100.6712 | XYZ changed from (7296.399902, 876.320007, 3054.379883) to (7296.689941, 876.309998, 3054.349854). |
| A | f2f8a30dae6f46febc57318aab254f7c | 100.7244 | XYZ unchanged; visual viewpoint rotation consistent with Turn Left binding. |
| D | 8a79ca4855264a73a29d87a887790b09 | 100.4704 | XYZ unchanged; opposite visual viewpoint rotation consistent with Turn Right binding. |

S displacement is approximately 0.292 coordinate units, above the selected
0.05-unit reporting threshold (not a calibrated noise estimate).
S movement is consistent with the backward binding; this is not a calibrated
velocity or independent heading measurement. No yaw source is exposed by this
receiver, so A/D observations establish visual turn consistency, not numerical
angles or native orientation fields. No additional W trial was necessary.

Raw plans, source hashes, before/after receipts, input records and screenshots
remain under `artifacts/experiment-validation/session/` at the listed run IDs.
Task-level results, receiver output, binding screenshot and validation logs are
under `artifacts/movement-parity-20261020/`. These are ignored local evidence.
Existing V1 source and game binaries were not modified.

## Verification and completion

Added seven regression tests for four-key pulse preservation at both bounds,
invalid keys, pre-existing stop, changed post-input epoch, bounded nonadvancing
readback, stale/wrong-epoch gate propagation and stop-before-readback.
All 19 focused experiment tests passed.
The unchanged V1 screenshot guard remains responsible for freshness/review
validation; fake adapter tests do not establish that integration independently.

After D, explicit stop and recovery reported inputSent=false, pending=null,
paused=true. The read-only receiver/observer remain running and RIFT remains
in-world. Sending key-up is not attestation of actual game key state.
Mid-hold stop, hard-crash recovery, precise timing and native field qualification
remain outside this result. Full repository gate result is recorded below.

Full gate passed, exit 0: 273 C# tests (256 core, 17 Windows), 121 Python
tests, 108 Lua assertions, 22 actual Lua-to-C# cases, locked restore,
zero-warning Release build, formatting/module checks, native synthetic smoke,
deterministic replay and 229 relative documentation links. Evidence directory:
`artifacts/validation/20261020T105058Z-83f84b40`.
A SHA-256 manifest of all three retained run directories is saved as
`artifacts/movement-parity-20261020/evidence-hashes.json`.
