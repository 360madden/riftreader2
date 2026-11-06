# Bounded inline typed-scout capture pass — host test evidence, October 24, 2026

**Status: pure .NET 10 orchestration implemented and host-tested; no new published guest CLI, no VM access, no RIFT field qualification.** This work composes the [scout callback and byte-integrity capture primitive](typed-inline-neighborhood-host-proof-2026-10-24.md) into one pass suitable for later exact-process-epoch evidence publication.

## What changed

- Added `src/RiftReader2.Live/TypedApiInlineCapturePass.cs`: given **read-only** scanner and 4 KiB neighborhood delegates, an explicit time gate, bounded private-region list and scan limits, the command scans eligible native memory and **immediately copies** a plausible `RRAPIVAL2|{` neighborhood *inside the retained-prefix callback*, before the next 64 KiB scan block.
- Maximum **eight copied candidate neighborhoods** per invocation; each is at most **28,672 bytes / seven verified chunks**. Stale/NUL/static markers are recorded as `prefix-not-plausible`, with no 28 KiB copy. If the copy budget fills, further prefixes are retained as `copy-budget-exceeded` while the original scan's scope/coverage remains explicit. Neither a stopped copy budget nor a scanner's `partial` result can be reported as global absence or a valid typed frame.
- The collector retains separate scanner status/holes/resume cursor and per-candidate copy outcome and exact bytes, but **performs no file I/O**, publishes no identity claim on its own, and never contacts VM/VNC. A future CLI must pin the source process epoch, request/bundle hashes and no-overwrite artifact paths; fail closed if revalidation changes identity.

## Verified tests

- `TypedApiInlineCapturePassTests`: six pure test scenarios for one copied plausible marker plus one binary false positive; copy-cap saturation; relocation between scan buffer and copy; user-range boundary rejection; invalid copy caps; and propagation of a deadline to both copy and the scanner's partial coverage status.
- Existing [real Windows own-process proof](typed-inline-neighborhood-host-proof-2026-10-24.md) separately verifies the genuine `ReadProcessMemory` 64 KiB scout callback and immediate 4 KiB neighborhood reads with byte-for-byte identity. The new orchestrator tests intentionally run without the game.
- This checkpoint is not evidence of a current RIFT Lua wire frame. The last two RIFT-Lab-1 native reports had **zero complete frames** in their selected scope; [see the actual V14 restoration and negative diagnostic](typed-snapshot-first-live-pair-2026-10-24.md).

## Next gate

1. Add an exact-target `scout-copy-typed-native` CLI and versioned request/output manifest; use a new output directory with no-overwrite snapshot request files, strict `native-memory-snapshot/1` original reports, SHA references and per-prefix decline/copy statuses. Never let invalidated process identity publish a usable candidate.
2. Run the full .NET/Python/Lua, strict wire-parser, CLI failure/no-overwrite and Windows self-process checks; pin a new guest bundle only after completion.
3. Guest execution remains gated by fresh **V14** authenticated readiness and same RIFT/VM identity, genuine normal V14 STOP/release, exclusive read-only maintenance and subsequently verified coordinator restoration. No game memory write or injection.
