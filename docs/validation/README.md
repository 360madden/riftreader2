# Validation index

This directory records actual checks separately from proposed measurements.

| Record | Meaning |
|---|---|
| [Repository setup](repository-setup-2026-10-18.md) | File, Git, and Workbridge checks for the documentation baseline. |
| [Foundation validation](foundation-2026-10-18.md) | Full gate evidence for the modular offline foundation. |
| [Success measures](success-measures.md) | Measurement framework and current foundation baseline. |

The current full gate passed 75 tests in Release with zero build warnings, exact
SDK and locked restore checks, formatting and dependency checks, deterministic
synthetic replay, and relative-link checks. This validates the saved-input
foundation in that checkout. It does not establish binary analysis, live-game
capture, RIFT field meaning, restart/update recovery, or performance.

For future checks, record the input/build identity, command or tool request,
actual result, evidence location, and limitations. A successful launch is not
an end-to-end workflow result. A passed historical check is not evidence that a
changed working tree was tested.

Documentation changes need proportionate review. Application behavior and data
contracts need focused tests plus the full gate in
[the development workflow](../workflows/development.md).
