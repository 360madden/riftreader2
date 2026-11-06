# Current-epoch typed-prefix scout: reuse-first pivot

Date: October 24, 2026 (America/New_York). **Research/design only** following the successful host retention of the complete live map. No new guest memory scan, character input, VM change or field qualification occurred in this phase. Current native coordinator at this checkpoint: V12 PID 15336, connected/ready/disarmed.

## Evidence, not assumptions

The exact PID **6940** `native-memory-map/1` report (2,831,071 bytes; SHA-256 `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`) identifies **20,838** committed/readable regions and **7,846,682,624** readable *virtual* bytes. Private regions alone account for **7,648,837,632** bytes. A maximum 64 MiB snapshot covers **less than 0.9%** of those private bytes; two same-range snapshots do not increase spatial coverage. Randomly guessing a few ranges and declaring the absence of `RRAPIVAL2|` would be weak evidence.

Historical October 16 typed frames occurred at `0x3D3189F0` and `0x3D2BD3B0`, but neither address belongs to any readable region in the October 24 map. Treat them as proof of heap mobility, not usable cross-process pointer locators.

## Existing implementations inspected (read only)

1. **V1 observer** `C:\rift modding\RiftReader\tools\RiftReader.GuestObserver\GuestReadbackWorker.cs`: installed deployment sidecar exposes `enableReadback` and `enableTypedApi`, but the worker constructs `GuestReadbackOptions` with only the typed switch overridden. That leaves the source default **4 GiB/10 s** budget fixed; there is no deployed configuration key for safely varying scan byte/time bounds. The V1 incomplete-scan result deliberately suppresses typed freshness, so increasing one number without requalifying semantics is not the repair. **Do not edit V1.**
2. **V2 already has an optimized memory scanner:** `src/RiftReader2.Live/WindowsMemoryScanner.cs` enumerates readable private regions, reuses a **64 KiB** buffer for `ReadProcessMemory`, respects cancellation/time, resets its accumulator at region gaps, and retains candidate/coverage counters. Its current API is specialized for `RR2L1` challenge-envelope scanning, **not** the typed `RRAPIVAL2|` producer. It also preflights *all* private bytes and returns `byte-budget-exceeded` **before reading anything** when the planned bytes exceed its caller's budget. Simply calling this implementation unchanged cannot discover today's typed frames.
3. **V2 strict native epoch boundaries are reusable:** `WindowsNativeMemorySession.OpenAsync` checks exact PID, process start and executable SHA, and `RevalidateAsync` checks the same handle and module afterward. Its existing public `Read` deliberately limits each snapshot chunk to 4,096 bytes. **Preserve that snapshot contract** while using a separate bounded buffer-read path for the prefix scout.
4. **V2 strict source parser already exists:** `inspect-typed-wire` inspects two saved `native-memory-snapshot/1` reports, validates the complete frame and suffix, rejects malformed/conflicting copies and requires independently advancing sequence/time. A new live scout must **not duplicate or relax** this parser; it only locates likely prefix addresses for targeted snapshots.

## Decision: a bounded marker-only scout, not another full dump

Introduce a V2-only `scout-typed-native` read-only command that uses the existing Windows memory enumeration/read infrastructure to find the byte prefix **`RRAPIVAL2|`**, without dumping entire private heaps or claiming that a prefix equals a valid typed frame. Preserve the existing `map-native` and `snapshot-native` behavior.

Proposed request (specification, **not yet implemented or deployed**):

- `schemaVersion=1`, `evidenceKind=native-typed-prefix-scout-request/1`, exact current process PID/start/executable SHA.
- `startAddress` (canonical hex) for deterministic multi-pass progress; no historical absolute address reused.
- Explicit `maxScanBytes` no more than **512 MiB per pass**, `maxDurationMilliseconds` no more than **30,000**, `maxRegionCount` no more than **32,768**, and `maxMatchCount` no more than **128**. Match type fixed to UTF-8 `RRAPIVAL2|`; no arbitrary command or game input syntax.
- Report source/request hashes, implementation identity, timestamps, exact guest RIFT process identity (with separate host VMware epoch receipts), region/byte scope, readable-byte holes/failures, prefix addresses, `nextAddress`, reason, and an explicit **scope-complete/partial/invalidated** status. Do not claim global absence or uniqueness from one partial pass.
- Reuse **64 KiB streaming memory reads** with a small prefix overlap across successful contiguous chunks. Never carry match state across unreadable gaps or discontinuous memory regions. Candidate overflow, time/byte cap, cancellation and process/VM identity drift must fail closed with retained partial evidence, not fabricated complete coverage.
- A prefix hit is only a **candidate**. Acquire a fresh, strictly bounded `snapshot-native` neighborhood at candidate addresses, repeat after source refresh, and run the already tested offline `inspect-typed-wire`. Only actual complete and advancing frames can be compared to a separate read-only native `follow-pointer` at current root RVA `0x32E0200`.

## Implementation and validation order

1. Extract a small pure streaming-prefix matcher with tests for exact start, split-across-64-KiB chunks, back-to-back candidates, overlapping prefix, resets on holes, false prefixes, candidate cap and no global-uniqueness claim.
2. Add an exact-epoch, bounded scanner path reusing `WindowsMemoryScanner`'s 64 KiB buffer/region traversal and `WindowsNativeMemorySession` identity checks. Do not loosen existing 4 KiB `snapshot-native` input limits.
3. Add a separately versioned request/report contract, no-overwrite report writer, CLI help, synthetically tested partial/resume behavior and reporting of uncovered private bytes. Keep max-time and max-byte caps hard.
4. Run focused plus full .NET/Windows/Python test gates and scoped format/CLI tests; pin the new guest binary bundle hash before transfer. Any guest trial requires fresh V12 supervisor/queue/VM preflight, normal STOP/release and exclusive console, then a new exact-epoch successor coordinator restoration.
5. First live pass is **bounded to 512 MiB and 30 seconds**, reports its limited coverage whether hits exist or not; continue further address windows only with explicit evidence and preserved identity. No movement or game inputs are part of the scout.

**What is not established:** No October 24 `RRAPIVAL2|` candidate address, complete typed frame, advancing Lua source, or native/Lua XYZ match has yet been found. The new scout is the next implementation step; this note is a reviewed choice grounded in the real map and code, not a claim that a scan ran.
