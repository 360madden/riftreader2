# Current-build native XYZ writer evidence

Evidence checkpoint: November 7, 2026 Eastern. Authoritative checkout:
`C:\work\riftreader2` on AMD-DESKTOP. This note synthesizes retained bytes and
static traces; it grants no live, input, reload, bind, restart or debugger authority.

## Result and exact-build boundary

The native self-key/entity/position ownership recipe is practical and repeatable.
**A passively fresh, independently changing player-position source and its
primary updater remain unqualified.** The two decoded optional refresh branches
are ineligible in 49 retained historical position captures across seven epochs.
That does not enumerate all engine writers or establish the current guard state.

All RVAs below apply only to executable SHA256:
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
The historical `7C356C9D...` root `0x32E0200` and XYZ offsets
`+0x320/+0x324/+0x328` do NOT apply. Do not carry absolute pointers across epochs.

## Native owner chain — static recipe, historically observed ownership

1. `[module+0x33623E0]` player system → QWORD `+0x360` self key.
2. `[module+0x33624A8]` manager → `+0x50` full-key hash table → entity.
3. Signed selector metadata at `module+0x2F588A0` → entity selector byte
   `entity+0x18+index` → table `[entity+0x78]` → selected component.
4. Position-component primary float32 XYZ: `+0x48/+0x4C/+0x50`;
   secondary XYZ: `+0x88/+0x8C/+0x90`.
5. Reacquire PID/start/build/module/self key and owner links, then bracket payload
   and anchors. Component `+0x10` backlink must match the admitted entity.
   Sequential equality is non-atomic and cannot exclude ABA.

Source map: `docs/reference/native-current-coordinate-code-map.md`,
SHA256 `DA9AB7E2C34A30B2E80D6107873195FB8FD50A1ABB32746769ED34113431AF86`.
Reader source: `src/RiftReader2.Live/CurrentBuildPlayerLookup.cs`,
reviewed SHA256 `80146294F907D13FD652D1301396737B87D71D61F1AA8D9CEB390F24A22C13E7`.
Source changes require fresh inspection; these hashes are evidence, not a runtime pin.

## Historical source-selector finding — TWO epochs, not all 49 captures

The distinct upstream source selector is `module+0x2F57918`. Broader retained
module snapshots contain raw DWORD `2E000000` (signed index 46). The small
`roots-request.json` captures do not cover it. Never substitute position index 34,
or hardcode historical index 46/slot6 into a current reader.

| Lab | Module snapshot under artifacts/native-module-roots | Whole JSON SHA256 |
| --- | --- | --- |
| Lab1 | lab1/31698603c86a445b8736a2435caf6a92/snapshot.json | 8A42DF19375EBF6B139B61244C4B08909A9D986C67F7B5940BA7818D6EA10E91 |
| Lab2 | lab2/6adb062aee0843c98c7ea804cb2c86cb/snapshot.json | 74651FA7937E7DB12CBCBC3E4605B2B795285F47E034386D4B139CB8A5F654C9 |

Relevant 4KiB chunk hashes:

- Lab1 `5A70B87E59E244A7525C44013734037984D528F5DA1F23672547EB7A72EE4B32`.
- Lab2 `50EAF00B4D90146227B85CB112178FBA67202E1F40EF2E8DEB98B20499C843C3`.

Same-process later self entity captures show selectors 22→FF,30→17,34→6,46→FF.
Entity JSON hashes: Lab1
`EA129236876631487F4AE3E937C3FF5931E20F0755EED6DD0C02811C5EAB088E`;
Lab2 `1DFB830739E6F305F6B62CCDA03AF9669EE65ECF3B79CA8C12597C92B6882B48`.
Their directories are the two native-unit-manager runs listed below.
Module snapshots were Oct31 ~21:27UTC; entity/component captures Nov1
~01:30/01:32UTC. Matching process epochs do not make the acquisitions simultaneous.

## Independently verified historical guards — 49/49, SEVEN epochs

Source scope: every `artifacts/native-unit-manager/lab{1,2}/*/component-values.json`
then present: 49 files. Every admitted position chunk was exactly 272 successful
bytes. Full JSON digests were computed; relevant raw Base64/chunk hashes,
PID/start/build, entity/pointer/value identities, table-slot pointer and
component backlink were checked. No parse/hash/ownership mismatch occurred.

