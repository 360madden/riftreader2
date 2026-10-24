# Content-addressed guest map transfer and V12 normal recovery

Date: October 24, 2026 (America/New_York). Guest upload accepted at **10:21:58 EDT**; V12 recovery verified by **10:23:33 EDT**. This follows the [live V10 map and V11 recovery](current-epoch-native-map-2026-10-24.md) and supersedes that checkpoint's statement that the map was only present in the guest.

## Outcome: full map is now on the host

The existing exact-current-process guest memory map was copied **losslessly** to ignored Windows host artifact:

`C:\work\riftreader2\artifacts\update-recovery-20261023-01\rr2-map-oct24-01-host.json`

- **Byte length:** `2,831,071`.
- **Full SHA-256:** `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`. This matches the original guest-computed report hash, the guest's pre-upload recheck, the receiving server's streaming hash, its receipt and the independently computed host file hash.
- **Report contract:** `schemaVersion=1`, `evidenceKind=native-memory-map/1`, `status=complete`, `reason=null`, **20,838** regions, request SHA `F1C41A5F8B2D8B343105583CB086896D000C356D7130BF0768EA8F9370E1F2F3`.
- **Acquisition time, from original report:** `2026-10-24T13:52:45.2047453Z` to `13:52:45.4100626Z`. This is the original guest map's source window, **not** transfer time.
- **Target identity verified inside report:** RIFT PID **6940**, process-start ticks **639284177321390013**, `rift_x64.exe` SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`, main module base `0x7FF6EBDA0000`, size **62,611,456 bytes**. Guest deployed Live bundle hash is `70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E`.

## Reuse-first bounded transfer

Added `scripts/receive_guest_memory_report.py` (commit `183bd71`) because the existing guest receiver ZIP server handled *host-to-guest GET only*. The new endpoint:

- Binds only `192.168.56.1:8765` on the already configured host-only VMware network, accepts only a **single POST** to `/rr2-map-oct24-01-report.json` from guest source `192.168.56.128`, and requires the exact preobserved SHA-256. It does not answer GET with a file, execute commands, or control Rift.
- Rejects wrong route/source/type, absent/invalid Content-Length, over **16 MiB**, wrong hash, existing destination, and publication races; writes to a temporary file and publishes via an atomic **no-clobber hard link**. Automatically stops on accepted delivery or timeout (maximum 600 seconds). It is source/content-bound, **not a general authenticated file server**.
- Reuses the existing normal-user `pythonw.exe` firewall exception; **no new firewall rule, public bind, guest password, VM configuration, gameplay input, or V1 edit** was made.
- Passed **12/12 isolated loopback tests**, including wrong hash, peer, route, method, size, type, absent length, no-overwrite and atomic collision. The broader Python suite passed **514/514**. `git diff --check` passed. No .NET code changed in this feature.

Live server was independent `pythonw.exe` **PID 628**, Windows session **2**, `inJob=false`, with pinned launcher/runtime/checks. Its receipt is `artifacts/update-recovery-20261023-01/rr2-map-oct24-01-transfer-receipt.json`; it recorded `state=received`, source `192.168.56.128`, bytes `2831071`, and matching SHA at `2026-10-24T14:21:58.297873Z`. Subsequent independent check: **zero listeners on 8765; PID 628 no longer alive**.

## Exclusive guest maintenance and V11 → V12

1. V12 exact-same-VM-epoch handover plan was prepared **while V11 was still running and ready**, with clean canonical authority. V11 PID **60420** received its unique STOP marker and produced an actual normal exit receipt at `2026-10-24T14:18:18.157137Z`.
2. Before opening the one-use HTTP receiver and before any guest input, the authoritative SQLite queue was confirmed **blocked=1**, holder `null`, cleanup receipt `null`, pending requests **0**; prior coordinator PID gone. A preliminary `VmEpochGuard.collect` had correctly returned `controller-busy` while V11 held the exclusive mutex. That lock was **respected**; the upload launcher explicitly required normal V11 exit/quarantine.
3. Guest PowerShell was opened via the authenticated, mutex-protected VM-console bootstrap. Its source file `$env:TEMP\rr2-map-oct24-01-report.json` recomputed the expected SHA and **2,831,071** bytes before gated `Invoke-WebRequest -Method Post -InFile`. The receiver accepted the exact bytes. The guest explicitly printed `MAP_UPLOAD_GATE=True` and `UPLOAD_HTTP=201`; the sender shell then exited, and V12 subsequently confirmed Rift foreground.
4. V12 was launched **only after** renewed exact VM/runtime/config hash and blocked queue preflight. Normal independent `pythonw.exe` **PID 15336**, start ticks **134373253939305796**, Windows session **2**, `inJob=false`. V12 `--reconcile-existing` returned authenticated **connected/ready**, owned supervisor **running** with `initialCleanupVerified=true`, guest **disarmed/idle**, no sampled buttons down, exact game PID/start/build, **Rift foreground**, and unchanged VMware PID **38044**/log epoch `2026-10-24T05:41:51.833Z`.
5. Fresh read-only queue snapshot after V12: **blocked=0**, no holder, zero pending, cleanup receipt `nav-cleanup:9a67f11d4085e04e604d89a90020c765f0cc0b115f3ae42d0aedd9eb88d3a517`. **No manual queue reset or concurrent VNC connection.**

Retained upload-console screenshots under ignored artifact root include:

| Screenshot | SHA-256 |
| --- | --- |
| `rr2-map-upload-console-01-03/screen.png` — guest SHA and byte count | `98CDEE896C487D2FCBA2E49470375E89024A170021789E4B040DFDD7539499C1` |
| `rr2-map-upload-console-04-04/screen.png` — content/size gate | `06E4823F6356FC82F159D9D94CC15B26D953B4FEF59DCE71B5C6A9FECBE5A0A2` |
| `rr2-map-upload-console-07-07/screen.png` — upload response | `60E1CD260939253A4326133701399712C2A9E79BF552462FAA611513D4727108` |
| `rr2-map-upload-console-08-08/screen.png` — return to Rift | `5E4EF177F0C0B781F2CBE2A8DE7AA1A874D852E25467023A00D87984F69DB1F5` |

The receiver's one-use launcher, stdout/stderr, process receipt, sent-command manifest, and VM-console batch receipts remain in ignored local artifacts; the **report is intact on the host** for offline analysis.

## Actual current-epoch memory landscape (offline report parsing)

| Region class | Count | Readable virtual bytes |
| --- | ---: | ---: |
| Private (`0x20000`) | 19,956 | 7,648,837,632 |
| Image (`0x1000000`) | 596 | 140,021,760 |
| Mapped (`0x40000`) | 286 | 57,823,232 |
| **Total** | **20,838** | **7,846,682,624** |

Of 20,838 returned regions, **20,090** have protection `0x4` (read/write). Only **8 readable regions** appear below the 4 GiB virtual-address boundary, totaling **537,018,368** bytes. Historical October 16 typed-frame absolute addresses `0x3D3189F0` and `0x3D2BD3B0` are **not contained in any currently listed readable region**. Thus old absolute pointers are invalid search inputs for this process epoch. The largest returned private span is 512 MiB at `0xD2F0000`.

These are **readable virtual-address ranges**, not physical RAM/resident-set usage, not guaranteed heap ownership and not evidence that any typed frame was found. The 7.85 GB readable scope also explains why a blind 4 GiB full-private-memory budget is insufficient for this process.

## Next field-discovery gate

With the complete, hash-verified map available offline, design a V2 **bounded, coverage-accounted region/window selector** for two current-epoch `snapshot-native` captures. Choose explicit private/readable windows from actual map evidence, balance budget against coverage and likely Lua allocations, and record skipped bytes rather than implying an exhaustive search. Follow with strict `inspect-typed-wire` selected-frame advancement and a new same-epoch native pointer readback for XYZ comparison.

**Not achieved in this transfer:** no new memory snapshots, typed `RRAPIVAL2` detection, player XYZ correlation, movement or guest reboot. V12 is the current active host *as of this checkpoint*; rediscover exact identities before further guest interaction.
