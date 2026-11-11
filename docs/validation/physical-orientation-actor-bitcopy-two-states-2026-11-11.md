# RR2 physical native orientation / actor-matrix cross-check — 2026-11-11

**Machine:** AMD-DESKTOP independently verified. **Target:** physical RIFT x64. **Mode:** read-only native captures and offline analysis; no movement/input. **Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`.

## Result: repeat of an established static copy relationship at a second orientation

**This is not the first discovery of the matrix copy.** RR2's existing `docs/reference/native-current-coordinate-code-map.md` documents exact-build code path `0x687320`, which copies the player-owned position component's secondary matrix `position+0x94` to the actor component's matrix `actor+0x398`. `docs/workflows/development.md` already recorded one matching physical stationary snapshot near 111.882°.

The new contribution is a **second physical orientation state** (10.228°) and a reusable, source-hash-pinned offline comparison that checks the actual nine float32 bit patterns and component ownership.

| Capture state | Position secondary `+0x94` | Actor `+0x398` | Float32 raw bits equal | Capture separation |
| --- | ---: | ---: | --- | ---: |
| Earlier stationary pose | 111.88233336294573° | 111.88233336294573° | **9/9 identical** | 10.633786 s |
| Current stationary pose | 10.228061838975606° | 10.228061838975606° | **9/9 identical** | 12.704 s |

All checks matched the same process ID **44888**, process start ticks **639299470183328173**, exact game SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, player key **239816685251645959**, and position component `1779061326720`. Actor component `1779162622528` was independently resolved by the actor-pose reader.

The *different* primary position matrix `position+0x60` measured **10.228623878°** in the current capture, 0.000562039° from the secondary. At the older orientation the primary was **111.881677631°**, 0.000655732° from the secondary. These small differences do **not** establish interpolation timing, active heading, camera yaw, or player body facing.

## Reusable check

`scripts/compare_physical_orientation_actor_matrix.py` reuses RR2's existing validated `analyze_physical_turn_pair._load`, not a new memory reader. It requires orientation-before-actor capture ordering, same process/build/player, exact position-component identity and distinct source hashes. It checks all nine raw bits per sample, verifies within-burst matrix stability, and labels a nonmatching capture as **unresolved**, not as proof that the static copy routine is broken.

Example, from PowerShell in `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe scripts/compare_physical_orientation_actor_matrix.py `
  --orientation artifacts/physical-native-orientation-145e7f2c196e4b91893b9cb6622aed07.json `
  --actor-pose artifacts/physical-native-actor-pose-c2917b47db4943b5bf7654c41447ab8b.json `
  --out artifacts/new-unique-source-comparison.json
```

Actual retained JSON output: `artifacts/physical-orientation-actor-bit-alias-20261111.json`. Earlier state repeat: `artifacts/physical-orientation-actor-bit-alias-historical-20261111.json`. These contain both raw source SHA-256 values, process/owner pins, gap and bitwise result.

**Focused checks:** **18/18 tests passed** combining the new cross-source comparator's tests with RR2's existing turn-pair tests. Cases include bit-identical stationary reads, changed-state mismatch, source kind, process epoch, component owner, time gap and no-overwrite output.

## Desktop capture blocker (separate)

During preparation of a new visual A-turn baseline, Workbridge's `desktop_capture_window` returned `DESKTOP_TREE_UNSETTLED` **before any game input**. Exact request `rr2navposebeforeA20261111b`, lock lease `d85dd9f0-93e8-4e09-a8ca-ab996efb8586`, acquired 2026-11-11T16:21:46.827Z; quarantine record created 2026-11-11T16:22:02.159Z with `automaticRetryAllowed=false` and unsettled process tree. The owner stamp PID **32516** is the currently connected Workbridge process, so the previous operator-reviewed archival of an **absent-owner** November 9 lock is not directly reusable as authorization or proof of settlement. **No lock was modified, cleared or bypassed.** Screenshot baseline and new A/D paired turn remain pending.

## Qualification boundary / next practical task

The two native matrix paths are **not independent validators**. Static code and observed raw bit equality make the copy relationship strong, but neither establishes update latency or which field reflects controllable facing. The default output retains `actorHeadingQualified=false`, `independentGameResponseVerified=false` and `navigationEligible=false`. When screenshot/control ownership is restored by reviewed maintenance, obtain one same-epoch A or D pulse with precise native before/after pose, independently inspected screenshots and clean release. Do not infer degrees/sec from separated stationary reads.

No LEGION, VMware, cross-host deployment or source changes to another developer's work occurred.
