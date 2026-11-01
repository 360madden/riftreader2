# Current RIFT client code map — health, resources and ability fields (2026-11-01)

Status: **current-build static health/resource/ability code paths plus a historical, untyped Lab1 HP record capture**. HP's guarded type/candidate calculator and an opt-in **untyped** mana/energy raw-record collector are implemented and synthetically tested. No fresh typed two-lab HP read or **any live mana/energy/cooldown observation** was made in this offline pass. Independent UI/API comparison, passive freshness and restart qualification remain pending. Unless explicitly labeled as a captured session address, addresses below are RVAs relative to `rift_x64.exe`.

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
- Current-build mana/energy resource ownership and ability/cast field-builders are now statically traced below, but their record type fingerprints, live values and restart-safe addresses are not qualified.

## Resource ownership and getter paths — exact-build static validation, 2026-11-01

A new, longer extraction and independent x64 instruction-boundary disassembly resolved the current `Inspect.Unit.Detail` **owner** of resource getters. These are verified **code paths** in the pinned executable, **not** a sampled or validated resource pointer from either running lab:

```text
module+0x33623E0 -> playerSystem+0x360 -> native self key
module+0x33624A8 -> manager+0x50 -> full-key hashed entity
health component = entity's dynamic selector (module+0x2F57850)
resource kind = int32(*(healthComponent+0x40) + 0x168)
resource wrapper = *(healthComponent+0x38)
record reference slot = *(resourceWrapper+0x10)
record pointer = *(record reference slot), accepted only through a native type check
```

At `0x9B8A0A`, `R13` receives the selected health component from the entity component table. Function `0x5E36D0` fetches the resource-kind value. The **kind-3** branch (`0x9BA0AC/0x9BA0BA`) takes wrapper `[R13+0x38]` at `0x9BA0C3`; the **kind-4** branch (`0x9BA19C/0x9BA1AA`) takes the same wrapper offset at `0x9BA1B3`. Missing wrapper or other kind must yield **unavailable/not applicable**, never an invented zero or a guess that all resource kinds coexist.

| Native field | Kind | Getter called by Unit.Detail | Resolver / expected low16 type | Record / wrapper inputs |
|---|---:|---|---|---|
| 🟣 `mana` | **3** | call site `0x9BA0D3` → **`0x133DD10`** | `0x1CDC680` / **`0x072A`** | Record rate `+0x18`, base `+0x1C`, revision `+0x20`, maximum `+0x24`; wrapper revision `+0x1C`, cached clock `+0x24` |
| 🟣 `manaMax` | **3** | `0x9BA0FF` → **`0x133E050`** | `0x1CDC680` / **`0x072A`** | Signed int32 record `+0x24` |
| 🟣 `charge` / conditional `chargeMax` | **3** | `0x9BA136` → `0x133DAF0`; `0x9BA162/0x9BA173` → `0x133E020` | Kind-3 wrapper; `ChargeMax` invokes `0x1CDC680` / **`0x072A`** | Charge-specific record fields distinct from simple max; `ChargeMax` reads `+0x2C`, and is not always emitted |
| 🟡 `energy` | **4** | `0x9BA1C3` → **`0x133F2C0`** | `0x2320200` / **`0x072B`** | Record base `+0x20`, maximum `+0x24`, rate `+0x28`, revision `+0x34`; wrapper revision `+0x18`, cached clock `+0x1C` |
| 🟡 `energyMax` | **4** | `0x9BA1EF` → **`0x133E450`** | `0x2320200` / **`0x072B`** | Signed int32 record `+0x24` |
| Other resource getter | Not assigned here | **`0x133DE60`** (earlier mislabeled `ManaMax`) | Different resolver `0x1FE8420` | Not the **kind-3 Unit.Detail ManaMax** branch; no player-field claim |

Both resource resolvers call native type helper `0x127303C`, but require **different** low16 types: mana/charge `0x072A`; energy `0x072B`. The getters manage temporary reference counts and may update cached clock/revision. RiftReader2's external native probe must **never invoke them, touch refcounts or write caches**. Current-value getters involve the shared game-clock pointer at `module+0x33DC2B0`, float32 arithmetic and native constant **`-0.009999999776482582`** (4-byte constant at RVA `0x26B08A4`). Full boundary behavior and read-only type-fingerprint paths for these resource records are **not qualified**. Offset `+0x24` has a meaning only within its particular resolved, type-checked record.

Static evidence, all passed on exact SHA `1935A05C...`: `rr2-serialized-energy-owner-pe-slices-20261101-01`, `rr2-serialized-resource-wrapper-owner-pe-slices-20261101-01`, `rr2-serialized-mana-type-and-maximum-pe-slices-20261101-01`. These byte ranges were independently decoded as x86-64 machine instructions, not inferred from API names. Earlier 96-byte getter prefixes were insufficient to classify `0x133DE60` and caused the **corrected ManaMax mapping**.

