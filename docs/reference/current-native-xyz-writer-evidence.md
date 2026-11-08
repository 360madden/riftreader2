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
