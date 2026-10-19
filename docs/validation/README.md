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
| [Native capture](native-capture-2026-10-19.md) | Final native bundle: bounded raw reads, explicit failures, exact identities, publication, and ordinary RIFT restart rejection/reacquisition. |
| [Field catalog](field-catalog-2026-10-19.md) | Offline qualification of content-bound definitions and assessments, scoped confidence, disagreement, expiration, and deterministic rebuilding. |
| [Success measures](success-measures.md) | Measurement framework and current foundation baseline. |

The latest full gate passed 214 C# tests (205 portable and 9 Windows), 108 Lua
assertions, 22 actual Lua-to-C# cases, 9 Python host-gate tests, and the published
single-file native smoke, with zero Release warnings, locked restore,
format/dependency checks, deterministic motion/catalog replay, and 174 relative
links before final handoff edits; all 177 final documentation links passed.
The catalog gate produced byte-identical
reports from a retained synthetic bundle; it establishes no real game field.

Runtime records identify their own exact binaries. The final native bundle
passed bounded acquisition and an ordinary RIFT restart; the earlier addon
transport binary passed its game/VM restart gates. These do not establish full
loaded-module equality, native game-field meaning, hard-crash or snapshot
recovery, update recovery, production remote consumption, or general performance.

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