| Lab | PID / process-start UTC ticks | Captures with QWORD(+0x100)=0 and BYTE(+0x108)=0 |
| --- | --- | ---: |
| Lab1 | 7164 / 639294897866244204 | 15 |
| Lab1 | 11672 / 639296016581575957 | 5 |
| Lab1 | 8164 / 639290507142219120 | 3 |
| Lab1 | 1952 / 639294190379863806 | 1 |
| Lab2 | 9752 / 639294897826627677 | 16 |
| Lab2 | 7012 / 639290507554340644 | 8 |
| Lab2 | 11572 / 639293038821710082 | 1 |

The initial 26-file/six-epoch cohort was a correct single-chunk subset, not the
whole retained set. Eight more files have position first plus another chunk;
15 have health 72 bytes first and position 272 bytes second. Select by ownership
pointer, NOT chunk order. All 49 report complete acquisition. Two files have
other nonzero bytes within +0x100..+0x10F; **only the actual branch guards are
claimed zero across all 49**, not the entire 16-byte region.

Independent Workbridge receipt:
`rr2-peer-guard-cohort-pointer-selected-chunk-20261108-01` — PASS/exit0,
untruncated, 2026-11-08T01:39:36.522–01:39:37UTC; output contains every matched
path and individual JSON/raw digest. Supporting bounded passes:
`rr2-peer-independent-guard-cohort-included-first-chunk-20261108-01` (34 files)
and `rr2-peer-guard-cohort-exclusion-shapes-20261108-01` (chunk ordering).

Two anchor originals under `artifacts/native-unit-manager/`:

- `lab1/5a654fbadb324803a6bba83520329d46/component-values.json`,
  SHA `E5DBE57BBE80B9D6D03228630CBD5E96DF80975B5263D01CDD6B91FDA0B26971`.
- `lab2/a4e8474dbfef4a1490b7cee6655e46c8/component-values.json`,
  SHA `FE34732A410CDF3098635F42563F8F5B43757A7AE4981783F8992C2ED6B41253`.
Corresponding `entity.json` and `component-pointers.json` close the ownership chain.

## Static writer distinctions — NOT observed execution

RVA and offset numerals in this table are hexadecimal.

| Route / RVAs | Proven retained instruction meaning |
| --- | --- |
| 6996C0, handle nonzero | 6A0040 resolves the key at position+100; source selector 2F57918 is applied to the RETURNED entity, not automatically self; 612EE0 supplies XYZ |
| 699855 / 699859 | Conditional primary +48/+50 stores after comparison |
| 6998A4 / 6998B2 | Secondary +88/+90 stores in that handle branch |
| 6996C0, handle zero / flag+108 nonzero | Uses position+10 owner entity/source selector 2F57918; requires component and 6136B0 admission; calls 612B50 |
| 699991 / 699999 | Primary +48/+50 stores in alternate branch |
| 6999C7 / 6999D2 | Secondary +88/+90 stores in alternate branch |
| 698460 | Getter returns position+48 after optional 6996C0 refresh; not another writer |
| 698480 | Shared-clock timestamp +0xD4 / adjacent cached fields; NOT primary XYZ |
| 698EC0 | Matrix+60..80 and derived F0/F4; NOT primary XYZ |
| 612B50 | Caller-output vector writer with provider/fallback; not universally player-bound |
| 687320 | Secondary XYZ plus actor translations → actor+3BC..3C4; downstream |
| 688F20 | Actor/model composition → render+C4; downstream, not primary-cache writer |

Zero handle at 6996E7 jumps to 699923; zero flag there jumps to 699A2A,
bypassing both known store groups. This is a static branch deduction applied
to the historical guard bytes, NOT proof that no external writer exists.
A returned mutable cache pointer is a lead, not an identified caller store.

Retained successful exact-build jobs: `rr2-serialized-native-xyz-refresh-full-20261031-01`,
`rr2-serialized-native-xyz-accessor-20261031-01`,
`rr2-serialized-native-upstream-resolver-20261031-01`,
`rr2-serialized-native-upstream-xyz-20261031-01`.
The 832-byte 6996C0 slice was independently decoded without rereading the PE;
raw slice SHA `028F06A97F523621BC35EEE542D8C730E01DB0592F0A78EDF32F63697BE8F342`.
It is a partial-function slice, not an exhaustive writer search.

