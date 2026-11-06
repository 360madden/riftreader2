# Current RIFT client code map — health, resources and ability fields (2026-11-01)

Status: **current-build static health/resource/ability code paths, type-checked live Lab2 HP and Energy raw-record candidates, and a historical untyped Lab1 HP record**. Three authorized Lab2 captures completed on 2026-11-01 UTC with the same pinned client identity; the third established the live Energy **type fingerprint `0x072B`**. Its exact native current-value math was subsequently reconstructed and replayed **offline** from that captured record, yielding a **100/100 Energy calculation candidate**. Independent synchronized UI/API correlation, passive freshness and restart qualification remain pending for both resources. Mana kind3's type path and live cooldown owner remain unidentified. Unless explicitly labeled as a captured session address, addresses below are RVAs relative to `rift_x64.exe`.

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

Historical approval boundary: the initial typed Lab2 live command `rr2-serialized-native-typed-health-lab2-20261101-01` was **rejected at the tool approval step** and was never retried through another route. On November 1 Joey granted **fresh explicit Lab2 access**; new separate commands `rr2-approved-lab2-typed-hp-20261101-01` and `rr2-approved-lab2-untyped-resource-20261101-01` subsequently completed successfully. Their evidence is recorded below. Approval does **not** remove the independent UI/API, passive freshness, restart or other-lab verification gates.

For screenshots, reuse existing capture/queue primitives, not the full old XYZ workflow guard: `run_xyz_workflow.read_config` pins obsolete coordinate-profile RVAs. Direct `control_client._capture` also does not perform dependency startup by itself; the normal `control_client.run` capture entrypoint does. Acquire against current authenticated identity/epoch, never arm or send input, and wait for watchdog cleanup rather than treating `q.finish` as completed release. No bypass of an occupied queue, foreground failure, or permission denial.

### First authorized Lab2 live type-checked HP and untyped Energy — 2026-11-01 UTC

The two opt-in, *read-only* guest native snapshot workflows completed on **the same Lab2 client process identity**: PID **7012**, process-start ticks **639290507554340644**, exact installed executable SHA **`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`**, native player ID **`u035400012DFEB5BC`**. Both probes returned `status=complete`, stable ownership and mutable-input rechecks, and exit code **0**. Captures were **separate sequential collections**, not an atomic paired HP/resource frame.

| Lab2 evidence | HP capture 06:35:29 UTC | Energy capture 06:36:57 UTC |
|---|---|---|
| Native record candidate | `0x2186C54CFB0` (session address) | `0x21806591350` (session address) |
| Record vtable RVA / descriptor getter RVA | `0x2C0EE88` / `0x20CCC60` | **`0x2D19498` / `0x231BEB0`** (untyped fingerprint starting points) |
| Type and record consistency | Verified exact-build **`0x02C2`** health chain; record/wrapper revision **74/74** | Selected kind **4** Energy; expected resolver type `0x072B` **not yet verified**; revision **56/56** |
| Raw fields | HP base **10,635**, max **10,635**, modifier **14,250**, caps 1.0/1.0 | Energy base **100**, max **100**, rate **2,000**; raw only |
| Derived output | Finite ordinary-case **calculated HP candidate 10,635/10,635** | **No trusted current/max calculation**; type fingerprint incomplete |
| Ownership/input stability | Passed | Passed |

- Guarded HP job: `rr2-approved-lab2-typed-hp-20261101-01` → `artifacts/native-unit-manager/lab2/16994df05b7f495b8959477f9e253477/review.json`, SHA-256 **`A94E9053800599F2F4369B93BF03ED358B94D6D1E75A83379A83BFC1B2027B3D`**.
- Raw Energy job: `rr2-approved-lab2-untyped-resource-20261101-01` → `artifacts/native-unit-manager/lab2/d6757494c51b4bf782ac310697460ec8/review.json`, SHA-256 **`ED2BAAF1F71E364C45FC98323B16C3FB649813B15F8328A4A07959AAD7842E90`**.
- The historic Bolinao screenshot shared by Joey also displays **10,635/10,635** HP, but it is *not timestamp-synchronized to this snapshot* and does not qualify current HP. A safe new UI capture needs the controller's true exclusive queue lease, proper foreground/identity checks, a screenshot-only operation without input, and observed watchdog cleanup; the old XYZ workflow's pointer-profile guard is obsolete for this SHA.
- That previously pending Energy type trace **now passed** exact-build static and new read-only live metadata checks, as documented below. The next steps are the passive Energy current-value arithmetic and independently synchronized Lua/UI changes. No mana or cooldown sample was collected. No game input, addon deployment, process-memory writes, restart or native getter invocation took place.

