# Physical W/Q/E helper-receipt calibration — November 11, 2026

**Host:** AMD-DESKTOP (verified). **Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`. **Game:** physical RIFT x64. **Mode:** entirely offline replay of *previously completed* bounded helper-command receipts; **no new input**.

## Practical result

RR2 now has `scripts/physical_move_key_calibration.py`, a small offline importer that reads the exact JSON stdout of its existing C# `move-key` helper. It validates the reported Windows key insertion, single W/S/Q/E selection, bounded completion and key release, fixed game/player identity, native XYZ before/after chronology, reported XYZ deltas, position-distance consistency and **observed** key-hold duration. It emits an evidence-hashed **candidate-only** velocity vector.

The input receipt was recovered directly from the retained Workbridge command output, copied unchanged to ignored `artifacts/`, and then replayed through the importer. Its output was reread and JSON-validated.

| Key | Actual hold (ms) | Candidate X units/ms | Candidate Z units/ms | Candidate X/Z displacement |
| --- | ---: | ---: | ---: | ---: |
| W forward | 408.2 | -0.006001716 | -0.000751471 | 2.467820 |
| Q strafe left | 519.9 | +0.001073077 | +0.005919038 | 3.128072 |
| E strafe right | 511.1 | -0.001073777 | -0.005921526 | 3.075247 |

**Q/E candidate vector symmetry:** Cosine similarity **-0.9999999991717016**, angle **179.99766799°**, and speed ratio **0.99957247**. These nearly opposite vectors are a useful controlled observation but **not independent proof of game-input consumption**.

**Crucial limitation:** Q and E were recorded around 14:15 UTC, W around 14:54 UTC. Multiple turn experiments occurred elsewhere in this session. These W and Q vectors must **not** be combined as a same-facing steering basis until heading alignment is independently established. The source receipts cannot prove no intervening user input, collisions, or zone/instance changes.

## Evidence and reproducibility

All three live commands were already finished before this import.

| Key | Original command ID | Exact saved source receipt SHA-256 |
| --- | --- | --- |
| W | `rr2-nav-steering-w400-baseline-20261111a` | `1D338F741D8224661FF0BB0992ED792F74F610DE0C1ABE2D3A52EDC3E4F2F7C2` |
| Q | `rr2-live-q500-20261111a` | `6025646F5642363A6777EB6BF74038323870ADE87496690E67384895083EF5E6` |
| E | `rr2-live-e500-20261111a` | `50066FF78A0A31F13302CE5C1F2EE947A06D6214C00452B14EDEAF0F4650788A` |

Retained ignored files:

- `artifacts/physical-move-key-receipt-{w400,q500,e500}-20261111.json` — source receipts, one JSON object each.
- `artifacts/physical-move-key-calibration-{w400,q500,e500}-20261111-validated.json` — separately validated candidate outputs.

Usage from repository root on owning Windows host, with **an already captured receipt**:

```powershell
C:\Python314\python.exe scripts/physical_move_key_calibration.py --receipt artifacts/physical-move-key-receipt-w400-20261111.json --out artifacts/calibration-new-unique-name.json
```

The importer uses the actual `observedMilliseconds` (rounded to integer only for `dx/dz per ms` denominators) rather than blindly assuming the requested hold was exact. It checks raw receipt hash and owns no process-memory, keyboard, screen or desktop-control API. The standalone `physical_calibration.py` path also now accepts 20–1000 ms reference holds; neither path increases the **20–150 ms** waypoint-action cap.

## Verification and limitations

**Focused tests:** `python -m unittest tests.test_physical_move_key_calibration tests.test_movement_controller tests.test_physical_calibration tests.test_physical_waypoint_decision -v`: **39/39 pass**, including malformed/duplicate JSON, incorrect player, bad timing, bad deltas, key delivery/release failures, longer reference holds, and refusing to overwrite a preexisting output.

Two initial implementation errors were identified and corrected during testing: missing repository path on direct Python execution and an overescaped output newline. The first, invalid W result file was retained under `artifacts/physical-move-key-calibration-w400-20261111.json` and **must not be used**; the later `-validated.json` files were checked by JSON parsing.

All outputs have `movementEligible=false`, `actionVerified=false`, `headingQualified=false` and `gameResponseVerified=false`. Their provenance distinguishes one helper-receipt SHA from a pair of independent native burst-file hashes. They are offline data for future calibration, **not an automatic waypoint controller**.

**Next functional step:** Qualify same-facing W/Q movement vectors with new tightly paired actor-angle and native position evidence when live actions are eligible; then wire only that jointly qualified basis into the short bounded waypoint controller. The previously tool-blocked live W-after-A request was not repeated.
