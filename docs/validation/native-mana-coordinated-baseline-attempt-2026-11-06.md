# Coordinated Mana baseline attempts — November 6, 2026

## Successful reviewed baseline

Status: **PASS — `stable-baseline-agreement`.** After the corrected owner probe,
descriptor bracket, producer pin and assessor received independent review, one
serialized Lab-1 run completed in the fixed `API-before → native-owner →
API-after` order. No game input, bind, reload, restart, process write, native
getter invocation or retry occurred.

All three observations retained PID `7164`, process-start ticks
`639294897866244204`, build
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`
and player `u035400012FA2D678`. API-before, the externally calculated native
candidate and API-after each reported Mana **3980/3980**. The independent API
source advanced from sequence `38418` to `38752` (delta `334`) and
`Inspect.Time.Frame` `78302.515625` to `78473.5859375` (delta
`171.0703125`). This rejects a reused API frame; it does not synchronize the API
frame clock to the host/native clocks.

The complete final native observation interval was
`2026-11-06T13:22:55.1815399Z–13:22:55.4671070Z`. API-before snapshot
acquisition completed `85.342503` seconds before native acquisition began, and
API-after snapshot acquisition began `86.164510` seconds after native
acquisition completed. Both gaps passed the declared 180-second bound. These
are host acquisition timestamps around sequential reads, not an atomic or
shared-clock sample.

### Evidence receipts

- Coordinator result:
  `artifacts/native-mana-short-window/runs/8c94c7eda85443a4801adeda10ef17f0/`.
  `assessment.json` SHA-256:
  `C4EB1A55289409600ECE6D53741A95894620DD102BF513695E838EE9239B37EF`.
- API-before capture:
  `artifacts/native-current-reference/runs/lab1/0f9a6a0b1909414da9f7bfe8bee26d5a/`.
  Summary SHA-256 `8509308EAEE816A256DA322198B91636D51BEC9CCE8CB1A6D8CEBFE9B9CD7168`;
  archive SHA-256 `37E5C5224406A3408A2167646D6509AAD43113475C036BA22E1A97AE67DAA178`;
  selected report SHA-256 `98DFC38C53B98C9625F272430CEA58E7333EB954B5E2306899205048B4674012`;
  snapshot SHA-256 `53F9F44B815708A6FF5E597DD4523FC8607FEC6E26A0A81F8BBCB097E6F45397`;
  wire SHA-256 `052CCE12A32FFB38ACC8A2482201ECC7A63CABD05D644BB4D09BBD016EFC8A73`.
- Native owner evidence:
  `artifacts/native-unit-manager/lab1/1150a430fe5f436ca2619f8bb63a22c3/`.
  `review.json` SHA-256:
  `2B22BBD3D1B758A039A65841D9217E12E86852F6E2C95565326917A2E262C8BB`.
- Fresh descriptor proof:
  `artifacts/native-mana-descriptor/lab1/d99978ce7ab24487940bf58b79ea8f24/review.json`.
  SHA-256 `11F198B83ED6FFC27C0EE02F8ACF3010E9189C3FE381AD670D11A506DC069910`;
  descriptor producer SHA-256
  `231B56A2B8B03B4181B4C4ED1EE92872D6D189589498548347421CA3C4C6C945`;
  before/after owner review SHA-256 values
  `3D90E7BDBF74A64DBD0D89944F8C7B14DCB128E941971B1F53DD135A3B8B5BAF`
  and `5B5862823246E9DAFC8A43E85F3D9E9FFFA2EDE67B2F26FBBB26840B24DD0C4A`.
- API-after capture:
  `artifacts/native-current-reference/runs/lab1/39578e40265b4f0ea924724da7dc0b4f/`.
  Summary SHA-256 `FA6CDE5E6E5FC28B445EEF1B476157B353B229B63DBB6C500EE25F3A1313FAC9B`;
  archive SHA-256 `CA5D5448AD217E8B126F3E3D9FF52F411533E734570E3191536AB172150A438FE`;
  selected report SHA-256 `EBA354E5F91DADB185FDC46F86DDB93E0C156F11DDEA2D6A5CF7384806DB7061`;
  snapshot SHA-256 `15DD813D27304DEEFF76FF9AFA1627A14FFECEF55A51B1C8D9286F2500B8EE9F`;
  wire SHA-256 `86B1A5B947634C4988E2C28148D2EF2BE01FC2507A278D2C64646C93707EA2F6`.
- Pinned reader SHA-256:
  `362ECD5A1BE3F10BD3AE9E78B66FA0B56D390E5DD7234B4B5997649926B83A53`;
  owner-probe SHA-256
  `9326E2C23EAE05AF2900DBC5F6E9C78F8C9C3D4B9B222394FD4FF77AE695349A`;
  workflow SHA-256
  `A1F56E3B841DCBE1E23C699C8AB343A303C007269DAE9EFEACC06194F92A972B`.

### Qualification boundary and shared-getter limitations

This result qualifies an advancing-source, same-player, exact-build **stable
baseline correlation** only. The native value is calculated from a type-checked
record and shared game-clock input; RiftReader2 did not invoke the game's getter.
The resolver/type helper and game-clock route are shared with other resources,
and those shared mechanisms do not by themselves prove Mana semantics or
player-component ownership. Getter invocation could also update reference counts
or cache clock/revision state, which is precisely why it remains prohibited.
Sequential owner, record and clock reads can still be torn or experience ABA.
The matching 3980 values do not prove changed-state tracking, semantic/passive
freshness, continuity, boundary behavior, or restart qualification. A separately
reviewed Mana-changing observation is still required for changed-state evidence.

## Initial fail-closed attempt and diagnosis

Status: **BLOCKED FAIL-CLOSED during the native phase; no retry.** The reviewed
Lab-1 operation completed API-before, then the existing native owner probe stopped
with `resource-ownership-anchor-changed`. API-after was not started. No game
input, bind, reload, restart, memory write or native getter invocation occurred.

API-before retained current PID `7164`, process-start ticks
`639294897866244204`, exact build `1935A05C...4BE8`, player
`u035400012FA2D678`, sequence `35000`, frame clock `76549.09375`, and Mana
`3980/3980`. Its snapshot interval was `12:52:16.8004260–12:52:16.8031192Z`.
Partial coordinator evidence is under
`artifacts/native-mana-short-window/runs/fc5e1b4a98014b1c9e2ff58ffa730129/`;
`api-before.json` SHA-256 is
`6D010CA1160FFF6F61ADCA1C4130C5AFA54267AEF1340E43015FA417337A04BC`.

The incomplete native review is under
`artifacts/native-unit-manager/lab1/ad2e2c438b9341d7a3f0457686db28b5/`;
its `review.json` SHA-256 is
`91CFEC396CB650E42E4D3F7F54486E949FA23F597062E525BB2A6F8917AE6621`.
It retained the same VM/game identity and `sourceStableAtPublish=true` but made no
Mana value claim.

## Offline anchor diagnosis

The preserved raw reads show no ownership-pointer or type-path drift. The
resource wrapper remained at `0x2B81AF39690`, reference slot at
`0x2B81AF38C30`, record at `0x2B81C5C1D70`, and record vtable, descriptor getter,
type getter, kind, base, maximum and rate bytes remained unchanged. Only dynamic
revision/cache fields changed during the approximately 10.27-second resource-read
to final-anchor interval:

| Location | Offset | Before | Final |
| --- | ---: | ---: | ---: |
| Wrapper | `+0x18` | 20 | 21 |
| Wrapper | `+0x1C` | 18 | 19 |
| Wrapper | `+0x20` | clock A | later clock A |
| Wrapper | `+0x24` | clock B | later clock B |
| Record | `+0x20` | 18 | 19 |
| Record | `+0x28` | 20 | 21 |

The paired revisions were internally coherent in both observations:
wrapper `+0x1C ==` record `+0x20`, and wrapper `+0x18 ==` record `+0x28`.
Both pairs advanced exactly once. This is evidence of a coherent resource-cache
epoch transition during the probe, not an ownership change. It is not yet proof
of Mana passive freshness because no accepted native value was published and the
API-before frame was not bracketed by API-after.

## Bounded correction

The native probe should keep immutable owner/type anchors strict while treating
the resource revision, clock and value inputs as one mutable state. A final reread
may be accepted only when:

- owner pointers, record pointer/vtable, descriptor route and resource kind are
  byte-identical;
- each before/final mutable state is internally revision-consistent;
- both resource clocks are finite and nondecreasing;
- the transition is retained explicitly, with no mixed-revision calculation;
- the final coherent state supplies the published candidate and observation time.

Mixed revisions, backward clocks, pointer/type drift or malformed values must
still fail closed. This correction should be implemented and independently
reviewed before another live coordinated attempt.
