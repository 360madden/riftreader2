# Offline typed Lua wire inspection from native snapshots

Status: implemented in V2, October 24, 2026. **Offline analysis only; no fresh current-process typed capture has been obtained yet.**

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

1. Verify the **currently active** VM/game/coordinator and canonical queue (V13 was last independently confirmed after the October 24 live scout; always re-detect). Do not open VM console concurrently with the live coordinator. The [bounded V2 prefix scout](typed-prefix-scout.md) can locate candidate snapshot neighborhoods without changing V1.
2. Obtain a **read-only** `map-native` report in the correct guest after genuine coordinator STOP/release. Use [memory discovery](memory-discovery.md). Select bounded committed/readable/private or plausible heap regions using this *same process epoch*. Historical October 16 absolute addresses were mobile **within** the old process; these are only heuristic hints, never current guest addresses.
3. Produce two separate `snapshot-native` reports of explicitly chosen regions with source request and real process identity pinned. The [host-only two-snapshot follow-up plan](../validation/typed-scout-snapshot-followup-plan-2026-10-24.md) preserves two hash-identical *requests*, not two captured *reports*, for the three current-session marker candidates. Revalidate that exact process epoch before reuse; if it changed, rescout. Preserve actual complete reports, request bytes and hashes, and missing-range warnings. Restore a correctly pinned native host/coordinator after guest maintenance.
4. Run `inspect-typed-wire` on the two retained reports. Investigate `blocked` and `unavailable`; do not quietly enlarge broad scans or promote negative/incomplete scopes to success.
5. Only if `advanced-in-covered-scope` with independent source checks, acquire a same-epoch native `follow-pointer` report for RVA `0x32E0200` and owner float32 offsets `+0x320/+0x324/+0x328`. Compare source XYZ and native XYZ with timestamps and errors through the field-evidence workflow, retaining both original raw reports. A match would advance field qualification; a disagreement must be documented, not suppressed.

## Reuse and limits

This **V2-owned** diagnostic borrows the published **wire contract** from read-only inspection of the V1 `TypedApiSnapshotParser` and `TypedApiFreshnessTracker`, not the V1 application architecture or code. The V1 observer uses a global private-memory scan whose 4 GiB limit was exceeded in an earlier game epoch. This tool instead uses V2's bounded, integrity-verified, selected snapshot ranges.

Tests use synthetic complete frames and intentionally negative fixtures. A passing test is not proof the present RIFT process contains an accessible typed frame. For the blocker, historical positive sample and process identities, see [typed recovery research](../research/typed-api-bounded-recovery-2026-10-24.md).
