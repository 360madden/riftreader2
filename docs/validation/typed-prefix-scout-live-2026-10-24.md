# First live V2 typed-prefix scout and normal V13 restoration — October 24, 2026

**Result:** A read-only `scout-typed-native` scan actually ran in **RIFT-Lab-1**, found **three current-epoch `RRAPIVAL2|` prefix candidates**, returned a **partial** 512 MiB coverage report, transferred the original JSON losslessly to the Windows host, and restored the authenticated V13 coordinator. **No typed Lua frame or player XYZ is qualified by these results.**

This follows the [host-only implementation validation](typed-prefix-scout-host-validation-2026-10-24.md) and [pinned transfer readiness](typed-prefix-scout-transfer-2026-10-24.md), which did not themselves claim guest execution.

## Exact acquired environment

- VMware: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, vmware-vmx PID **38044**, Windows start ticks **134372941117887852**, VNC 5905, log epoch **2026-10-24T05:41:51.833Z**.
- Actual RIFT process: guest PID **6940**, UTC start ticks **639284177321390013**, on-disk `rift_x64.exe` SHA-256 **`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`**.
- Pinned V2 guest executable: **74,209,699 bytes**, SHA-256 **`C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C`**. Downloaded to guest Temp as `rr2-scout-oct24-01.exe`; guest PowerShell independently printed the complete SHA, byte count and **`EXE_GATE=True`**. Bundle identity in the actual result is `deploymentKind=single-file-bundle`, same SHA.
- Guest read-only request file SHA-256 **`4511BCA5A3D5F1FB15ADE88427A33AC6EB3FBB91BF1B91D4ED5E43811A87D14F`**. The decoded guest file independently printed matching hash and **`RUN_GATE=True`**. It fixes PID/start/build, `startAddress=0x10000`, 512 MiB byte cap, 30-second duration, 32,768-region limit and 128-match cap.

## Actual guest scan result

The native report records an acquisition from **16:42:13.4536214Z** to **16:42:14.2549234Z** (October 24), `status=partial`, `reason=byte-budget-exceeded`, CLI **`SCOUT_EXIT=3`** (documented partial status, not process crash).

| Evidence | Actual value |
| --- | --- |
| Eligible readable MEM_PRIVATE virtual bytes at acquisition | **9,469,878,272** across **23,124** private regions |
| Attempted / examined | **536,870,912 / 536,870,912 bytes** (512 MiB) |
| Covered scope | Exactly one private span: base **`0xD2F0000`**, length **536,870,912** |
| Private regions touched | **1** |
| Prefix candidates | **3** |
| Unreadable holes | **0** |
| Eligible-private-byte coverage | **5.669%**, not a whole-process search |
| Reported next cursor | **`0x7FFDFFF7`** (preserve exact value; next-pass behavior not tested live) |

Exact candidate prefix addresses in this unchanged game-process epoch:

| Prefix address | Offset within the `0xD2F0000` covered region |
| --- | --- |
| `0xD3DB230` | `0xEB230` |
| `0xD6C0550` | `0x3D0550` |
| `0xD763500` | `0x473500` |

The host independently checked that all three distinct address integers lie within the fully covered span, that the request SHA matches the original request file, that attempted and examined bytes both equal the 512 MiB cap, that there are no holes, and that the report's exact PID/start/build/bundle identities match the pinned values.

**Scope limitation:** `RRAPIVAL2|` is only an 11-byte *prefix*. These matches might be valid complete producer frames, incomplete copies, old copies or unrelated byte sequences. No follow-on `snapshot-native`, two-time `inspect-typed-wire`, source advancement, or native/Lua position correlation has yet run. The prior October 24 memory map had fewer readable private bytes; these totals were measured at different instants, so the difference does not itself prove a process-layout regression. Likewise, the next cursor is recorded, not yet proven by a second scan.

## Verified host transfer and recoverable evidence

