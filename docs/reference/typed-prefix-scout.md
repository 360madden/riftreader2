# Bounded native typed-prefix scout

Status: **implemented, Windows-host tested and first run read-only in RIFT-Lab-1 on October 24, 2026**. The initial exact-process pass returned three `RRAPIVAL2|` candidate addresses (`0xD3DB230`, `0xD6C0550`, `0xD763500`), after examining **512 MiB** with **zero holes**; it returned the documented **partial/byte-budget** result, not complete coverage. Original report and safely restored V13 coordinator are documented in [live scout validation](../validation/typed-prefix-scout-live-2026-10-24.md). These are *candidate byte prefixes*, not qualified Lua frames or player coordinates.

This command is separate from the existing `RR2L1` challenge scanner and the 4 KiB `snapshot-native` read contract. It reuses the strict `WindowsNativeMemorySession` process-epoch identity checks and its readable-region enumeration; a separate 64 KiB reusable buffer calls read-only `ReadProcessMemory`. V1 source and game memory remain unchanged.

## Exact-target request

In the **same 64-bit Windows environment as the target RIFT process**, execute the pinned `RiftReader2.Live.exe` binary (or the verified .NET invocation) with:

```powershell
.\RiftReader2.Live.exe scout-typed-native --request .\scout-request.json --output .\scout-report-01.json
```

The output path must not exist. Use a different path for each acquisition. A report published locally inside a guest must later be transferred to the host using a verified, content-pinned evidence path.

Version-1 JSON shape (this **October 24 epoch is an example, not a reusable future process identity**):

```json
{
  "schemaVersion": 1,
  "evidenceKind": "native-typed-prefix-scout-request/1",
  "target": {
    "processId": 6940,
    "processStartUtcTicks": 639284177321390013,
    "executableSha256": "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
  },
  "startAddress": "0x10000",
  "maxScanBytes": 536870912,
  "maxDurationMilliseconds": 30000,
  "maxRegionCount": 32768,
  "maxMatchCount": 128
}
```

Do **not** reuse the example after process/VM restart, game update or hash/identity drift. Capture PID, exact unrounded process-start ticks and full on-disk SHA-256 again. The request's JSON bytes are SHA-256-bound in the report.

Strict limits:

| Field | Contract |
| --- | --- |
| `startAddress` | Canonical uppercase hex `0x...` with no leading zeroes, at least `0x10000`, below `0x7FFFFFFFFFFF`; this is a **process-epoch** address cursor |
| `maxScanBytes` | 65,536 through **536,870,912** (512 MiB); limits *attempted* memory bytes, including failed reads |
| `maxDurationMilliseconds` | 1 through **30,000**, covering enumeration, reads and post-read identity revalidation for status determination |
| `maxRegionCount` | 1 through **32,768** readable regions; too many regions fails rather than silently omitting a tail |
| `maxMatchCount` | 1 through **128** retained complete marker prefixes; the first omitted match is exposed as a resume cursor |
| Marker and scope | Fixed `RRAPIVAL2|`; committed, readable, non-guard **MEM_PRIVATE** regions at or after `startAddress`; MEM_IMAGE/MEM_MAPPED are not searched |

No arbitrary memory pattern, process name, game key, injection, debugger or write control is accepted by this command.

## Evidence report (`native-typed-prefix-scout/1`)

The no-overwrite JSON contains:

- `requestSha256`, `coverageContentSha256`, implementation assembly/bundle identity and the full bounded request;
- exact native process PID/start/path, executable SHA and main-module identity, plus UTC acquisition bounds;
- `status`, `reason`, fixed `scope` and `marker`;
- `startAddress` and nullable `nextAddress`, both **hex strings** to preserve exact 64-bit values;
- `eligiblePrivateBytes`, `attemptedBytes`, `examinedBytes`, private-region count and touched-region count;
- `prefixAddresses` (hex candidate addresses only), contiguous `coveredSpans` and explicitly sized `holes` with relevant Win32 errors.

Only bytes actually examined by the matcher count toward `examinedBytes`. `attemptedBytes` also includes failed or unexamined portions of already requested 64 KiB chunks. A partial pass need not have examined every attempted byte. No raw heap bytes are included. The content hash covers the canonical JSON of request digest, identity, timestamps, status, reason and scanner result under repository serializer settings; it is evidence integrity metadata, **not proof of Lua semantics**.

| Report status | Exit | Meaning |
| --- | ---: | --- |
| `complete` | 0 | No holes, limits or identity drift across the **selected private-region suffix**; zero matches means absence only within that exact observed scope |
| `partial` | 3 | Byte/time budget, prefix limit or unreadable holes; inspect `reason`, coverage and `nextAddress`; global absence/uniqueness is unsupported |
| `identity-invalidated` | 3 | Post-read PID/start/path/file/module identity failed; any prefix addresses are untrusted and **no resume cursor** is issued |
| Request, map enumeration or output error | 2 | Input/identity/OS/file failure before a normal report; do not infer coverage |
| Cancellation | 130 | No completed report published |

The partial `nextAddress` normally backs up **10 bytes** (marker length minus one) to recover a prefix split across passes. It can re-read already covered bytes and can point back to the earliest unreadable hole. Deduplicate candidates using **exact process epoch + address** and retain each pass's coverage receipt. Repeated holes can prevent convergence; do not claim completed coverage by skipping them.

## Acceptance sequence (steps 1–3 passed for the October 24 RIFT-Lab-1 run)

For the exact October 24 PID/start/build epoch, the guarded V12 release, pinned binary transfer, 512 MiB bounded scan, host report transfer and verified V13 restoration **all completed**; see the [actual guest execution record](../validation/typed-prefix-scout-live-2026-10-24.md). Steps 4–5 below are **pending**. All steps must be rechecked when the process/VM epoch changes.

1. Verify **fresh** VM, guest, coordinator and canonical SQLite queue state. Do not compete with the live coordinator's exclusive console. Guest use requires a verified normal coordinator STOP/release, then a correctly pinned successor restoration.
2. Build and hash-pin the tested V2 guest bundle; transfer and validate it in the exact guest without overwriting prior evidence. No default request can run against a different PID/start/SHA.
3. Run one bounded 512 MiB/30-second pass, retain its original request, report bytes/hash, result/coverage and the exact implementation identity. Continue only if the process epoch is unchanged; a partial result is useful limited evidence.
4. For positive prefix candidates, use the [SHA-pinned two-request offline planner](../validation/typed-scout-snapshot-followup-plan-2026-10-24.md) to select small `snapshot-native` ranges. Capture those byte neighborhoods in at least **two independent acquisition windows**, then run [strict `inspect-typed-wire`](typed-wire-snapshot.md). An address hit alone is **not** a Lua frame or current XYZ.
5. Only when a complete typed source advances independently, compare with the same-epoch native pointer chain rooted at RVA `0x32E0200`; retain the raw evidence and do not promote unverified field meaning.

The [host→guest streaming transfer readiness](../validation/typed-prefix-scout-transfer-2026-10-24.md) is a historical host-only preflight and should **not** be treated as evidence of a guest run. The subsequently completed [live scout report and V13 recovery](../validation/typed-prefix-scout-live-2026-10-24.md) separately provide that evidence.

See the [scout reuse-first rationale](../research/typed-prefix-scout-reuse-2026-10-24.md), [actual live map and V12 restoration](../validation/guest-map-report-transfer-2026-10-24.md) and [current status](../status.md).
