# First live current-epoch native XYZ and V16 recovery — October 24, 2026

**Result: LIVE SUCCESS for bounded native-pointer acquisition, guest-origin original-byte transfer, independent offline position comparison, and normal V16 recovery.** The outcome is `candidate-compatible`, **not** a synchronized or motion-qualified game field. All timestamps below are UTC unless stated otherwise. The experiment crossed 00:00 UTC on October 25 while remaining October 24 in New Jersey.

## Scope, ownership, and real execution

- The verified live RIFT instance was PID **6940**, process start ticks **639284177321390013**, executable SHA-256 **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**. VMware remained PID **38044**, start ticks **134372941117887852**, log epoch **2026-10-24T05:41:51.833Z**, port **5905**.
- Preflight found V15 PID **27856** authenticated, ready, disarmed, no held keys, RIFT foreground, canonical queue unblocked and unheld with a cleanup receipt, and **no listener on 192.168.56.1:8765**. A new benign WMI-launched `pythonw.exe` proof, PID **22716**, independently verified signed-in Windows session **2**, `inJob=false`, no VM/network access.
- The one-use `STOP-NATIVE-20261024-V15.request` was created at **23:57:46**. V15 wrote its normal exit receipt at **23:57:47**, and the old PID was unavailable. The canonical queue then verified `(blocked=1, holder=None, cleanup=None)` before the VM console was opened. V15 was never overlapped with the guest maintenance session.
- The guarded guest trial issued **bootstrap + all 33 exact SHA-linked PowerShell actions** under the exclusive VM mutex. A screenshot visibly confirmed `EXE_GATE=True`, the live guest executable bundle SHA **70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E**, `RUN_A_EXIT=0`, `PTR_A_GATE=True`, `RUN_B_EXIT=0`, and `PTR_B_GATE=True`. Action receipts intentionally prove console delivery/screenshot, not command success; these on-screen results plus the original reports supply independent completion evidence. No movement keys or process writes were used.

## Two original native pointer reports

The unchanged request is `native-pointer-follow-request/1`, SHA **C6B90D59DCF472E50DCEEAE6992AED98446754D466AE2AFA1AE9510EFD5BE9EE**: one main-module root RVA **0x32E0200**, one offset **0x0**, exactly **816 terminal bytes**, and **5,000 ms** maximum read duration. Both actual reports completed successfully and resolved:

- Main module base **0x7FF6EBDA0000**; root slot **0x7FF6EF080200**; terminal owner **0x211D37C0010**.
- Candidate `float32` XYZ at terminal owner **+0x320/+0x324/+0x328**.
- **A** completed **2026-10-25T00:00:31.528099Z**; original report SHA **6433E809E5177E6371DBBFBD906BCD6E4499E80F0FCFEF09317600E4721DFAD5**, **3,122 bytes**.
- **B** completed **2026-10-25T00:02:24.644708Z**; original report SHA **1E7BAB245C147062B0CA48C4BD81271ADA82C10FE8140506C26A0380245C940F**, **3,122 bytes**. Exact separation **113.116609 seconds**. Both native results are **(7461.19921875, 863.8524169921875, 2977.061767578125)**.

## Guest-produced ZIP and independent byte proof

The guest PowerShell packaged precisely `rr2-v16ptr-a.json` (**321 bytes**, original request SHA above), `rr2-v16ptr-a-report.json` and `rr2-v16ptr-b-report.json`. Guest ZIP: **3,135 bytes**, SHA-256 **1BD407E20FC7ACFD2691D30BFFCA2E534870491FE40D9F933275B6CE9257B3E3**.

- A one-use independent session-2 `pythonw.exe` **claim** process, PID **57972**, bound `192.168.56.1:8765` only for step 31. Exact guest peer `192.168.56.128`, request/game/bundle/ZIP hash and byte count were verified; process exited and port closed. Claim receipt SHA **C6E294A47B4B7643B59CDFECB739356C0900BA1BF57E8E2AF04D8FD19AB8734A**.
- A separate one-use session-2 `pythonw.exe` **upload** process, PID **27848**, owned that same bound port only for step 33, after the claim server exited. The full actual uploaded ZIP exactly matched the prior declaration and process/bundle/peer identities; it exited and the port closed. Upload receipt SHA **A4BF40C566A6879056E5E732053F9B8D3F12FFFCB6854AD4337A828B8657F5CA**.
- Original guest ZIP and receipts remain untracked beneath `artifacts/update-recovery-20261023-01/`; the strict, no-overwrite verifier recovered all three originals to `rr2-v16-native-pointer-reviewed-live-oct24-01/`. Proof `archive-proof.json` SHA **CFE2C1BD2961EDB7630A765408DC0FFF8A1E7324D371B674086DBA2C0C02EFC7** (see actual file hash; spacing here is not part of the digest). Its `transferEvidence.state` is `claim-upload-and-extracted-bytes-agree`, **not a host-only fixture**.

