# Current RIFT client code map — native health (2026-10-31)

Status: **current-build static code plus a bracketed, untyped Lab1 raw-record capture**. The exact-build type interpretation and guarded calculator are implemented and synthetically tested; a fresh typed two-lab HP read, independent value comparison, passive freshness and restart qualification remain pending. Unless explicitly labeled as a captured session address, addresses below are RVAs relative to `rift_x64.exe`.

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

From the decompiled HealthMax path, the intermediate handle expression is `*( *(healthComponent + 0x28) + 0x40 ) + 0x640`; `healthComponent` is the selected component described below, not the raw entity. The resolver interprets that address as a reference-counted pointer slot, performs a type-like check, and returns a temporary handle; `*(resolved + 0x50)` is the value returned by `HealthMax`. Parentheses here describe **pointer dereferences**, not a validated static module-rooted locator.

The Health core also reads the resolved object's `+0x48`, `+0x60`, `+0x68`, `+0x6C`, `+0x70` fields and references a separate global pointer slot at RVA `0x33DC2B0`. The getter calls the arithmetic leaf at RVA `0x133B150`; therefore the live `health` value must not be assumed to live as a single unchanged `int32` beside a naive max-HP marker. Member names, ownership, and runtime validity remain hypotheses.

## Current native self-key/entity to health component — 2026-11-01 UTC

The current `Inspect.Unit.Detail` routine selects the **health component**, not the raw unit entity, before calling Health/HealthMax:

1. The same native 64-bit unit key is resolved through the manager's `0x6A0040` out-parameter lookup at `0x9B89E8`.
2. RVA `0x9B89F1` loads signed selector-index metadata from **`module+0x2F57850`**.
3. It reads `slot = byte(entity+0x18+index)`; `0xFF` means absent.
4. It reads `componentTable = *(entity+0x78)`, then `R13 = *(componentTable+slot*8)` at `0x9B8A0A`.
5. `0x9B9F18 MOV RCX,R13; 0x9B9F1B CALL 0x5E8400` invokes Health, and `0x9B9F44 MOV RCX,R13; 0x9B9F47 CALL 0x5E8C80` invokes HealthMax.

Position uses **different selector metadata**, `module+0x2F588A0`, through the same entity's component table. The selector globals and slot values must be read dynamically; a shared clock does not imply shared components. The new [coordinate ownership map](native-current-coordinate-code-map.md) documents native self-key root **`module+0x33623E0 -> system+0x360`**, manager root `module+0x33624A8`, the full-key hash lookup, and the read-only probe.

Given selected `healthComponent`, the known raw-read topology is:

```text
ownerObject = read_u64(healthComponent + 0x28)
container   = read_u64(ownerObject + 0x40)
record      = read_u64(container + 0x640)
maximum     = read_i64(record + 0x50)
```

This reproduces pointer traversal only. Resolver `0x20CF270` calls type helper **`0x127303C`** and accepts low16 result `0x2C2`; its exact-build pure-read interpretation is now documented below. Fresh live type/value validation is still required before promoting a record. Never invoke the game resolver, change refcounts, or write the getter's cached revision/clock. Core-wrapper revision/clock are at `healthComponent+0x30/+0x34` (the core's adjusted wrapper `+0x8/+0x0C`); the record revision is `+0x68`. A read-only reconstruction must reject inconsistent mutable fields or handle their semantics explicitly.

Evidence: passed exact-build jobs `rr2-serialized-manager-lookup-code-20261101-01` and `rr2-serialized-manager-hash-health-prologue-20261101-01`, plus retained Ghidra files named above. The ordinary finite calculator reconstruction does not establish exact boundary behavior, stable live ownership, or passive freshness.

## Read-only type interpretation and first raw health record — October 31, 21:43 EDT

The exact-build type path is now resolved statically. This supersedes the earlier unresolved-type note; it does **not** retroactively type-validate the first live record capture.

| Step | Exact-build evidence |
|---|---|
| Record virtual table | The first Lab1 raw record has vtable RVA `0x2C0EE88`; slot `+0x40` contains getter RVA `0x20CCC60`. |
| Descriptor getter | `0x20CCC60` jumps to `0x20E0DE0`, whose initialized return is the address `module+0x355F430`. Never invoke its lazy initializer. |
| Descriptor table | The static initializer assigns vtable `module+0x2C281B0`; its `+0x08` slot contains type getter `0x20F2480`. |
| Type result | `0x20F2480` calls `0x20E64C0` with seed `0x00560291`. That branch returns `0x6A3BBB7C`; low16 XOR `0xB9BE` gives **`0x02C2`**, exactly the resolver's accepted type. |

