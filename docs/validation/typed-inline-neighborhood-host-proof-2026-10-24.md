# Inline typed-marker neighborhood capture — host implementation proof, October 24, 2026

**Scope: implemented and tested on the Windows host, not yet exposed through a new guest CLI or deployed to RIFT-Lab-1.** The live two-snapshot result [showed the earlier three scout addresses were stale or binary-backed](typed-snapshot-first-live-pair-2026-10-24.md); the normal V14 coordinator remains the last verified exclusive VM console owner.

## Implementation and limits

- The existing `TypedApiPrefixScout.Scan` pure stream now offers optional `onMatch` notifications **within the same 64 KiB block as the observed prefix, before the next scanner read**. The existing `scout-typed-native` public command does not use the hook and its report and guest binary are not changed.
- New `src/RiftReader2.Live/TypedApiImmediateNeighborhood.cs` provides a reusable *read-only* capture primitive for that hook. It immediately re-reads **`RRAPIVAL2|{` (11 bytes)** at the exact candidate address. If the header is unavailable or moved, or the marker is followed by binary/NUL instead of a JSON opening brace, it **rejects that single candidate without copying seven pages or making absence claims**.
- For plausible starts the primitive copies the **two preceding pages, marker page and four following pages**, exactly **28,672 bytes / seven individually validated 4 KiB reads**. Every successful/partial chunk carries actual byte count, base64 bytes and SHA-256; failed chunks carry reason/Win32 error, with no zero-filling. The caller supplies a bounded time gate and cancellation. A future command must bind these bytes to the correct process epoch, source snapshot-request SHA, implementation identity, non-overwrite output, and post-capture revalidation before they can be trusted.
- The `ToSnapshotFile` method wraps only actual captures in the **existing** strict `native-memory-snapshot/1` schema; reject/header-unavailable/no-chunk cases cannot be silently published as normal snapshots. This explicitly preserves the existing offline `inspect-typed-wire` interface.
- **There is no built-in delay, autonomous repeated game sampling, producer validation, user input, change to V1, process-memory write, or new guest deployment.** It is one safe acquisition building block, not yet the end-to-end candidate capture workflow.

## Actual independent host tests

- `TypedApiImmediateNeighborhoodTests`: **11 focused cases** for plausible and stale markers, binary/NUL rejection, a marker straddling a 4 KiB boundary, inaccessible chunk/no zero fill, time expiry before or during capture, out-of-bounds address, impossible reader byte counts, canonical strict snapshot-loader round-trip, and **real Windows self-process native memory**.
- The Windows integration allocates 28 KiB inside the *test runner only*, uses the actual `WindowsNativeMemorySession.OpenAsync` read-only process handle, actual 64 KiB `ReadScanChunk`, the new inline scout callback, and actual 4 KiB `ReadProcessMemory` chunk reads. It reconstructs and compares every byte of the allocation, verifies the exact discovered address, and revalidates its own process identity. **This is not a game observation.**
- The preexisting match hook has **3 additional focused tests** for prompt observer call, retained-candidate overflow, cross-chunk prefix and unreadable-gap boundaries, with unmodified CLI behavior.

## Next integration and live gates

1. Create an exact-process-epoch, versioned, bounded **one-command scout-and-capture** orchestration layer using the tested callback/copy. Enforce hard scan bytes/time, maximum candidates and copied bytes, marker plausibility, source request digest, post-capture process revalidation, no-overwrite original output and explicitly partial scans. Preserve success/failure for each candidate.
2. Ensure two temporally independent *valid* snapshots (Lua producer nominal refresh ~0.5 s), preferably re-discovering dynamic frame addresses for each sample, and pass **existing strict** `inspect-typed-wire`. Never declare typed freshness from the cheap `RRAPIVAL2|{` prefix.
3. Run full host tests and pin a new guest bundle. Any guest trial requires freshly observed V14/game/VM identity and SQLite state, genuine normal V14 STOP/release, exclusive maintenance, SHA-pinned guest execution and recovery to an independently verified V15 coordinator. **No concurrent VM control**.

**Outcome:** The pure scan→immediate-copy path now has actual Windows self-process proof and preserves existing read-only/byte-integrity contracts. Fresh RIFT typed frames and native/Lua XYZ still have **not** been qualified.
