# Native XYZ sampler: guest deployment and bounded movement, October 25

**Result: live deployment, 30/30 native samples spanning one supervised movement pulse, and near-time native/Lua endpoint and displacement comparison passed.** The strict reviewer returns `candidate-motion-consistent`. This is exact-build, same-process evidence, not restart/patch qualification or a field-catalog promotion.

All times below are UTC. Evidence lives under ignored `artifacts/update-recovery-20261023-01/xyz-live-oct25-02/` (called `E` below). The user explicitly requested deployment, verification and bounded movement on October 25. No application source, V1 source, native process memory, global setting or installed historical bundle was modified.

## Identity and deployment

- Repository started clean at `a1925c556c35334c8f8dea40aa9b800912b61c26`, branch `codex/modular-foundation`.
- RIFT PID **6940**, start ticks **639284177321390013**, executable SHA **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**. These were freshly checked and remained unchanged across the trial.
- RIFT-Lab-1 VMware PID **38044**, process start ticks **134372941117887852**, VM log epoch **2026-10-24T05:41:51.833Z**, console port **5905**. Every maintenance action rechecked the exact VM identity and acquired the existing exclusive mutex after normal coordinator exit and queue quarantine.
- Installed in a new guest directory: `C:\RIFT_TRANSFER\RR2-XYZ-oct25-02\`. The prior reader installation was preserved.
- `RiftReader2.Live.exe`: **74,349,475 bytes**, SHA **5CA4A6EA9B8904C4987315AA2AE287B3F32B4BB8ED27F5BA951D4D704682C07B**.
- `position-candidate-profile.json`: **395 bytes**, SHA **FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8**.
- Independent, signed-in session-2 `pythonw.exe` one-use delivery processes used the existing pinned payload helper and VMnet8 guest allowlist. Both guest SHA/length gates visibly returned `True`. Originals of transfer events remain in `artifacts/validation/position-sampler-transfer-events-oct25-01/`.
- Initial guest `sample-position --samples 3 --interval-ms 500` completed **3/3**, exit **0**, at **10:37:00–10:37:02**, with steady native XYZ about **(7461.4087, 863.8388, 2976.638)**. Its original `smoke.json` and NDJSON were recovered in `E/recovery-originals/recovery/`.

The recipe is still the exact-build candidate: main-module RVA `0x32E0200`, one dereference, 816 owner bytes, float32 XYZ at `+0x320/+0x324/+0x328`. Owner `0x211D37C0010` applies only to this process epoch; the sampler resolves it anew per sample.

## Independent Lua acquisition and retained failures

The first `scout-copy-typed-native` attempt stopped before scanning because whole-process readable-map enumeration exceeded its existing **32,768-region** request limit. The limit was not increased. Its exact request, error screenshot, and separately successful pointer/sample results are retained in the recovery ZIP's `first-attempt/` directory.

A targeted **16 MiB** `snapshot-native` read over the previously evidenced Lua heap neighborhood returned a **partial** original: **3,344/4,096** successful chunks, with the leading unmapped interval explicit. Its complete segments contained three complete Lua-frame candidates. A subsequent **3,200-byte** snapshot at two saved string addresses completed, but contained **zero** frame prefixes: the strings had relocated. That negative original remains in `E/prestate-originals/`; it was never used as movement evidence.

Successful bytes in the retained recovery original identify one contiguous readable range: **`0xD2F0000`, 13,697,024 bytes**. Two pre-movement and two post-movement explicit snapshots of that range all completed. This avoided global map enumeration, preserved the existing bounds, and captured moving Lua strings without assuming that a previous string address stayed valid. It is a same-epoch scope, not a restart-stable locator.

The unchanged strict C# `inspect-typed-wire` loader verified retained chunk hashes, exact snapshot/process identity, complete producer contracts, sequence/clock advancement and same player `u035400012FA2D207`. Both the pre-state pair and final before/after comparison returned **`advanced-in-covered-scope`**. The final selected sequences are **206626 → 207242**, frame clock **104281.2890625 → 104591.8828125**. No source snapshot was trimmed, rewritten or synthesized to obtain a positive result.

## One pulse and a native feed spanning it

The guest launched a hidden, finite `sample-position --samples 30 --interval-ms 2000` process, PID **5632**, retaining stdout, stderr and the final report in the new installation directory. This read-only process issued no game input and required no console ownership.

- Feed acquisition: **10:49:52.2377186–10:50:55.0698351**, **30/30 complete**, no failed/stale reads, empty stderr. The 2,000 ms interval is a post-read delay; observed starts were about **2.16 seconds** apart.
- A fresh access-queued controller screenshot was visually reviewed: RIFT foreground, open ground, no dialog or text-entry field. The existing controller issued exactly one **100 ms W** action at **10:50:35.156077–10:50:35.3161026**.
- The independent action receipt records key-down at **10:50:35.2095384** and key-up at **10:50:35.31455** (about **105.012 ms** between insertion events), successful delivery/release, no target loss, no uncertain state and no recovery requirement. Windows insertion is not itself proof of game consumption.
- Feed sample **21**, starting **10:50:35.4230877**, was the first changed sample, after the recorded release. Samples 1–20 were stationary; samples 21–30 held the new XYZ. Native displacement magnitude was **0.6473471 game units**. This is temporal corroboration at the feed's cadence, not frame-level synchronization or a measured host/guest clock offset.

The strict offline paired-motion reviewer independently checked both raw 816-byte pointer originals against the advancing Lua comparison:

| Observation | Native XYZ | Lua XYZ | Native read after Lua acquisition |
| --- | --- | --- | --- |
| Before | (7461.40869140625, 863.8388061523438, 2976.637939453125) | (7461.4096679688, 863.83996582031, 2976.6398925781) | 8.318 seconds |
| After | (7460.76220703125, 863.810546875, 2976.6201171875) | (7460.759765625, 863.80999755859, 2976.6198730469) | 8.492 seconds |

All endpoint differences are below **0.0025 units per axis**, inside the unchanged **0.02** gate. Native displacement is **(-0.646484375, -0.0282592773, -0.0178222656)**; Lua displacement is **(-0.6499023438, -0.0299682617, -0.0200195312)**. Their largest per-axis residual is **0.0034179688**, inside the unchanged **0.04** gate. Result: **`candidate-motion-consistent`**, qualification **`candidate-only-no-stimulus-or-clock-skew-proof`**. The reviewer deliberately does not consume the separate action receipt or elevate that qualification.

## Original evidence and replay

Guest ZIPs were first declared through the existing exact-epoch/bundle hash-and-length claim receiver, then independently uploaded through the unchanged SHA-bound one-use receiver. Separate process/exit receipts prove signed-in session 2 and `inJob=false`; originals were recovered only after actual byte length and SHA matched the declarations. Operational plans, AST-only previews, before/after screenshots and per-command hashes are retained in `E`.

| File relative to E | SHA-256 |
| --- | --- |
| `prestate2.zip` (5,629,616 bytes) | `02E0EE520DE66F870DFB8966EF3FA17071D074542D2AE58CF07FFADD1A5E02AB` |
| `poststate.zip` (5,638,943 bytes) | `28D072897F9C6A65297C6E51AB646F26D07BAAC19C3AE4253DB3EFAAC539812C` |
| `recovery.zip` (retained partial/failed attempts) | `95D10FDA83710E60E8430374E96616E036F8A9E3EE198210371C1BF94E429432` |
| `prestate.zip` (zero-prefix narrow snapshot) | `84E5CB9A998F7F5A2D74A08BC93F8FD36280DCA9FE6B817D9482A73517169B25` |
| `prestate2-originals/prestate2/pointer.json` | `D171C5C83F45EF23F0EF74D3661BB49697CF834458D3CACAFC6B53116E290B14` |
| `poststate-originals/poststate/pointer.json` | `B1DB6CF599C003AA377EE0345F06DE77C6F7DE59F5E15BB7C58E3BCD81694350` |
| `motion-typed-comparison.json` | `65890B71C2DF4605B15EBE29DC52CFCACF8C9695CAC0B29C29E70B5BDFEE33FA` |
| `motion-review.json` | `C86C3B6C34881C9547EBCFD49998A26E9103962C037A0AB228329D14439BE483` |
| `motion-action.json` | `317375861895154C7017727182B8312B0DC02360693D7B22880379EC45717778` |
| `poststate-originals/poststate/motion-feed.json` | `879AB673BBA18FD98FA68BAAB9BA33871E78BAF809B7AA0AD5ABA6BDE9163A36` |

`E/live-validation-summary.json` records exact sample/action timestamps, selected source frames, endpoint differences and evidence hashes. Replay the unchanged [typed inspector](../reference/typed-wire-snapshot.md) on the two `snapshot2.json` originals, then the [motion reviewer](../reference/native-motion-pair-review.md) on the pointer originals and SHA-pinned comparison, writing new output paths. All captured input identities and profile hashes must remain pinned.

## Controller recovery and remaining scope

V16 stopped normally before maintenance. An incomplete feed-launch command left the shell open; foreground verification caught this before any movement. V17 was normally stopped, the unfinished input cancelled in the verified shell, and the shorter feed commands were executed and visually checked. The shell's real exit/game foreground was then verified before independent V18 launch. V18 alone owned the reviewed movement grant, then stopped normally for post-state acquisition. No forced termination, competing console owner or bypass of queue authority was used.

After actual post-state upload and verified shell exit, independent **V19 PID 67508**, session **2**, `inJob=false`, restored exclusive supervision. Authenticated status showed **ready/connected**, supervisor running, initial cleanup verified, same game/build/VM epoch, RIFT foreground, guest **disarmed/not busy**, **no sampled held inputs**. Transfer port **8765** was closed. These are dated observations; reacquire current ownership on resume.

Focused delivery **9/9** and motion reviewer **17/17** tests passed, all operational command sets passed Windows PowerShell AST parsing, and actual original-byte replay/summary assertions passed. The final **PowerShell 7.6.8 full gate exited 0 at 2026-10-25T11:00:09Z**: **450 .NET tests** (311 core + 139 Live), **669 Python**, **108 Lua**, **22 real Lua-to-C# cases**, locked restore, zero-warning Release build, published native synthetic smoke, deterministic replay, formatting and **510 documentation links**. Evidence: `artifacts/validation/20261025T105909Z-de2d4c8b` and `E/full-gate-03.log` / `E/full-gate-03-result.json`.

The first full local gate exposed `CreateToolhelp32Snapshot` error **299** while initializing a disposable test process; a focused retry reproduced it. Only the fixture's existing five-second, child-still-alive startup wait was extended from error 18 to errors 18/299; production process opening remains fail-fast. The next gate passed all **450 .NET** tests but exposed a receiver-ISO test selecting Windows PowerShell 5.1, whose separate local script policy is Restricted on this executor. That fixture now prefers the repository's supported PowerShell 7, retaining its PS5.1 fallback. No execution policy was changed. Both corrected suites passed **4/4** focused checks. Initial failure logs are retained in `E/full-gate.log` and `E/full-gate-02.log`; these are test-environment repairs, not deployed reader changes.

The deployed fast reader and a single bounded movement correlation are now live-proven for this exact build/process. The Lua observations are near-time endpoints, not a simultaneous continuous Lua stream; host/guest clock skew and precise input-consumption timing remain unmeasured. No restart, patch, further movement, health/camera discovery or semantic catalog qualification was performed. Next useful separate gate: normal game restart and reacquisition using this deployed sampler, preserving the exact-build rejection rule.
