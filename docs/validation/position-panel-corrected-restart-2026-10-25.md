# Corrected position window: full game restart passed, October 25

The Start / Read / Stop interface is installed and live-validated through **one
complete normal RIFT exit and relaunch with the corrected reader**. The
[first trial](position-panel-restart-2026-10-25.md) exposed initialization values
incorrectly labeled live. Its originals remain preserved separately. Commit
`8e94c5b` corrects that observed case; the second trial verifies the fix.
Patch recovery remains deferred.

## Correction and full gate

The panel rejects any subnormal float32 XYZ component from live presentation,
clears coordinates/current identity and displays **Waiting for position**.
Monitoring continues retrying. Zero and normal negative coordinates remain
accepted. Raw sampler reports are retained unchanged before presentation
filtering. This numerical guard addresses the observed startup case; it does not
prove that every finite normal value is semantically ready.

Four added regression cases cover each axis and observed initialization followed
by same-process recovery without another Start. The corrected full gate passed
**469 .NET (311 portable + 158 Live), 669 Python, 108 Lua and 22 Lua/C# contracts**,
zero-warning build, native publish/smoke, replay, formatting and **551 relative
links**. Exit 0 at **14:25:02 UTC**; evidence:
`artifacts/validation/20261025T142358Z-0930c594/`,
`artifacts/validation/position-panel-startup-guard-full-gate.log` and its result JSON.

## Exact deployed build and restart

New guest installation: `C:\RIFT_TRANSFER\RR2-XYZ-Interface-oct25-02\`.
The first installation was preserved. The read-only validation courier checked
reader/profile sizes and SHA-256 before installing.

| Payload | Bytes | SHA-256 |
| --- | ---: | --- |
| Corrected reader | 116,924,768 | `E01EA1DF88BD70E760F91D4DDB33757D647290A293166EC272DA2BAF2A617E95` |
| Unchanged profile | 395 | `FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8` |
| Validation-only courier | 39,424 | `5E61CAFB9AD38155D2A532C986DBAF4173DC6FBC9667AA1352A3BB54D4392F77` |

Actual guest clicks exercised Read, Start, Stop clearing and Start again. Panel
process **12036** remained monitoring across normal RIFT **Exit Game**, its
countdown, Glyph **Play** and Atank's world-entry **Play**. No force-close, guest
terminal, debugger, process-memory write or gameplay automation was used.

| Identity | Before | After |
| --- | --- | --- |
| Game PID | 11712 | 1224 |
| Process start UTC ticks | 639285339497136209 | 639285359295548343 |
| Session-local owner | `0x1C233730010` | `0x202BA8B1480` |

Both game epochs use SHA
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
The unchanged recipe resolves RVA `0x32E0200` afresh and reads float32 XYZ at
`+0x320/+0x324/+0x328`.

Absence proof found **zero RIFT processes**, old exact process ended, sampler
**exit 2/no report**. The window showed Waiting for RIFT with no identity or XYZ.
Independent **3/3 before + 3/3 after** samples and separate 816-byte pointer
reports agreed exactly at float32 byte level:
**(7460.6298828125, 863.8043823242188, 2976.61669921875)**. The old-epoch pointer
request after relaunch also returned **exit 2/no report**.

## Startup behavior verified against original reports

All **323** report files/hashes in the **1,133-event** panel journal verified.
There are 82 old-process reports, process exit/absence failures, then the new
epoch. During initialization, the new epoch retained **one invalid pointer
report and 59 subnormal reports**. Every subnormal report was followed by
`unavailable / position-values-not-ready`, clearing identity and observation.
**Zero subnormal reports were published live.** A screenshot at character
selection independently shows Waiting for position, blank XYZ and retry guidance.

The first correct new-epoch report, `read-00217.json`, completed at **14:39:56 UTC**.
The same monitoring run produced **181 correct live reports**, with **zero
intervening Start actions**. An in-world screenshot shows the new PID and XYZ.
After restart, Stop cleared values, Read worked while stopped, its result
expired, and normal close returned **exit 0 at 14:43:50 UTC**.

## Evidence, transfer and cleanup

Working evidence:
`artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-02/`.
Original `restart.zip`: **537,644 bytes**, SHA
`8456D319242DA19A3982B4F66155626E61C35856C3463AB68CDDF9E256496899`.
All **356** manifest-declared lengths/hashes verified in a new safe extraction;
the remaining file is the self-excluded manifest. Verification record SHA:
`F8E3AF318C9621717C0634ADE5D66284973310602B3009A59B26332CEF96622F`.

Separate one-use claim/upload owners **66624 / 21824** ran in signed-in Windows
session 2, `inJob=false`, through the proven WMI/CIM launch pattern. Exact peer,
target epoch, reader hash, archive length/SHA matched; both services exited
normally. The pointer-named protocol was transport only.

At Joey's explicit request to recover the saved VMware password and use the CLI,
the current user's existing Windows credential entry enabled authenticated
`vmrun` media operations. The password was not printed or written into scripts,
receipts, documentation or exports. CLI disconnect/write/connect plus runtime
readback attached the corrected ISO; guest File Explorer confirmed `RR2_XYZ_UI2`.
After courier close, the same CLI sequence restored and read back the original
`C:\work\riftreader2\artifacts\field-discovery\rr2-fields.iso`. No VM reboot or
isolation change was needed.

Independent **V21 PID 73252**, session 2, `inJob=false`, resumed at **14:47:05 UTC**.
Authenticated status at **14:49:58 UTC** and cleanup at **14:50:29 UTC** confirmed
ready/connected, exclusive console, running supervisor, guest disarmed/idle/no
held inputs, queue unblocked/unheld with cleanup receipt and transfer port 8765
closed. Target is PID 1224; the last status marked the game not foreground.
VMware PID **38044** and its start/log epoch stayed unchanged. The failed trial-01
temporary Scheduler registration was removed and its absence rechecked. Refresh
these dated identities before further input.

Portable local export: `artifacts/exports/xyz-interface-restart-20261025-02.zip`,
with `.zip.sha256`, `checksums.json`, readable `report.html`, both original guest
ZIPs, verification, selected screenshots/action receipts, cleanup and full-gate
evidence. Credentials, private configuration, binaries and operational helpers
are excluded. Trial 01 stays labeled as the defect-producing trial.

This establishes one corrected-reader same-game-build restart. No new Lua or
movement comparison was collected. General semantic readiness, unlimited
reliability, VM/host restart durability, field promotion and patch recovery
remain outside this result.