### Energy type path and first fresh type-checked raw-record sample — 06:49 UTC

The live **kind-4** Energy record supplied the narrow seed, **not** an indiscriminate PE scan. With exact exe SHA `1935A05C...4BE8`, four bounded, passed read-only PE jobs (`rr2-approved-lab2-energy-vtable-getter-static-20261101-01`, `rr2-approved-lab2-energy-descriptor-initializer-static-20261101-01`, `rr2-approved-lab2-energy-type-getter-static-20261101-01`, `rr2-approved-lab2-energy-type-helper-static-20261101-01`) and independent x64 disassembly proved the following:

| Step | Exact code/data evidence |
|---|---|
| Captured record virtual table | RVA **`0x2D19498`** is in PE `.rdata`; its virtual slot `+0x40` points to getter **`0x231BEB0`**, also captured live. |
| Descriptor getter / initializer | Getter `0x231BEB0` has direct JMP to `0x232FDC0`. That lazy initializer returns the descriptor global **`module+0x35AEB80`**; its code stores descriptor vtable **`module+0x2D1D420`** into the global. **Do not invoke it.** |
| Descriptor type slot | The descriptor vtable slot `+0x08` at **`module+0x2D1D428`** holds type getter **`0x233E9B0`**. |
| Native type calculation | `0x233E9B0` passes EDX seed **`0x002239C5`** to helper **`0x23354F0`**; the helper's first unsigned `JBE` compares it to `0x17E6D245` and returns `0x2DD59D90`. The getter XORs low16 with `0x9ABB` → **`0x072B`**, exactly the Energy resolver's required type. |

`checked_energy_type` in `scripts/probe_native_unit_manager.py` reproduces that **pure-read fingerprint** only for kind4, checks the record vtable/getter and reads the *live* initialized descriptor-vtable and type-getter slots without calling game code. Those two live qwords, record/wrapper/owner pointers and mutable inputs are rechecked at the end. Mana kind3 remains untyped. **34/34** focused Python tests passed, job `rr2-new-energy-type-guard-offline-tests-20261101-01` (exit0), including deliberately corrupted fingerprints.

The approved **new live Lab2** job `rr2-approved-lab2-typed-energy-20261101-01` completed exit **0** at 06:50:01 UTC; its type-checked raw record observed at **06:49:42 UTC** and has exact previous Lab2 PID/start/SHA/player key. It returned `resourceRecordCandidate.status=type-checked-raw-record-candidate`, `typeCode=0x72B`, `inputsStable=true`, Energy kind4, stable record at session address `0x21806591350`, matching record/wrapper revisions **59/59**, raw **base100 / max100 / rate2000**, and passed static descriptor-slot and full ownership rechecks. Evidence: `artifacts/native-unit-manager/lab2/cb89bea7ed9e4d6a9d029d65b5a446b6/review.json`, SHA-256 **`CF1103CBFF83C4C0C3C1CDA6A0684C74581DD7AC283EF0776C06AF1B3F31B7DE`**.

### Current Energy calculator — exact-build native x64, offline replay

After the type-checked live run, independent full instruction disassembly of native **Energy getter `0x133F2C0..0x133F3A6`** (`rr2-approved-energy-current-getter-pe-offline-20261101-01`, exit0) resolved the ordinary-domain calculation without invoking its mutating getter:

