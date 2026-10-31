# Current RIFT client code map — native health (2026-10-31)

Status: **offline static-code evidence only**. No player-owned live HP pointer is qualified on the current build. All addresses below are RVAs relative to `rift_x64.exe`, not absolute process addresses.

## Exact source and reproduction

- Installed 64-bit Windows PE: `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe`, **60,493,640 bytes**.
- Exact SHA-256: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; matches the game build observed on both labs on October 31.
- Offline Ghidra 12.1.2 project (ignored evidence): `artifacts/power-locator-20261025-01/rr2_current_hp_20261031_02`. Complete PE imported using `-noanalysis`, with focused function decompilation rather than a full-program semantic analysis.
- Decompiled health getters: `artifacts/power-locator-20261025-01/current-hp-decompile-20261031.txt` (SHA-256 `FA574639DA01A438564846D97E5D483E5776797365C66BA57FBE0D7E54967292`).
- Decompiled shared helpers: `artifacts/power-locator-20261025-01/current-hp-support-20261031.txt` (SHA-256 `2EC64B367DFEF25AB9EF08FC474FA67EE84D4C9431F0582C2B7CC221BCBF2C48`).
- Independent cloud GNU objdump verified the extracted current-build Health and HealthMax machine-code bytes. The whole executable was **not** uploaded to the cloud; the complete copy remained in the Windows Ghidra project.

## Verified function map

| Function | RVA | Verified behavior |
|---|---:|---|
| Health getter thunk | `0x5E8400` | Adjusts the unit-wrapper pointer and jumps to core. |
| Health core | `0x5E8410` (413 bytes) | Resolves a ref-counted component; reads several fields and calls the HP calculator. |
| HealthMax getter | `0x5E8C80` (59 bytes) | Resolves the same component path and returns its 64-bit field at `+0x50`. |
| Reference resolver | `0x20CF270` (101 bytes) | Copies/increments the smart reference, verifies type-like code `0x2C2`, clears an invalid reference. |
| Reference release | `0x75C7F0` (41 bytes) | Decrements its reference count and clears the temporary handle. |
| HP calculator | `0x133B150` | Receives current/base input, maximum, modifiers and a fractional cap; contains arithmetic and bounding logic. Its complete field semantics need validation. |

From the decompiled HealthMax path, the intermediate handle expression is `*( *(unit + 0x28) + 0x40 ) + 0x640`. The resolver interprets that address as a reference-counted pointer slot, performs a type-like check, and returns a temporary handle; `*(resolved + 0x50)` is the value returned by `HealthMax`. Parentheses here describe **pointer dereferences**, not a validated static module-rooted locator.

The Health core also reads the resolved object's `+0x48`, `+0x60`, `+0x68`, `+0x6C`, `+0x70` fields and references a separate global pointer slot at RVA `0x33DC2B0`. The getter calls the arithmetic leaf at RVA `0x133B150`; therefore the live `health` value must not be assumed to live as a single unchanged `int32` beside a naive max-HP marker. Member names, ownership, and runtime validity remain hypotheses.

## HP arithmetic leaf: bounded static reconstruction

The branch-complete leaf spans RVA `0x133B150..0x133B1D5` (inclusive; followed by `INT3` padding). Its multiplier constant at VA `0x14277F5E8` is the PE `float64` value **`-0.009999999776482582`**. Under ordinary positive maximum-health inputs, an assembly-level pseudocode reconstruction is:

```text
if base_value == 0: return 0
delta = truncate_int64(modifier * (-0.009999999776482582) * clock_delta)
bounded = min(max(base_value - delta, 0), maximum)
if (bounded / maximum) > fractional_cap:
    return truncate_int64(maximum * fractional_cap)
if base_value > 0 and maximum > 0 and bounded <= 0:
    return 1
return bounded
```