## API influence and smallest next evidence

`Inspect.Unit.Detail` invokes 698460→6996C0. RR2 ordinary addon Producer polls
Detail at a healthy default 0.5s even without an RR2R1 nonce. Thus unbinding the
reference, waiting, or reading native before an EXPLICIT API request does not
establish API quietness. Other addons may query too; actual callers are unmeasured.
Source fingerprints: `addon/RiftReader2/main.lua`
`A0DA4E537DDC84CAC08E77FCEE708078FE8203670CDD439F2F422F73B668DE03`;
`producer.lua` `BA565468BDA7FC054186D1BB1F15B504620565EEB448818451FFA346887DC779`.

Next root-owned, separately admitted no-input discriminator:

1. Fresh exact epoch/self key/component; record native-before primary/secondary
   XYZ, guards and source selector with owner/byte rereads and monotonic/UTC bounds.
2. Acquire an independently advancing same-player RR2R1 API reference using a
   current qualified nonce/source, then native-after; label API-quiet
   true/false/unavailable from actual evidence, never assumption.
3. Compare endpoint presence and ordinary finite API hundredth quantization;
   bound acquisition skew. Equal coordinates or advancing clocks are not motion.
4. If primary XYZ changes with both guards zero, report change unexplained by
   the TWO retained refresh branches, not identification of a new writer.
   Unchanged data is inconclusive. No automatic input/reload/disable is implied.

Missing edge: a source-hashed store outside these branches whose destination
is demonstrably the SAME player position component+48/+4C/+50. No such updater
was verified. Actor/render and universal source+F8 claims cannot fill that gap.
Current-build changed-state, passive freshness and full-game-restart durability
remain separate pending gates; old-build acceptance does not transfer.

## Expanded exact-build decompilation — November 7, 2026, 23:23–23:25 EST

This continuation used installed **Ghidra 12.1.2 headless**, importing the exact
installed executable with `-noanalysis`, then manually decoding only eight
bounded target windows and ten directly related helper windows. The program
identity was rechecked in the analysis log:

- Executable SHA256:
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Image base: `0x140000000`; language `x86:LE:64:default`; compiler `windows`.
- Project: `artifacts/rea/RiftNativeFocusedV2`.
- First successful bounded CFG run: `rr2-ghidra-focused-native-v2-noanalysis-20261108-a089-retry`.
- Full targeted pseudocode export: `rr2-ghidra-focused-native-v5-process-20261108-a089`;
  output `artifacts/rea/ghidra-v5-pseudocode.txt`, SHA256
  `78ad0d1edb84eba9dcf309911c0117df17369f1ea0b85230608e1f248fea30b1`.
- Helper pseudocode export: `rr2-ghidra-focused-native-v6-process-20261108-a089`;
  output `artifacts/rea/ghidra-v6-pseudocode.txt`, SHA256
  `2cb270ce303de75afab4e9721b80c2313988945d9ee32a53763bbacd0c42a35b`.
- Reproducible script sources remain under ignored `artifacts/rea/`:
  `Rr2FocusedNativeV5.java` SHA256
  `2efe875c51b4f05fe3147694591973af93a3ae45c04f70cd7d2a47c127fc60d8`;
  `Rr2FocusedNativeV6.java` SHA256
  `4b8cc0cebf86a61c01dd00f0230c076772c31a6ff433209d7417aeef9b955989`.
- The focused CFG decoder reconstructed 669 instructions / 2,614 instruction
  bytes in the original eight windows; all eight explicit function-body updates
  succeeded. Ten helper windows were subsequently decoded and decompiled.
  These are static executable findings, not live branch execution.

### 1. `0x6996C0` — both primary cache-update routes

The decompiled function confirms that `param_1` is the position-component
candidate already being inspected. It has two mutually exclusive top-level
routes, and both write the primary cached XYZ at `+0x48/+0x4C/+0x50`:

**Handle route — `QWORD(component+0x100) != 0`:**

1. Lazily obtains the unit manager at global `0x1433624A8`.
2. Calls `0x6A0040(manager, component+0x100, &resolvedEntity, 0)` to resolve
   the handle. The returned entity, not automatically the owner/self entity,
   is then used for the next selector.
3. Applies source-selector metadata RVA `0x2F57918` to the returned entity's
   selector byte/table. An absent `0xFF` selector or null component exits.