```text
require kind == 4, recordRevision == wrapperRevision, maximum > 0
elapsed = f32(f32(gameClock) - f32(wrapperClock))
rate = f32(rateRaw)                  # CVTDQ2PS signed int32 -> float32
adjustment = trunc_int32(f32(f32(rate * f32(-0.01)) * elapsed))
current = clamp_int32(baseRaw - adjustment, 0, maximumRaw)
```

Native **revision mismatch writes** wrapper revision and clock, so the read-only calculator rejects it. The real function uses `MOVD`/`CVTDQ2PS`, twice-rounded `MULSS` with the exact f32 literal at RVA `0x26B08A4` (`0A D7 23 BC`), `CVTTSS2SI` and a signed 32-bit subtraction before clamping. The Python `calculate_energy` fails closed on nonfinite/negative clock intervals, unsafe conversion, positive-max requirement, sentinel and signed subtraction overflow rather than reconstructing native writes or undefined boundaries. It reports a **calculated candidate**, never a trusted production field. **38/38** focused Python tests passed (`rr2-energy-calculator-38-focused-tests-20261101-01`, exit0), including the `2^24` float32 rate rounding, depletion/regen, stale revision and numeric-boundary negative cases; independent static review found no material ordinary-domain defect.

Read-only **offline replay**, `rr2-offline-typed-energy-native-formula-replay-20261101-01` (exit0), validated the source report SHA and exact prior Lab2 identity/type/inputs, then calculated from the **06:49:42 UTC** retained type-checked record: game clock **61827.53515625**, wrapper clock **61610.41796875**, elapsed **217.1171875s**, rate **2000**, truncated adjustment **-4342**, base **100**, max **100** → **candidate current Energy 100/100**. The replay adds **no new simultaneous live measurement**. Independent Lua/UI comparison and at least two correctly correlated value changes remain outstanding; a full-bar baseline alone is weak evidence. No game input, process-memory write, addon deployment, VM restart or controller screenshot occurred.

### Exact native getter cache-write sites, not game-resource writers

Independent replay of retained Energy getter disassembly establishes:
record revision at +0x34 is compared to wrapper revision +0x18 at
RVA 0x133F2F0. On mismatch, 0x133F2F5 copies the revision to wrapper
+0x18, and 0x133F2F8–0x133F302 copies shared game clock from
[module+0x33DC2B0] object's +0x18 to wrapper +0x1C. The analogous
HP wrapper revision/clock cache writes occur at 0x5E845B and 0x5E8468.
**These getters update wrappers, not the underlying HP/Energy record's
revision fields**; use an independent static writer trace to find the
producer of actual record updates. No game code was executed or memory
modified for this result.

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
- Current-build resource ownership and ability/cast field-builders are statically traced below. The live **Energy** raw-record type fingerprint is now checked, but **Mana** type, Energy current-value arithmetic, independent UI/API comparisons, passive freshness and restart-safe addresses are not qualified.

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

Both resource resolvers call native type helper `0x127303C`, but require **different** low16 types: mana/charge `0x072A`; energy `0x072B`. The getters manage temporary reference counts and may update cached clock/revision. RiftReader2's external native probe must **never invoke them, touch refcounts or write caches**. Current-value getters involve the shared game-clock pointer at `module+0x33DC2B0`, float32 arithmetic and native constant **`-0.009999999776482582`** (4-byte constant at RVA `0x26B08A4`). Full boundary behavior and **Mana** type fingerprint remain unqualified. The new read-only **Energy** type fingerprint passed against the live kind-4 record; this does **not** qualify current Energy values. Offset `+0x24` has a meaning only within its particular resolved, type-checked record.

An independent pre-vtable RTTI sanity check (`rr2-serialized-hp-vtable-rtti-sanity-20261101-01`) found that the eight bytes at **HP vtable RVA `0x2C0EE88 - 8`** point to executable code RVA `0x71610`, **not** an MSVC Complete Object Locator. Static resource type discovery must therefore prove the descriptor path directly; an adjacent-RTTI-table shortcut is not available at this positive control. This does not prove that every class lacks RTTI.

