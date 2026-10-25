# Current status

Updated: 2026-10-25 (America/New_York; Windows host clock).

## October 25: Known-build XYZ direct sampler and NDJSON feed — CODE VERIFIED; NO NEW GUEST SAMPLE

- **Reuse-first operational path:** The new Windows Live `sample-position` command consumes a small strict `native-position-profile/1` JSON recipe pinned to the October 24 RIFT executable SHA **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**, root RVA **0x32E0200**, and owner float32 offsets **+0x320/+0x324/+0x328**. It discovers exactly one fresh `rift_x64` PID, opens a read-only exact-build session, re-resolves the chain per sample without heap/Lua rescanning, and refuses stale/wrong-build identity. Bounds: 1–30 reads, 0–2000 ms post-read interval, at most 60 seconds scheduled delays.
- **Honest, immediate consumption:** Each sample emits one compact JSON line as soon as it completes, including explicit unavailable/nonfinite states; the final line summarizes the run. A separate no-overwrite `native-position-samples/1` report retains native owner session address, terminal-byte SHA, actual timestamps, XYZ when finite, and failure status. The report remains **candidate-only-not-motion-or-update-qualified**; the direct reader neither promotes catalog truth nor proves game behavior or future patch applicability. [Usage and limits](reference/known-position-sampling.md).
- **Real host verification:** Seven new focused .NET 10 tests pass (known build, changing XYZ, profile hashing/schema, wrong build, identity invalidation, failed reads, nonfinite values, live sample callback), and the Windows Live `--help` smoke lists the command. Final PowerShell **7.6.8** full gate exited **0 at 2026-10-25T08:36:37Z**: **448 .NET tests** (309 core + 139 Live), **660 Python**, 108 Lua, 22 Lua→C# contracts, published-native synthetic-host smoke, format, and **496 documentation links**; evidence `artifacts/validation/20261025T083534Z-0d3b488a`.
- **Explicit live boundary:** The new sampler has **not** been installed or run against the RIFT-Lab guest yet. The last verified VM authority was V16 exclusive coordinator; check fresh console ownership/process/build before any guest maintenance. Next: guarded exact-epoch publish/guest smoke, then near-time motion evidence via the existing [V17 offline reviewer](reference/native-motion-pair-review.md). Automatic cross-patch locator rediscovery remains separate.

## October 24: Evidence-preserving discovery compilation and offline explorer — NO VM INPUT

- **Finalized plan and implementation:** D0 [bounded compilation roadmap](planning/discovery-compilation-roadmap.md) commit `d62cbc3`, D1/D2 compiler/filter/sort/JSON+CSV+JSONL commit `0f31cf6`. Strict explicit SHA/byte-pinned source manifest, honest per-row qualifications, stable filters/sorts, deterministic results, and never-overwrite output. The self-contained `scripts/discovery_explorer.html` previews a user-chosen JSON compilation in a browser with search, header sorting, categorical filters, evidence inspection, pagination, and local filtered downloads. See [usage contract](reference/discovery-compilation.md) and [ADR 0007](decisions/0007-discovery-compilation-views.md).
- **Actual historical RIFT input replay, read-only:** One V15/V16 advancing-typed-source original and one native pointer review original were pinned in an ignored local manifest, compiled to two distinct rows with separate source hashes and epochs. Typed row remains `advanced-in-covered-scope` / source-only; native row remains `candidate-compatible` / **not synchronized or motion-qualified**. This run did not contact VMware, start a host listener, read the game process, or alter V16 console ownership. [Evidence and limitations](validation/discovery-compilation-2026-10-24.md).

- **Actual local Chrome UI proof and final gate:** Independent headless Chrome loaded **6 synthetic** and **2 previously retained real RIFT** rows via the local file picker; status/SHA filter, precise UTC sort, CSV and JSON filtered downloads passed (jobs `rr2-disc-d4-browser-real-01`, `rr2-disc-d4-browser-live-evidence-01`). The full PowerShell 7.6.8 `scripts/validate.ps1` gate then finished **exit 0 at 2026-10-25T01:51:18Z**, **441 .NET**, **660 Python**, 108 Lua, 22 Lua→C# contracts, published-native smoke, formatting, 490 links. Evidence `artifacts/validation/20261025T015017Z-106b7fd1`. [Full proof](validation/discovery-compilation-2026-10-24.md); human visual/accessibility review remains separate.

## October 24: V17 host-only motion comparator and safe successor STAGED — NO VM INPUT

- **Fresh V16 read-only proof:** At **2026-10-25T00:25:38Z**, the authenticated owner remained ready/connected, RIFT foreground PID **6940**/exact build, VMware PID **38044**/same epoch, no held keys, guest disarmed, supervisor running and console exclusively reserved. The no-overwrite **V16→V17 same-epoch handover** prepared plan and launcher at **00:26:31Z** using the existing clean queue; **no V16 STOP marker, VM console access, game input or V17 launch** was performed.
- **New moving-XYZ offline reviewer:** `scripts/review_native_motion_pair.py` consumes strict advancing typed Lua before/after plus two exact-epoch original native pointer reports. It checks SHA pins, root/owner bytes, player identity, independent snapshots, nonoverlapping chronology, **unrounded at-most-180-second pair lag**, 0.02-unit endpoint tolerance and 0.1-unit minimum source displacement. Status is `candidate-motion-consistent`, `candidate-motion-disagrees`, or `insufficient-source-motion`, always **candidate-only** without stimulus/clock-skew proof. **17/17 focused safety tests** pass, including a real V16 original negative control and direct CLI. The full PowerShell 7.6.8 gate then passed exit **0 at 2026-10-25T00:34:39Z**: **660 Python**, **432 .NET**, 108 Lua, 22 Lua→C# cases, native publish/replay/format, **471 links**; evidence `artifacts/validation/20261025T003336Z-def5acac`. No new actual movement claim. [V17 evidence contract and safe multi-owner sequence](reference/native-motion-pair-review.md).

## October 24: FIRST LIVE current-epoch native XYZ — TWO ORIGINALS MATCH, V16 RECOVERED

- **Actual game-memory result:** Normal V15 STOP and quarantined queue preceded 33 bounded exact-PID read-only guest PowerShell commands. Two independently saved pointer reports (113.116609 seconds apart) resolved main-module RVA **0x32E0200**, owner **0x211D37C0010**, and owner offsets **+0x320/+0x324/+0x328** to identical native XYZ **(7461.19921875, 863.8524169921875, 2977.061767578125)**. Guest screenshots showed **EXE_GATE=True**, both native command exit codes **0**, and **PTR_A_GATE=True/PTR_B_GATE=True**. No movement or process writes.
- **Real original-byte proof and independent reviewer:** Separate signed-in session-2, out-of-job one-use claim/upload services cryptographically bound guest **192.168.56.128**, same game/build/bundle epoch, declared SHA and actual transferred **3,135-byte** ZIP (SHA **1BD407E20FC7ACFD2691D30BFFCA2E534870491FE40D9F933275B6CE9257B3E3**). Exact three original members recovered, source-linked native/Lua reviewer returned **candidate-compatible**, each axis delta under **0.0025** versus qualified advancing Lua. **Qualification stays candidate-only-not-synchronized** because the source frame was about 2.4 hours older and no controlled movement was performed. [Full original hashes, times, values, scope and limitations](validation/native-pointer-xyz-first-live-2026-10-24.md).
- **Safe restored owner:** Verified guest-shell close restored RIFT foreground, both one-use services and port 8765 are closed, and independent **V16 PID 28496** (Windows session 2, not in a job) is authenticated ready/connected with supervisor running and exclusive VM console ownership. Exact RIFT PID **6940** / VMware PID **38044** remain unchanged; guest disarmed, no held keys, canonical queue unblocked/unheld with fresh cleanup receipt. V16 is now the live owner. **Do not access its console concurrently.** Next gate: prepare a new guarded handoff for near-time advancing Lua + supervised bounded movement/native before-after comparison.
- **Validated and repeatable:** Strict reviewer was replayed on the actual guest ZIP through its direct CLI; all five output files were byte-identical in separate no-overwrite directories. Windows Python/PowerShell subprocess and authentic-receipt test isolation problems were corrected in test harnesses. The authoritative PowerShell 7.6.8 `scripts/validate.ps1` now discovers all Python tests: **643/643 Python**, **432/432 .NET 10**, 108 Lua lifecycle/encoder, 22 Lua→C# contracts, published-native smoke, deterministic replay, format, **468 links**. Exit 0 at **2026-10-25T00:24:06Z**, evidence `artifacts/validation/20261025T002307Z-755c5bd7`.

## October 24: V16 guarded native XYZ guest trial, dual one-use services and abort path — HISTORICAL HOST PREPARATION

