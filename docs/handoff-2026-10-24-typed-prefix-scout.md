# Operational handoff: current-epoch typed Lua prefix scout

Prepared: **2026-10-24, approximately 10:50 EDT** (America/New_York).
Repository: `C:\work\riftreader2`; branch: `codex/modular-foundation`.
The handoff is a *checked snapshot*, not a guarantee that live Windows process identities remain unchanged. Re-detect before any guest access.

## Immediate outcome

- The RIFT-Lab-1 VM, RIFT client, guest receiver and independent **V12** native host were connected/ready at the final read-only check. No game input, process write, debugger attachment, VM restart or manual queue reset occurred during this handoff.
- The complete current-game memory map was acquired in the guest and copied **byte-for-byte** to the Windows host. The report records **20,838 readable regions / 7,846,682,624 readable virtual bytes**; of these, **19,956 private regions / 7,648,837,632 bytes**. These counts are *virtual address space*, not physical RAM.
- Reuse-first research selected a bounded marker-only scan for `RRAPIVAL2|` instead of random large memory snapshots or changing V1's 4 GiB/10 s observer defaults.
- **Step 1 implemented and committed:** `TypedApiPrefixMatcher` streams contiguous byte ranges, retains absolute marker addresses, handles 64 KiB read boundaries and overlapping partial prefixes, resets on gaps, checks address overflow and reports match-budget overflow without silent truncation. It does not decode or qualify Lua frames. **It is not yet wired into a live scanning command.**
- No current typed frame or native/Lua XYZ agreement has been established. Work remains in V2 native-scanner integration and source qualification.

## Ten most recent project commits before this handoff

| Short SHA | Verified purpose |
| --- | --- |
| `6db17e1` | V2 typed-prefix matcher plus 12 synthetic tests; .NET full gate 395/395 |
| `36e5eb2` | Bounded scanner reuse-first design and scope controls |
| `d90c600` | Complete map and successful V12 restoration evidence |
| `183bd71` | One-use hash-pinned guest-to-host JSON receiver; Python 514/514 |
| `1e3c2af` | Current-epoch guest map and verified V11 recovery evidence |
| `da7b079` | Strict offline `inspect-typed-wire` against two native snapshots |
| `4e3ffb4` | Three-frame native visual comparison and provenance |
| `9ddd90c` | Typed Lua readback recovery investigation and positive historical frames |
| `b983f52` | Exact-same-VM-epoch coordinator handover guard |
| `b7d1a15` | Authenticated V10 leased screenshot and STOP/release baseline |

The new handoff commit will become HEAD **after** this list was captured. Use `git log -10 --oneline` for the latest rolling list. No push was performed.

## Latest live identity and authority check

Checked through `scripts.control_client status` at **2026-10-24T14:49:02Z** and a separate read-only SQLite transaction at **14:49:54Z**:

| Layer | Evidence |
| --- | --- |
| VMware | `vmware-vmx.exe` PID **38044**, `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, VNC port **5905**, log epoch **2026-10-24T05:41:51.833Z**, VM process `startTicks=134372941117887852` |
| RIFT guest | `rift_x64.exe` PID **6940**, `processStartUtcTicks=639284177321390013`, executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD` |
| V12 coordinator | Last independently launched `pythonw.exe` PID **15336** (session 2, outside Workbridge job). Authenticated status: host **connected**, coordination **ready**, supervisor **running**, `initialCleanupVerified=true`, game **foreground**, guest **disarmed**, **idle**, zero sampled desktop inputs down. Reconfirm OS process ID if a new handover is required. |
| Canonical queue | `artifacts/native-coordination-live/queue.sqlite3`, resource `vm:rift-lab-1`; `blocked=0`, holder **null**, **no queued/active/cleanup requests** (the snapshot helper would raise otherwise); newest cleanup receipt `nav-cleanup:dd28b9be952b422e77ccf17cc7429a15e880545899ac9070163f4d3f083ccad9`. |
| Exclusive console | Live coordinator holds the console reservation. **Do not open a competing VNC/console route while it is running.** For guest maintenance first complete the legitimate exact-owner STOP/release and confirm normal exit/quarantined authority, then restore a new coordinator and verify cleanup. |

The Windows host map:
`artifacts/update-recovery-20261023-01/rr2-map-oct24-01-host.json`