A bounded **offline type-leaf scan** of exact-build `.text` RVA `0x20F0000..0x20F6000` found **103** simple `mov seed; call helper; xor low16; ret` getter patterns. It correctly rediscovered the HP positive control `0x20F2480 → 0x20E64C0 → 0x02C2`, but an over-approximate immediate-constant filter found **zero** candidates for `0x072A/0x072B` in that narrow family. This *was inconclusive at that stage*: Energy's actual type getter `0x233E9B0` lies **outside** the small scanned window. Job `rr2-serialized-resource-type-leaf-candidate-scan-20261101-02` passed. The later observed-record-seeded trace below, rather than a broad pattern scan, established Energy type `0x072B`.

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

### Verified exception/unwind ranges and value-producer clues

`scripts/find_native_api_xrefs.py --function-bounds` now parses the SHA-pinned PE32+ exception directory and annotates static field-string references with their containing `.pdata` unwind-function ranges. The **303,143** entries in the exact installed EXE passed image-size, executable-section, unwind-RVA, section-overlap and directory virtual/raw range checks; all 12 field assignments matched exactly **one** range. These are compiler unwind **chunks/funclets**, not necessarily independent semantic functions or owners. The scanner explicitly reports `instructionBoundaryVerified=false` for its byte-pattern candidates; the 12 listed field assignments were separately instruction-disassembled. A range is **not** a live value address.

| Native function / funclet range (end exclusive) | Covered field references | Inference allowed |
|---|---|---|
| `0x995E5A..0x9962A6` | `idNew` | Ability identity field's enclosing code |
| `0x996548..0x996639` | **All five** current-cooldown fields | Shared timer-field builder; same RIFT clock-slot input |
| `0x99664D..0x996E11` | `costPower`, `costMana` **twice**, `costEnergy` | One cost-builder range with multiple branches; not duplicate records |
| `0x9B8347..0x9B84E2` | First `uninterruptible` | Castbar code path A |
| `0x9B84F0..0x9B88CD` | Second `uninterruptible` | Separate castbar code path B |

**2026-11-01 castbar owner/producer follow-up (saved exact PE, no live reads):**
The two castbar Lua marshalling paths at `0x9B8300` and `0x9B86B0`
consume the **same-shaped temporary result** in stack buffers shifted by
`+0x30`, not two established heap records. They use the same
`uninterruptible` literal `0x26D8D50`, numeric-field builders,
ability-like ID calls `0x49FA20/0x1357250`, and an object helper.
Both pass the native unit key returned by `0xA1AAA0` into
**cast-state producer `0x91DED0`** (with a caller-owned output buffer).
This producer uses manager `0x4A4750`, key→entity `0x6A0040`, and
dynamic component selector **module RVA `0x2F57260`** through
`entity+0x18+index` and the `entity+0x78` table. It is therefore
a native player-key-owned cast-associated component branch, **not**
an unqualified static pointer chain.

Two small native accessors are concrete:
`0x5A75C0` reads a nullable child pointer at **component+0x280**
then returns `DWORD(child+0x08)` via helper `0x58B30`;
`0x5A7570` does the same at **component+0x290**.
`0x91DED0` requires at least one nonzero child+8 value before
marshalling cast state. **`0x5A9940` is not a passive getter:**
it copies the smart reference at component `+0x280/+0x288`
into an out-buffer and **increments the reference control's
refcount**. Never invoke it in an external reader. Native timers and
boolean fields are calculated through downstream helpers
`0x5A6CB0`, `0x49F960`, `0x49D440`, `0x49DFE0`,
`0x49D210`, and `0x4948E0`; no persistent cast timer,
component type/vtable, or changed-state correspondence is qualified.
The Casting addon independently reads `Inspect.Unit.Castbar(player)`
but omits `uninterruptible`, so it cannot validate that particular
flag. The source was the independently SHA-pinned 60,493,640-byte
saved current executable; bounded snapshot byte anchors matched the
retained disassembly. All claims remain **static candidate** facts,
not live record addresses or permission to cast.

