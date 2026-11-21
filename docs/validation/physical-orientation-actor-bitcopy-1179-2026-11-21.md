# Physical RIFT build-1179: position-orientation and actor-matrix raw-bit agreement

**2026-11-21, ~11:08 EST · AMD-DESKTOP · read-only native evidence**

## Result

The earlier [two-orientation, older-build copy relationship](physical-orientation-actor-bitcopy-two-states-2026-11-11.md) was reproduced on the **current RIFT build 1179** without game input. The existing native orientation and native actor-pose readers independently acquired original exact-source bytes under one physical RIFT process, and the existing offline bit-level comparator confirmed that the **position-secondary matrix at position-component +0x94 and actor matrix at actor-component +0x398 had identical raw float32 bits, 9 of 9 elements**, across two sequential (not simultaneous) source captures.

| Property | Measured/current-build candidate |
|---|---|
| Machine | AMD-DESKTOP (confirmed physical client) |
| PID / process start UTC ticks | `37676` / `639308565554559088` |
| Exact RIFT executable SHA-256 | `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01` |
| Native position secondary `+0x94` | `-29.09768058635053°` candidate |
| Native actor `+0x398` | `-29.09768058635053°` candidate |
| Position primary `+0x60` | `-29.097986418212482°` candidate |
| Primary minus secondary | `-0.00030583186196508905°` candidate |
| Bitwise mismatch | **0/9 float32 elements** |
| Source capture separation | `9.9099174` seconds |
| Repeated read samples | 3 orientation + 3 actor-pose samples, stable within each burst |
| Actor-vs-position planar XYZ residual | `0.0` for all three actor brackets |
| Actor world Y-offset candidate | `-0.06` RIFT units |
| Heading verified? | **No** — `actorHeadingQualified=false` |
| Independent game response verified? | **No** — `independentGameResponseVerified=false` |
| Navigation use authorized by evidence? | **No** — `navigationEligible=false` |

The original, ignored evidence is preserved at:

- `artifacts/physical-native-orientation-20261121-1109-p37676.json` — SHA-256 `5DC38CE317F3B40D6CAA8354F93975A2C8987FAB7464BD939D9D45011D45EF95`
- `artifacts/physical-native-actor-pose-20261121-1109-p37676.json` — SHA-256 `AF6AC25371C6E249C1571B0EF340C1F24557D1C1861BA143BFA185F53DEC3BF4`
- `artifacts/physical-native-orientation-actor-bitcopy-20261121-1109-p37676.json` — SHA-256 `78E1C1B65390CD17D39E42827C3B1129DF1056CE74136A6D91AA4F10A1FE092B`

The current build's raw-bit equality strengthens the **copy/alias relationship** found in the older executable. These are two native data paths, **not independent proof of controllable character yaw**, response to A/D, camera/body separation, write/update latency, or server-authoritative movement. Separated stationary samples also cannot establish a causal turn rate.

## Reproduction

PowerShell 7 under `C:\work\riftreader2`, with a **freshly verified current PID**. The commands below are **read-only**, use a new artifact filename per run, and do not send movement input.

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --read-native orientation --samples 3 --interval-ms 200 --output artifacts\NEW_ORIENTATION.json
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --read-native actor-pose --samples 3 --interval-ms 200 --include-position --include-transform-sources --output artifacts\NEW_ACTOR_POSE.json
C:\Python314\python.exe -B scripts\compare_physical_orientation_actor_matrix.py --orientation artifacts\NEW_ORIENTATION.json --actor-pose artifacts\NEW_ACTOR_POSE.json --out artifacts\NEW_MATRIX_COMPARISON.json
```

The existing focused comparator, actor-pose reader and turn-pair suites passed **22/22 offline Python unit tests** on November 21, 2026. No source logic changes were needed.

**Next meaningful qualification:** Capture a tightly paired, same-PID/build, reviewed A or D action bracket with native pose before/after and independent screenshots, including successful release and a stationary settle, to separate body heading from camera rotation. Do not assume the numerical `-29.09768°` scalar represents verified actor facing without that evidence. No gameplay input, process-memory write, UI reload, restart, or sibling-repository modification was performed for this milestone.
