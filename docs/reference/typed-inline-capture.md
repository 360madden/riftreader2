# Same-scan typed-neighborhood capture command

Status: **implemented, host-validated, and proven in the actual RIFT guest (October 24, 2026).** Two independent partial-but-bounded 512 MiB scans saved six complete 28 KiB snapshots; exact guest ZIP/receipts/hashes passed, and the strict C# inspector qualified six advancing same-player Lua source pairs. The next V16 trial obtained **two live native XYZ originals** agreeing within 0.0025 game units with that prior Lua player position, but the readings were about **2.4 hours apart** from the typed Lua source and remain **candidate-only-not-synchronized**, without movement response. See the [actual typed Lua scan](../validation/typed-inline-first-live-six-snapshots-2026-10-24.md) and [subsequent native XYZ proof](../validation/native-pointer-xyz-first-live-2026-10-24.md). This command addresses the earlier [scout→snapshot delay and zero-frame result](../validation/typed-snapshot-first-live-pair-2026-10-24.md).

## Command and pinned request

From PowerShell in the **same 64-bit Windows environment as the process**:

```powershell
.\RiftReader2.Live.exe scout-copy-typed-native --request .\scout-copy-request.json --output .\artifacts\scout-copy-run-001
```

**`--output` must be a nonexistent directory.** Rerunning the same command against that directory fails before any native read. Evidence is staged into a unique adjacent temporary directory; request/report files are published with strict no-overwrite writes, then the entire validated directory is renamed to its final name once. A failed publication never overwrites a prior run.

Version 1 exact-target request properties:

```json
{
  "schemaVersion": 1,
  "evidenceKind": "native-typed-inline-capture-request/1",
  "target": {
    "processId": 6940,
    "processStartUtcTicks": 639284177321390013,
    "executableSha256": "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
  },
  "startAddress": "0x10000",
  "maxScanBytes": 536870912,
  "maxDurationMilliseconds": 30000,
  "maxRegionCount": 32768,
  "maxMatchCount": 128,
  "maxCopiedCandidates": 8
}
```

The PID/start/hash above are **only an October 24 example**. Never reuse after a game restart, executable change, VM epoch drift or a failed fresh preflight. A request's original JSON bytes are hashed before any read; process identity is checked both on open and after all acquisition.

## Read-only acquisition semantics

- Scans **committed, readable, nonguard `MEM_PRIVATE`** ranges from canonical `startAddress`, using the tested 64 KiB streaming `RRAPIVAL2|` matcher. The scan bound is 64 KiB–512 MiB, 1–30 seconds, at most 32,768 regions and 128 prefix matches, with retained coverage spans, holes, counts and resume cursor.
- The same scanner callback rechecks a candidate's actual bytes for `RRAPIVAL2|{`. If already changed, inaccessible, or followed by binary/NUL, it is recorded as a **declined marker, not a valid frame**; no neighborhood copy is made. For plausible starts, it copies **exactly seven 4 KiB pages / 28,672 bytes**, two before, marker page and four after, retaining exact bytes, chunk SHA-256, statuses and read-error data. Total copies are limited to **eight** per pass.
- A copy-cap exhaustion is reported separately from scanner coverage, which may itself be `partial`; it does **not** mean every matching or valid frame has been captured. Time budget includes the scanner/copies/revalidation. A changed process identity invalidates the entire run and **no ordinary snapshot files are published** for it.
- Only read-only `OpenProcess`/memory reads and process/map queries are used. No game input, write, injection, VNC action or V1 code change is part of the command. Session absolute addresses are *not* a durable locator.

## Published artifacts and interpretation

Each final output directory contains:

- **`index.json`**: `native-typed-inline-capture/1`, original exact request hash/contents, implementation and game identity, UTC acquisition interval, global status/reason, copy cap/used count, exact scanner scope/coverage, canonical-hex marker addresses and per-marker copy/rejection status. It references individual artifact filenames and SHA-256 values.
- For each successfully attempted neighborhood copy: **`capture-01.request.json`** (internally generated exact-process `native-memory-snapshot-request/1` specifying the actual 28 KiB range, hashed from *saved bytes*) and **`capture-01.snapshot.json`** (the standard `native-memory-snapshot/1` original, strict-loader validated with 4 KiB chunk hashes). Subsequent captures use unique numbered filenames. Missing chunks remain explicit.
- A newly staged `index.json` is written last; after its SHA is read, the entire output directory is atomically renamed without overwrite. If interrupted before this rename, a temporary directory may retain recoverable partial artifacts; it is **not a published successful run**.

Exit **0** means the command published a `complete` scan/copy diagnostic; **3** means `partial` or `identity-invalidated`; **2** is a request, identity-open or publication error; **130** is cancellation. **Exit 0 never certifies any Lua frame or XYZ.** Read actual `status`, `reason`, candidate statuses and per-snapshot completeness.

Two separate, identity-matched, time-separated command invocations can supply candidate `capture-NN.snapshot.json` reports to the existing strict `inspect-typed-wire --before ... --after ...` analyzer. Candidate numbering/address can change between passes. Require actual complete, producer-valid **advancing** frames and stable source player before any same-epoch native XYZ comparison.

A two-run guest trial can return one exactly SHA-pinned ZIP rather than transfer many JSON files separately: preserve each original input request, generated index and all referenced request/snapshot pairs in two run folders. The bounded [offline archive verifier and actual Windows host end-to-end proof](../validation/typed-inline-archive-two-run-host-2026-10-24.md) preserve complete originals and invoke the existing strict typed-wire gate separately. That earlier ZIP proof was host-only; the subsequent actual RIFT guest acquisition and exact guest receipts are independently documented in the first live six-snapshot record. For an actual guest ZIP transfer, the [separate one-use exact-epoch SHA/length claim and two-receipt verifier](../validation/typed-inline-zip-claim-host-2026-10-24.md) must be used before any source provenance is accepted.

## Validation status and live preflight

[Windows self-process CLI tests](../validation/typed-inline-capture-cli-host-2026-10-24.md) actually exercise read-only memory scan, SHA-linked request and full snapshot report publication, strict loader recovery, and replay overwrite rejection. Another test rejects wrong process start before any output directory is created. A subsequent actual RIFT-Lab-1 run read live game memory twice, saved six complete same-process candidate snapshots and qualified advancing Lua frames; the later native pointer trial supplied agreeing but non-synchronized XYZ evidence.

The October 24 typed-inline trial used fresh exact V14/game/VM evidence, normal V14 STOP, exclusive guest PowerShell, an independently SHA-verified 74 MB binary, two original scan-copy runs, a declared and independently verified guest ZIP upload, and strict offline cross-run decoding. **V15 was the historical recovered owner; a later normal V15 STOP and successful pointer trial restored V16 PID 28496 as the current exclusive VM console owner.** Any further guest trial requires a newly prepared exclusive handover from V16; no concurrent VM entry is permitted.