4. Calls `0x612EE0(sourceComponent, &xyz, owner+0x10)`.
5. If returned XYZ differs from cached `+0x48/+0x4C/+0x50`, stores the new
   primary triplet. It also mirrors the result into `+0xD8/+0xDC/+0xE0` and
   `+0x88/+0x8C/+0x90`; a conditional downstream callback may follow.

**Alternate-provider route — `QWORD(component+0x100) == 0`:**

1. Requires `BYTE(component+0x108) != 0`; otherwise it exits before resolving
   any source component.
2. Applies source-selector metadata RVA `0x2F57918` to the owner entity at
   `component+0x10`, then requires a non-null selected component.
3. Calls `0x6136B0(selectedComponent)` as a further admission predicate.
4. Calls `0x612B50(selectedComponent, ..., component+0x48, 0)` for the primary
   provider result, then calls it again with mode `1` for the secondary
   `+0x88/+0x8C/+0x90` triplet.
5. Writes the primary triplet and its `+0xD8/+0xDC/+0xE0` mirror, plus
   secondary XYZ and matrix/auxiliary fields. `0x612960` supplies the associated
   quaternion-derived 3x3 matrix; it is not another XYZ writer.

The store groups already mapped in the prior note remain the exact instruction
sites: primary handle stores `0x699855/0x699859`, secondary handle stores
`0x6998A4/0x6998B2`, primary alternate stores `0x699991/0x699999`, and
secondary alternate stores `0x6999C7/0x6999D2`.

### 2. Exact cheap alternate-provider predicate — `0x6136B0`

The 23-byte routine is now fully decompiled. Given the selected source component
pointer in RCX, it returns true exactly when:

- `*(int *)(*(QWORD *)(component+0x48) + 0x24) >= 0`; and
- `QWORD(component+0x58) != 0`.

Otherwise it returns false. This is a cheap passive predicate, not proof that
the caller's alternate route is reached. It is evaluated only after the
top-level `component+0x108` flag is nonzero and the `0x2F57918` source selector
resolves a component.

### 3. The `0x612EE0` / `0x6126F0` source distinction

`0x612EE0` is a caller-output XYZ getter, not a primary cache writer:

- It first calls `0x6126F0(param_1, param_3, &sourceObject)`.
- On success, it reads source-object `+0xF8/+0x100` and adds the global actor
  offset vector. This is a conditional source-object route, not a universal
  player-world owner.
- On failure, it applies position-component selector metadata RVA `0x2F588A0`
  to the entity at `param_1+0x10`; when that component exists, it calls
  `0x698460` and reads the component's cached `+0x48/+0x4C/+0x50`.

`0x6126F0` searches the collection rooted at `param_1+0x48` for an entry whose
`+0x18` key matches `param_2`, resolves its associated object, then uses actor
selector metadata RVA `0x2F58490` and `0x67BFB0` to return the conditional
source object through `param_3`. This is the exact reason `+0xF8/+0x100`
cannot be treated as a universal player-world owner.

`0x612B50` is a provider adapter: if `component+0x58` is null it copies the
caller-provided vector; otherwise it invokes the selected component's vtable
method at `+0x08` and returns three floats. It does not itself store the
position-component cache; `0x6996C0` owns those stores.

### 4. Bounded adjacent helpers are consumers/derived transforms, not primary XYZ writers

- `0x698460` calls `0x6996C0` and returns `component+0x48`.
- `0x6983F0`, `0x698410`, and `0x698440` each call `0x6996C0`, then return
  `component+0x60`, `component+0x94`, and `component+0x88` respectively.
- `0x613800` obtains actor and position components, calls `0x6996C0`, then
  reads matrix/transform helpers and passes derived data to `0x687320`.
- `0x687320` writes actor translation at
  `actor+0x3BC/+0x3C0/+0x3C4` and related actor/render transform fields. These
  are downstream actor coordinates, not the position component's primary
  `+0x48/+0x4C/+0x50`.
- More precisely, `0x613800` selects the position component with selector
  `0x2F588A0`, calls `0x6996C0`, then obtains `component+0x88` through
  `0x698440` and `component+0x94` through `0x698410`. It passes those
  values to `0x687320`; that routine adds actor offsets from `+0x4F8/+0x4FC/
  +0x500` and `+0x770/+0x774/+0x778` to the secondary `+0x88` triplet
  before storing actor translation. Thus the actor/render position path consumes
  the secondary cache, not the primary Lua-facing `+0x48` cache. This is a
  downstream transform path, not an independently proven cache writer.