At the call site, `base_value` comes from component `+0x48`, `maximum` from `+0x50`, `modifier` from `+0x60`, `fractional_cap` is the smaller of the float32 values at `+0x6C/+0x70`, and `clock_delta` derives from a global float32 at pointer-slot RVA `0x33DC2B0` plus `0x18`, relative to the wrapper's cached `+0x0C`. This is consistent with a time-scaled regeneration/adjustment mechanism and could explain slow visual HP recovery following a mentor-level increase, **but the meaning and units of these fields have not been tested live**. The actual code contains signed-boundary handling that this compact pseudocode suppresses.

## Relevance to movement and resources

- The same native API's `Inspect.Unit.Detail` function exposes `coordX`, `coordY`, `coordZ` keys as documented by the original RIFT API, so those string/call references are the next offline movement-code anchors.
- An earlier build (`7C356C9D...`) validated module RVA `0x32E0200` to player owner and float32 XYZ at owner `+0x320/+0x324/+0x328`, including a guarded movement comparison and a normal restart. **That root is not qualified on current SHA `1935A05C...`.** See [XYZ field catalog](xyz-field-catalog.md) and [native motion comparison](native-motion-pair-review.md).
- Mana, energy, charge and ability/cast code are separate code-map tasks. Finding native CODE locations does not prove player DATA pointer ownership or production telemetry readiness.

## Resource getter byte-slice cross-check

A second pass extracted the **first 96 bytes** at each already-known current-build resource getter RVA from the exact installed `.text` section and disassembled them independently in the cloud. Max-getter return chains were complete within that slice; the longer current getters were **prefixes only**.

| Native getter | RVA | Directly observed code evidence |
|---|---:|---|
| Mana | `0x133DD10` | Reads a resolved component `+0x20`, caches a revision-like `+0x1C`, uses global clock pointer slot `0x33DC2B0`. |
| ManaMax | `0x133DE60` | Reads a resolved component `+0x18` and `+0x1C` during calculation; full return semantics not verified in 96 bytes. |
| Energy | `0x133F2C0` | Reads a resolved component `+0x34` and `+0x20`; uses shared clock slot `0x33DC2B0`. |
| **EnergyMax** | `0x133E450` | Calls resolver at `0x2320200`, takes **int32 at resolved `+0x24`**, releases temporary handle, returns it. |
| Power | `0x133D1C0` | Reads a resolved component `+0x1C` and `+0x18`; uses shared clock slot `0x33DC2B0`. |
| Charge | `0x133DAF0` | Reads a resolved component `+0x28` and `+0x34`; uses shared clock slot `0x33DC2B0`. |
| **ChargeMax** | `0x133E020` | Calls resolver at `0x1CDC680`, takes **int32 at resolved `+0x2C`**, releases temporary handle, returns it. |

The component object/owner, corresponding player identity and any runtime change response remain unqualified. The `+0x24` and `+0x2C` members are reached through **different resolver functions**; they must not be stitched into one generic player structure.

For the next ability/cast pass, installed RiftReader2 scaffolding already uses `Inspect.Ability.New.List`/`.Detail`, `Inspect.Unit.Castbar`, current cooldown fields and `Event.Ability.New.Cooldown.Begin`/`.End` (see [casting readout](casting-readout.md) and [spell dump API reuse](spelldump-api-reuse.md)). Those are **API string anchors**, not yet native-code XREFs. Legacy `Inspect.Ability.Detail` should not be presumed supported.

## Promotion gates

1. Trace the current-build unit identity/owner chain to the component and test a single player under exact PID/start/SHA gates in **read-only** native memory.
2. Compare at least two separately captured, independently sourced HP/XYZ observations; reject replicated UI/cache copies or data unchanged despite controlled source changes.
3. Reuse the existing exclusive controller, screenshot, lease, and freshness gates for any later movement trial. Lab 1's prior eight-minute freshness failure blocks that trial until repaired.
4. Requalify a candidate through a normal game restart, then integrate a version-gated native reader. No live pointer was promoted by this offline decompilation.

No game binary patching, process-memory write, debugger attach, gameplay input, VM restart, or addon edit occurred in this research.
