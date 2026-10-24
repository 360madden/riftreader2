# Current-epoch native memory map and clean V10 → V11 coordinator handover

Date: October 24, 2026 (America/New_York). Actual guest work: approximately 09:48–09:56 EDT; V11 normal recovery verified at 09:58 EDT. This is **live read-only process evidence**, not a field qualification or a navigation/movement trial.

## Exact identity and scope

- VMware VMX: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, VNC port 5905, `vmware-vmx.exe` PID **38044**, log epoch `2026-10-24T05:41:51.833Z`, exact Windows start ticks **134372941117887852**.
- Guest Rift: `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, PID **6940**, process-start UTC ticks **639284177321390013**, executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- The guest request uses `native-memory-map-request/1`, the exact preceding target identity, `maxRegionCount=32768`, and `maxDurationMilliseconds=10000`. Guest request SHA-256: **`F1C41A5F8B2D8B343105583CB086896D000C356D7130BF0768EA8F9370E1F2F3`**.
- Guest executable was confirmed present at `C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad\RiftReader2.Live.exe`. The guest decoded the 276-byte request using `certutil -decode` and independently computed the matching SHA-256 before invoking the executable.

## Actual result

- Read-only guest CLI command `map-native --request %TEMP%\rr2-map-oct24-01.json --output %TEMP%\rr2-map-oct24-01-report.json` completed with **`MAP_EXIT=0`**.
- The guest parsed the retained JSON report and printed **`MAP_STATUS=complete COUNT=20838`**: 20,838 mapped committed/readable regions from this exact game process. The largest displayed `type=0x20000` private region starts at **`0xD2F0000`** with **536,870,912 bytes (512 MiB)**. Other displayed private regions were tens of MiB; these are only search-space candidates, **not** proof of typed Lua data or player XYZ.
- **Guest-computed report SHA-256:** `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`.
- Full JSON report is **still guest-local** at `$env:TEMP\rr2-map-oct24-01-report.json` for the guest user's PowerShell environment; it has **not** been copied to the host or parsed offline. Its guest SHA and screenshots should be used to verify any eventual lossless transfer. The host does **not** yet possess usable raw map rows for selecting snapshot ranges.

## Exclusive console and restart sequence

1. Before guest input, normal V10 coordinator PID **8168** was intentionally stopped by its unique STOP marker. Its normal exit receipt is dated **2026-10-24T13:42:55Z**. Owner was gone, listeners 49712/49715 were closed, queue was **blocked=1/unheld** with no cleanup receipt. The canonical SQLite queue was not reset.
2. Initial screenshot-only console call with `C:\Python314\python.exe` failed before guest input because that interpreter lacks `vncdotool`. The dedicated existing V2 virtual environment `artifacts/native-vm-control/venv/Scripts/python.exe` has it; through the normal `ControlMutex` and existing Credential Manager-backed console path, a retry succeeded. No credential was printed or copied.
3. Independent screenshot initially showed idle Rift. A single permitted `windowsRunText` bootstrap opened guest PowerShell, confirmed by a fresh screenshot. Fifteen individually scoped PowerShell commands transmitted, decoded, SHA-verified, executed, parsed, and hashed the **read-only** map request. Each console batch guarded exact VM epoch, V10 exit and V11 not-yet-running, and released the console mutex; no game ARM, movement, keyboard control, debugger injection, memory write, or queue bypass occurred.
4. A one-use guarded `exit` closed guest PowerShell, and another screenshot showed Rift foreground and unobscured.
5. At **2026-10-24T13:57:23Z**, the V11 preflight independently verified exact unchanged VMware identity, matching config and five runtime hashes, V10 exit, absent V11 marker/receipt, closed host listeners, and the expected blocked/unheld canonical queue with no pending work.
6. V11 started through ordinary Windows WMI `Win32_Process.Create`, not a Workbridge-owned job: **`pythonw.exe` PID 60420**, process start ticks **134373238668010962**, Windows session **2**, `inJob=false`. Its pinned launcher ran `--reconcile-existing` and emitted a process receipt.
7. Actual V11 `control_client status` returned **connected=true**, coordination **ready**, supervisor **running**, `initialCleanupVerified=true`, console reservation held by the owner, and the exact original VM/game identities. Guest **armed=false**, **busy=false**, no sampled desktop inputs down, Rift **isForeground=true**. Authoritative read-only SQLite inspection then returned **blocked=0**, holder **null**, no pending requests, and cleanup receipt `nav-cleanup:9a2b79107381b51cef63c5c846f3ed9398366243f1b83bc7848aad5bc79daa1d`. This normal owner reconciliation, **not a manual unquarantine**, restored service.

## Retained local evidence

Ignored host-side evidence root: `artifacts/update-recovery-20261023-01/`. The underlying evidence files are local Windows files, not Git-tracked snapshots.

| Evidence | Screenshot SHA-256 |
| --- | --- |
| `rr2-map-console-07-09/screen.png` — request decode, verified hash, deployed CLI present | `C221884DA5E7361C480A93AFE5C59602AF84E9099A0852E30911C433C2537C46` |
| `rr2-map-console-11-13/screen.png` — successful exit and **20,838** regions | `8C11C6002C60C33ABD89D0442B377AF5D3C3540821617DD45250A2879472E3CA` |
| `rr2-map-console-14-15/screen.png` — private region summary and full guest report SHA | `09FE8314D4360DFC7413E050A503EE3869B05FEA6B85C97E4F7985DBC92D2878` |
| `rr2-map-console-closed-20261024-01/screen.png` — game foreground after guest shell exit | `9EBD9B6513BE7F5E90E40B0C62CEAE48919EA055B45DEA3987F24FBDAAA37C16` |

Batch receipts also exist in their corresponding directories. V10 and V11 process/exit receipts and the pinned V11 plan/launcher remain alongside them. The screenshots cannot substitute for transferring the actual JSON report or validating native field meaning.

## Next acceptance gates

1. Transfer the existing **guest read-only map report** to the host via a scoped, authenticated, size-bounded and hash-checked route, without exposing a reusable general-purpose network service. Reject it if its bytes do not hash to the recorded guest SHA-256. Any renewed console use must again STOP/release V11 and prove exclusive ownership; the present V11 must not be raced.
2. Select small, explicit current-epoch readable regions rather than scanning all 20,838 entries or an unbounded 4 GiB heap. Capture two independent, identity-bound `snapshot-native` reports far enough apart for the Lua producer to advance.
3. Run the existing V2 `inspect-typed-wire --before ... --after ...` strict offline verifier, then—**only with actual advancing source frames**—compare same-epoch Lua XYZ against a fresh read-only native `follow-pointer` of root RVA `0x32E0200`. Record holes, conflicts and contrary evidence; do not prematurely qualify any navigation field.

**Explicit limits:** This run did **not** obtain a typed Lua frame, copy the full map to host, take new snapshots, establish native/Lua XYZ agreement, test guest unattended reboot, or move a character. The coordinator is V11 **as of this checkpoint**; future process/VM epochs must be rediscovered before use.
