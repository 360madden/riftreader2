# Offline typed Lua wire inspection from native snapshots

Status: implemented October 24, 2026; **new October 27 Lab-2 game build independently verified**. Two exact-process, time-separated `scout-copy-typed-native` passes yielded four complete typed API source snapshots, and all four strict cross-run comparisons returned `advanced-in-covered-scope`. See the [new-build proof](../validation/lab2-typed-inline-postpatch-2026-10-27.md); the [earlier negative scoped pair](../validation/typed-snapshot-first-live-pair-2026-10-24.md) remains valid as historical evidence. The analyzer remains offline-only.

RiftReader2's existing `snapshot-native` command produces process-epoch-bound JSON reports with verified chunks, explicit missing-byte status, and SHA-256 provenance. The separate `RiftReader2.Cli` command below examines **two saved** reports for complete `RRAPIVAL2|` UTF-8 frames. It does not open RIFT, contact VMware, control the guest, read live memory, or change the older RiftReader/V1 observer.

## Invocation

On the Windows host in PowerShell, from `C:\work\riftreader2`:

```powershell
dotnet src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll inspect-typed-wire --before artifacts/typed-scope/sample-01.json --after artifacts/typed-scope/sample-02.json --output artifacts/typed-scope/scoped-comparison.json
```

Replace all three file paths with actual retained snapshots. The output path must **not** already exist. The command returns exit 0 when it successfully publishes a **diagnostic report**, even if its embedded status is `blocked` or `unavailable`; inspect `status` and `reason` rather than treating exit 0 as a positive typed frame.

**Preconditions:** The original producer must have captured two independent windows separated in time, with the *same* native PID, full process start ticks, file identity and module identity. A report with `identity-invalidated`, overlapping windows, invalid SHA-256, forged lengths, wrong process epoch, or no valid source metadata is rejected before comparison.

## Fail-closed selection

- Reads only the successful byte segments exposed by the existing strict `NativeMemorySnapshotFile` loader. Adjacent successful 4 KiB chunks are joined; partial/unavailable chunks and unmapped gaps are **never** zero-filled or bridged. Total input is already bounded by the loader: 96 MiB JSON, 64 MiB requested bytes, 16,384 chunks.
- Recognizes exact `RRAPIVAL2|` prefix, `|RRAPIVALEND` suffix, and at most 8,192 JSON payload bytes. Boundary detection accounts for quoted strings, backslash escapes, and JSON braces. Limits accepted candidates to 128 per input; overflow is `blocked`.
- Strictly validates UTF-8, JSON depth 32, recursively duplicate-free keys, schema version 2, producer `RiftReaderApiProbe` version `0.6.0`, `source=rift-api`, `Inspect.Time.Frame` clock, positive sequence, producer input-state invariants, and complete v0.6 player/target field inventory. Available player X/Y/Z must be finite typed numbers; absent or malformed values are **not** fabricated as zero.
- Any malformed *complete* frame, or any incomplete candidate fragment in the inspected scope, blocks a positive claim. Ranks valid copies by frame time first and sequence second; equal-ranked copies with conflicting full-wire hashes are rejected. Copies can move to a different heap address in the same process.
- Requires the selected frames to have the same `player.unitId`, strictly advancing sequence and source frame clock, and sequential distinct capture windows. It reports selected addresses, frame hashes, XYZ, candidate multiplicity, coverage warnings, source file hashes and metadata. The report does **not** replace raw snapshot evidence.

Positive status is **`advanced-in-covered-scope`**. It means valid advancing typed producer content was found *in the requested bytes*. It is **not** a proof of global uniqueness, whole-process coverage, precise wall-clock freshness, semantic equivalence to native memory coordinates, game movement, or restart/update survival.

Other statuses are `blocked` (conflicting, malformed, incomplete, stale, or player-changed evidence) and `unavailable` (no usable frame in the covered subset). The tool is deliberately strict; a narrow negative scan is a scope-limited observation and does not show absence of the Lua producer.

## Acquisition and validation sequence

1. Verify the **currently active** VM/game/coordinator and the exclusive console ownership before any guest operation. Historical V14/V15/V16 controller PIDs are not current state. On October 27 the live recovery target is **RIFT-Lab-2 only**, with a new game executable SHA; see the [patch validation](../validation/rift-lab2-patch-2026-10-27.md). Do not control the console concurrently. The [bounded inline scanner](typed-inline-capture.md) can copy typed frame neighborhoods within the same read pass.
2. Obtain a **read-only** `map-native` report in the correct guest after genuine coordinator STOP/release. Use [memory discovery](memory-discovery.md). Select bounded committed/readable/private or plausible heap regions using this *same process epoch*. Historical October 16 absolute addresses were mobile **within** the old process; these are only heuristic hints, never current guest addresses.
3. Prefer two independent, time-separated [same-scan `scout-copy-typed-native`](typed-inline-capture.md) runs with exact game process identity and SHA. An older separated scout→snapshot pair returned no complete frame because the candidate heap moved; do not recycle those absolute addresses. Preserve original request, index, every candidate request/snapshot, ZIP/transfer hash and partial-scan coverage. If process identity changes, stop and repeat current preflight.
4. Run `inspect-typed-wire` on the two retained reports. Investigate `blocked` and `unavailable`; do not quietly enlarge broad scans or promote negative/incomplete scopes to success.
5. Only if `advanced-in-covered-scope` with independent source checks, begin **new-build** bounded `scout-values-native` float32 candidate discovery and compare a separately qualified native XYZ candidate with fresh Lua XYZ under observed state changes. The historical root RVA `0x32E0200` and float32 offsets `+0x320/+0x324/+0x328` belonged to the **prior executable SHA** and must remain invalid for the October 27 build. Native locator/pointer recovery and restart testing are separate gates; record disagreements.

## Reuse and limits

This **V2-owned** diagnostic borrows the published **wire contract** from read-only inspection of the V1 `TypedApiSnapshotParser` and `TypedApiFreshnessTracker`, not the V1 application architecture or code. The V1 observer uses a global private-memory scan whose 4 GiB limit was exceeded in an earlier game epoch. This tool instead uses V2's bounded, integrity-verified, selected snapshot ranges.

Tests use synthetic complete frames and intentionally negative fixtures. A passing test is not proof the present RIFT process contains an accessible typed frame. For the blocker, historical positive sample and process identities, see [typed recovery research](../research/typed-api-bounded-recovery-2026-10-24.md).
