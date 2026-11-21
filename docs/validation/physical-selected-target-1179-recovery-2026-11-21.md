# Physical RIFT build 1179 — selected-target native retrieval restored

**November 21, 2026, 3:50–3:58 PM EST · AMD-DESKTOP · physical RIFT x64, read-only**

## Working result

Restored the existing **full native selected-target reader and scriptable CLI** on the November build-1179 executable without replacing or adding a game-input controller. Previously the reader and command launcher used historical 1177 hardcoded manager, health-selector, position-selector, numeric-level-selector, owner type and executable SHA values. Other RR2 native readers already carried independently recovered exact-build roots; the selected-target reader now reuses those verified mappings while preserving the previous 1177 route.

Current process identity: PID **37676**, start UTC ticks **639308565554559088**, executable SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**, HWND **3541956**. This identity was freshly verified before the physical acquisition.

A successful **real selected-target** sample returned:

| Candidate | Native value |
|---|---|
| Exact selected unit ID | `u800000009A0026CE` |
| Decimal 64-bit unit key | `9223372039438477006` |
| Target entity address | `2275681213968` |
| Health | **522/522** candidate |
| Energy | **100/100** candidate |
| Numeric level | **10**, alternate-secondary component |
| Raw owner level / raw combat byte | **0 / 0**; do not substitute for presented level/reaction |
| Native XYZ | **(6046.1846, 832.3002, 3125.9717)** |
| Name-seed branch | **unavailable**, deliberately withheld on build 1179 |

The full selected-target source uses anchored current-player and selected-entity relationships and revalidates native bytes; it does not prove that these values are fresh in the game UI, independently API-verified, or valid across a restart.

## Independently acquired matching native evidence

- `artifacts/physical-selected-target-1179-20261121-1552.json`, SHA-256 **3C1BE94F05B24CAAB63826D944F2F13953516C715827CE1DA4C1833C26F127CF** — primary selected-target payload with health/level/energy/position.
- `artifacts/physical-selected-position-1179-20261121-1553.json`, SHA-256 **930709D7E6969BC2E01DBB26E8431CA3186B3DA0A09547BF2D77B21B22F75E38** — two-sample independent selected-position reader returned **the exact same decimal target key and XYZ**.
- `artifacts/physical-selected-target-name-1179-20261121-1553.json`, SHA-256 **5663C09B113D38FDE43C559894F7CFB751C8D088861D638C1FC215793C71D07C** — independent native keyed-template-name reader returned **Argent Glade Guard**, with the exact target entity address above.
- `artifacts/physical-selected-target-wrapper-1179-20261121-1558.json`, SHA-256 **ADC476E5F72D4E9686D16F5055B5A11E63A4D00D6EEEF934845B32EB63FE71AA** — first successful standard RR2 Python wrapper run on the patched build with native read `selected-target`.

**All four source files are original ignored local artifacts**, not published GitHub evidence files. The corresponding committed code and this summary are retained in the repo. The independent native position/name readings were separated by seconds, not an atomic snapshot; equal stored values do not by themselves establish API semantics or action causation.

## Reproduction

With PowerShell 7 in `C:\work\riftreader2`, always use a **new** exact-PID preflight and a fresh unused output path:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid CURRENT_VERIFIED_PID --read-native selected-target --output artifacts\NEW_SELECTED_TARGET.json
```

The wrapper automatically provides the qualified build SHA, requests guarded selected context and position, and projects lossless decimal keys plus candidate level, health/energy/mana and XYZ. On build 1179, the historic internal name-seed branch is explicitly withheld instead of making stale pointer claims; use the independently verified `unit-names` reader for a raw cache-only name candidate.

## Validation and limits

- Debug native reader rebuilt on AMD-DESKTOP: **0 warnings, 0 errors**.
- Focused native selected-target tests: **38/38 passed**.
- Full `.NET 10` Release solution: **1,945/1,945 tests passed** (445 core + 1,500 Live).
- Python selected-target admission, strict decoder and native unit tests: **32/32 passed**.
- Native original-source selected-target projection from the actual physical sample: passed.
- No game input, foreground activation, casting, restart, UI reload, process-memory write or other-repository modification.

**Outstanding qualification:** a controlled real selected-target A→B→A bracket, independently observed API/UI level and HP, passive freshness/restart, hostility and combat suitability. These static candidate values must not be promoted to automated combat or movement authority.
