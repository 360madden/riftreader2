# RiftReader2 handoff — October 25, 2026 (native XYZ direct sampling)

**Purpose:** Resume Joey's RiftReader2 work in a later ChatGPT conversation without mistaking staged code for live RIFT proof. This is a durable, tracked checkpoint, not a request to replay stale VM actions. All UTC timestamps are explicit; otherwise use America/New_York.

## Read this first

- **Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`. Use Workbridge for the user's Windows host; current bridge seen as `0.16.3-dev`, root `C:\work`. Read repository `AGENTS.md`, `docs/status.md`, and [known-position sampling](reference/known-position-sampling.md) before changes. `C:\rift modding\RiftReader` is V1 **reference-only**.
- **Verified pre-handoff HEAD:** `7aab1f3ffc845baf50716f03bf8bae1b75da9eb8`. Workbridge Git status at handoff preparation was clean (`## codex/modular-foundation`). A handoff commit after this paragraph will become the new HEAD; inspect history rather than assuming an old hash remains HEAD.
- **Authorization:** Repository step 6 allows supervised, bounded movement/turning and read-only RIFT memory discovery. Do **not** attach a debugger, inject/write native process memory, modify V1 or REA, or run a competing VM controller. Use exact session/build identity and preserve originals. Commit verified meaningful milestones without unrelated files; Joey specifically approved timely progress commits.
- **Current objective:** Make already-known player XYZ *operationally easy to read*, leaving live source/motion qualification and restart/update resilience separate. Avoid re-running a full heap/Lua scan solely to get known-build candidate coordinates.

## Verified result and three new commits

1. `e1d85cbad7f935ea0075692ce45a56b964f0f5b6` — **direct read-only native XYZ sampler** in .NET 10 `RiftReader2.Live`, `sample-position`. It locates exactly one fresh `rift_x64` process, gates the exact executable SHA, resolves the known module-rooted pointer afresh per sample, obtains 816 owner bytes, decodes finite float32 XYZ at `+0x320/+0x324/+0x328`, and emits per-sample compact JSON lines plus a no-overwrite report. No broad scan, process writes, game input or native field promotion.
2. `15c823b250cd26a38002139f29dbc15342d47f9c` — **coordinate changes in the feed**. Each consecutive successful sample adds XYZ deltas, 3D distance and monotonic time; report adds a 0.1-unit candidate-change hint, first-to-last distance, largest excursion and step. Tests cover coordinate jitter, return-to-start and failures without reuse of stale values. A change is *native candidate bytes changed*, **not proof that a player moved**.
3. `7aab1f3ffc845baf50716f03bf8bae1b75da9eb8` — **guest delivery staged, not executed**: new isolated `scripts/serve_guest_position_sampler.py` with exact-byte pinned `executable` and `profile` bundles and host-only dry run by default. It reuses the older delivery HTTP handler but does **not** edit its historically SHA-pinned source. Separate route, guest IP allowlist, bounded one-use Pythonw-only server and ignored receipt directory. No live server was opened.

Key tracked files:

- `config/position-candidate-profile.json`
- `src/RiftReader2.Domain/PositionCandidateProfile.cs`
- `src/RiftReader2.Application/PositionCandidateSampler.cs`
- `src/RiftReader2.Infrastructure/NativePositionProfileFile.cs`
- `src/RiftReader2.Live/PositionSampleCommand.cs`
- `tests/RiftReader2.Tests/PositionCandidateTests.cs`
- `scripts/serve_guest_position_sampler.py`
- `tests/test_serve_guest_position_sampler.py`
- `docs/reference/known-position-sampling.md`

### Verified build and observed coordinates

- **RIFT executable SHA-256:** `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`
- **Candidate root:** main-module RVA `0x32E0200`, one root dereference, exactly **816 terminal owner bytes**, float32 XYZ at `+0x320/+0x324/+0x328`.
- **Last independent live native original:** two Oct 24/25 V16 acquisitions had XYZ `(7461.19921875, 863.8524169921875, 2977.061767578125)`, terminal owner `0x211D37C0010` **for that specific process epoch**. The earlier typed Lua source was `(7461.1997070312, 863.84997558594, 2977.0598144531)`. Axes match numerically within 0.0025, but the source was about **2.4 hours older** and stationary. State is **`candidate-compatible` / `candidate-only-not-synchronized`**, not a qualified live player field. See [first live evidence](validation/native-pointer-xyz-first-live-2026-10-24.md).
- The old absolute owner pointer, PID and start ticks must **never** be blindly reused after restart or patch.

### Code verification

Last complete Windows PowerShell 7.6.8 gate:

- Command: `& 'C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.8.0_x64__8wekyb3d8bbwe\pwsh.exe' -NoProfile -File scripts/validate.ps1` from `C:\work\riftreader2`.
- **Exit 0** on the handoff revalidation at `2026-10-25T09:36:44Z`. **450 .NET 10 tests** (311 core + 139 Live), **669 Python**, 108 Lua checks, 22 Lua-to-C# contract checks, published-native synthetic-host smoke, formatting and **502** doc links.
- Evidence: ignored `artifacts/validation/20261025T093540Z-12ff745f`.
- Focused new position tests: 9/9; new + legacy + recovery transfer tests: 34/34.
- Read-only preflight of both new transfer choices passed: exact byte length/hash, route, peer. **No live download or guest execution is proven.**

### Exact-pinned guest delivery ingredients

