# RR2 handoff — measured A-turn and hybrid C# heading reader

**2026-11-10 ~03:52 EST.** Authoritative machine: **AMD-DESKTOP**, repository `C:\work\riftreader2`, branch `codex/modular-foundation`. Other untracked source files were preserved.

## What actually works

- ✅ Baseline-first movement plan committed `f26c361`. Follow-up historical yaw candidate probe + 59/59 tests committed **`f45edfa`**.
- ✅ Current exact-build Lab2 player-owned position matrices produced two provisional angles **87.997707527°** (+0x60) and **87.997980806°** (+0x94) with current player XYZ (6981.9404, 845.1422, 3280.7927). These are **matrix candidates**, not yet independently validated actor yaw. The 2026-10-18 old-build V1 yaw locator `QWORD(module+0x32E0200)+0x304` remains a historical reference and was unavailable on the new game SHA.
- ✅ Lab2 pre-turn screenshot captured 08:31:30Z, SHA256 `B877B535E95F235184B5AEE6733BD3A1242BCC5576723FFCCA1F991164C477AF`, at game PID 6228/start ticks 639298670575905950/SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` **at that observation**, not guaranteed current. Capture cleanup verified key release, not gameplay response.
- ✅ Pillow **13.0.0** installed for `C:\Python314\python.exe` in Joey's user site-packages; `where python` and `where pip` place C:\Python314 first, no PATH edit. BMP import/verify and the full `observe_target.py --preview` workflow passed.
- ✅ C# `ControlAgent` now exposes `native-orientation` over the authenticated read-only guest/host channel, with process-epoch/hash checks and native-read lease. Host route `/api/native-orientation`. Commit **`8562d6c`**; **24/24** focused .NET and **17/17** Python host tests passed.
- ✅ New `scripts/fresh_native_orientation.py` retrieves bounded C# matrix candidate snapshots, validates instance/VM/game/timestamps, saves hashed raw evidence. **21/21** combined Python client/XYZ tests passed; pending commit in this handoff.
- ✅ Self-contained .NET 10 release published: `artifacts/native-orientation-release-20261110/publish/RiftReader2.Live.exe`; **118,036,320 bytes**, SHA256 `10F5A282735D3733FEA40D7090BB7A1CD20A6B0114A8C1AC4E1EEEA53CF5B97B`.

## Blockers and truthful limitations

- 🟡 Joey was typing during a prior A-turn attempt; classify it **contaminated/inconclusive**. **No A-turn/game movement input was sent by this continuation.** No independently measured actor-yaw change yet.
- 🟡 At 08:50Z, `stage_managed_guest_release.py --managed-lab lab2` stopped at preflight with **`managed-owner-refused`** from `ensure_controller._verify_existing_owner`. The new binary was **not copied to the guest or activated**, and the running agent/game were untouched. Never force ownership or evade the control guard. Read-only owner diagnostic at 08:53:50Z: UI port **49921**, listener PID **14220**, managed receipt **`ManagedReceiptError: managed-runtime-changed`**.
- 🟡 The running host server and guest controller may still be earlier binaries, so the new endpoint is **offline-tested only**. New source code on disk does not imply a deployed capability. No live benchmark of end-to-end orientation response latency exists yet.

## Next smallest practical steps

1. Read-only investigate Lab2 controller ownership and queue. Resume stage/update only through existing managed maintenance guard when the current owner allows it. Do not repeat the failed request against an unresolved owner.
2. Reload/restart the Python host *through its documented controller lifecycle* and activate the hash-pinned C# guest release after exclusive idle status; verify fresh `nativeOrientationVersion:1` on this exact authenticated instance.
3. Invoke `fresh_native_orientation.query` with **fresh VM/game pins**, record pre-turn candidate and screenshot. In a user-keyboard-quiet exclusive interval, run one reviewed 100ms `A` pulse; verify actual key-down/up separation, release, disarm, zero held keys, and capture post-turn candidate and image.
4. Treat candidate-angle delta as scaffolding, not actor-yaw proof. Use a later camera-only negative control and D opposite-turn when practical; retain Lua addon feedback alongside C# memory and actuation. Replace Lua field-by-field only when the C# stream is useful and stable.

**Primary plan:** `docs/planning/turn-heading-2026-11-10.md`. Raw observation: `artifacts/native-unit-manager/lab2/5e7dea2f257d46a390e4941725aa8242/review.json`. No gameplay input authorization is durable across sessions.