The code immediately before cost assignments uses **`[RSP+0x58]` as an unverified ability-template/context pointer**; from it, it reads a child-reference vector at `+0x6D0` (`[header]` begin, `[header+0x08]` end, elements supplying child references). The owner of the stack value and element stride still need tracing; it calls native type helper `0x127303C` and branches on **`0x1E29` before Power cost, `0x1E2A` before Mana cost and `0x1E2C` before Energy cost**. A further nearby branch checks `0x1E2B`, whose output is not assigned here. These are **expected types in this particular ability-cost enumeration**; they must not be conflated with player resource record types `0x072A/0x072B`, and no cost child object is live-type-validated. The Power/Mana/Energy amount producers include calls `0x49EF10`, `0x49D600`, and `0x49F000` respectively. Their caller handles references and even mutates flags/refcounts; an external reader must never invoke these getters.

The cooldown builder invokes **`0x5A5E40`** with `RCX=RSI`, `EDX=R12D` and `R8=&[RSP+0x54]`. Its float32 return `T` and optional float32 output `D` are **two distinct values**, not one memory field or pointer. Independent instruction disassembly of retained exact-build code establishes how the native Lua marshaller constructs four fields:

| Native Lua field | Verified calculation in the field builder | Key RVA evidence |
|---|---|---|
| `currentCooldownBegin` | **`T - D`** | `0x996565` subtraction → `0x99659F` assignment |
| `currentCooldownDuration` | **`D`**, the producer's optional out value | `0x996543` out-argument setup → `0x9965C4` assignment |
| `currentCooldownExpired` | **`-(T - gameClock)` on the negative branch**; positive branch behavior needs full path/context | `0x996571` clock subtraction; `0x9965D8..0x9965F6` sign/assignment path |
| `currentCooldownRemaining` | **`max(T - gameClock, XMM7 threshold)`**, threshold value not yet qualified | `0x99660A` float max → `0x99661D` assignment |
| `currentCooldownPaused` | Conditional comparison involving **`T - D`**; predicate/threshold not yet established | `0x99657A..0x996595` |

These are verified **field-construction formulas**, not independently located live data addresses. The return `T` may represent a timer deadline, but its originating ability object, optional duration source, pause threshold and native time-base mapping are not yet proven. The cooldown and cost unwind ranges begin without ordinary function prologues; they may be split pieces of one larger marshaller. Saved source job: `rr2-serialized-ability-code-owners-pe-slices-20261101-01`.

#### Downstream native cooldown resolution — read-only PE evidence

A subsequent exact-SHA extraction and independent x64 disassembly of the **actual float producer** `0x5A5E40` demonstrates that it is **not** a direct immutable timer-field read. Its code spans adjacent unwind segments `0x5A5E40..0x5A5E6E`, `0x5A5E6E..0x5A5FCC`, `0x5A5FCC..0x5A5FEF`; reading just the first `.pdata` range would truncate legitimate control flow. It validates an ability-like handle, uses reference-counted/native-manager helpers and branches through further producers before returning float32 `XMM0`. Reconstructing it by invoking the native getter would **mutate game state and is prohibited**.

| Callee RVA | Observed code path | Unresolved boundary |
|---|---|---|
| `0x1353620` | Looks up a reference and tests the first child of an object `+0x5F0` vector against expected type **`0x078A`** | This is a cooldown-eligibility/type test, not proof of a live cooldown-record type |
| `0x5A6F20` | Resolves another ability-related object and reads a `+0x5F0` reference path; sets flags and manages references | Upstream player/ability key and element ownership remain unverified |
| `0x5A9440` | Decoded secondary float producer: resolves state, loops its +0x4B8/+0x4C0 ID vector, compares keyed timer lookups `0x5A7450` against a possible context +0x1C0 starting entry; optional duration uses conditional branches | Live ability context and resolver-owned state pointer still unverified; details below |
| `0x5526F0` | Reuses unit lookup `0x6A0040`, dynamic health selector **`module+0x2F57850`**, component table `entity+0x78` and further accessor `0x5ECCA0` | Shared selector does **not** mean an HP pointer is a cooldown pointer |

