# Validation index

This directory records actual checks separately from proposed measurements.

| Record | Meaning |
|---|---|
| [Repository setup](repository-setup-2026-10-18.md) | File, Git, and Workbridge checks for the documentation baseline. |
| [Foundation validation](foundation-2026-10-18.md) | Full gate evidence for the modular offline foundation. |
| [Addon contract validation](addon-contract-2026-10-18.md) | Actual Lua 5.1 producer, C# decoder, and shared contract gate. |
| [Live preparation](live-preparation-2026-10-18.md) | Historical host-only preparation, superseded for current status by the actual-client record. |
| [Actual-client addon validation](addon-live-client-2026-10-18.md) | Bare RR2A1 loaded and advanced in one identified RIFT-Lab session. |
| [Nonce-bound live transport](live-transport-2026-10-18.md) | RR2L1 advancement, stale rejection, reload clearing, reader restart/rebinding, delivery, and host snapshot gate. |
| [Restart recovery](restart-recovery-2026-10-18.md) | Final executable, RIFT process restart, graceful VM power cycle, persistence, reacquisition, rebinding, and fresh recovery. |
| [Saved wall-motion replay](wall-replay-2026-10-19.md) | Independent V2 replay of one content-pinned V1 capture: free-travel plausibility and two decisive wall disagreements. |
| [Success measures](success-measures.md) | Measurement framework and current foundation baseline. |

The latest full gate passed 183 C# tests (177 core and 6 Windows), 108 Lua
assertions, 11 RR2A1 plus 11 RR2L1 actual-Lua-to-C# cases, and 9 Python host-gate
tests, with zero Release build warnings, exact SDK and locked restore checks,
formatting/dependency checks, deterministic synthetic replay, and 153 relative
links. A separate final check reproduced the saved wall-motion result twice.
The live records additionally
validate bounded end-to-end lab paths,
including an ordinary RIFT restart and graceful VM power cycle with manual
relaunch and rebinding. They do not establish loaded-module bytes, native-field
meaning, hard-crash or snapshot-restore recovery, update recovery, production
remote consumption, or general performance.

The saved wall-motion record separately establishes one repeatable offline V1
evidence conclusion. It qualifies the replay procedure for the pinned capture,
not a native velocity field or current-build motion behavior.

For future checks, record the input/build identity, command or tool request,
actual result, evidence location, and limitations. A successful launch is not
an end-to-end workflow result. A passed historical check is not evidence that a
changed working tree was tested.

Documentation changes need proportionate review. Application behavior and data
contracts need focused tests plus the full gate in
[the development workflow](../workflows/development.md).
