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
| [Success measures](success-measures.md) | Measurement framework and current foundation baseline. |

The latest full gate passed 173 C# tests (167 core and 6 Windows), 108 Lua
assertions, 11 RR2A1 plus 11 RR2L1 actual-Lua-to-C# cases, and 9 Python host-gate
tests, with zero Release build warnings, exact SDK and locked restore checks,
formatting/dependency checks, deterministic synthetic replay, and 135 relative
links. The live record additionally validates one bounded end-to-end lab path.
It does not establish loaded-module bytes, native-field meaning, RIFT process
restart, VM power-cycle or update recovery, production remote consumption, or
general performance.

For future checks, record the input/build identity, command or tool request,
actual result, evidence location, and limitations. A successful launch is not
an end-to-end workflow result. A passed historical check is not evidence that a
changed working tree was tested.

Documentation changes need proportionate review. Application behavior and data
contracts need focused tests plus the full gate in
[the development workflow](../workflows/development.md).