## Independent same-player native/Lua comparison

The prior original strict C# typed-wire advancing pair was `pair-a1-b2-typed-comparison.json`, SHA **CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5**, player unit **u035400012FA2D207**, producer sequences **112332→112588**. Its Lua XYZ was **(7461.1997070312, 863.84997558594, 2977.0598144531)**.

| Axis | Original advancing Lua source | Each native read | Native minus Lua |
| --- | ---: | ---: | ---: |
| X | 7461.1997070312 | 7461.19921875 | -0.0004882812 |
| Y | 863.84997558594 | 863.8524169921875 | +0.0024414062 |
| Z | 2977.0598144531 | 2977.061767578125 | +0.001953125 |

Both independent native reads fall within the configured **0.02-unit** tolerance on all axes. The derived `position-review.json` SHA is **1973D0C6A9CDCAE2D2B4B4826BB26C70BA36081EE090F0F7AC792BF96A6AAD53**. Exact reviewer status: **`candidate-compatible`**; qualification **`candidate-only-not-synchronized`**.

**Limitation:** this advancing Lua source preceded native A by **8,642.292 seconds** and native B by **8,755.409 seconds**. The character appeared stationary; numeric agreement across that interval is promising but does **not** establish simultaneous values, axis response to motion, pointer chain validity after a future RIFT patch, or final game-field semantics. Retain all originals. Do not call the position field fully qualified yet.

## Safely restored operational owner

The guest shell was closed under its success-only receipt after exact ZIP proof; the closing screenshot showed RIFT in the foreground again. Pinned V16 successor was launched independently, **PID 28496**, exact process ticks **134373603929515259**, signed-in Windows session **2**, `inJob=false`. At **2026-10-25T00:06:43Z**, fresh authenticated host status verified connection and supervisor **ready/running**, `initialCleanupVerified=true`, exclusive VM reservation held, guest disarmed/no keys, RIFT foreground, same RIFT PID/build and VMware epoch. Canonical queue: `(blocked=0, holder=None, cleanup=nav-cleanup:e43ed0c97ce2a568450a1e7a4640268655236fd17d93b48a5ef0320fde5e7484)`; port 8765 remained unbound. **V16 now owns the console. Do not connect another VM controller while it is alive.**

## Independent replay and regression hardening

- The strict offline archive verifier first returned `candidate-compatible` on the actual uploaded ZIP and three extracted originals. Its direct standalone `python scripts/verify_pointer_zip_archive.py --help` command exposed a missing repository import path; this was corrected without changing archive validation semantics. A second **standalone** run of the **same exact 3,135-byte guest ZIP** into a new, no-overwrite ignored destination produced **byte-identical copies of all five reviewer outputs**, including `position-review.json` and `archive-proof.json`. The original archive/review output directories were not modified.
- The authentic claim/transfer receipts exposed a stale test assumption that no real one-use service had run. Test fixtures were isolated from the repository's live receipt directory; the service correctly fails closed against mismatched evidence. Full-suite discovery also exercised Windows HTTP refusal-path behavior and was hardened to avoid a rejected POST leaving an unread request body in the test server; production receiver behavior was unchanged.
- The PowerShell 7.6.8 Store-package executable successfully ran the repository's real locked-build/test/publish/Lua/format/document-link validation. The older validation script used an explicit Python test-module list, which excluded newer V16 safety modules; the improved gate discovers **all** `test_*.py` tests. Actual **full gate passed exit 0** at **2026-10-25T00:24:06Z**: **643 Python**, **432 .NET 10** (139 Live + 293 other), **108 Lua lifecycle/encoder** checks, **22 Lua→C# contract** cases, published native smoke, deterministic replay, format, and **468 relative documentation links**; retained evidence folder `artifacts/validation/20261025T002307Z-755c5bd7`. The first broadened attempt uncovered a real PS7-parent→PS5.1 test-child module path problem; that test now explicitly restores PS5.1's inbox module path and passed both its focused 4 tests and the final broad gate. No production receiver or ISO builder was modified.

## Next experiment

1. Keep this native candidate at **candidate-compatible**. Source acquisition is not synchronized; do not promote to qualified based solely on the numeric match.
2. Build a guarded **V16→V17** successor only when the next offline-validated experiment is ready. Reuse same-epoch normal STOP/queue quarantine/exclusive console handoff, independent signed-in session-2 launch, screenshot capture, and SHA-pinned one-use original transfers.
3. Capture a **fresh advancing typed Lua producer observation temporally near native before/after samples**, then use an already-authorized **small supervised movement pulse** to test whether both Lua and native XYZ change consistently. Apply explicit stop/release evidence and keep gameplay automation outside RiftReader2.
4. Preserve report JSONs and screenshots in ignored artifacts; record small, exact findings in tracked docs and commit verified milestones.
