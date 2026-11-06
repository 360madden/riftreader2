# First live V2 inline typed frames — RIFT-Lab-1, October 24, 2026

**Outcome: SUCCESS for native scan-and-immediate-copy acquisition and independent advancing Lua-source evidence; native XYZ agreement remains untested.** Six 28 KiB original guest memory snapshots were returned and cryptographically verified. The existing strict C# wire inspector found six advancing, same-player comparisons from two time-separated game-process reads. Normal V14 shutdown and independent V15 recovery both succeeded.

## Exact epoch and guarded maintenance

- VM: RIFT-Lab-1, vmware-vmx PID **38044**, start ticks **134372941117887852**, log epoch **2026-10-24T05:41:51.833Z**, port **5905**; guest DESKTOP-8632QPL.
- RIFT: PID **6940**, start ticks **639284177321390013**, executable SHA **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**. Same live game/VM identity before and after.
- Guest native tool: pinned single-file V2 executable **74,254,755 bytes**, SHA **484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716**. Guest PowerShell screenshots independently showed **EXE_GATE=True** and **REQ_GATE=True** for exact-process request SHA **B7CF3747A3DED22FAC9707E5EF6095DCEE9232329AE5F06BC7EFD23D3DAA145F**. Exact 64-bit ticks were preserved.
- Latest read-only V14 preflight at **21:26:09 UTC** found nativeReady=true, RIFT foreground, queue unblocked/unheld/zero pending; ignored SHA proof **0AC6BA958737A854E02D3316F6BC5CECCF6A9411DC44E67D28562BF0DFAC32B7**.
- Normal V14 STOP marker caused its PID **36776** to exit at **21:26:37 UTC**. Native control listeners closed and queue became blocked=1, unheld, cleanup=null. Exclusive, screenshot-gated PowerShell steps opened the guest shell, downloaded/hashed the executable, wrote the original exact request, and executed only two bounded read-only scans. No game controls, memory writes, debugger, injection, V1 edits or queue bypass.
- An important observation: the 74 MB download took **about 167 seconds** to finish, exceeding the stepper's 42-second screenshot wait. Step 3 had issued input but the screenshot still showed a PowerShell download at 23,713,723 bytes. Progress was held until the independent one-use host sender actually logged state=delivered, exactly **74,254,755 bytes**, 0 incomplete responses/denials at **21:30:44 UTC**, then guest SHA was verified. Console-action receipts must not be confused with completed guest commands; the post-live controller hardening described below now makes this distinction explicit.
- Three sequential no-overlap independent Windows session-2 pythonw.exe one-use services handled download, ZIP hash claim and exact-hash ZIP byte upload. Each bound VMnet8 host-only 192.168.56.1:8765, accepted only guest 192.168.56.128 and exited afterward. Guest PowerShell closed normally.
- Pinned V15 was launched outside the Workbridge job as Windows session-2 pythonw.exe **PID 27856** at **21:42:26 UTC**, inJob=false, after exact VM/config/runtime and quarantined queue preflight. Independent authenticated recovery at **21:42:44 UTC** passed: nativeReady=true, new host instance, same guest/game/VM epoch, **foreground=true**, queue blocked=false, holder=null, pending=0, fresh cleanup receipt, generation **1362**. Baseline ignored SHA **95C9D7BBE3F1E33D0F61D38155A392FD4804519DFADA2C9035B9966D04A5FC44**. **V15 now exclusively owns the VM console.**

## Exact original source provenance

- Each read-only scanner inspected exactly **536,870,912 bytes** in a committed private-memory span with **zero reported holes**, limited to 512 MiB / 30 seconds / 128 matches / 8 immediate 28 KiB copies. Both reports correctly say **partial, byte-budget-exceeded**, not whole-process complete.
- Run 01: **21:34:19.589–21:34:20.449 UTC**, 3 prefix matches, 2 complete saved candidate snapshots, index SHA **3B748CCFE4678C0E2EE85BA62DBA05FBD4C9FB04EC0C0807A9ADF41415C2037F**.
- Run 02: **21:36:29.138–21:36:29.800 UTC**, 5 prefix matches, 4 complete saved candidate snapshots, index SHA **D8520C17AE61464FA8F37A66FC2C854B1A8F5047200BE9B44E48084785DCF852**.
- The old binary-followed prefix at **0xD3DB230** recurred and was correctly declined by the immediate brace check. Four other plausible marker locations changed between samples. The marker at **0xD8ACDB0** retained the same *valid but stale* sequence-107851 frame across both.
- Guest-produced ZIP was **90,878 bytes**, SHA **26D5DF797ADDC263B8A8D0DECEB8A856B8708326F1CD36B7700D5A5BC4CD8D58**. Original retained ignored at artifacts/update-recovery-20261023-01/rr2-inline-oct24-01-host.zip. Guest hash claim receipt SHA **105DEEEC8E57E2007C2007FE17C5EB909D704BBE0FCB9F6A24F9050EB12F37C6**, and independently hashed actual upload receipt SHA **7D5B9294C4DE74C52416E7169627EB8EADDD040A6C79F01E6710344C3B5DFF1E**.
- The strict offline ZIP verifier accepted both receipts, fixed guest, exact game PID/ticks/SHA, source bundle, two original input requests, every SHA-linked file, all saved Base64 chunk lengths/checksums and capture separation. Published **six complete original snapshots / 272,936 recovered JSON bytes**, with no overwrite. Original archive proof SHA **C98EE8C8619F315A2F90EDBDCBB1BAA3BCA4ED6A209977993493287443E5568**, retained in ignored rr2-inline-oct24-01-recovered/archive-proof.json.