- **Guest operation prepared:** New `scripts/run_guest_pointer_trial.py` assembles 33 exact-epoch, serial read-only PowerShell actions (+bootstrap, success-close or abort). Each transport command is regenerated and matched to its canonical pinned source; the previous action receipt must match the exact command SHA, stage, VM identity and request SHA, with no false guest-completion claim. The actual 33 commands passed Windows PowerShell 5.1 AST syntax parsing, **33/33, no commands executed**. The installed guest executable, 816-byte pointer request and both complete native resolutions are independently gated before ZIP packaging.
- **Independent service ownership:** `scripts/run_guest_pointer_service.py` reuses separate, fixed-IP one-use SHA/size claim and content-matched ZIP upload services on port 8765. The guest POST gates require the actual Windows listener PID and process start identity, not just a startup receipt; claim/upload phases cannot overlap. An incorrect claim-server source SHA pin was detected by the first offline preview and corrected before any listener. New `--abort` requires no live service/port, a verified PowerShell screenshot and canonical guest authority; it records failure without pretending a ZIP was received. **14/14 focused safety tests and 642/642 full Python tests passed**, plus Python compilation, Git diff check and the 33-command PowerShell AST gate.
- **Fresh read-only live preflight at 22:41:02 UTC:** V15 exclusively owns console and remains authenticated ready/connected; guest RIFT PID **6940**, exact start ticks/build, VMware PID **38044**/log epoch unchanged, game foreground, guest disarmed/no keys held. **No V15 STOP, VNC/guest interaction, native pointer reports or V16 startup yet.** [Exact physical sequence, abort/recovery and evidence gates](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: V16 native XYZ pointer ZIP transfer host-proven — NO GUEST ACTION

- **Pointer originals transfer pathway now host-proven:** Extended the existing guest ZIP SHA claim and one-use content-pinned receiver with a distinct native-pointer route, preserving old inline/map defaults. New scripts/verify_pointer_zip_archive.py requires the exact three-file ZIP, verifies both process/guest/bundle/receipt identities and actual archive-member bytes, runs the strict native-vs-Lua reviewer and publishes no-overwrite originals/derivation. **52/52 focused archive/transport tests passed (including legacy compatibility)**. No new listener/guest access yet. [V16 complete staged gateway](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: V16 native XYZ pointer gate staged — HOST PREPARATION ONLY

- **Current read-only owner/status:** V15 PID 27856 remains authenticated ready, guest disarmed/no keys held, RIFT foreground PID 6940/ticks 639284177321390013, VMware epoch unchanged (read-only host status 22:00:47 UTC). Canonical same-epoch V15→V16 successor plan/launcher was prepared safely (22:01:28 UTC), but **V15 STOP not requested and V16 NOT launched**.
- **Two precise native pointer requests staged:** Existing guest PowerShell planner generated two separate 10-step no-overwrite plans with the same SHA-pinned exact-game request C6B90D59DCF472E50DCEEAE6992AED98446754D466AE2AFA1AE9510EFD5BE9EE. Each follows root RVA 0x32E0200 once, reads 816 bytes to include offsets +0x320/+0x324/+0x328, and caps execution at 5 seconds. They have NOT run in the guest.
- **Native comparison reviewer implemented:** New scripts/review_current_pointer_xyz.py verifies both complete pointer reports, exact root/byte-level pointer hops, process/build/epoch, qualified stationary advancing Lua source and SHA, temporal separation and XYZ float32 differences. Synthetic focused 10 tests passed; it also accepted the actual source comparison SHA CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5. **Still missing: two real pointer originals, guest SHA-pinned transfer and actual native/Lua agreement.** [Full V16 native XYZ preparation and safe next sequence](validation/current-epoch-pointer-v16-preflight-2026-10-24.md).

## October 24: post-live guest transfer completion hardening — HOST ONLY

- The successful real 74,254,755-byte guest download took approximately 167 seconds, beyond the earlier fixed screenshot delay. The guarded guest stepper now expressly marks every step receipt as a completed console action, not verified guest-command completion. After the download command, step 4 and later require distinct one-use independent service owner/exit receipts and the genuine exact-peer, exact-route, full-byte, correct-SHA delivered sender event. Step 30 and later require the completed guest ZIP claim before upload.
- The new guard passed against the retained actual delivered sender event (read-only, V15 untouched), plus 25/25 focused fail-closed tests covering missing/partial transfers, mismatched PID, VM epoch, SHA and guest IP. The full Python suite passed 598/598, compileall passed. A service test was isolated from now-existing real claim artifacts so it remains repeatable. This was applied after the real capture; it does not retroactively prove guest-command completion in the old receipts. V15 still exclusively owns the VM; no fresh guest input was generated.

## October 24: FIRST LIVE same-scan RIFT captures — advancing Lua producer frames QUALIFIED

- **Live game capture and provenance:** Two exact-PID/build read-only 512 MiB scan-and-immediate-copy runs executed with the SHA-pinned new V2 guest CLI after a normal V14 STOP/exclusive maintenance. Run 01 found **3 prefixes/2 complete copied snapshots**; Run 02 **5 prefixes/4 complete copied snapshots**. Both correctly partial by byte cap, zero holes. Guest returned a **90,878-byte** ZIP, SHA **26D5DF797ADDC263B8A8D0DECEB8A856B8708326F1CD36B7700D5A5BC4CD8D58**; separate exact guest hash/length claim and actual content-addressed upload matched. The strict offline verifier accepted both receipts and preserved **6 original snapshots/272,936 JSON bytes**, proof SHA **C98EE8C8619F315A2F90EDBDCBB1BAA3BCA4ED6A209977993493287443E5568**.
- **Breakthrough C# strict wire result:** Independent **2 × 4 = 8** cross-run comparisons found **6 statuses advanced-in-covered-scope**, two appropriately blocked stale pairs. Freshest same-player unit **u035400012FA2D207** advanced producer sequence **112332→112588** and frame clock **56728.363→56858.117** while Lua XYZ remained **(7461.20, 863.85, 2977.06)**. Native XYZ comparison and movement **not yet qualified**. A stale valid frame at 0xD8ACDB0 was negative control; old binary-followed 0xD3DB230 prefix correctly declined. Source evidence scoped to 512 MiB per run, not whole-process.
- **Restored operational owner:** V14 exited normally, one-use transport listeners shut down, guest PowerShell exited. SHA-pinned **V15 PID 27856**, independent Windows session 2, inJob=false, authenticated ready/disarmed at **21:42:44 UTC**, RIFT foreground, exact unchanged game+VM epoch, clean queue. **V15 now owns the VM; no concurrent console access.** [Complete first live original hashes, advancing pair matrix and guarded V15 recovery](validation/typed-inline-first-live-six-snapshots-2026-10-24.md). Next engineering gate: independently validate live native XYZ for this source-qualified Lua position; guard future console transitions with the new receipt boundary.

## October 24: guarded V14 → V15 typed-inline guest trial prepared, foreground restored — HOST ONLY

- **Fresh owner check:** V14 authenticated and ready, game PID **6940** / exact 64-bit start/build unchanged, VM epoch unchanged, queue unheld/unblocked/0 pending. Joey corrected a VMware dialog stealing focus; a renewed read-only observation at **21:08:34 UTC** confirmed **RIFT foreground=true**. V14 still owns exclusive console, with **no STOP, bundle transfer or new guest memory scan**.
- **Ready for serial maintenance:** New `scripts/run_guest_inline_trial.py` creates 31 bounded, individually receipted guest PowerShell commands guarded by V14 normal exit, blocked/unheld queue, exact V15 VM epoch, screenshot-gated shell and request/bundle SHA. New `scripts/run_guest_inline_service.py` restricts independent one-use download → ZIP hash claim → exact-hash upload to signed-in Windows `pythonw.exe`, exact guest IP and mutually exclusive phase receipts. **20/20** focused host tests passed; real PowerShell ZIP format rechecked byte-identically. Fixed a would-be **64-bit start-tick precision loss** in initial request construction *before use*. [Strict operational handoff](validation/typed-inline-v15-guarded-sequence-host-2026-10-24.md).

## October 24: closed guest ZIP checksum/receipt gap — HOST LOOPBACK VERIFIED

- **One-use receiver reuse:** New bounded guest ZIP declaration receives only fixed-IP, exact-epoch **SHA + byte count**; existing one-use exact-digest ZIP upload receiver is unchanged. The archive verifier now binds *both* original receipts to actual ZIP SHA/length, path, guest peer, game process and bundle before publishing; it refuses mismatches and marks host fixtures separately. No new VM listener opened.
- **Proven host path:** Actual loopback claim → original ZIP upload → exact-receipt crosscheck → eight recovered originals passes. New claim tests 9, added receipt-crosscheck tests 2, combined 24 focused pass; full Python **573/573** pass. Normal no-listener Windows preflight pinned latest-known game/build and reported guestZipReceived=false. [Strict claim and transport proof](validation/typed-inline-zip-claim-host-2026-10-24.md).

## October 24: TWO native self-process captures archived and recovered — full host path proved

- **Actual host execution:** The published single-file V2 capture ran **twice** against a controlled live Windows test-process allocation, each copying seven 4 KiB pages byte-for-byte. A real PowerShell ZIP archived both distinct reports. New bounded host verifier rechecked exact archive/game/bundle/provenance/chunk hashes and restored **8 originals / 92,272 bytes** with a no-overwrite receipt. ZIP **7,575 bytes**, SHA **A5CE12ECD37AADD90CBB6D210C9A719A5B5B263ACD672B5BB9890159CFD71A7A**.
- **Strict independent diagnostic:** C# inspect-typed-wire opened both recovered complete snapshots and correctly returned **blocked: incomplete-typed-fragment-in-covered-scope** for the deliberate test-only prefix. Focused archive tests **13/13**, full Python **562/562**, diff check pass. **This is a test-process proof, not in-game Lua/XYZ.** No VM interaction, V14 STOP or guest file upload. [Two-run archived evidence and live gate](validation/typed-inline-archive-two-run-host-2026-10-24.md).

## October 24: new published typed-capture bundle now allowed by guarded one-use transport — HOST ONLY

- **Reuse-first delivery improvement:** `scripts/serve_guest_native_scout.py` now supports explicit `--bundle typed-inline`, with a distinct exact URL and the SHA-pinned 74,254,755-byte single-file executable, while the existing `scout` default, one-use, exact-peer, expiry and no arbitrary-file serving remain. Both original and new ~74 MB sources passed **real full-file SHA preflights without opening a socket**.
- **Gates:** 14/14 focused new/legacy transfer tests, 26/26 combined sender/receiver tests and **549/549 full Python tests** passed. A preexisting Windows socket-abort flake in header-refusal receiver tests was fixed **in test harness only**, retaining exact refusal-code checks; production receiver unchanged. No guest transfer, V14 STOP or guest capture. [Transport proof and next gate](validation/typed-inline-bundle-transfer-host-2026-10-24.md).

## October 24: V14 live preflight; V15 PREPARED ONLY, foreground not confirmed

- **Read-only host observation at 19:30:35 UTC:** RIFT-Lab-1's V14 supervisor was ready/connected, disarmed and held the exclusive console; exact RIFT PID 6940/start ticks 639284177321390013/SHA and VMware PID 38044/log epoch unchanged. Canonical queue generation 1248, 0 pending, unblocked. **Guest `foreground=false`**, so a future UI operation must not assume focus. **No gameplay input.**
- **19:31:32 UTC:** normal same-epoch **V15 successor plan generated but not executed**. V14 remains owner; STOP not requested; no VM maintenance, bundle transfer or guest capture. [Observed evidence and guarded next steps](validation/typed-inline-capture-v15-preflight-2026-10-24.md).

## October 24: same-scan typed CLI HOST VALIDATED; tested guest bundle ready, not deployed

- **V2 implementation:** New `scout-copy-typed-native --request PATH --output NEW_DIRECTORY` uses an exact PID/start/executable-SHA-bound, **512 MiB/30 s/128-prefix** maximum private-memory scout and **at most eight** in-callback `RRAPIVAL2|{`-plausible **7 × 4 KiB** snapshots. Outputs are source-request/SHA-linked strict `native-memory-snapshot/1` originals with per-candidate status in `native-typed-inline-capture/1` `index.json`, published under a new folder by no-overwrite final directory rename. Post-capture process identity drift invalidates the manifest and suppresses usable snapshot files. The old prefix scout, V1 and gameplay controls are unchanged. [New command contract](reference/typed-inline-capture.md).
- **Real host validation:** The command actually scanned/copied the **Windows test process**, saved two-level content hashes, passed strict snapshot loader, and refused output overwrite/stale target. The **published single-file executable itself** also scanned/copied **28,672 test-process bytes** byte-for-byte and passed a separate published native `MZ` read/replay/stale-epoch smoke. Bundle: ignored `artifacts/validation/rr2-scout-copy-publish-oct24-01/RiftReader2.Live.exe`, **74,254,755 bytes**, SHA-256 **`484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716`**. Published trial manifest SHA **`E70078F55DE1780216E8C4AC7E7E0C4FB1E59724C5ABE1556E4AF5270D850DDF`**.
- **Gates:** full .NET **432/432** (139 Live + 293 core), Python **545/545**, Lua 5.1 **108** and actual Lua→C# **22** cases, targeted format, bundle publish and native self-process smokes passed. Stock all-in-one PowerShell validation **not completed** because PowerShell 7 is unavailable and PS5.1 changes native quoting/BOM; component checks were rerun independently. [Full real host proof and restrictions](validation/typed-inline-capture-cli-host-2026-10-24.md).
- **Live next step, NOT YET PERFORMED:** fresh exact V14/game/VM preflight and safe V14→V15 normal handover, SHA-pinned bundle transfer to guest, two distinct bounded read-only scan-copy acquisitions and original report transfers, strict wire advancement check, independently restored supervisor. Do not enter the V14-owned VM console concurrently. **Current fresh valid typed Lua frames, native XYZ agreement and game-patch resilience remain unproven.**

## October 24: complete pure scout→copy pass; 430/430 .NET tests

- **Integrated host-only discovery primitive:** Added `TypedApiInlineCapturePass.Run` to compose the 64 KiB prefix scanner, immediate plausibility recheck and SHA-bound seven-page copier **in the same callback before the next scan read**. A hard **8-candidate copy cap** and the original scan byte/time/match budgets prevent runaway work. It retains candidate-level false-prefix, moved-header, out-of-range, copy-limited and partial-time statuses, without promoting prefixes or incomplete scan coverage to typed frames. **No public guest CLI or report publication yet**, no game/VM access.
- **Actual verification:** Six new pure orchestration cases, plus the earlier real Windows self-process scanner→copy byte-exact smoke. **Full .NET 430/430 tests passed** (137 Live + 293 core); `dotnet format --verify-no-changes` for the changed source/tests passed. The next engineering gate is a strict exact-target CLI with no-overwrite, hash-linked `native-memory-snapshot/1` files and fail-closed process revalidation. [Pass evidence](validation/typed-inline-capture-pass-host-validation-2026-10-24.md).

## October 24: tested immediate prefix→memory-copy primitive — host only

- **Substantial V2 code milestone, no guest deployment:** New `TypedApiImmediateNeighborhood.Capture` is a bounded synchronous consumer for the previously committed `onMatch` hook. It rechecks exact `RRAPIVAL2|{` in the same process handle, rejects NUL/binary/stale markers without dumping memory, then retains **7 × 4 KiB pages / 28,672 actual bytes** centered on a plausible candidate, with per-chunk SHA-256, partial/unavailable failures, strict time gate and safe `native-memory-snapshot/1` wrapping. This avoids assuming the earlier hour-stale addresses are still valid.
- **Actual Windows host proof:** Added **11 focused tests**, including a real Windows self-process allocation: the true 64 KiB read-only native scanner called the inline hook, which used the true Windows 4 KiB memory reader to copy 28 KiB from the **test process**, byte-for-byte verified with process identity revalidation. Full .NET **424/424 tests pass** (131 Live + 293 core), targeted `dotnet format --verify-no-changes` and `git diff --check` pass. This is not proof of a RIFT typed Lua frame or a new guest command. [Detailed host validation and next gates](validation/typed-inline-neighborhood-host-proof-2026-10-24.md).
- **Next:** wire the collector into a bounded, versioned no-overwrite live CLI with exact target/request proof, capture limits and process invalidation handling; obtain independent samples using newly found positions. **V14 remains exclusive console owner; no new VM action.**

## October 24: immediate post-match capture hook — host-only implementation

- **V2 pure scanner improvement, NOT YET A LIVE FEATURE:** `TypedApiPrefixScout.Scan` now accepts an optional, synchronous `onMatch` observer notified of **retained matches in the current 64 KiB scan block before the next read**. The observer cannot receive cross-hole matches or candidate-overflow entries; existing `scout-typed-native` CLI and scan request/report remain unchanged and do not install an observer. This provides a tested seam for future **same-operation read-only neighborhood capture**, avoiding the roughly hour-long stale-address lag of the first live scout/snapshot follow-up. New focused tests cover prompt notification, overflow and split/hole cases. **No guest bundle deployed, VM console input or game read issued as part of this code change.**
- **Next:** add a bounded, provenance-rich immediate capture consumer and test it without the game before touching V14; there is no current qualified typed wire or XYZ. [Scanner contract](reference/typed-prefix-scout.md).

## October 24: TWO REAL read-only native snapshot reports recovered; V14 healthy

- **Live acquisition complete (17:44–17:45 UTC):** After a normal V13 STOP, exclusive VM console acquired two independent `snapshot-native` reports from the unchanged RIFT PID **6940** / start ticks **639284177321390013**, using the 3 × 28,672-byte exact-session source windows. Every one of **21 chunks per report** was complete and independently SHA-verified, with no holes. Sample A: **126,199 bytes**, SHA `32FE40D65E0F2312378797A50F69E005D754F50693C613777B7F9268841DFA33`; sample B: **128,139 bytes**, SHA `13AF9B26B9DD8A846029AA81BD6589D5A2BCC981F2BD033D418AF14DF35602C2`. Both full originals, transfer receipts and hashes are retained under ignored `artifacts/update-recovery-20261023-01/`.
- **Strict wire inspection is NEGATIVE in covered scope:** `inspect-typed-wire` published a separately hash-verified report with `status=unavailable`, `reason=before:no-complete-usable-frame-in-covered-scope`; both inputs cover **86,016 bytes**, but contain **zero complete candidate frames**. One scout marker at `0xD3DB230` persisted next to binary, not JSON; the other two addresses lost their marker as their heaps changed. **No typed-frame advancement, native XYZ comparison, or whole-process negative claim.** Immediate scan-to-copy is the evidence-driven next approach.
- **V14 safely restored (independent verification 17:52:10 UTC):** Exactly pinned V13→V14 handover closed the PowerShell console and started independent `pythonw.exe` V14 **PID 36776**, session **2**, `inJob=false`. Authenticated **ready/connected**, supervisor **running/cleanup verified**, unchanged RIFT foreground, guest **disarmed/idle**, canonical SQLite **unblocked/no holder/zero pending**, generation **1152**. **V14 now holds the VM console; no concurrent VNC or game input.** See [full real pair, hashes, decoder and recovery evidence](validation/typed-snapshot-first-live-pair-2026-10-24.md). The prep sections below are historical, not current owners or pending gates.

## October 24: V14 exact-epoch successor prepared; V13 still in command

- **Independent live read-only preflight (17:17:53 UTC):** V13 `pythonw.exe` PID **65364** remains authenticated ready/connected with supervisor and exclusive console healthy, guest disarmed/idle, RIFT foreground PID **6940**/start **639284177321390013**/unchanged executable SHA, VMX PID **38044**/exact same start/log epoch. Canonical SQLite queue: **unblocked, no holder or pending, generation 1128**. The guarded same-epoch handover helper then returned `handover-prepared-not-executed` for **V13→V14**; V14 plan/launcher saved no-overwrite. **No STOP or guest activity was issued**.
- **Guest snapshot transport prepared, not used:** The one-use guest stepper validates pinned 84 KiB request, V13 normal STOP evidence, quarantined queue, VM mutex, and foreground PowerShell screenshot before typing. Offline preview reported **24 bounded commands** and the reference screenshot classifier correctly distinguished PowerShell from RIFT. New guest-IP-restricted two-digest receiver (SHA/size declarations only, no memory content) passed **8/8 focused and 545/545 full Python tests**; report originals must still transfer via the existing one-use content-hash receiver. [V14 preflight and pending gates](validation/typed-snapshot-v14-preflight-2026-10-24.md).

## October 24: exact-epoch two-snapshot plan generated offline; live capture pending

- **Host-only follow-up complete (17:10 UTC):** The tested `scripts/plan_typed_scout_snapshots.py` consumed the original **2,902-byte**, SHA-pinned game scout report and created two **identical, no-overwrite `snapshot-native` request files** plus provenance manifest at `artifacts/update-recovery-20261023-01/rr2-typed-snapshot-plan-oct24-01/`. Each future sample selects **3 × 28,672-byte** windows, starting at **`0xD3D9000`, `0xD6BE000`, `0xD761000`**; total **86,016 bytes / 21 chunks**, 10-second limit. Request SHA-256 **`0BF11FCFB280BF4042DC97CA68DE98AA8099B4194F9DD2D241F34C82E7DFF92F`**; independent manifest hash **`C8D508350162FBF5D245F65BBE5E140DD6A5A8BECD3DF67E3810CC2ADDDDE3A7`**. **13/13 focused, 537/537 full Python, and 410/410 unchanged .NET 10 regression tests pass**; this is **not** evidence of actual guest snapshots or advancing Lua data. [Exact plan and gates](validation/typed-scout-snapshot-followup-plan-2026-10-24.md).
- **Pending guest acceptance:** Fresh exact-VM, game process and coordinator status required before using absolute addresses; V13 remains the exclusive owner until a genuine normal V13→V14 handover. Acquire two independent guest `snapshot-native` reports, transfer originals with SHA checks, restore healthy coordination, and run strict `inspect-typed-wire`. No game movement, memory writes, new VNC owner, or guest operation occurred while constructing this offline plan.

## October 24: FIRST LIVE typed-prefix scout; V13 restored and healthy

- **Real guest execution and recovered evidence (16:42–16:54 UTC):** The SHA-pinned 74,209,699-byte `scout-typed-native` executable ran read-only in RIFT-Lab-1 against unchanged RIFT PID **6940** / start ticks **639284177321390013** / executable SHA **`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`**. CLI exit **3** is its documented `partial` / `byte-budget-exceeded` status. Exactly **536,870,912 attempted and examined bytes**, one covered private span and **zero holes** yielded three `RRAPIVAL2|` prefix addresses: **`0xD3DB230`, `0xD6C0550`, `0xD763500`**. The scan covers **5.669%** of eligible private virtual bytes; recorded but untested continuation cursor **`0x7FFDFFF7`**. They are **candidate byte prefixes only**, not complete fresh Lua frames or XYZ.
- **Original report preserved and SHA independently checked:** `artifacts/update-recovery-20261023-01/rr2-scout-oct24-01-host.json` is **2,902 bytes**, SHA-256 **`87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6`**, matching the guest and one-use transfer receipt; temporary transfer endpoints shut down. Detailed process, transfer, original screenshot hashes and operational receipts: [first live scout validation](validation/typed-prefix-scout-live-2026-10-24.md).
- **V13 normal recovery checked (16:54 UTC):** The previous V12 owner exited via STOP; only then did the exclusive maintenance scan run. Authenticated independent V13 `pythonw.exe` **PID 65364**, Windows session 2, now owns native console: **connected/ready**, supervisor **running**, initial cleanup verified, guest disarmed/idle, RIFT foreground, SQLite **unblocked, no holder or pending requests**, VM and game epoch unchanged. **Do not interact with its VM/VNC while it owns the console.** Next: design narrow, identity-bound `snapshot-native` windows for the three prefix hits; two time-separated snapshots and strict `inspect-typed-wire` require a new guarded V13→V14 handover.

## October 24: pinned native-scout transfer preflight and V13 plan (historical; now completed)

- **Reuse-first host→guest transfer ready, not launched:** New `scripts/serve_guest_native_scout.py` streams the exact **74,209,699-byte** hash-pinned V2 executable in 64 KiB blocks to only the existing VMnet8 guest IP and one route; it expires after one verified transfer or 600 seconds. Wrong peer, method, path, truncated content, and hash drift cannot count as success. **10/10 focused tests, 524/524 full Python suite passed**; actual Windows source-hash/size preflight passed without opening a listener. See [host-only transfer readiness](validation/typed-prefix-scout-transfer-2026-10-24.md).
- **V13 continuity prepared, not executed:** The existing same-epoch handover procedure pinned VMX PID **38044** and its unchanged log epoch, confirmed free canonical authority and V12 PID **15336** alive, and produced ignored V13 plan/launcher. V12 remains the live exclusive console owner; **no shutdown marker, guest input or transfer listener was issued**. Guest download, bounded scout, report return and normal V13 restoration are the next controlled acceptance gates.

## October 24: bounded typed-prefix scout CLI host-validated; guest trial pending

- **V2 implementation committed:** `c6908c8` adds the read-only, 64 KiB streaming `RRAPIVAL2|` scanner with coverage, holes, byte/time/match limits and overlap-safe resume cursor; `2e73b9a` adds `scout-typed-native`, exact process-epoch request validation, versioned hash-bound no-overwrite reports, and identity-invalidated status. Existing 4 KiB `snapshot-native` contract and V1 source were preserved.
- **Host-only validation:** 23/23 focused scanner/matcher, 4/4 focused CLI, **410/410 .NET 10** full solution (117 Live + 293 core), **514/514 Python**, **108 Lua + 22 real Lua-to-C# shared cases**, full .NET formatting and zero-warning Release build passed. The published single-file executable passed its own-process native identity/no-overwrite smoke; size **74,209,699**, SHA-256 `C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C` (ignored `artifacts/validation/rr2-scout-publish-20261024-01/`). **The one-shot PowerShell 7 composite was unavailable**, but its principal component gates ran separately. No RIFT guest memory was scanned. See [command contract](reference/typed-prefix-scout.md) and [host validation](validation/typed-prefix-scout-host-validation-2026-10-24.md).
- **Live state untouched:** most recent read-only coordinator status at **11:29 EDT** remained authenticated connected/ready, RIFT PID **6940** foreground, supervisor running, guest disarmed/idle. **No new guest binary, current Lua candidate, complete advancing typed frame, or native/Lua XYZ match yet.** Next: hash-pin the tested guest binary and execute the first bounded pass only after fresh exact-epoch/queue preflight and legitimate exclusive console release.

## October 24: handoff checkpoint — typed-prefix matcher committed, V12 live

- **New verified implementation (10:47 EDT):** `6db17e1` adds V2 `TypedApiPrefixMatcher` plus 12 passing focused tests. Full .NET 10 solution gate **395/395** (293 core, 102 Live); earlier Python **514/514** remains the last Python full-suite check. This pure code was **not deployed to the guest**. It reports `RRAPIVAL2|` prefix candidates only and does not verify a complete Lua frame.
- **Latest non-mutating live check (10:49 EDT):** V12 is authenticated **connected/ready**, owned supervisor **running** with initial cleanup verified; guest PID **6940** remains foreground, disarmed/idle, no sampled desktop input down. SQLite snapshot: authority **blocked=0**, holder absent, zero pending, fresh cleanup receipt `nav-cleanup:dd28b9be952b422e77ccf17cc7429a15e880545899ac9070163f4d3f083ccad9`. No VM or guest operation was performed in this check.
- **Resume from the handoff:** [October 24 operational handoff](handoff-2026-10-24-typed-prefix-scout.md) records current identity, last ten implementation/evidence commits, exact artifact checksums, tests, safe preflight and next acceptance gates. **Next**: connect the matcher to an explicitly bounded, exact-epoch 64 KiB V2 scanner and versioned report/CLI. No current typed Lua candidate, advancement or native/Lua XYZ qualification has been established.

## October 24: complete guest map on host; native coordinator V12 active

- **Lossless current-epoch report retained (10:21 EDT):** The full **2,831,071-byte** guest `native-memory-map/1` JSON is now at `artifacts/update-recovery-20261023-01/rr2-map-oct24-01-host.json` on the Windows host. Original guest, pre-upload, streaming receiver and independent host SHA-256 all equal `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`. The temporary one-use host-only upload receiver accepted exactly one hash-pinned POST and exited; no listener on 8765 remains. The new scoped receiver passed **12 focused** tests and the **514/514 full Python** suite; implementation checkpoint `183bd71`.
- **Map anatomy verified from actual JSON:** **20,838** committed/readable non-guard regions, totaling **7,846,682,624 readable virtual bytes** (not RAM usage); **19,956** private regions hold **7,648,837,632** bytes. Historical October 16 typed-frame absolute addresses are **not mapped as readable** in today's RIFT PID **6940**, confirming those old absolute locators cannot be reused. No current typed Lua frame or native/Lua XYZ agreement is claimed.
- **Coordinator restored safely (10:23 EDT):** After genuine V11 STOP/release, the exact source/VM-pinned V12 launched independently as `pythonw.exe` PID **15336** (Windows session 2, not in Workbridge's job). Authenticated status: guest connected/idle/disarmed and RIFT foreground, coordination ready, owned supervisor running with `initialCleanupVerified=true`. Read-only SQLite: **blocked=0**, holder absent, zero pending, new cleanup receipt; **no manual queue reset**. The earlier V11 checkpoint below is historical.
- **Next meaningful gate, revised after reuse-first code review:** One 64 MiB snapshot covers less than 0.9% of the private readable space, so build a **bounded V2 marker-only scout** for `RRAPIVAL2|`, reusing the existing 64 KiB streaming scanner and exact-epoch guards. Use positive prefix addresses to select small `snapshot-native` ranges for two advancing `inspect-typed-wire` samples, then compare native XYZ. See [scout design](research/typed-prefix-scout-reuse-2026-10-24.md) and [full-map transfer/V12 evidence](validation/guest-map-report-transfer-2026-10-24.md).

## October 24: current-epoch guest map succeeded; native coordinator V11 restored

- **Read-only guest acquisition succeeded (09:53 EDT):** Under exclusive VNC maintenance after a genuine V10 STOP/release, guest `RiftReader2.Live.exe map-native` returned `MAP_EXIT=0`, `MAP_STATUS=complete`, and **20,838** regions for exact RIFT PID **6940**, start ticks **639284177321390013**, unchanged executable SHA-256. The 276-byte request's guest SHA matched `F1C41A5F...`; guest report SHA-256 is `5A5F74EB80F81FBE86F7D04E9F2CCEA35D09709E18CDE959F2321DF9F04D9B3B`. The full JSON remains **guest-local**, not yet transferred to host; screenshots and one-use receipts are preserved under ignored artifacts. No Lua frame, native XYZ match, game movement or memory write was claimed.
- **Verified safe restoration (09:58 EDT):** Guest PowerShell was closed and Rift foreground verified. Independent V11 `pythonw.exe` PID **60420**, Windows session **2**, outside the Workbridge job, started from the exact VM/config/runtime-hash-pinned plan. Authenticated status: connected, coordination ready, owned supervisor running with `initialCleanupVerified=true`, guest idle/disarmed and foreground. Its normal startup reconciliation returned the canonical SQLite queue to **blocked=0**, no holder, zero pending, with new cleanup receipt. **No manual queue reset.** Earlier V10/V11 preparation statements below are historical snapshots, superseded by this V11 live state.
- **Superseded after the 10:23 EDT transfer:** The complete report was subsequently copied and hash-verified on the host, and V12 now owns the live coordinator. The still-open work is bounded snapshots, typed-wire advancement and same-epoch native/Lua XYZ agreement; see the newer section above and [the original guest map evidence](validation/current-epoch-native-map-2026-10-24.md).

## October 24: typed Lua wire — offline inspector verified; live acquisition pending

- **V2 bounded analyzer now exists:** Added `inspect-typed-wire` for two existing `native-memory-snapshot/1` files. It reuses the strict hash-verified snapshot loader, never bridges unavailable chunks, searches complete `RRAPIVAL2|` v0.6.0 strings, rejects malformed/incomplete/conflicting copies, and requires same game process, source player, advancing sequence and `Inspect.Time.Frame`. It reports XYZ as `advanced-in-covered-scope` only, not globally unique/fresh or native-field qualified. This does not interact with VMware or V1.
- **Validation:** 19/19 focused .NET tests, **383/383 full .NET 10** (293 core + 90 Live), clean scoped `dotnet format --verify-no-changes`, and CLI help smoke. The prior full Python suite was **502/502**; the PowerShell 7 composite runner remains unavailable through Workbridge. See [offline typed-wire validation](validation/typed-wire-offline-inspector-2026-10-24.md) and [usage contract](reference/typed-wire-snapshot.md).
- **Status after the subsequent live map milestone:** This offline checkpoint's `map-native` blocker is now resolved for current RIFT PID 6940; two bounded `snapshot-native` reports, host retention of the full map, fresh typed frames, and Lua/native XYZ agreement are still pending. See the newer section above.

## October 24: verified three-frame visual baseline

- **Three distinct foreground RIFT frames (12:21Z / 12:52Z / 12:53Z):** Existing V10 PID **8168** acquired two more authenticated Track B screenshots with unique queue leases; all requests **succeeded** with independent STOP/release cleanup and no ARM, movement, game keys or manual queue reset. Each verified BMP is **1211×686**/32-bit, 3,323,038 bytes, tied to unchanged RIFT PID **6940**/start/build and VMware PID **38044**. Host capture IDs, instants and hashes are distinct.
- **Temporal QA, not motion qualification:** Deterministic pixel comparisons show **73.5576%** changed in frame 01→02 (~31 min), **39.2586%** in 02→03 (~87s), and **42.1977%** within the central-world ROI in the latter pair (mean RGB delta 0.5093). Scene animation/UI noise remain possible; these numbers do not prove player/camera motion or object recognition. Added reusable offline `scripts/compare_native_frames.py` with **6/6 tests** and no-overwrite reports under ignored artifacts. Both this suite and handover tests are included in `scripts/validate.ps1`. See [three-frame evidence](validation/native-v10-temporal-frames-2026-10-24.md).

## October 24: typed Lua readback blocker — targeted repair research

- **Source-level cause confirmed, live fix still pending:** The V1 observer’s default 4 GiB/10 s broad private-memory scan stops with `scan-byte-budget-exceeded`; its incomplete pass deliberately prevents typed freshness evaluation. No evidence shows a missing Lua frame or changed game binary. The last blocked observation belonged to the older October 23 game epoch, **not yet remeasured** for current PID 6940.
- **Positive reuse evidence found:** An actual October 16 two-sample typed addon capture (same executable SHA-256) reported advancing source sequences **5603→5608** and frame clocks **5302.787→5305.596**, with **5→3** candidate copies. The selected heap address changed within the same process; old absolute locations are invalid for today’s process. Source/parser/producer hashes, exact frame contract and a bounded-scanning acceptance design are captured in [typed API recovery research](research/typed-api-bounded-recovery-2026-10-24.md).
- **Next core milestone:** obtain an exact-current-process bounded map/snapshot in the guest, locate complete typed wire frame(s) without budget expansion, require independent source advancement, and compare same-epoch Lua XYZ with native root RVA `0x32E0200`. No V1 edits, VM settings changes, additional network port or gameplay input were made by this research.

## October 24: guarded same-VM-epoch coordinator preparation

- **Prepared but did not launch V11 (12:33Z):** Added explicit `--same-epoch` to `scripts/prepare_native_host_handover.py`. It demands the exact unchanged VMware identity, a live V10 owner, matching config/runtime hashes, and read-only SQLite proof of `blocked=0`, no holder/pending requests, and a cleanup receipt. The existing restarted-VM mode still requires queue quarantine and a changed VM epoch. Python-only plan creation prevents JavaScript rounding of Windows 64-bit `startTicks`.
- **Verified live without interrupting V10:** V11 plan and launcher exist under ignored `artifacts/update-recovery-20261023-01/`; the V11 plan preserves exact `startTicks=134372941117887852`, all five runtime hashes, full VM identity, and has no shutdown marker. V10 PID **8168** remains alive; queue free/unheld/cleaned, no actions dispatched. **V11 is not running** and is valid only while this VM process epoch remains unchanged.
- **Tests:** 7 focused handover, **496 Python**, **364 .NET** passed, plus `git diff --check`. The full `validate.ps1` runner was not completed: PowerShell 7 executable unavailable via Workbridge; Windows PowerShell 5.1 fallback mispassed Lua inline-code quotes on its first test. See [same-epoch handover evidence](validation/same-epoch-native-host-handover-2026-10-24.md). Next: resume field qualification using the verified V10 capture; no coordinator handover is needed for read-only discovery.

## October 24: receiver and coordinated host restored after VM epoch change

- A fresh host read-only check at 2026-10-24T10:30:44Z confirmed vmware-vmx PID 38044 and its VNC listener on port 5905, with no native listeners on 49712/49715; old V7 coordinator PID 34352 no longer exists. V7 had first refused orderly shutdown (`shutdown-release-unverified`) and was terminated only after exact-process/no-in-flight checks. **This was not a guest STOP/release or cleanup receipt.** The prepared V8 coordinator has not been launched; its plan must be rechecked against the current VM epoch.
- The last documented read-only canonical SQLite snapshot for `vm:rift-lab-1` recorded **blocked=1**, holder absent, no cleanup receipt, and zero pending work. That queue was not queried in this follow-up process/port check. Preserve its database/journal/history; never infer that the emergency host exit unblocked it. RIFT pixels were visible through a separate host screenshot route, but authenticated guest-receiver readiness and unattended startup are still unverified.
- **Live native capture qualified (12:21Z):** V9's first leased capture was correctly rejected because RIFT was background; its request was cancelled and cleaned. After a clean supervisor-backed V9 shutdown, a taskbar click brought RIFT to the foreground without gameplay input. Losslessly generated V10 passed all identity/hash/queue checks, connected as independent PID **8168**, supervisor `initialCleanupVerified=true`. One authenticated leased screenshot succeeded: **1211×686 BMP, 3,323,038 bytes, SHA-256 `28297faf...`**, visually confirmed world/HUD with no window occlusion. Request `rr2-v10-scout-20261024-01` is **succeeded** and queue returned to free/unheld/zero-pending after verified STOP/release. No ARM/movement. V10 is current as of this checkpoint; guest reboot auto-start remains unproved. See [V10 live capture evidence](validation/native-v10-foreground-capture-2026-10-24.md).
- **Recovery completed (12:03Z):** The already installed current-user `RiftReader2 Receiver` Startup shortcut passed the pinned installer’s `already-installed`/exit-0 check. V8 first started without a connected guest, then **gracefully shut down** with no supervisor, verified exit and closed ports. The historical V9 host (PID **50980**, Windows session 2) was **connected/ready** to the correct guest and game PID 6940, supervisor `initialCleanupVerified=true`, guest disarmed/idle, no held keys. Read-only canonical SQLite inspection confirmed **blocked=0**, no holder, fresh cleanup receipt, zero pending work, with **no manual queue reset**. True unattended logon/reboot recovery remains untested. See [live recovery completion](validation/receiver-guest-recovery-2026-10-24.md).
- **Guest ZIP verified, manifest present, receiver not yet connected:** Fresh bounded VM-console interaction found an already downloaded ZIP in `C:\Users\mrkoo\Downloads` whose *guest-computed* SHA-256 exactly matched pinned `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`. An additional one-shot HTTP transfer received the exact guest request, but Chrome blocked that newer download as insecure; no security override was made. The previously extracted six-file folder was visible. In guest Windows, `CHECK-STATUS.cmd` validated the installed manifest/launcher/receiver/config and returned **`state=start`, `connectionVerified=false`, exit 0**, meaning receiver launch is possible, **not** that it is running. Those were subsequently verified in the recovery-completion checkpoint above. See [live guest recovery checkpoint](validation/receiver-guest-recovery-2026-10-24.md).
- The intact and SHA-256-verified six-file v2 guest installer ZIP has been placed into a new one-click Windows IMAPI2 ISO (63,488 bytes; SHA-256 507002784F251628E05DA12AEAD4F70391C6F88CFC3D6D3180D8A1C5174F25A1). Independent Joliet extraction confirmed the embedded ZIP byte-for-byte; 4/4 focused tests passed. **This is host media only:** the VM optical image remains unchanged, no guest installer ran, and no guest input was sent.
- **Next after restoration:** continue read-only RIFT field-discovery work through the authenticated, leased native host; review current pixels and keybinding evidence before any new bounded game input. Separately qualify one controlled guest logoff/logon and later VM reboot for **unattended** receiver Startup, preserving the canonical queue and requiring fresh cleanup/identity verification each time. The earlier [ISO/transfer preparation](validation/receiver-iso-host-prep-2026-10-24.md) remains historical host-only evidence, not a needed transfer step now.

## Receiver transfer — existing Pythonw firewall exception reused

**A limited-duration native Windows transfer endpoint was deployed on the host,
not inside guest Windows.** The existing Python 3.14 `pythonw.exe` had an enabled
Windows Firewall inbound TCP Allow rule (Public profile), unlike `python.exe`.
Using Python's standard HTTP server with a thin single-file/IP restriction, a
normal session-1 Pythonw process was launched independently of Workbridge and
verified still listening after the Workbridge job exited.

Observed launch: **2026-10-22T09:39:42.901691Z / 5:39:42 a.m. EDT**, PID 39644,
bind `192.168.56.1:8765`, allowed guest source `192.168.56.128`,
one pinned ZIP, and automatic stop after one download or ten minutes. **Do not
treat the historical PID or listener as permanently current.** Last checked
2026-10-22T09:42:04Z: running, zero downloads, guest installation unverified.
The existing native coordinator remained connected/ready, RIFT was not foreground.

Seven isolated HTTP tests passed, including an actual Pythonw.exe process,
exact file/host limits, HTTP 403/404/501 refusal, checksum, and automatic exit.
The real PowerShell launcher preflight passed; a simultaneous second launch was
correctly refused because port 8765 was already owned. No Windows Firewall,
VMware isolation, administrator rights, game input or guest credentials changed.
A valid package was also copied non-destructively to the existing configured
host media folder `C:\RIFT MODDING\Media\RR2-Guest-Startup-v2-20261022.zip`,
but guest HGFS remains explicitly disabled and guest read access is NOT proved.

If the live listener has expired, the physical-host launcher is
`artifacts/receiver-milestones-20261022-01/START-RECEIVER-TRANSFER-PYTHONW.cmd`.
In signed-in guest Windows, open
`http://192.168.56.1:8765/RR2-Guest-Startup-v2.zip`, verify ZIP SHA-256,
extract, and run `INSTALL-ONCE.cmd`. Host
`CHECK-RECEIVER-TRANSFER.cmd` reports a transfer receipt. No guest download
or startup installation has been established; GuestInfo remained empty.
Next acceptance still requires the one-time guest installation, then a
receiver restart and separate Windows guest login/reboot qualification.
See [the transfer investigation](validation/receiver-transfer-pythonw-2026-10-22.md).
Artifacts: `artifacts/receiver-milestones-20261022-01/`.

## Historical three receiver deployment milestones — host-side work complete

**Scope: host delivery and verification; the guest Startup shortcut is NOT yet installed.**
M1: standard-library Python HTTP transfer bound to private VMware **VMnet8 NAT-side**
address `192.168.56.1` was proven locally, with a
SHA-256-matching download and no VMware isolation/firewall changes. The server
was shut down; no guest-initiated download was claimed.

M2: six-file **v2** guest package adds launcher SHA-256 verification before
installation, status, or removal. Thirteen real Windows CMD/disposable checks
passed, including tamper, missing file and wrong-machine rejection. New ZIP:
`artifacts/receiver-milestones-20261022-01/host-only-download/RR2-Guest-Startup-v2.zip`
SHA-256 `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`.
Recommended host launcher: `artifacts/receiver-milestones-20261022-01/START-HOST-ONLY-TRANSFER-v2.cmd`.
The old v1 package and launch script are retained only as prior evidence.

M3: `scripts/verify_guest_recovery.py` provides read-only, exact-VM/host/
receiver/game and durable-queue baseline-and-compare checks. **18 focused tests
passed**. The live baseline succeeded while RIFT was **not foreground**;
an immediate no-restart comparison was correctly refused. A positive future
comparison by itself does NOT establish an actual Windows reboot or unattended
shortcut launch. Full main-repository gate: **364 C# / 462 Python**, 108 Lua and
22 shared Lua/C# checks, zero-warning Release. Totals overlap the focused tests.

The current coordinated native host and canonical authority were left running.
No guest install, receiver restart, VM reboot or movement trial was attempted.
Guest-side package transfer, a one-time normal-user installation and the actual
logon/restart trial remain required. Do not claim autonomous reboot recovery yet.
Read [the three-milestone evidence](validation/receiver-deployment-reuse-first-2026-10-22.md).
Ignored artifact root: `artifacts/receiver-milestones-20261022-01/`.
Previous dirty work/Git history and private config were preserved; no commit/push.

## Historical receiver deployment — original Windows Startup package

**Guest installation still pending.** Reuse-first verification selected Windows'
current-user Startup folder and the already tested RiftReader2 PowerShell launcher
rather than building another service, credential store, execution channel, or
privileged scheduled task. Microsoft documents the Startup folder; VMware's
supported guest-execution commands require separate guest Windows credentials.

Host-side package:
`artifacts/receiver-reuse-20261022-01/RR2-Guest-Startup.zip`
(SHA-256 `b219c79b52e70bf2fbbcfa06f0e0d3793174bf9a0f9f1b40c19a49a37f547712`).
It includes the unchanged launcher, an interactive one-time installer, status
checker, removal shortcut and instructions. Five packaged entries were verified,
and the existing launcher tests passed 3/3 (including its disposable 38-check
PowerShell contract). No guest binary, configuration or credential is included.

Read-only detection first confirmed the exact VM (PID 52872), then a connected
and ready native host; RIFT PID 5076 was disarmed but **not foreground**.
Guest management endpoints WinRM 5985/5986, SMB 445, and RDP 3389 were not
listening. The coordinated console mutex remained held; it was not bypassed.
No VM input, host restart or source/runtime modification occurred.

**Next:** a single installation while logged in to guest Windows: transfer
the package with an existing authorized VMware/USB file-copy method, extract it,
run `INSTALL-ONCE.cmd`, verify `shell:startup` and `CHECK-STATUS.cmd`.
Only after the actual shortcut works should the guest logon/restart test be
declared complete. Until then, autonomous reboot recovery remains **unproved**.
See `artifacts/receiver-reuse-20261022-01/PLAN.md`. Do not rerun the
previous blocked guest-console diagnostics or old single-use maintenance helpers.

## Historical receiver restart recovery — tested launcher; guest installation blocked

**The restart problem is still open. No guest Startup entry was installed.**
The current-user receiver launcher and installer/removal tests are integrated,
not deployed. The final isolated gate passed **364 C# / 444 Python** and existing
Lua contracts; three main focused cases passed, including 38 PowerShell contract
checks in temporary directories. These are not guest reboot/recovery evidence.

Two guest transfer attempts did not return the required acknowledgment and stopped
before installation. Each restored the coordinated host and original queue. A
separate Run-dialog diagnostic confirmed that shortcut visually but typed no
command text. A subsequent visible diagnostic was blocked by the tool safety
check and did not execute; it was not rerouted around the block.

At **2026-10-22T07:33:00.941243Z / 3:33 a.m. EDT**, the restored native host was
**PID 6560** (start ticks 134371277545443317), connected/ready with its watchdog
running. VMware 52872, RIFT 5076 and receiver 8b9468f7712941f487a232b6cf7c5329
retained their identities. Guest state: idle, disarmed, no recovery or sampled
held input. **RIFT was not foreground**; do not claim movement readiness.
The canonical queue had no active, queued or cleanup requests and kept its history.

Current process receipt and wrapper:
`artifacts/receiver-startup-20261022-01/evidence-a03/restored-host-process.json`
and `artifacts/receiver-startup-20261022-01/run_restored_host_a03.py`.
Current absent shutdown marker:
`artifacts/receiver-startup-20261022-01/STOP-NATIVE-HOST-A03`.
The prior host PID 54952 and shutdown markers below are historical. Re-detect the
actual host before maintenance; do not reuse old activation or reset the queue.
No VM, game or guest-receiver restart occurred in this task; three native-host
maintenance restarts used verified orderly shutdown, not forced termination.

Next: resolve the observable/permitted guest setup channel, install the tested
startup helper, prove receiver restoration via the actual shortcut, then qualify
one real guest logon/restart. Do not add more control-framework milestones instead.
See [the partial recovery report](validation/receiver-startup-recovery-2026-10-22.md).
Evidence: `artifacts/receiver-startup-20261022-01/`. Native runtime source, original
config, prior source work, Git index and HEAD were preserved; no commit or push.

## Historical NAV-SCHED-02I: coordinated host active and live-verified

**The production ownership system is now enabled on recovered RIFT-Lab-1.**
Native host PID 54952 replaced the older host after verified
STOP/idle release, without restarting VMware, RIFT or the guest receiver. The
original configuration/ports/credentials are unchanged. Fresh VM detection
preceded access. Activation: 2026-10-22T05:39:31.854007+00:00.

Actual host startup now owns one durable queue, the known console mutex, and a
verified supervisor for every guest connection. Reconnect joins the previous
supervisor and invalidates old grants/queued work using exact-row reconciliation
before fresh cleanup. Existing authority on process restart requires explicit
reconciliation; never delete/reset the queue to make a blocked state disappear.

Live no-movement acceptance passed: unleased capture refused, issued-lease capture
saved and hash-checked, request finished after verified cleanup, completed token
refused, known console contender excluded. After 135 seconds idle, **1
automatic reconnect(s)** returned the same host to ready, with no outstanding
requests. No ARM/action/movement was sent; cleanup STOP was sent and verified.
The capture was not visually reviewed, so it is not a fresh movement review gate.

Both final candidate and main gates passed **364 C# / 441 Python**, **108 Lua /
22 shared cases**, zero-warning Release, synthetic smoke and deterministic replay.
34 new Python cases are included. The failed fixture run and shutdown-journal
regression remain retained; diagnostics cannot unlock a blocked shutdown on write
failure. Code review was by the implementing assistant, not independent review.

Authority: `artifacts/native-coordination-live/queue.sqlite3`, resource
`vm:rift-lab-1`. Process receipt and launch/shutdown details are in
[the activation report](validation/navigation-coordinated-host-2026-10-22.md).
Evidence: `artifacts/navsched02i-20261022-01/evidence/`.
**Do not repeat the single-use activation or reuse old process IDs.** No OS
autostart/service was installed. Preserve queue/history and re-detect on resume.

Next: return to field-discovery/navigation experiments using the live ownership
system, with fresh screenshot/keybinding review before any bounded input. Known
cooperative console exclusion does not cover manual VMware UI or arbitrary bypass
clients. Git staging/HEAD, earlier source work and original config were preserved;
no commits, pushes, dependency or external-repository changes.

## Historical NAV-SCHED-02H: shared console exclusion qualified offline

The coordinated gateway can now reserve the existing per-VM Windows console
mutex for its lifetime, including idle periods and guest reconnects. Known V1/V2
console capture/bootstrap and legacy experiment entry points are blocked while
reserved. Native requests on other threads borrow that ownership but retain VM
identity, lease and supervisor checks. Native STOP/status/release remain usable.

Acquisition requires denied-first supervision and an exact configured VM. A
pending release keeps the lock until an explicit same-thread retry; another
thread cannot close the owned handle. Identity drift blocks native admission
without silently unlocking the console. Local lock release is not proof of guest
input cleanup, and production teardown must stop/join supervisors first.

The full isolated gate passed **364 C# / 407 Python**, **108 Lua checks / 22 shared
cases**, zero-warning Release, synthetic native smoke and deterministic replay.
There are **27 new reservation tests**; focused regression contains 286 cases.
The installed legacy mutex/observe tool and fake-adapter experiment entry paths
were verified against disposable VM paths with external sources unchanged.
Final promoted-checkout and preservation results are saved in
`artifacts/navsched02h-20261021-01/evidence/milestone-complete.json`.

**Not activated on the recovered host.** This adds an internal construction
option, not a new live config or automatic restart. The existing connection was
freshly identified before guest status; no live input, capture, ARM, STOP or
console reservation was sent. Prior source changes, config, Git index and HEAD
are preserved; no external-repository edits, commit or push.

Next: production per-session supervisor startup and explicit existing-resource /
reconnect reconciliation, then reviewed activation and one bounded live trial.
Known lock-participating legacy callers are excluded when ownership is enabled;
manual VMware UI and arbitrary bypass callers are not covered. See
[shared console evidence](validation/navigation-console-exclusion-2026-10-22.md).

## Historical NAV-SCHED-02G: native caller ownership and denied-first reconnects

HTTP, CLI and the browser panel now carry explicit ownership credentials to the
existing send-boundary queue check. Private lease files are bounded to 8 KiB;
only request ID/token are forwarded out-of-band, never to the guest or journal.
Older hosts reject the envelope and callers never silently retry without it.
STOP/release/status remain usable without a lease file. Panel import, replacement
and clearing invalidate prior reviews and prevent an accidental unleased fallback.
The panel no longer labels Q/E as guaranteed strafing bindings.

An explicit `require_supervisor=True` gateway construction option starts every
newly authenticated session suspended before publication. Reconnects cannot
inherit the former policy/lease. This is a composition option, not a new live
configuration switch; the recovered host remains unchanged and uncoordinated.

Focused tests passed **259** (22 new Python cases); the panel harness includes
eight additional ownership scenarios. The full gate passed **364 C# / 380 Python**,
**108 Lua checks / 22 shared cases**, zero-warning Release, native smoke,
formatting and deterministic replay. These counts overlap. Final hashes and
main-checkout acceptance are recorded under `artifacts/navsched02g-20261021-01/evidence/`.

The recovered VM was identified before guest status and was connected, foreground,
idle/disarmed and recovery-free. Re-detect rather than reuse those observations.
No live input, capture, ARM, STOP, host restart, new guest binary or configuration
change occurred. No staging, commit or push. Prior source changes remain preserved.

Next: reconcile VM-console/bootstrap/legacy ownership, wire per-session owned
supervision and explicit reconnect reconciliation into production startup, then
review activation and a bounded live trial. Manual callers can transport issued
grants; grant issuance/heartbeat/finish still belong to the coordinator. Full
live multi-controller exclusion is not claimed. See
[native caller verification](validation/navigation-native-callers-2026-10-21.md).

## Historical NAV-SCHED-02F: owned supervisor lifecycle complete offline

The recovered VM/control connection was freshly verified before guest status:
VM PID 52872, RIFT PID 11748, same receiver instance, foreground, idle/disarmed,
no recovery and no sampled held input. The live host is not restarted or
hot-reloaded by this source increment. Refresh identities and status on resume.

The new `OwnedSupervisor` explicitly owns startup, one joinable watchdog thread,
lease-expiry cleanup and shutdown. Readiness requires saved identity-bound cleanup
and the active runner; delayed start/stop never silently enables actions or claims
finished cleanup. Concurrent stop callers share one shutdown. Failed or stopped
supervision keeps the resource blocked and does not replay work or rebind targets.

A reproduced startup registration race is fixed: `require_absent=True` rejects an
existing resource inside the registration transaction. Session preparation also
excludes competing composition/cleanup without suspending an already running
owner. Six test processes produced exactly one new authority owner.

The expanded focused suite passed **237 tests** (25 new), and the isolated full
gate passed **364 C# / 358 Python**, **108 Lua checks / 22 shared cases**, zero-warning
Release, native synthetic smoke, formatting and deterministic replay. Focused and
repeated counts overlap. Final source hashes, full-gate and main regression results
are retained in `artifacts/navsched02f-20261021-01/evidence/`.

**Not live-enabled.** The ordinary native host still does not construct the
supervisor. Next: route manual panel/CLI and VM-console/legacy controllers through
one ownership contract, publish authenticated sessions only after deny-first
startup, then review activation. No movement, ARM, STOP, new guest binary,
configuration change, live queue creation, service restart, Git staging or commit.
See [owned lifecycle validation](validation/navigation-owned-supervisor-2026-10-21.md).

## Historical native connection recovery — October 21, 2026, evening

**The missing native host/receiver connection is restored and live-tested.**
Exact VMX/log/process-start/listener checks identified recovered RIFT-Lab-1
before any console access. The existing host was restored as a normal user
process that survives its bounded launcher; the existing hash-verified guest
receiver was started without a new binary or configuration change.

Observed identities for this recovery (refresh them on resume): VM PID **52872**,
host PID **49956**, RIFT PID **11748**, guest instance
`ad6bffc45e804a879a00d6f2a4c299df`, machine `DESKTOP-8632QPL`.
Native agent/UI ports **49712/49715** are restored. Fresh authenticated status
reports RIFT foreground, disarmed, idle, no recovery and no sampled held input.
Native screenshot capture and release-only STOP passed. A **135-second idle
reconnect test** recorded actual disconnect/reconnect journal events and returned
the same receiver/VM/game, still idle/disarmed, at **9:33 p.m. EDT**.

Windows bootstrap keyboard input was used to inspect/start the receiver and
restore game foreground. No native ARM or character-movement command was sent.
The first transient host launch and unsuccessful guest command launches are
retained as failed evidence, not successful deployments. No host/VM reboot,
credential, firewall, dependency, Git staging, commit or push was performed.
Implementation source and host configuration matched their baseline hashes.

**Do not repeat recovery merely because older sections say disconnected.**
First use fresh host/VM detection and native status. Normal host/guest processes
are running; no automatic Windows-startup service/task was installed. The
current bounded transport is now running in the restored host. NAV-SCHED
policy/watchdog/manual-path integration remains a separate unfinished rollout;
this restoration does not claim multi-worker exclusion or navigation success.

Report: [native connection recovery](validation/native-control-recovery-2026-10-21.md).
Evidence: `artifacts/native-recovery-20261021-01/evidence/`.
Before further live experiments, verify current game identity, foreground,
text-entry state and fresh visual evidence; do not reuse old review/arm tokens.

## Historical NAV-SCHED-02E: recovered VM verified; guarded bootstrap offline

Read-only detection at 9:01 p.m. EDT found exactly one VMware VM, matching
`C:\\rift modding\\VMs\\RIFT-Lab\\RIFT-Lab.vmx`, and VM process PID 52872
owning port 5905. The configured native control ports had no listener and the
status call returned WinError 10061. **VMware is running, but the RIFT guest
receiver and control host are not verified.** Do not send actions or use old
VM/guest process identities; detect everything again on reconnect.

`nav_supervisor_bootstrap.py` now prepares a new single-resource authority from
a qualified guest session and existing durable queue, initially **blocked**.
It suspends controls before read-only startup qualification, rejects reused
resource records, installs exact-resource admission, and constructs—but does not
start—the watchdog. Failures leave the session blocked. Six fake-guest integration
checks passed. The full repository gate passed **364 C# and 333 Python tests**,
108 Lua checks, 22 shared cases, and 291 relative documentation links; the
Release build had zero warnings. Closing host inspection still found only the
VM port 5905, without native control listeners. It is **not wired into the live host**; manual and legacy control
ownership, supervised runner startup and final release gates remain.

See [recovery and bootstrap report](validation/navigation-recovered-vm-bootstrap-2026-10-21.md).

## Historical NAV-SCHED-02D: startup identity preflight, offline

A new read-only `qualify_startup` helper collects two fresh status responses
from the same authenticated session and verifies durable VM/guest/RIFT identity,
idle/disarmed state, no recovery, and no sampled held inputs. It produces a
proposed resource epoch but **does not register an authority, install a policy,
start a watchdog, or enable gameplay control**. Changing command sequence
numbers are intentionally ignored; missing identity or unsafe state fails closed.

Eleven preflight checks, including real disposable guest framing, passed.
The final full gate passed **364 C# and 327 Python tests**, 108 Lua checks,
22 shared cases, zero-warning Release and 288 relative links. Evidence:
`artifacts/validation/20261021T225624Z-3ed013d8`.
The native endpoint refused the connection (WinError 10061), and read-only
host inspection found no VMware VMX process or matching control-port listener.
Current RIFT-Lab-1 connectivity is **not confirmed**. No restart, arming,
movement, or screenshot replacement was attempted.

Next: trusted startup authority/policy/watchdog composition, and manual/legacy
ownership reconciliation, before any reviewed activation. See the
[startup qualification report](validation/navigation-startup-preflight-2026-10-21.md).

## Historical NAV-SCHED-02C: stalled-send handling qualified offline

Authenticated-session frame writes now use nonblocking I/O with a two-second
whole-frame budget, a bounded send-lock wait, and a bounded-buffer reader.
Partial progress cannot extend the deadline. Failed/partial sends close the
session and fail pending requests without replay or a fabricated STOP/release.
The watchdog integration test confirms the resource stays blocked afterward.

Focused validation passed **195/195** (32 new transport cases). The isolated full
gate passed **364 C# tests, 316 Python tests, 108 Lua checks and 22 shared cases**,
zero-warning Release, locked restore, format, synthetic native smoke and replay.
Three additional runs passed all 96 executions of the same 32 transport tests;
these are repetitions, not extra unique tests. Full job:
`navsched02c-full-gate-20261021-01`. Main regression and preservation are recorded
in `artifacts/navsched02c-20261021-01/evidence/milestone-complete.json`.

**Not activated on the live host.** No game input, ARM, runtime restart, guest
installation, configuration change, Git staging, commit or push occurred.
Prior uncommitted work is preserved. See [transport validation](validation/navigation-bounded-transport-2026-10-21.md).
The two-second budget is for sending, not an end-to-end or hard real-time promise.

Next: fresh trusted startup identity/authority binding and policy/watchdog
lifecycle composition, then manual panel/CLI and competing VM-console/legacy
ownership participation. Activation and a bounded live trial still require fresh
visual review and independent observations. Do not repeat this completed slice.

## Historical NAV-SCHED-02B: expiry watchdog and verified cleanup, offline

The next integration slice adds a pinned-session LeaseWatchdog and a local
cleanup exclusion/drain boundary. Expiry now drives STOP in the fake-guest tests;
cleanup is published only after exact identity checks, successful STOP, drained
requests, fresh idle/disarmed/recovery-free status, no sampled held inputs and a
saved receipt. Uncertainty latches access blocked; an explicit cleanup retry does
not replay the original action. Shutdown stops but does not free the resource.

Focused validation passed **163 tests**, including **41 new cases**. The isolated
full gate passed **364 C# tests, 284 Python tests, 108 Lua checks and 22 shared
Lua/C# cases**, zero-warning Release, locked restore, format, native synthetic
smoke and deterministic replay. Full job: navsched02b-full-gate-20261021-01.
The first focused run exposed delayed waiter settlement on disconnect; close now
fails pending local waiters directly. The failure and diagnostic remain retained.

**Still not live-enabled.** Construction starts no process/thread; the explicit
watchdog loop ran only in disposable tests. The running RIFT-Lab-1 host, guest and
configuration were not restarted or armed, and no game input or screenshot
replacement was sent. The nine prior NAV-SCHED-02A source changes were preserved.

Next: bound stalled transport sends, wire fresh live identity/policy/watchdog
startup, and reconcile manual panel/CLI plus VM-console/bootstrap/legacy access.
Then perform reviewed activation and a bounded live experiment with current
screenshots and independent observation. Do not claim the active VM is already
protected by the new queue/watchdog. See
[watchdog validation](validation/navigation-watchdog-cleanup-2026-10-21.md).
Evidence: artifacts/navsched02b-20261021-01/evidence/. No independent reviewer,
commit, push, global settings or unrelated-project edits are claimed.

## Historical NAV-SCHED-02A: dispatch admission implemented offline

Joey approved starting the next integration after the live RIFT-Lab-1 status
check. The queue now has cooperative cross-process dispatch fencing and the
native gateway/session has an optional startup admission policy. Checks occur
at the actual send point, after queued-action/send-lock waits. STOP/release and
status bypass experiment admission; STOP/release invalidate older queued work.
No SQLite transaction remains open during transport send/reply waiting.

Focused acceptance passed **122 tests**, including **27 new fake-guest/fence
cases**. The isolated full gate passed **364 C# tests, 243 Python tests, 108 Lua
checks and 22 Lua/C# cases**, with a zero-warning Release build, native synthetic
smoke, deterministic replay and 269 relative links. Full-gate job:
`navsched02-full-gate-v2-20261021-01`. Source/test changes are preserved with
hash guards; final documentation additions receive separate link checks.

**Not live-enabled.** The current host/guest/configuration were not restarted,
deployed or armed, and no game input was sent. The native target baseline was
connected, foreground, idle/disarmed, with no recovery or sampled held input.
That is not a screenshot review or a new movement/navigation result.

Next: bind policy to fresh exact live identities; implement watchdog-driven
STOP, in-flight release reconciliation and evidence-backed cleanup; reconcile
manual panel/CLI and VM-console/bootstrap/legacy paths; qualify stalled sends.
Only then enable and validate one bounded live experiment. Do not treat the
admission seam alone as completed live coordination. See the
[dispatch validation and remaining gates](validation/navigation-dispatch-fence-2026-10-21.md).
Evidence: `artifacts/navsched02-20261021-01/evidence/`. No independent workers
or reviewers were launched; no commits, pushes or unrelated-project edits.

## NAV-SCHED-01: offline experiment access queue

Joey requested concurrent A/B/C navigation research with intelligent queuing for
conflicting live-client access. The [access queue roadmap](planning/navigation-access-queue.md)
now has a standard-library Python/SQLite core and CLI, durable requests and audit
records, priority aging, dependencies, atomic multi-resource reservations, bounded
leases, stale-token rejection, and cleanup-required handoff. This is experiment
coordination, not a new gameplay controller or a claim of native pathfinding.

Focused validation passed: 42 queue tests plus 53 existing native host/client/VM
helper tests (95 total). Tests include eight competing threads, six independent
processes, abrupt worker exit, transaction interruption/rollback, restart, stale
epochs, negative cleanup evidence, and heartbeat hard deadlines. These are offline
fixtures, not AI agents or live game trials.

Full repository validation passed: 364 C# tests, 216 Python tests (including the
42 new queue cases), 108 Lua checks, 22 Lua/C# cases, zero-warning Release, locked
restore, native synthetic smoke, formatting, deterministic replay, and 266 relative
links. Log: `artifacts/navsched-20261021/full-gate-01.log`; generated evidence:
`artifacts/validation/20261021T133445Z-4c3b1dd5`. Final documentation-only updates
receive separate link/whitespace checks; source/test bytes match the full gate.

Next: enforce leases in the actual native control gateway and every conflicting
control path, with an immediate STOP/release path and fake-guest acceptance before
any separately approved bounded live experiment. The queue currently cannot stop
or fence a caller bypassing it. No host restart, guest deployment, VM operation,
live game input, RRE edit, or independent worker launch occurred in this increment.

## Camera responsiveness and actual window blur

The [camera/focus pass](validation/camera-tracking-focus-2026-10-20.md)
reduced camera-only pulses to 20 ms, retained 100 ms movement, and limited
pending camera motion to one bounded action. Release/blur discard it immediately.
Nine actions per camera mode visibly changed the view; measured button intervals
were 21.84–38.73 ms. This improves pulse cadence, not a claim of continuous
frame-by-frame tracking or one-to-one camera mapping.

Actual physical Edge Alt-Tab tests now verify window-blur STOP, both while
armed and with a browser drag held. Visible feedback and native logs agree:
disarmed, idle, no recovery, no sampled input down. The native pulse completed
before blur; guest foreground loss mid-pulse remains unqualified live.

Full gate passed: 364 C# tests, 174 Python tests including 18 async panel
scenarios, Lua contracts, zero-warning Release, native smoke and repository
checks. Evidence: `artifacts/validation/20261020T173733Z-c655e828`.
Two gate failures also led to narrow native-capture process-exit hardening and
a disposable-process initialization fix. The deployed control agent is unchanged;
the restarted host (PID 43936) serves the revised panel using
`artifacts/native-usability-20261020/host.json`.

Next useful work: longer human comfort checks if needed, then information
discovery. Do not repeat the basic camera/zoom or real window-blur baselines
without a new reason. Continuous guest-held camera streaming would require a
separate bounded lifecycle design; it is not necessary for the current trials.

## Native control usability and session cleanup

The [usability pass](validation/native-control-usability-2026-10-20.md)
inspected the actual RIFT bindings and camera settings without changing them.
Browser trials demonstrated strafe, both camera drag modes, reversible zoom,
release cleanup, horizontal-wheel suppression, and preserved action feedback.
Computer Use could inspect VMware but did not reliably deliver menu input;
the repository-owned VM-specific console helper completed that inspection.

Fixed pending ARM/STOP races, duplicate arm submission, stale queued input and
responses, late Pointer Lock grants, surface-focus release, shortcut handling,
and status overwriting action evidence. The guest now invalidates old review
authorization on STOP, recovery, and replacement capture. A live page-exit
failure led to keepalive on every STOP; the corrected trial acknowledged STOP
0.481 seconds after ARM and left the guest disarmed with no sampled input down.

Full gate passed: **364 C# tests**, **174 Python tests** including 14 executable
async panel scenarios, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release,
native smoke, locked restore, formatting/module checks, and deterministic
replay. Evidence: `artifacts/validation/20261020T161445Z-98004030`.
The deployed native executable matches that gate. Active configuration:
`artifacts/native-usability-20261020/host.json`; receiver
`d26484f41ed34c9da6911d465530bdf9`. Final status: connected, disarmed, idle,
no recovery or sampled input down. Temporary bootstrap stopped.

Next authorized work can resume information discovery. Longer human usability,
live window-blur qualification outside the in-app tab-switch behavior, smooth
continuous camera tracking, numerical camera calibration, other builds, and
fullscreen remain open. Do not repeat completed basic movement/zoom trials
without a new reason.

## Native wheel zoom fixed and verified

The [zoom validation record](validation/native-zoom-2026-10-20.md) closes the
remaining wheel-control gap in the identified RIFT-Lab-1 windowed session.
Joey confirmed physical-wheel zoom works. The old native insertion path still
produced no visible zoom; targeted `WM_MOUSEWHEEL` dispatch produced reversible
zoom out/in on the final deployed binary. Four static ground patches returned
to their original pixel positions after the opposite notch.

The native agent checks exact process/window/foreground/client geometry,
dispatches once with a 100 ms timeout, and never retries an unknown result.
The panel reports dispatch separately from observed zoom. Existing movement,
camera drag, review/arm, and release behavior remain intact.

Full gate passed: **358 C# tests**, **173 Python tests**, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native smoke, locked restore,
deterministic replay, formatting and module checks. Evidence:
`artifacts/validation/20261020T131932Z-22b4af08`. The deployed executable is the
exact full-gate published binary. Native host/guest remain connected, disarmed,
idle, with no pending release or sampled input down; bootstrap server stopped.

Next useful work is sustained human panel usability and further information
discovery. Numerical camera calibration, other builds/fullscreen, optional
Pointer Lock outside Codex, and hard-crash cleanup remain unqualified. Do not
repeat completed S/A/D or wheel baselines without a new reason.

## Earlier native control follow-up: browser drag and timing

The [follow-up record](validation/native-vm-controls-followup-2026-10-20.md)
documents the latest improvement set. The Codex browser rejected Pointer Lock;
the panel now defaults to bounded click-and-drag camera input, which reached
the guest and visibly changed the view. Pointer release cancelled the final
pulse, released the button, and left its result visible alongside release
feedback. Camera modes, review countdown, expiry feedback, and mode-change
stops are explicit.

The hold budget now includes setup after the first press. Completed 100 ms
trials measured 101.97–113.96 ms button intervals in this small sample.
Cursor preparation avoids unnecessary warps, rejects existing button-down
state or insufficient client space, and never restores the cursor after input.
Status includes read-only Windows input-state diagnostics.

Final full gate: **336 C# tests** (274 portable, 62 Windows), **172 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting and module checks.
Evidence: `artifacts/validation/20261020T125211Z-934ab6e9`; 251 links checked.
The final deployed executable matches the full-gate published binary.
Native host/guest remain connected and disarmed, with no pending release or
sampled input down. Temporary bootstrap service is stopped.

At this earlier checkpoint, wheel zoom was unresolved. The subsequent physical
baseline and native message-path fix are recorded above. The historical
follow-up record preserves the earlier negative observations.

## Initial native supervised movement and camera controls

The [native control roadmap](planning/native-vm-control-roadmap.md) is
implemented with recorded validation limits. The repository now owns its
guest-local input agent, persistent host connection, operator panel, CLI,
bounded executor, and VM bootstrap/capture helper. The recommended control path
does not import or run original RiftReader source. See
[usage](reference/native-vm-controls.md) and the
[live record](validation/native-vm-controls-2026-10-20.md).

On RIFT-Lab-1, reviewed trials demonstrated S/A/D, W+Q, left camera orbit, and
right yaw/pitch; an earlier native trial demonstrated W. Emergency stop
interrupted a 250 ms action, acknowledged in 39.19 ms, and released the key.
Idle host reconnect cleared an armed session. The final host/guest remain
available, disarmed, with no pending release. The panel was opened for review.
V1 receiver/observer and the temporary bootstrap server are stopped.

Wheel zoom remains unverified despite successful insertion in both directions.
One camera-button interval missed the proposed ±20 ms timing target.
Numerical camera calibration, fullscreen capture, sustained human Pointer Lock
usability, and hard-crash cleanup are unqualified. Next priority is a human
panel usability pass and binding-aware wheel diagnosis, then further field
discovery. Do not repeat the completed S/A/D baselines as discovery.

Final full gate passed: **315 C# tests** (271 portable, 44 Windows), **168 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, zero-warning Release build, native
smoke, locked restore, deterministic replay, formatting/module checks, and
246 relative links. Evidence: `artifacts/validation/20261020T121433Z-4e11a754`.
The final published hash matches the guest timeout-fix binary. A 35-second idle
review and brief panel keyboard/release test passed after deployment.

## Earlier supervised movement-control parity work

The [movement-control parity roadmap](planning/movement-control-parity-roadmap.md)
now has separate successful 100 ms S/A/D trials on Joey's selected RIFT-Lab-1,
with fresh receiver/observer identity, reviewed screenshots, release delivery,
and advancing independent API samples. S changed position; A/D produced opposite
visual viewpoint rotations with unchanged XYZ and confirmed turn bindings.
Heading/angle remains unmeasured. The controller is stopped with no pending
release. See the [October 20 record](validation/movement-parity-2026-10-20.md).
Do not repeat these baselines on resumption; reacquire current identity for any
new experiment. Next useful discovery remains changed-state health/resource
capture using the completed targeted-audit tools.

October 20 full gate passed: 273 C# tests, 121 Python tests, 108 Lua assertions,
22 Lua/C# cases, zero-warning Release build, native synthetic smoke, locked
restore, replay, formatting/module checks and 229 links. Evidence:
`artifacts/validation/20261020T105058Z-83f84b40`. Older verification sections
below describe their own earlier milestones.

## Direction and completed scope

RiftReader2 is an independently developed hybrid Lua addon plus modular .NET
application. Keep it a practical personal research tool. V1 remains unchanged
reference material and selected lab infrastructure. See [architecture](architecture.md)
and [roadmap](planning/implementation-roadmap.md).

Steps 0–6 and the additionally requested memory-discovery feature are implemented
within their recorded limits:

- Five production modules, pinned .NET 10, strict configuration, and one validation gate.
- Content-pinned replay, motion analysis with explicit gaps, and durable output.
- First-class Lua producer/C# decoder with shared executable contracts.
- Nonce-bound addon transport with freshness and session/reload invalidation.
- Bounded read-only native capture and a durable field catalog/qualification workflow.
- One supervised movement/turning pulse with reviewed screenshots, exact VM/game
  binding, stop/release recovery, and before/after API evidence. See
  [experiment usage](reference/guarded-experiments.md).
- Read-only memory maps and bounded snapshots, typed value/pattern searches,
  snapshot comparisons, RVA-rooted reverse pointer discovery, and live chain
  resolution. Uses existing modules, no new projects or packages. See
  [memory discovery](reference/memory-discovery.md).

Git author remains repository-local `360madden <360madden@gmail.com>`; branch
`codex/modular-foundation`. Use Git for current commit/worktree state.

## Latest verification

The earlier native-player-field discovery pass was **incomplete at Joey's
handoff request**; a subsequent live restart and field sweep is recorded below. One bounded live capture resolved `[rift_x64+0x32E0200]` and found
float32 XYZ at owner offsets `0x320/0x324/0x328`, within 0.004 of fresh typed Lua
values in one stationary sample. The historical nearby health offsets failed.
A supervised 100 ms forward pulse completed with release and newer API
coordinates, but no post-movement native capture or game restart was performed.
No gameplay field was qualified. See the [resumption record](validation/native-player-fields-2026-10-19.md)
for exact identities, evidence, candidate paths, and the next steps.

This pass changed documentation only; the temporary capture helper and raw
evidence remain under ignored `artifacts/field-discovery/`. The original DVD is
restored and connected; the temporary GuestObserver, host receiver, and watcher
were stopped. RIFT remains logged in. Documentation/link/Git checks apply to
this handoff; the full application gate below belongs to the preceding build.

The final combined gate passed **238 C# tests** (225 portable, 13 Windows),
**21 Python tests**, 108 Lua assertions, 22 actual Lua-to-C# cases, locked restore,
zero-warning Release build, formatting/module checks, deterministic motion and
catalog replay, the published native smoke, and 198 relative links before final
handoff edits. Evidence: `artifacts/validation/20261019T052736Z-c7039e2e` and
`artifacts/memory-validation/full-gate.log`.
All 196 links in the final documentation passed a separate check.

The [memory runtime record](validation/memory-discovery-2026-10-19.md) covers the
same exact published bundle as the full gate, SHA-256
`17A1C90E5EB5864F314DE9B6218DA6FB685A15E910E020B3CCE8029EBF63B9EC`.
In RIFT PID 11620 it mapped 8,281 readable regions, captured/repeated the header,
retained unreadable-memory failures, rejected wrong epoch/build and overwrite,
and followed the PE ImageBase pointer at RVA `0x1B8` back to `MZ`. All four
portable discovery commands processed these exact runtime snapshots. This is a
real RIFT acquisition/pointer check, not a player-object or gameplay-field claim.

The [experiment record](validation/experiments-2026-10-19.md) covers a supervised
100 ms `w` pulse with key-up, matching identity, and newer ReaderBridge API
coordinates, plus identity/duplicate rejection and stop-before-input. The final
adapter also has tested retry handling for transient post-release unavailability;
the successful live trial's retained hashes identify the preceding adapter revision.

Independent review checked native rights, identity/failure provenance, strict IO,
bounds, pointer/work limits, and stop/release behavior. The original DVD is
restored, temporary observer/receiver processes are stopped, and RIFT remains
logged in. No V1 source or global configuration changed.

Earlier records separately cover [addon recovery](validation/restart-recovery-2026-10-18.md),
[native process restart](validation/native-capture-2026-10-19.md),
[fixed wall replay](validation/wall-replay-2026-10-19.md), and
[catalog semantics](validation/field-catalog-2026-10-19.md). They identify their
own inputs/builds and do not requalify this new bundle for every recovery scenario.

## October 19 resumed evidence review

Two later **previously retained** native reports (05:57 and 06:00 UTC) were found
in ignored `artifacts/field-discovery/runs/`, after the earlier 05:45 capture.
Both independently reread the root and show post-movement XYZ within 0.004 of
fresh typed Lua values in the same RIFT process/build as the original capture.
A fresh 08:22 UTC host receipt confirmed the same live game process and Lua
coordinates, but did not include a fresh native capture. No new movement or
RIFT restart was performed in this review. The VMware CD/DVD configuration
currently selected the field-lab ISO; this was observed, not changed.

The new [native position evidence reviewer](reference/native-field-evidence.md)
replays all three reports, pins source bytes/hashes, checks exact game/observer
identities and root-owner bytes, measures XYZ agreement, and distinguishes the
first capture's **unrecorded** root stability reread from the later verified
ones. Its output is `movement-consistent-stability-unverified` with exactly one
process epoch, `candidate-only`, and no restart/update qualification. Local
review: `artifacts/field-discovery/candidate-review-20261019.json` (ignored).
The reviewer has a dedicated regression suite and is included in the full
`validate.ps1` gate. See the [updated live handoff](validation/native-player-fields-2026-10-19.md).

The resumed full repository gate passed on October 19: 238 C# tests,
40 Python tests (including 19 for the new reviewer), 108 Lua assertions,
22 Lua-to-C# cases, zero-warning Release build, locked restore, native
smoke, deterministic replay, formatting checks, and 208 relative links.
Evidence: `artifacts/validation/20261019T083341Z-16701712` (ignored).

## October 19 live restart and health candidate sweep

An additional bounded guest capture at 08:54 UTC used the existing read-only
field-lab executable and fresh typed Lua in game PID `11620`. The report at
`artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json`
(SHA-256 `2D2120DCC8E2986BB284F3401B6EBBB7E49BBC0790E3B4AD1E3A144910B676B9`)
scanned 1,073,741,824 bytes with zero read failures and 126 matches for health
18,208 (119 int32, 7 float64). It hit the byte limit and is not exhaustive.

The guest game then exited via its ordinary in-game Exit Game menu; a fresh
GuestObserver report showed zero game processes and foreground Glyph. Glyph
restarted the same RIFT build without sign-in, and Atank re-entered the world.
The new game PID `8356` started `2026-10-19T09:11:06.5141458Z`
(UTC ticks `639279978665141458`), replacing PID `11620`
(UTC ticks `639279813293755454`). The Lua observer stayed alive and its
typed generation reset from 1 to 2, with fresh advancing values.

A second independently bounded read-only native capture at 09:13 UTC resolved
the same root RVA `0x32E0200` with a successful root reread, now to a
**different** session owner `0x220BF9406A0` instead of `0x216ECFE06A0`.
The resulting XYZ `(7296.40381, 876.31891, 3054.37769)` matched fresh
Lua `(7296.39990, 876.32001, 3054.37988)` within 0.004. The source is
`artifacts/field-discovery/runs/4ebbe9ee91c148c4a05466ebb9049d25/report.json`,
SHA-256 `07DB7E70D98EA102FE0939A9CD89C1153FA8A0D0318B5E431B90D3BC3766415F`.
This is **observed same-build cross-process-epoch locator recovery**, not
semantic qualification or update survival. A separate invalid-old-epoch
request was not run in this session.

The new capture scanned 977,739,776 bytes with zero read failures and stopped
at 128 exact health matches. The tracked
[native field reviewer](reference/native-field-evidence.md) now also validates
recorded health-hit contexts and clusters and distinguishes same-build
cross-epoch candidate evidence from actual qualification. The health review
produced 111 clusters and no authoritative health/resource locator. Health
was 18,208/18,208 and raw power 100 before and after both scans; there was
no changed-health reference to distinguish cached values. Full raw captures,
reviews and screenshots stay under ignored `artifacts/field-discovery/`.
See [the chronological validation record](validation/native-player-fields-2026-10-19.md).

The full repository validation passed again on October 19, including **238 C#
tests, 58 Python tests** (37 native-field reviewer tests), 108 Lua assertions,
22 actual Lua-to-C# contract cases, locked restore, a zero-warning Release
build, published native synthetic-process smoke, deterministic replay,
formatting/module checks, and 210 relative links. Local gate evidence:
`artifacts/validation/20261019T091919Z-2dba17e0` (ignored). No V1 source or
RIFT executable was modified; the RIFT-Lab game was relaunched normally.

## October 19 offline cross-epoch health structure comparison

The new `--compare-health-hits` replay in
[the field evidence guide](reference/native-field-evidence.md) checks the
existing 08:54 and 09:13 raw reports against each other without touching the
live game. Both reports have different PID/start epochs but the same build,
player, and unchanged typed health/max `18208/18208` and power `100`.
Only validated int32 marker layouts are compared; no absolute heap address
is treated as a portable locator.

Of 104 and 111 recorded health-hit groups, **10 and 7** respectively
contained informative multi-marker layouts. Exactly one layout recurred:
**8 instances before restart and 5 after** with repeated health, power and
independently observed level `45` values at the same relative offsets.
That multiplicity argues against assuming any instance is a unique field.
The ignored replay report is
`artifacts/field-discovery/health-cross-epoch-shapes-20261019.json`
(SHA-256 `6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD`).
It records `candidate-only`, no tested changed-state values, and no
qualified restart or update survival for health. The comparison is bounded,
deterministic, and covered by focused tests. No live game changes occurred.

The full October 19 gate passed with 238 C# tests, **73 Python tests**,
108 Lua assertions, 22 actual Lua-to-C# contract cases, a zero-warning Release
build, native synthetic smoke, locked restore, replay, formatting checks, and
212 relative documentation links. Evidence:
`artifacts/validation/20261019T120612Z-21633586` (ignored).

## Limits and next useful work

No native position, health/resource, combat, cast, cooldown, or ability field is
qualified yet. Memory hits and chains are candidates. Use Lua/API observations
as reference, then record field meaning, units, locator/build applicability,
contrary evidence, and restart/update checks in the [catalog](reference/field-catalog.md).
The next task is to gather controlled **changed-state** health and raw resource
observations, capture only relevant regions, and distinguish true fields from
copied/cached structures. Measure reacquisition over additional restarts and
separately check old-epoch request rejection for the specific field chain.
Always reacquire process/session/build identity; never reuse heap addresses.
Update survival requires a different executable build and independent evidence.
Use the saved replay and catalog rather than repeating completed baselines.

Snapshot reads are sequential, capped at 64 MiB per explicit request, and are
not atomic. Pointer discovery searches selected bytes, 8-byte-aligned x64 slots,
main-module roots, depth up to four, and nonnegative offsets up to 4,096. Results
report truncation. Encoded pointers and other-module roots are not supported.
A process restart requires fresh inspection and explicit requests; build changes
require separate validation. Large scans have not been benchmarked in RIFT.

Experiments retain timing uncertainty: host/guest skew is unmeasured, so their
API samples support coarse before/after comparisons, not precise motion timing.
Mid-hold stop, hard crash, snapshot restore, and update recovery remain unqualified
in RIFT. Sending key-up is not proof of game key state. Dedicated navigation,
combat, and casting automation remain outside this repository.

The foundation implementation is complete; the native position candidate has
same-build restart evidence, but semantic catalog qualification, health/resource
discovery and update recovery remain unfinished. Keep versioned files; there is no
measured reason to add the roadmap's optional SQLite index. Routine fixtures,
field entries, and documentation can use cheaper models with the same gate;
identity, native IO, pointer semantics, and input control still warrant strong review.
