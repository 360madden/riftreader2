# RR2 physical smoothed-scalar versus actor-angle negative control — 2026-11-11

**Host:** AMD-DESKTOP (machine-local verified). **Repo:** `C:\work\riftreader2`. **Target:** physical RIFT x64, same PID/start/build/player across both states. **Method:** retained, read-only native memory reports and offline comparison; **no game input, no VMware or LEGION access**.

## Useful result

The existing entity-owned four-float `smoothed-scalar` candidate is **not observed tracking the actor-matrix angle** across two separated, stationary player states.

| Raw field | Earlier (02:08 UTC) | Later (16:36 UTC) |
| --- | ---: | ---: |
| Actor matrix planar angle candidate | 111.88233336294573° | 10.228061838975606° |
| Scalar `currentCandidate` | 0 | 0 |
| Scalar `sourceCandidate` | 0 | 0 |
| Scalar `targetCandidate` | 0 | 0 |
| Scalar `factorCandidate` | 15 | 15 |

The **shortest signed actor-matrix change candidate is −101.654271524°**, while all four scalar float32 raw-bit values remained exactly unchanged. Capture gaps between matched scalar and pose reports were **6.470692 seconds** and **10.098707 seconds**, respectively. Owner identity matches: process PID **44888**, start ticks **639299470183328173**, build SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, player key `239816685251645959`, player entity `1779162488336`, scalar component `1779061295856`, actor component `1779162622528`.

**Interpretation:** These four values are poor evidence for a *direct absolute heading* source. That does **not** disprove their role as relative turn-control offsets, smoothing targets, or other state. The actor-matrix angle is itself still **unqualified as player body yaw**. There was no contemporaneous A/D action establishing causal response between these widely separated samples; one state was retained historical evidence.

## Reproducible offline check

New `scripts/compare_physical_scalar_actor_states.py` validates saved scalar raw-bit floats with the existing `fresh_native_smoothed_scalar.validate_report` logic and validates actor-pose reports with `analyze_physical_turn_pair._load`. It checks byte provenance, exact build/process epoch/player entity/component stability, timing, same-state stability, and 15° angle-change threshold, without opening RIFT or invoking any input API.

From PowerShell in `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe scripts/compare_physical_scalar_actor_states.py `
  --old-scalar artifacts/physical-native-smoothed-scalar-0ca4c44693fe4667939b933bda07bd95.json `
  --old-pose artifacts/physical-native-actor-pose-823b891c15ed46798ca5b1b43d644791.json `
  --new-scalar artifacts/physical-native-smoothed-scalar-43b9af6442fe4eea96f1408c376fb4d8.json `
  --new-pose artifacts/physical-native-actor-pose-b11e38ca16214b26b124689c3e694bb8.json `
  --out artifacts/unique-scalar-actor-comparison.json
```

The exact real result was saved (ignored from Git) as `artifacts/physical-scalar-vs-actor-negative-control-20261111-v2.json`. The output retains `headingQualified=false`, `navigationEligible=false`, `gameInputResponseVerified=false`. **24/24 focused Python tests passed** across the new comparator and the existing matrix/turn readers; tests cover unchanged scalar, changing scalar without semantic promotion, insufficient actor change, wrong identity, too-large gap, corrupt bit pattern, and no-overwrite behavior.

## Separate live visual blocker

The current WinApp screenshot operation `rr2navposebeforeA20261111b` created Workbridge quarantine lease `d85dd9f0-93e8-4e09-a8ca-ab996efb8586` with `DESKTOP_TREE_UNSETTLED`. Its read-only recovery classifier on November 11 at 16:35:37Z returned `POSTLEASE_DESCENDANT_UNATTRIBUTED`, **two post-lease descendant candidates**, owner PID **32516** still present, `releaseEligible=false`, and `automaticRetryAllowed=false`. This is **not** the earlier retired November 9 lock; do not blindly reuse that earlier archive authorization. No clearance/override, screenshot retry, desktop input or game input was performed.

**Next productive milestone:** Once the desktop-control quarantine is cleared through separate reviewed maintenance, pair an exact bounded A/D pulse with native pre/post actor-matrix angles and inspected game screenshots. Until then, prioritize already-working native actor/position candidates and do not use the constant smoothed scalar as assumed absolute yaw.