This is a function-derived constant, **not a type field at descriptor+0x08**. The implemented read-only guard requires the record vtable, descriptor getter, initialized descriptor vtable and type getter to match all four exact-build fingerprints. It does not call game code, initialize metadata, increment references, or accept other untraced derived types.

Passed static source jobs (exact installed SHA above; bounded original PE byte slices, independently disassembled):
- `rr2-serialized-health-type-and-arithmetic-20261101-01`
- `rr2-serialized-health-concrete-descriptor-20261101-01`
- `rr2-serialized-health-descriptor-root-20261101-01`
- `rr2-serialized-health-type-id-leaf-20261101-01`
- `rr2-serialized-health-type-id-transform-20261101-01`

### Retained Lab1 raw observation — not a new current HP reading

The earlier raw-record run completed at **2026-10-31 21:38:12 EDT / 2026-11-01 01:38:12 UTC**, on PID8164/start639290507142219120, native self ID `u035400012FA2D207`. Its status is deliberately still `untyped-record-candidate` because the descriptor/type guard and game-clock capture were added afterward.

| Field | Captured value |
|---|---:|
| Base candidate | 14,830 |
| Maximum candidate | 14,830 |
| Modifier candidate | 13,138 |
| Record / wrapper revision | 9 / 9 |
| Wrapper clock (float32) | 43139.0546875 |
| Fractional caps | 1.0 / 1.0 |
| Ownership anchors and relevant inputs | Stable across the bracketed reads |

Selected health component/owner `0x23D011C1BB0` led to container `0x23D7C711BE0`, record `0x23D51951290`. These are session addresses, never portable locators.

Evidence directory: `artifacts/native-unit-manager/lab1/880371d2ed0c49dcbda28162f3a6e6f5/`.
- `review.json` SHA256 `47572B9CFDA6A87E8724BAC3F6D5236DF30105A839A16E2CCF718EB3751D6760`.
- `health-record.json` SHA256 `EE2667BDD26D8EE3A80BE5BDE243EC8AB205C7C685710F392C43F9473B83E630`.
- `health-type-getter.json` SHA256 `8A10188F11AA400303BB259D4712B3E45374E52B631CBEEECAF44BC1269C6BE7`.
- `anchors-after.json` SHA256 `4B63E776FEB4BBC8A234CC4DEBE490C70558E231F47B656027E0F86BE4B55368`.

### Implementation and validation boundary

`scripts/probe_native_unit_manager.py --lab lab1|lab2 --health-record` now adds the type fingerprints, clock capture, revision/input consistency checks and a finite ordinary-value HP calculation. It retains float32 rounding and the native `-0.009999999776482582` multiplier, rejects nonpositive maximum/out-of-domain values, and preserves the native cap-before-alive-floor ordering. It never updates the game's cached revision/clock. Matching stable inputs yield `calculated-candidate`, not production-qualified HP.

**25 focused synthetic tests passed**, job `rr2-serialized-native-typed-health-tests-20261101-01`, exit0 at 01:43:35 UTC. Independent read-only review found no blocking defect in the declared arithmetic domain or ownership rechecks. Sequential reads still are not atomic and cannot exclude an ABA change.

The new typed Lab2 live command `rr2-serialized-native-typed-health-lab2-20261101-01` was **rejected at the tool approval step**. It was not retried or routed through another tool. No new typed-health live run or screenshot comparison completed. Lab2 raw health has not yet been captured by this path. Await explicit approval, then run Lab2 and Lab1 serially and compare against fresh protected controller captures. Do not relabel the retained raw capture or a synthetic test as that missing live validation.

For screenshots, reuse existing capture/queue primitives, not the full old XYZ workflow guard: `run_xyz_workflow.read_config` pins obsolete coordinate-profile RVAs. Direct `control_client._capture` also does not perform dependency startup by itself; the normal `control_client.run` capture entrypoint does. Acquire against current authenticated identity/epoch, never arm or send input, and wait for watchdog cleanup rather than treating `q.finish` as completed release. No bypass of an occupied queue, foreground failure, or permission denial.

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
