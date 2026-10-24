# Same-scan typed-neighborhood capture command

Status: **implemented in V2 and tested on the Windows host (October 24, 2026); no RIFT guest deployment or valid fresh typed frame yet.** This command directly addresses the [first live scout→snapshot delay and zero-frame result](../validation/typed-snapshot-first-live-pair-2026-10-24.md).

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

## Validation status and live preflight

[Windows self-process CLI tests](../validation/typed-inline-capture-cli-host-2026-10-24.md) actually exercise read-only memory scan, SHA-linked request and full snapshot report publication, strict loader recovery, and replay overwrite rejection. Another test rejects wrong process start before any output directory is created. No current game RIFT memory has been read with this newly added command.

A RIFT-Lab-1 trial requires a fresh authenticated V14 coordinator/queue, exact guest process PID/start/EXE hash, same VMware VMX epoch, correctly pinned guest bundle and normal **V14 STOP/release** before opening the exclusive guest console; then original no-overwrite guest reports must be transferred with content-pinned integrity and a fresh successor coordinator independently verified. Until then, **V14 retains console ownership.**