- `0x698EC0` writes the matrix at `component+0x60..+0x80` and derived
  `+0xF0/+0xF4`; it does not write primary XYZ.
- `0x698910` calls `0x6996C0` and interpolates/forwards transform state into the
  actor path; it is not an independent primary XYZ cache writer.
- `0x612960` constructs a matrix from a quaternion/provider; it is orientation
  support, not position.

These bounded results strengthen the known `0x6996C0` route map. They do NOT
constitute an exhaustive whole-image search for every external store to the same
component offsets.

### 5. Historical admission remains negative; current runtime remains unknown

The previously audited **49/49** pointer-selected historical position-component
captures across seven process epochs had `QWORD(+0x100)=0` and
`BYTE(+0x108)=0`. Therefore, neither top-level `0x6996C0` route was eligible
in those captures. Separately, retained module-root snapshots from two historical
epochs showed source-selector index `46` at `0x2F57918`, with SELF slot `46`
absent. Those snapshots are historical and not simultaneous with every
component capture.

Consequently:

- Ordinary `Inspect.Unit.Detail` can call `0x698460 -> 0x6996C0`, but a getter
  invocation is not evidence that either update route passed its gates.
- The historical zeros explain why these known branches did not refresh the
  sampled component in those receipts; they do not prove the current live gates.
- No other source-hashed store to the same player component
  `+0x48/+0x4C/+0x50` has yet been established. A changed cache value with both
  routes ineligible would remain unexplained until another destination-matched
  writer is found.
- Current-build branch admission, actual writer execution, passive freshness,
  changed-state, full-game restart and body-heading qualification remain open.

No game process was read or changed during this static Ghidra continuation; no
VM/game input, controller, addon, reload, deployment or restart occurred.

## Instruction-level callsite confirmation — November 7, 2026, 23:29 EST

A second bounded Ghidra export checked the actual callsite register setup rather
than relying on decompiler argument naming alone:

- Job: `rr2-ghidra-native-callsite-dump-20261108-a089`.
- Output: `artifacts/rea/ghidra-v7-callsite-instructions.txt`.
- SHA256: `ca66aca8543b4e2f0b70f7669025c0d3fe419c4a0864a7ae9832ac625e1ac530`.

This confirms the handle route at instruction level:

1. `0x6997CC–0x6997D3` passes manager, address of component `+0x100`, and
   output storage to `0x6A0040`.
2. `0x6997E0–0x699802` applies selector RVA `0x2F57918` to the returned
   entity and loads its selected component into RBX.
3. `0x69980B–0x69981B` calls `0x612EE0` with RCX=that selected component,
   RDX=the local XYZ output, and R8=the QWORD at
   `*(QWORD *)(positionComponent+0x10)+0x10`.
4. In `0x612EE0`, `0x612EEC–0x612F09` forwards incoming R8 as the second
   argument to `0x6126F0`. A successful result is dereferenced at
   `sourceObject+0xF8/+0x100`; this is the conditional source-object path.
5. If `0x6126F0` fails, `0x61303B–0x61305D` resolves selector
   `0x2F588A0` on the selected component's owner entity, places the resulting
   component pointer in RCX, and calls `0x698460`.
6. `0x698460` receives that selected component in RCX, calls
   `0x6996C0` at `0x698469`, and returns the selected component's `+0x48`
   pointer. Thus the fallback getter can re-enter `0x6996C0` on the
   position-component selected from the resolved entity. Whether that nested
   component is identical to the outer component in any live case is not
   established here; do not assume either identity or recursion depth.

The alternate branch is independently confirmed at `0x699923` onward:
the top-level handle-zero branch checks `BYTE(component+0x108)`, resolves
selector `0x2F57918`, calls `0x6136B0` at `0x69995D`, then calls
`0x612B50` at `0x699979` and `0x6999AF`. Primary and secondary stores
occur at the exact RVAs listed above. The instruction dump also confirms the
`0x6136B0` two-condition predicate at `0x1406136B0–0x1406136C6`.

This register-level pass validates the static argument flow and the possible
nested fallback getter. It does not establish current live pointer identity,
actual branch execution, a second external primary-cache writer, or passive
freshness.
