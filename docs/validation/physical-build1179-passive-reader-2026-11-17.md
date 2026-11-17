# RIFT 1179 — independent passive native-reader correlation (AMD-DESKTOP, Nov 17 2026)

**Scope:** RR2-only, physical RIFT, read-only; no game input, window focus, desktop lock, VM, other host, or RRE repository changes. This is a retained candidate-evidence replay, **not** qualified autonomous movement, native-vitals semantics, field passive freshness, or source-to-action causation.

## Fresh identity and reader result

- Independently verified `[Environment]::MachineName=AMD-DESKTOP` on Nov 17, ~10:40 EST.
- Exactly one observed `rift_x64.exe`: PID **77980**, started **2026-11-17T14:11:23.4918403Z**, executable SHA-256 **`DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`**, build `STABLE-1-1179-a-1256672`. These are expired-on-restart observations, not durable PID/absolute addresses.
- Existing `scripts/physical_rift.py` successfully executed **five** host-local, no-input native reader invocations using `--expected-host AMD-DESKTOP --physical-pid 77980`: two XYZ reports, two actor-pose-with-position reports, and one facing report. All returned status `complete` with matching game executable SHA, PID/start ticks, module identity and decimal self-key `239816685251645959`.
- Early window **15:42:30–15:42:49Z**: native XYZ **(683.59796, 850.637, 359.37646)**, matching the independent actor-pose position bracket. Actor planar angle **−34.021612° candidate**.
- Later window **15:43:49–15:45:09Z**: facing entity XYZ **(7206.161, 843.1973, 3117.333)**, independently matched by the next native XYZ and actor-pose position brackets. Facing body-bearing **+42.929211° candidate** and later actor planar angle **−42.929211° candidate** under the prior sign convention; optical camera remained unavailable.
- Exact before/after coordinate difference is **(+6522.56304, −7.43970, +2757.95654)**, planar endpoint difference **7081.677265** source units. **No traveled distance, walking path, continuous stream, cause, world/zone continuity, or speed is inferred across the unobserved gap.** Another session may have acted during this interval. These retained numbers show independent same-epoch candidate *values changed*, not that passive freshness or player semantics is proven.
- A read-only Python replay loaded all five original reports, required exact equality of process/build/module and self-key, and independently compared both actor position brackets and facing position against the paired XYZ values: **5 sources / all comparisons passed**, exit 0. There was no code modification needed.
- Existing focused `unittest` physical reader/facing/position/orientation cases: **65/65 passed**; `pytest` was absent from the base Python 3.14 installation, so the already-supported unittest runner was used without installing dependencies.

## Immutable local evidence (ignored research artifacts, not added to Git)

| Capture | Local file under `artifacts/` | SHA-256 |
| --- | --- | --- |
| Early XYZ | `physical-native-position-e0e4307df801426d8d185aaf3ae589af.json` | `05f42a369e33f8f9b278a02a7f31f307b956360da3469347093ab1368fd696cb` |
| Early actor | `physical-native-actor-pose-ab050fa373924d0cbeb5c87c143f4ff1.json` | `6363cfb7811bc8c23ecd2704d393f4dea3fc20f60438c6faa2e430b9f9ec2de6` |
| Later facing | `physical-native-facing-e9535b231d5246f0b840d44e08202dfa.json` | `2f85935c9955887866fde00fcce72af687222701d491698cca63ee7f54e4638a` |
| Later XYZ | `physical-native-position-2eab463c4d934f8ca5b0e1d2efa2118f.json` | `a39b043fbd1477cfea1feec6e43c35e344d259cb4346d09ff5974a011776eebd` |
| Later actor | `physical-native-actor-pose-1dbaf6912847443d821825a680ca4ac8.json` | `52f9a6fa42e30005e9e9ad9a10cc61114434ca85534a7a0542db64abb6ee8b1b` |

## Discovery intake / next practical test

The RRE-owned handoff was read-only at SHA-256 `419eae3d18d094b56a63798358a1675af34abc89c9072ef270f149c772e68c4e`. Its new-build ROOT-001 `InGame` adapter B receiver and host `+0x6A8` remain **conditional static source only** and not ready to import as a current-player resolver; no RVA was imported. This work independently advances RR2's newly updated physical reader corroboration. Next, capture a separately qualified same-epoch changed-state/Lua comparison and physical RR2R1 nonce only under current-identity and readiness gates. A full hunt → retreat → recover → rejoin still needs its own physical acceptance.