- Validated single-file executable: ignored `artifacts/validation/20261025T084650Z-2e1829ff/native-published/RiftReader2.Live.exe`; size **74,349,475**, SHA `5CA4A6EA9B8904C4987315AA2AE287B3F32B4BB8ED27F5BA951D4D704682C07B`.
- Tracked profile size **395**, SHA `FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8`.
- Host-only no-listener checks: `python scripts/serve_guest_position_sampler.py --bundle executable` and `python scripts/serve_guest_position_sampler.py --bundle profile`.
- Any future `--serve` requires separately arranged, signed-in Windows `pythonw.exe` outside Workbridge's short-lived job, fixed VMnet8 `192.168.56.1:8765`, only guest `192.168.56.128`. Serve one bundle per short-lived process; do not overlap. Guest must independently verify SHA before executing in a **new** install location; do not overwrite the previously installed reader.
- **Important regression:** Initial attempt to add these bundles to `scripts/serve_guest_native_scout.py` caused the full suite to fail because `scripts/run_guest_inline_service.py` pins that script's exact SHA. That change was completely undone. The isolated helper was implemented instead, and the **full** suite then passed. Do not casually edit the legacy SHA-pinned scripts or update historical pins to mask this guard.

## VM operational state — read-only observation, not current truth

At **2026-10-25T09:00:23Z**, authenticated read-only `scripts/control_client.py --config artifacts/native-usability-20261020/host.json status` returned:
- V16 exclusive coordinator **ready/connected**, supervisor running and VM console held; guest `armed=false`, `busy=false`, `recoveryRequired=false`, no sampled held inputs, RIFT window foreground.
- Game `rift_x64.exe` PID **6940**, start ticks **639284177321390013**, executable SHA above.
- VMware VMX PID **38044**, log epoch `2026-10-24T05:41:51.833Z`, console port 5905; same VM epoch as previous proof.
- Prior validated coordinator PID **28496**; check a **fresh** process/owner status before using it. **Do not connect to VNC/VM console while V16 exclusively owns it.**
- **V16→V17 successor is only staged** under `artifacts/update-recovery-20261023-01/` (`coordinated-host-plan-v17.json`, `run-coordinated-host-v17.py`). No V16 normal STOP, no V17 launch, no new guest file transfer or new movement has occurred as of this handoff. See [motion reviewer and safety sequence](reference/native-motion-pair-review.md).

## Exact next work — do in this order

1. Reopen `AGENTS.md`, `docs/status.md`, this handoff, known sampling docs, and the V17 motion/VM handover guidance. Get fresh Workbridge Git/status, current RIFT and VMware PID/start/build, coordinated host owner, clean queue, and service-port state. Do not trust the Oct 25 PIDs as current.
2. Prepare and **offline/syntax-test a minimal, bounded guest deployment/smoke sequence** for the pinned executable + profile using existing guarded Windows guest PowerShell console helpers and original transfer handler semantics. Prove both source SHA and exact guest target. Ensure a verified V17 independent successor launch/abort path is ready **before** stopping V16.
3. When handover gates all pass: request a normal V16 STOP; verify actual exit and quarantined/unheld queue, acquire the sole VM console maintenance mutex, review screenshots, deliver the two pinned payloads sequentially to new guest paths, verify guest SHA-256, execute read-only `sample-position` against fresh game identity, preserve independent guest output/original receipts, close shell and restore game foreground, launch V17 independent owner, and re-verify exclusive healthy control. Abort and recover safely on any focus/hash/epoch/ownership problem. Do not run unreviewed movement commands in the guest PowerShell shell.
4. Example **inside the Windows guest** (only after verified installation, choose an output path that does not exist):

   ```powershell
   .\RiftReader2.Live.exe sample-position --profile .\position-candidate-profile.json --samples 30 --interval-ms 500 --output .\position-samples-new.json
   ```

   This is a short candidate feed. A completed report proves read success **not field semantics**. Sample actual cadence may be slower than 500 ms because of process identity checks.
5. Separately obtain near-time typed Lua + native **before and after** originals and use `scripts/review_native_motion_pair.py` with source SHA, clock/stimulus evidence and bounded queued movement pulse under the **actual sole active controller**. No synchronized motion trial has yet passed. Old V16 Lua/native observations are intentionally rejected as chronologically overlapping/stale.
6. Only after a verified live operational fast path, work on **restart re-acquisition** and **patch-version profile registry/re-discovery** as separate code milestones; never auto-apply an unknown-build offset. Preserve raw evidence and commit verified meaningful results.

## Other related project work

The separate discovery compilation/explorer was completed just before the XYZ work: `d62cbc3` plan, `0f31cf6` bounded compiler/filter/sort JSON+CSV+JSONL export, `3ca64a9` browser smoke and handoff. See `docs/reference/discovery-compilation.md` and `scripts/discovery_explorer.html`. Do not regress these features while pursuing the native position test.

## Resume prompt for Joey

> Regain full RiftReader2 context from `C:\work\riftreader2\AGENTS.md`, `docs/status.md`, and `docs/handoff-2026-10-25-native-xyz-sampler.md`. Review the last 10 Git commits and current Workbridge/VM status. Continue the already-implemented, build-pinned direct XYZ sampler's **guarded live guest deployment and read-only smoke test**, then near-time native/Lua movement validation. Do not repeat broad memory discovery just to read the known candidate XYZ. Preserve V16 exclusive controller until a verified normal handover, preserve the old SHA-pinned guest transfer scripts, and commit successful milestones. Be explicit about what is actually live-verified versus only staged.