#### Additional cooldown timer-table decoding — 2026-11-01 read-only follow-up

After independently hashing the entire saved 60,493,640-byte PE at
artifacts/lab2-rift-exe-20261027-01-copy.exe against the pinned installed
SHA (passed job rr2-exe-research-saved-copy-sha-20261101-01, exit 0), a
specialist inspected bounded raw instruction slices without invoking RIFT.

- RVA 0x5A9440 accepts an ability context (RCX), 32-bit ID (EDX), and
  optional duration output (R8). The resolved state object's [0x4B8,0x4C0)
  span holds a four-byte-stride ID vector. Each ID is passed to 0x5A7450,
  and 0x5A9440 compares these values with a possible context +0x1C0 entry
  used to initialize the result. The earlier max-across-IDs-only description
  was incomplete; see the [November 6 follow-up](native-cooldown-static-followup-2026-11-06.md).
- RVA 0x5A7450 does a keyed lookup using the original context's +0x240
  table root, +0x248 stride, +0x250 count/capacity, compares entry +0x08
  to ID, and reads the matched float32 value at entry +0x10; no match
  yields zero. These are instruction-derived offsets, **not** yet a
  located live cooldown table.
- Duration comes from conditional paths involving 0x5A8E00, a float
  member +0x14, child integer +0x18, or resolved integer +0x54.
  Float32 constant at RVA 0x26A33C8 is 0.001 (milliseconds-to-seconds
  is plausible, not independently qualified). Do not claim one
  unconditional duration offset.
- Module-rooted context discovery proceeds through 0x4A4250 reading
  [module+0x33624C8], and 0x1274AD8 reading [module+0x3372C18]
  with a 16-bit selector at context +0x40. The lookup 0x129043C /
  0x1290458 tests mode owner+0x274 and conditionally selects a
  collection, with owner+0x200 as one fallback. **The conditional
  collection/ability-key mapping and returned object type are still
  unresolved**; a fixed pointer chain is unsafe. Lazy singleton
  initialization and refcount-changing native functions must not be
  invoked by an external reader.

The next shortest static task is finishing conditional lookup 0x1290458
and caller's numeric ability ID provenance; dynamic qualification then
requires independently changed cooldown values, native-before/after
with an approved controlled ability action, and a fresh exact-process pin.
No live ability object was read or game input issued in this follow-up.

A related ability **Energy cost** getter at `0x49F000` also selects a component through a different metadata index (`module+0x2F57260`) and in an alternate path checks resource kind `4` before accessing wrapper `+0x38`. Cost is a context-dependent calculation, not necessarily a literal independent mana/energy cost field in player memory. These getters contain flag/refcount updates; an external read-only reconstruction must source the same data by static ownership and passive memory reads alone.

Evidence: passed serialized exact-EXE jobs `rr2-serialized-native-cooldown-and-cost-producers-20261101-01`, `rr2-serialized-cooldown-producer-expanded-code-20261101-01` and `rr2-serialized-native-cooldown-downstream-producers-20261101-01`. No runtime ability/HP/resource value was sampled; all session addresses and ownership claims remain gated.

Reproduction: first exact-SHA function-range job `rr2-serialized-ability-pdata-function-bounds-20261101-02`, followed by **strict image/section/unwind validation** `rr2-serialized-pdata-image-section-integrity-20261101-01` and exact-source scanner replay `rr2-serialized-current-ability-strict-pdata-reproduction-20261101-01` (exit0, **12/12 unique matching unwind ranges, all 12 scanner instruction boundaries explicitly unverified**). The scanner and native candidate tests now pass **47/47** offline Python regressions (`rr2-offline-strict-pdata-native-gate-tests-20261101-01`, exit0), including out-of-image/unmapped-unwind/section-overlap/REX-adjacency negatives.