## Independent strict typed-wire comparisons

Release net10.0 inspect-typed-wire ran on every 2 × 4 cross-run candidate pair and published eight independent no-overwrite reports. Each verifies frame syntax, full contiguous snapshot bytes, exact game identity, source unit, producer sequence and clock.

| Pair | Run-01 marker / sequence | Run-02 marker / sequence | Strict result |
| --- | --- | --- | --- |
| a1-b1 | 0xD897B40 / 112332 | 0xD3E3AD0 / 112586 | **advanced-in-covered-scope** |
| a1-b2 | 0xD897B40 / 112332 | 0xD571C00 / 112588 | **advanced-in-covered-scope** |
| a1-b3 | 0xD897B40 / 112332 | 0xD8242D0 / 112587 | **advanced-in-covered-scope** |
| a1-b4 | 0xD897B40 / 112332 | 0xD8ACDB0 / 107851 | blocked: no sequence/clock advancement |
| a2-b1 | 0xD8ACDB0 / 107851 | 0xD3E3AD0 / 112586 | **advanced-in-covered-scope** |
| a2-b2 | 0xD8ACDB0 / 107851 | 0xD571C00 / 112588 | **advanced-in-covered-scope** |
| a2-b3 | 0xD8ACDB0 / 107851 | 0xD8242D0 / 112587 | **advanced-in-covered-scope** |
| a2-b4 | 0xD8ACDB0 / 107851 | 0xD8ACDB0 / 107851 | blocked: identical stale frame |

Best fresh-to-fresh pair **a1-b2**: same playerUnitId **u035400012FA2D207**, two distinct full producer wire hashes, sequence **112332→112588** (+256), producer clock **56728.36328125→56858.1171875** (+129.75390625). Independent strict report SHA **CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5**, file pair-a1-b2-typed-comparison.json. Position in all six valid frames was **X=7461.1997070312, Y=863.84997558594, Z=2977.0598144531**. This is consistent with a stationary player despite advancing frames. No native XYZ field was measured in this trial.

The two blocked comparisons are essential retained negative controls. Successful inspector process exit means diagnostic publication; only the six **advanced-in-covered-scope** statuses establish source temporal advancement. Neither this proof nor unchanged Lua XYZ establishes native-memory field agreement, movement correctness or patch resilience.

## Next actions and operational caveats

1. **Committed:** the source evidence summary and status links; all exact originals and receipts are retained in ignored artifacts, re-verifiable without the game.
2. **Post-live implemented and validated:** each step receipt now says consoleActionCompleted=true and guestCommandCompletionVerified=false, so a screenshot timeout cannot be reported as completed guest execution. Step 4+ fails closed until same-VM independent download owner/exit receipts and the actual complete 74,254,755-byte delivered event with pinned route/SHA/source/destination agree. Step 30+ requires ZIP claim service exit and exact claim validity. The genuine historical delivery passed the new host-only guard. Focused 25/25, full Python 598/598, compilation passed. This real capture predated code hardening; no claim that the improved gates were used during that capture.
3. **Unlock the next native field gate:** use existing V2 read-only native pointer/map/snapshot tools to independently measure current exact-epoch game XYZ and compare against qualified Lua **(7461.20, 863.85, 2977.06)**. Validate any historical pointer root/RVA fresh; no absolute address is patch-proof. If guest-console intervention is needed, prepare and independently verify a new normal **V15→V16** handover and restore supervisor afterward.
4. Only after native position agreement consider controlled player movement/wall detection or navigation engine reuse. Current success is a strong *advancing Lua-source* milestone, not an automated navigation success.

**Final state:** all temporary transport listeners closed, guest PowerShell exited, game foreground, V15 independently healthy/disarmed, six exact-original snapshots and eight strict comparison reports verified offline.