- One-use VMnet8 GET endpoint `192.168.56.1:8765` (only guest peer `192.168.56.128`) ran independently as `pythonw.exe` PID **7048**, Windows session 2, outside Workbridge's job. It served **74,209,699** pinned executable bytes, checked the streamed SHA and reported `delivered` with zero incomplete responses. It subsequently exited and released port 8765.
- Guest report `$env:TEMP\rr2-scout-oct24-01-report.json` was independently hashed on guest, **2,902 bytes**, SHA-256 **`87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6`**.
- Reused the tested one-use POST receiver, hash-pinned to that exact digest, through independent `pythonw.exe` PID **60720**. It accepted guest `192.168.56.128` at **16:51:17.803661Z** and automatically exited. Although its old fixed route is named `/rr2-map-oct24-01-report.json`, its stored *content* is the new scout report, not a memory map.
- Original report retained at **`C:\work\riftreader2\artifacts\update-recovery-20261023-01\rr2-scout-oct24-01-host.json`**, still **2,902** bytes with **identical independent host SHA**. The no-overwrite receipt `rr2-scout-oct24-01-upload-receipt.json` confirms state `received`, guest IP, byte count and matching SHA.
- Related original request, immutable command manifests, one-use transfer launchers, guest step receipts, screenshots, and server event are retained in ignored `artifacts/` folders. No existing report was overwritten.

Representative retained original guest screenshots (SHA-256):

| Screenshot | Verified visual observation | SHA-256 |
| --- | --- | --- |
| `rr2-scout-guest-step-06/screen.png` | `EXE_GATE=True` and full executable SHA / bytes | `C2EFDA84ADC69B42B5B23E3FB972B3A357AAEDF1CE102EB1EC6412CCDE7880DF` |
| `rr2-scout-guest-step-14/screen.png` | Request SHA matches; `RUN_GATE=True` | `C67A712754D4E01B6D46FCDC91532616BF37252801B2CDD9D691E4D8C74FF495` |
| `rr2-scout-guest-step-16/screen.png` | Actual native partial report and three matches | `A5EADE959E8C420A3A5118D4F0A2EF3CD93F271765CC8EB74981D81E7BE8D030` |
| `rr2-scout-guest-upload-step-03/screen.png` | PowerShell closed, RIFT visible | `6BE5E2000E0C8421B4D99ABF0431AD67262452C9F31E5F93209D98CD138F15FE` |

## Exclusive maintenance and post-scan operational state

1. V13 same-epoch plan was prepared while V12 was still healthy. Verified original V12 PID **15336**, live connected/ready, no queued/held requests and a canonical cleanup receipt, identical VM epoch, and no transfer listener. The expected attempt to query the *mutex-acquiring* `VmEpochGuard` while V12 held its exclusive console lock returned `controller-busy`; the separate read-only VM identity collector was used, without lock bypass.
2. Wrote only V12's unique STOP marker. The V12 process exited **normally** with its exit receipt; process PID was gone, native ports 49712/49715 closed, and SQLite authority explicitly **blocked=1**, no holder, no cleanup receipt, zero pending.
3. Every guest action used the existing V2 console mutex, exact VM identity before/after, individual no-overwrite one-step receipts and screenshots. Opened guest PowerShell; made the bounded download/hash/request/scan/upload checks; then sent `exit`. No game movement, debugger, injection, memory write, VM settings change, credentials transfer, or manual queue update occurred.
4. Revalidated the full host report hash, closed temporary HTTP listener, blocked/unheld authority and original VM epoch; launched existing SHA-pinned V13 recovery as independent Windows-session-2 `pythonw.exe` PID **65364**.
5. **Post-restoration Python-exact-64-bit check passed at 16:54:46Z:** authenticated `connected=true`, coordination **ready**, supervisor **running**, `initialCleanupVerified=true`, guest disarmed/idle, no held inputs, RIFT foreground, unchanged PID **6940** / exact start ticks **639284177321390013** / executable SHA. Canonical SQLite authority **blocked=0**, holder absent, zero pending and a new verified cleanup receipt. V13's process receipt confirms Windows session 2 and **`inJob=false`**. No manual unquarantine or overlapping VNC owner.

## Next acceptance gate

1. Offline-check narrow `snapshot-native` window requests around **each** of the three candidate prefixes, with a generous enough suffix to include a complete typed frame and explicit 64 KiB/byte limits. Preserve a plan with exact current process identity and no reuse of historical absolute addresses.
2. Obtain **two independent time-separated guest snapshots** only under a *new* legitimate V13→V14 normal STOP/recovery transaction, with no movement or memory writes.
3. Transfer both originals and use the already-tested strict `inspect-typed-wire` verifier. Require a complete frame with the same Lua source, an advancing sequence and time frame, before considering a same-epoch native XYZ pointer comparison.
4. Consider a separate bounded continuation from `0x7FFDFFF7` after qualifying this focused region; deduplicate by process epoch and address, and never imply whole-heap absence from this 5.669% pass.
