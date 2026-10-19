# Validation index

This directory records actual checks separately from proposed measurements.

| Record | Meaning |
|---|---|
| [Repository setup](repository-setup-2026-10-18.md) | File, Git, and Workbridge checks for the documentation baseline. |
| [Foundation validation](foundation-2026-10-18.md) | Full gate evidence for the modular offline foundation. |
| [Addon contract validation](addon-contract-2026-10-18.md) | Actual Lua 5.1 producer, C# decoder, and shared contract gate. |
| [Success measures](success-measures.md) | Measurement framework and current foundation baseline. |

The latest full gate passed 138 C# tests, 85 Lua assertions, and 11 actual
Lua-to-C# shared cases, with zero Release build warnings, exact SDK and locked
restore checks, formatting/dependency checks, deterministic synthetic replay,
and relative-link checks. This validates the offline contracts in that checkout.
It does not establish binary analysis, live-game
capture, RIFT field meaning, restart/update recovery, or performance.

For future checks, record the input/build identity, command or tool request,
actual result, evidence location, and limitations. A successful launch is not
an end-to-end workflow result. A passed historical check is not evidence that a
changed working tree was tested.

Documentation changes need proportionate review. Application behavior and data
contracts need focused tests plus the full gate in
[the development workflow](../workflows/development.md).