The cooldown cluster `0x99655B..0x99662C` also references the **same game-clock global slot** `0x33DC2B0`. Cooldown remaining is at least partly derived through native math and clock reads; field-string pointer `R8` is **not** an ability/cooldown data pointer. The cost and castbar assignments occupy different unwind chunks/paths, which does not establish independent owning records. Next purely static tasks: trace the owner and input type of `0x5A5E40`, the source of `[RSP+0x58]` and the castbar stack-result producers before their Lua setters. No native ability/cooldown/castbar object has been accepted as live or restart-safe.

The retained **API-only** Atank Light's Decree sample shows Power 100→80→81 while a cooldown declined about 11.977→11.863 s (`artifacts/casting-20261025-01/ranged-evidence-03/evidence.json`, observations 5498–5500). Its executable SHA was not saved; it remains historic behavior reference only, not a native memory corroboration.

### Read-only resource-candidate collector — live Lab2 Energy type gate passed

`scripts/probe_native_unit_manager.py --lab lab1|lab2 --resource-record` is an **opt-in** extension of the existing SHA/PID/start-pinned native snapshot workflow; its first **Lab2** run completed at 06:37 UTC as documented above. It walks the current-build selected component → kind-owner → resource-wrapper → reference-slot → record path, captures the game-clock input, and rechecks kind, wrapper, reference, vtable, mutable record inputs and process identity. For kind **3** it preserves **untyped Mana** offsets with expected resolver type `0x072A` still unverified; for kind **4 Energy** it checks the newly traced exact-build record-vtable/descriptor/type metadata against `0x072B` and rechecks those **live descriptor slots** at the end. All other kinds report `not-applicable`. Mismatched revisions are unavailable; nonfinite clock inputs fail closed. A stable kind-4 record is now `type-checked-raw-record-candidate`, **not** calculated current Energy. The native Energy getter's ordinary-domain arithmetic has now been reconstructed and independently tested; `calculatedEnergy` is added **only after exact type and stable input/anchor gates**, while **no value is published as production-trusted telemetry or written back**.

**31/31 initial Python synthetic tests passed**, job `rr2-offline-native-resource-candidate-tests-20261101-01` (exit 0); subsequent record-alias and hardened `--function-bounds` tests yield **47/47 combined native-probe/scanner tests** (`rr2-offline-strict-pdata-native-gate-tests-20261101-01`, exit0). The new Energy type positive/negative tests passed **34/34 native-probe tests**, job `rr2-new-energy-type-guard-offline-tests-20261101-01` (exit0). Existing offline receipt, movement, source-pin and on-demand receiver contract suite also passed **63/63**, job `rr2-offline-reader-receipt-py-contracts-20261101-01`. These tests require no game, VMware, controller or network access.

**Remaining validation:** independently compare the new **Energy current-value candidate** and HP candidate against fresh Lua/UI values across changes; trace the still-unknown **Mana** descriptor type only if kind3 is observed, then prove passive freshness and normal restart qualification. The new Lab2 guest native reads were authorized and completed **after** the offline code passes above; no controller/screenshot operation, addon edit, game input or game restart was part of those captures.

## Promotion gates

1. The current-build native self-key/entity/component chain passed both labs historically. Lab2 **Energy type** is now a guarded live raw-record candidate; finish other resource-type paths only when applicable and obtain fresh, exact PID/start/SHA, read-only validation for each field before promotion.
2. Compare at least two separately captured, independently sourced HP/XYZ observations; reject replicated UI/cache copies or data unchanged despite controlled source changes.
3. Reuse the existing exclusive controller, screenshot, lease, and freshness gates for any later movement trial. Lab 1's prior eight-minute freshness failure blocks that trial until repaired.
4. Requalify a candidate through a normal game restart, then integrate a version-gated native reader. No live pointer was promoted by this offline decompilation.

No game binary patching, process-memory write, debugger attach, gameplay input, VM restart, or addon edit occurred. Only the explicitly authorized bounded Lab2 read-only native memory captures above were added after the earlier offline research.