- Size: **2,831,071 bytes**.
- SHA-256: `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`.
- Source: `native-memory-map/1`, complete at **2026-10-24T13:52:45Z**, exact game identity above.
- Two historical October 16 typed-frame heap addresses, `0x3D3189F0` and `0x3D2BD3B0`, are **not readable in the present map**; do not use them as current locators.
- The one-use inbound transfer on port 8765 exited after the upload; do not assume an upload service is still listening. See [transfer/V12 validation](validation/guest-map-report-transfer-2026-10-24.md).

## Validation that actually ran

1. `dotnet test tests\RiftReader2.Live.Tests\RiftReader2.Live.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~TypedApiPrefixMatcherTests`: **12 passed**.
2. `dotnet test RiftReader2.slnx --configuration Release --no-restore --verbosity quiet`: **395 passed** (102 Live + 293 core); no test failures.
3. `git diff --check`: passed before the matcher commit; the working tree was subsequently clean before the handoff.
4. Prior receiver milestone: **514 Python tests** passed; these were not rerun for the C#-only matcher change.
5. The complete `pwsh -NoProfile -File scripts/validate.ps1` composite was **not run** for this incremental checkpoint because PowerShell 7 was not available via Workbridge; do not imply Lua/cross-language gates were rerun. All of the above .NET tests ran on the Windows host, **not in the guest VM**.

## Authorized next work: V2 bounded scanner (no guest run yet)

1. Reuse the existing V2 memory-region traversal and 64 KiB `ReadProcessMemory` buffer in `src/RiftReader2.Live/WindowsMemoryScanner.cs`, but do **not** call its existing `RR2L1` challenge scanner unchanged: it preflights the entire private region space and rejects a smaller byte budget before reading any bytes. Preserve existing behavior for that scanner.
2. Add a separate **read-only, exact-process-epoch** scanner path using `WindowsNativeMemorySession.OpenAsync` and `RevalidateAsync`. Do not weaken `WindowsNativeMemorySession.Read`'s existing 4,096-byte snapshot contract. Scanner chunks may use a separately bounded 64 KiB read method, with explicit failed-read holes and no marker carry-over across holes.
3. Design and test versioned `scout-typed-native --request PATH --output PATH` inputs and no-overwrite report: exact PID/start/SHA, canonical `startAddress` cursor, **at most 512 MiB / 30 s / 32,768 regions / 128 retained prefix matches per pass**, byte/region coverage, `nextAddress`, holes, reason and partial/complete/invalidated status. A partial pass never proves global absence or uniqueness. Read-only synthetic tests must exercise time, byte, hole, match and identity limits.
4. When source/tests/CLI/report are passing and a pinned guest binary is prepared, perform fresh *read-only* VM/guest/coordinator/queue checks. Guest deployment or console interaction must use the exact coordinated handover protocol; do not reuse an old PID or prior one-use shutdown marker, and never reset the canonical queue.
5. Only after current-epoch positive prefix candidates: take two small, separately timed `snapshot-native` captures around candidate addresses; run the existing strict `inspect-typed-wire` parser to require complete frames and independently advancing Lua sequence/time. Compare to a fresh read-only `follow-pointer` at root RVA `0x32E0200` in the **same** game process epoch. Do not promote a pointer or field meaning before independent verification.

Reference: [typed scout design](research/typed-prefix-scout-reuse-2026-10-24.md), [typed-wire parser contract](reference/typed-wire-snapshot.md), [live map evidence](validation/current-epoch-native-map-2026-10-24.md).

## Five-minute safe resumption

In **PowerShell on the Windows host** (do not enter in the game or guest):

```powershell
Set-Location C:\work\riftreader2
git status --short --branch
git log -10 --oneline
C:\Python314\python.exe -m scripts.control_client --config artifacts/native-usability-20261020/host.json status
C:\Python314\python.exe -c "from pathlib import Path; from scripts.prepare_native_host_handover import authority_snapshot; print(authority_snapshot(Path(r'C:\work\riftreader2\artifacts\native-coordination-live\queue.sqlite3'), 'vm:rift-lab-1'))"
dotnet test RiftReader2.slnx --configuration Release --no-restore --verbosity quiet
```

If VM epoch, guest PID/start/build, supervisor/queue, or source hashes differ, **stop any guest access** and follow the exact-identity recovery workflow, not a historical plan. Keep generated guest maps, binaries, screenshots and coordination receipts in ignored `artifacts/`; do not stage these or unrelated user work. Prefer small verified commits for significant findings. Do not edit V1, alter guest memory, attach a debugger, automate gameplay, push remotely or change OS/VM settings as an incidental step.
