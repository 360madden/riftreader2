# Physical build-1179 selected-target profile: one-command native correlation

**November 21, 2026, ~4:06 PM EST · AMD-DESKTOP · physical RIFT x64 only**

## Delivered retrieval capability

The new read-only `scripts/physical_selected_target_profile.py` reuses **existing** exact-build native readers to produce one bounded, internally cross-checked current-selected-target candidate:

1. Read the guarded current selected target, including health, power, numeric level and XYZ candidates.
2. When a target is present, independently read a two-sample selected-position burst (100 ms apart).
3. Resolve its exact decimal 64-bit unit key through the existing native keyed unit-name reader.
4. Read the guarded selected target again, requiring the same player, target **key and entity address** at both endpoints, exact process/start/build identity, ordered acquisition times and a total source span of no more than 30 seconds.
5. Reopen the original reports and check their **SHA-256 receipts**, preserving the four source files in one newly created local artifact directory. A stable name is displayed only when the keyed name has the same entity address; an unstable level or drifted XYZ is withheld. No-target baseline uses only two selected-target reads and reports no invented name/vitals.

It is **sequential** sampling, not a single atomic snapshot. An A→B→A change between reads is still unknown; therefore the report explicitly states `selectedIdentityAtEndpointsMatched=true` but `intermediateSelectionHistory=unavailable`. Its `hostilityStatus` and `combatSuitabilityStatus` remain `unqualified`, and `gameplayInputSent=false`.

### CLI

PowerShell 7 in `C:\work\riftreader2`, after a fresh physical game identity preflight:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\physical_selected_target_profile.py --expected-host AMD-DESKTOP --physical-pid CURRENT_VERIFIED_PID --output-dir artifacts\NEW_SELECTED_TARGET_PROFILE
C:\Python314\python.exe -B scripts\replay_physical_selected_target_profile.py --profile artifacts\NEW_SELECTED_TARGET_PROFILE\profile.json
```

The **independent offline replay** command reopens all original native sources and their SHA-256 receipts, re-runs the existing strict 1179 projection decoders, reconstructs the positional identity/time brackets and refuses altered, re-ordered, substituted or missing source files. It does **not** need a running RIFT process.

### Actual physical result

The current exact physical process was verified on AMD-DESKTOP: PID `37676`, start ticks `639308565554559088`, executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.

`artifacts/physical-target-profile-20261121-1607-p37676/profile.json` completed with exit **0** and was independently replayed from its original four source files with exit **0**.

| Source candidate | Result |
|---|---|
| Selected unit ID | `u800000009A0026CE` |
| Base name | `Argent Glade Guard` (native template cache candidate) |
| Level | **10**, unchanged across the two guarded target reads |
| Health | **522/522** native calculated candidate |
| Energy | **100/100** native calculated candidate |
| XYZ | **(6046.1846, 832.3002, 3125.9717)** |
| Maximum adjacent sequential position delta | **0.0000463** native units |
| Selected unit key/entity | Identical at beginning and end |
| Total observed source acquisition span | **1.067764 seconds** |
| Target-change history inside the interval | **Unavailable** |
| Gameplay input / memory writes | **None** |

Ignored original evidence SHA-256 values:
- Profile: **2345BB4B3608F7A2839DC371896BE916990B18DA911E8A87DF55A1473F16258C**
- Selected before: **BFDAF9BA01B1BA50A5785C89CA05A651300FE883053C771D411628C9F2241809**
- Selected position: **54AF71353952AC2BA0EB76A501039B7229205CA96083273503AD0C56BD35C6C7**
- Keyed name: **FCED9C479C96D2FD4B92F35384EFC1273C23D2F54804CC9CD2D0F687768BF2E3**
- Selected after: **2E50AB1EC7FE06E9644B7D560837E14B407CC184D8774512F0B970CDC6ADAE63**

## Verification

Focused Python selected-target-profile acquisition, independent source replay, original selected-target admission, and nearby native-unit suites ran **53 tests: 52 passed, 1 skipped**. The skipped case exercises Windows symlink creation, unavailable without required local privileges. The native .NET selected-target decoder was already built and tested in the immediately preceding recovery milestone (1,945/1,945 full solution tests); this small follow-up reuses that reader without modifying its C# implementation.

The new profile is useful for read-only hunt/route target assessment and for future target A→B→A observations. **It does not establish Lua/UI level or HP agreement, actual target change history, hostility, elite/group status, path clearance, attackability, or authority to cast or move.** No addon deployment, RIFT restart, UI reload, focus change, game input or sibling-repository modification occurred.