### Resource API-key assignments

Saved current-build static key scan `rr2-static-api-text-xrefs-20261031-a` confirms `energyMax` literal RVA `0x26D3C30` at setter `0x9BA204`, `chargeMax` RVA `0x26D3C18` at `0x9BA188`, and `healthCap` RVA `0x26D3BF0` at `0x9BA017`. The new branch/getter disassembly corroborates which wrapper feeds the assignments. This does **not** type-check a runtime object or establish fresh current/max readings.

### Abilities, costs, cooldown and castbar: native field-builders, not yet data owners

The bounded, exact-SHA `scripts/find_native_api_xrefs.py` run `rr2-serialized-native-ability-field-xrefs-20261101-01` passed. Separate longer code extractions `rr2-serialized-ability-code-owners-pe-slices-20261101-01` independently confirmed RIP-relative `LEA R8,[RIP+field string]` at these real instruction boundaries, followed by Lua field-setting calls:

| API field | Literal RVA | Verified native code assignment RVAs |
|---|---:|---|
| `idNew` | `0x26D6420` | `0x995FF8` |
| `currentCooldownPaused` | `0x26D64B8` | `0x99658E` |
| `currentCooldownBegin` | `0x26D64D0` | `0x99659F` |
| `currentCooldownDuration` | `0x26D64E8` | `0x9965C4` |
| `currentCooldownExpired` | `0x26D6500` | `0x9965F6` |
| `currentCooldownRemaining` | `0x26D6518` | `0x99661D` |
| `costPower` | `0x26D6590` | `0x996859` |
| `costMana` | `0x26D65A0` | `0x9968C3`, `0x996B50` |
| `costEnergy` | `0x26D65B0` | `0x996939` |
| `uninterruptible` | `0x26D8D50` | `0x9B8385`, `0x9B8728` |

The cooldown cluster `0x99655B..0x99662C` also references the **same game-clock global slot** `0x33DC2B0`. Cooldown remaining is at least partly derived through native math and clock reads; field-string pointer `R8` is **not** an ability/cooldown data pointer. The cost and castbar clusters are separate functions/paths, and repeated fields do not establish duplicate player records. Next purely static task: identify containing `.pdata` function ranges, then trace the *value-producing* register and owner-acquisition call before each setter. No native ability/cooldown/castbar object has been accepted as live or restart-safe.

The retained **API-only** Atank Light's Decree sample shows Power 100→80→81 while a cooldown declined about 11.977→11.863 s (`artifacts/casting-20261025-01/ranged-evidence-03/evidence.json`, observations 5498–5500). Its executable SHA was not saved; it remains historic behavior reference only, not a native memory corroboration.

### Offline resource-candidate collector — no new live reads

`scripts/probe_native_unit_manager.py --lab lab1|lab2 --resource-record` is now an **opt-in** extension of the existing SHA/PID/start-pinned native snapshot workflow; it was **not executed against a lab**. It walks the current-build selected component → kind-owner → resource-wrapper → reference-slot → record path, captures the game-clock input, and rechecks kind, wrapper, reference, vtable, mutable record inputs and process identity. For kind 3 it preserves raw mana offsets and unverified expected resolver type `0x072A`; for kind 4 it uses the **different** energy layout/type `0x072B`; all other kinds report `not-applicable`. Mismatched revisions are reported unavailable; nonfinite clock inputs fail closed instead of producing a value. The record remains `untyped-record-candidate` even with a stable raw read, and **no native current/max value is calculated, published as trusted telemetry, or written back** until the full resource type fingerprint is established.

**31/31 Python synthetic tests passed**, job `rr2-offline-native-resource-candidate-tests-20261101-01` (exit 0). Existing offline receipt, movement, source-pin and on-demand receiver contract suite also passed **63/63**, job `rr2-offline-reader-receipt-py-contracts-20261101-01`. These tests require no game, VMware, controller or network access.

**Remaining validation:** trace per-resource record vtable → descriptor getter → descriptor vtable → type getter; qualify no-write record values under explicit live-operation approval; compare independently sourced native and Lua/UI readings across changes; prove passive freshness and normal restart qualification. No new game/VM/memory read, controller/screenshot operation or addon edit occurred in these offline static and code passes.

## Promotion gates

1. Trace the current-build unit identity/owner chain to the component and test a single player under exact PID/start/SHA gates in **read-only** native memory.
2. Compare at least two separately captured, independently sourced HP/XYZ observations; reject replicated UI/cache copies or data unchanged despite controlled source changes.
3. Reuse the existing exclusive controller, screenshot, lease, and freshness gates for any later movement trial. Lab 1's prior eight-minute freshness failure blocks that trial until repaired.
4. Requalify a candidate through a normal game restart, then integrate a version-gated native reader. No live pointer was promoted by this offline decompilation.

No game binary patching, process-memory write, debugger attach, gameplay input, VM restart, or addon edit occurred in this research.
