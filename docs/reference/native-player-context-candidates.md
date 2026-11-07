# Native self target, level and combat candidates

Updated2026-11-07 at12:14 Eastern. Exact game SHA256:
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

Use `python scripts/sample_current_native_player_context.py --lab lab1|lab2`.
The read-only command reacquires VM/game identity and uses a separate SHA-specific
guest cache. Native command: `sample-current-player-context --pid N
--start-ticks N --output PATH`. No getter, initialization, refcount update,
game input or action-preflight integration is performed.

## 16:05 checkpoint — corrected zone and independent baseline

Earlier zone NULL reports sampled erroneous provider RVA337EBF8 and do not
establish actual provider absence. Corrected RVA336EBF8 passed12 focused tests.
Lab2 `artifacts/native-zone-seed-20261107/runs/lab2/ceb09450de10448ab717c22c93062121/samples.json`
SHA256 `A33DC84C32846EDCA8F31F141B2895AB3460C19ACBFB566EB9AA9D34D36E542D`
reports typed0073 candidate and `z0000000CB7B53FD7`. The retained SC628 decoded
wire document reports the same zone, race `mathosian`, localized raceName
`Mathosian`, calling `rogue`, name `Bolinao`, and level43. Its request identifies
PID9752/start639294897826627677 and the same executable SHA; the independent
native zone sample is later. Decoded document file SHA256 is
`99BEF5BC35CB71A3387C60AC184C15EA87E1547AD3824A0B5774EFCA3AAEA648`, distinct
from receipt payload SHA256 `589AC1AFFFE7026AD7055D90211C504DB1C6248AF63DA5B7638B9A50CD73A774`.
Receipt snapshot/reader/image hashes and request identity were verified. This is
one historical baseline match, not authenticated producer, passive freshness,
changed-state or restart qualification.

## Observed cases

| Target | Numeric level candidate | Raw combat byte | Target-key candidate | Native acquisition |
| --- | ---: | ---: | --- | ---: |
| Lab1 |41|0 / false|`u80000002CD0034D1`|9.375ms|
| Lab2 |43|0 / false|zero key|10.957ms|

Lab1 receipt:
`artifacts/native-player-context-20261107/runs/lab1/22accb18dddb400d99bc0e411d437f73/samples.json`,
SHA256`EBEEBC9410C6AF405E1ABFD3F705CD4222A431FE6D796DD7B27115C5B7462252`.
Lab2 receipt:
`artifacts/native-player-context-20261107/runs/lab2/8f1837b51d774559b6af20d934a1bca0/samples.json`,
SHA256`C8A825A1ACBB52C2EAEE019BF1A2651743A2B8208E7214A5DD1AC2566AA4732A`.
Each has its own PID/start/module/player identity. These are two independent
states on different players, not a controlled target change or combat transition.

## Ownership and branch guards

The existing exact-build player lookup resolves self key/entity and health
component H using selector RVA2F57850. The reader verifies `[H+10]==entity`,
the player-system self key and cached entity, then owner O=`[H+40]` with the
initialized0294 fingerprint: objectVT2927448/getter19D21E0,
descriptor34731B0/VT2929BD0/getter19F4D60. These are module RVAs.
All consumed bytes and lookup ownership are reread; final process validation
precedes publication. The read budget is2MiB.

Combat is BYTE`O+19D`, nonzero=true. Zero is a false predicate; the API builder
can omit the combat field rather than explicitly publishing false.
Raw level is signed DWORD`O+100`. Selector RVA2F58270 absent or its table slot
null permits the numeric getter path. A matching cached self context at
system+400==H additionally supports the numeric presentation candidate. A
nonnull alternate component remains unavailable; the API can separately show`??`.

Target fallback is QWORD`O+20`. This is NOT an unconditional selected-target
field. Selector RVA2F582E0 is distinct from the level selector, and its non-FF
slot immediately selects the fallback. With FF, absent/null selection component
(selector2F57260) also selects it. Otherwise both coherent reference pairs at
selection+280/+288 and+290/+298 must be null. The reader then requires a readable
state at`[H+320]+40`: states outside6..11 select fallback; states6..11 also
require a null reference at selection+2A0/+2A8. Unresolved/active/incoherent
override paths retain only the raw fallback and publish no target-key candidate.
A guarded zero key remains a zero observation. Nonzero GUIDs are lossless uint64
and formatted as16-digit unit IDs; Lab1's key exceeds signed int64.

Nine focused native guard cases passed. Host checks accepted the retained Lab2
receipt and rejected mismatched identity and unresolved-target leakage. The
repository command then completed the independent Lab1 live read. No full-suite
or changed-state/API/restart qualification is claimed.

Reader117450592 bytes, SHA256
`3424206628DC6ABF4E22E1EF16A0653E187618FB3BABE8DF04FF655F1B7CBE9C`,
at`artifacts/native-player-context-20261107/publish/`. Existing active readers
and control ownership were not replaced by this sampler.

## Already-selected target vitals —12:30 Eastern

`python scripts/sample_current_native_selected_target.py --lab lab1` now resolves
the exact guarded target key through the unit-manager hash table and reuses the
existing vitals reader's caller-supplied ownership callback. The default self
vitals reader was not changed. Full64 key comparison, tagged chains, target
health-component back-reference, typed fields and self/target rechecks bind
the nested values. An unresolved/zero target does not produce target vitals;
a target change rejects the capture. No target selection or cache writes occur.

The first Lab1 capture returned target`u80000002CD0034D1`, health candidate
1224100/1224100, in13.2605ms total. Mana/Energy were explicitly unavailable for
its kind. Receipt:
`artifacts/native-selected-target-20261107/runs/lab1/d26d36a5496e4c91b58ff0c3b10c351e/samples.json`,
SHA256`307EDA0EF3086A0EDB21CB2AD15772662F9B481802B92E2B67E89818329B7985`.
The repository command independently passed using the cached reader:
`artifacts/native-selected-target-20261107/runs/lab1/860f7c9e8fe546c2b8d0365e7dba4bfc/samples.json`,
SHA256`9431FF5CA79A2AFC62153C9B4652D04236A1B2CF411207BE4BA2CD07CEFD9A27`.
Stable values across these reads are not changed-state or passive-freshness proof.

Five focused lookup/gate cases passed. Host validation accepted the retained
report and rejected a nested self-key substituted for the target. Reader
117462880 bytes, SHA256
`E6CD3F1D0F9DD6A0072D7E3D2942C07171EB5A4B85B0025AA6FA96FF690F84BC`,
at`artifacts/native-selected-target-20261107/publish/`. No action preflight uses
these candidates. Selected-target names remain a separate uncaptured seed.

## Target name seeds —12:46 Eastern

Name-enabled follow-up at12:46 Eastern: ordered bounded UTF16/localization/virtual
seeds were added without invoking methods. Eight focused cases passed. Lab1's
receipt `artifacts/native-selected-target-20261107/runs/lab1/88de2bc970e749c5ad52e4d9d8d54240/samples.json`
(SHA256`2CEE76E4B0B9A01526AFD674169A1A7774B6CEF0A6729BC1C44CFD4DF50DB3F9`)
preserved health but returned`branch=alternate`, `status=empty-unresolved-fallback`.
No name accepted. Capture entity VT+18 for static analysis; do not call it or
bypass observed branch order. The source primary-direct empty case is different
and does not fall through to localization. Static trace is in
`artifacts/discovery-20261107-cast/unit-name-next-step.md`.
Name-capable reader117471072 bytes, SHA256
`783573AAE552AC5E6BC6977929B4BEBE88A70908E9F0F1E663F550808662597B`,
at`artifacts/native-selected-target-name-20261107/publish/`. The repository launcher
previously pinned it. Eventual text remains a base/locale1 candidate, with API decoration
and language unverified.

## Selected-target position —13:03 Eastern

The repository selected-target command now also reuses the position reader with
an injected exact-target owner. Position selector2F588A0 must resolve on that
same entity and its component+10 must point back to the entity. Missing position
is explicit and does not substitute self XYZ. Target/epoch/consumed bytes are
rechecked. Eighteen position-core and eight target-focused cases passed.

Lab1 returned target`u80000002CD0034D1`, cached XYZ candidate
`7428.7246,863.526,2950.8438`. Receipt:
`artifacts/native-selected-target-20261107/runs/lab1/c993ae87a90142e58134894ed8959750/samples.json`,
SHA256`12639A21472437F19326062994EBA4001A672090D59DA336CC82287123B58189`.
Position interval18:03:12.4428152Z–18:03:12.4432145Z. Reader SHA256
`1960292C6227F8E14C20050EF73FF67E43003F9336D9F93E76AD1CE2591A0046`,
117475168 bytes at`artifacts/native-target-position-20261107/publish/`.
The launcher pins that reader. Cached XYZ semantics, passive freshness and
restart remain unverified; no distance/action readiness is inferred.

The completed independent name-route diagnostic retained target/entity/provider
anchors: entity+1D0 is null, entity+1B8 key1847420318, provider33E3A98 selector623.
Receipt directory`artifacts/native-selected-target-name-20261107/lab1/ddf9cd65a5a84b4289aae0cd782fddb8/`.
Static trace passes that WORD unchanged to the common composite cache. A hit
requires type0274, then+A8 type1E17 name reference. No getter was called and no
name text has been accepted. A cache miss does not imply template absence.

## Template name fallback captured —13:07 Eastern

`python scripts/sample_current_native_target_template_name.py --lab lab1`
completed a guarded template cache hit in34.713ms. Target key/entity, provider
selector623, TLS index20/all-thread collection choice, composite node, record
type0274 and nested name1E17 passed the capture anchors. The typed name has
localization key1290053851 and raw fallback **Normal Practice Dummy**.
Resident dictionary lookup for that key missed. Raw fallback is exposed
separately; no active manager branch, locale1 text or API-decoration agreement
is inferred. This is useful name input, not a public-name qualification.

Receipt`artifacts/native-target-template-name-20261107/runs/lab1/9a6ac42b49ad4d519ae7c3cbebda5306/samples.json`,
SHA256`60C2053E175017C83652B7496421D5691BD404B9DA1643EDF80DB27E05AD2A14`.
Reader117491552 bytes, SHA256
`2390DB519546D4884E14D7B00DD78257740104808792E15B8C58F1E57F9806FD`.
Four focused native cases passed; host validation and retained-receipt decode
checks passed. A cache miss never establishes name absence. No getters/input.

## Name branch selected —13:11 Eastern

Follow-up captured/rechecked localization manager DWORD+4==1 and global DWORD
module+3373784==0. Static7DD960 selects the nonempty typed fallback in mode1;
7D1A80 bypasses its later string formatting when that flag is zero. Thus
**Normal Practice Dummy** is now a selected base-name candidate, independent of
the resident dictionary miss. No native methods were invoked. API/UI agreement,
changed-state, passive freshness and restart are still unverified.

Receipt`artifacts/native-target-template-name-20261107/runs/lab1/ef16c6ed167d4b6bbbe8655d84c42b56/samples.json`,
SHA256`934E6EB33CAA2EE1F6EE12B93D2774444933E1C6AE14D47A91A5D6D31CA64F94`,
capture36.257ms. Reader117496160 bytes, SHA256
`4B481314B7E72B83CB8F5163D895818236E1C1B4E48FEFD2C6C56B66BCB1BB0F`,
at`artifacts/native-target-template-name-mode-20261107/publish/`. Five focused
native checks passed, including changed formatting-flag rejection.

## Target raw context —13:13 Eastern

Optional target context resolved `[targetHealth+40]` and passed the exact0294
object/getter/initialized-descriptor fingerprint. Raw signed owner+100 was0;
raw combat byte+19D was0 (candidate predicate false). The reader retains typed
raw inputs only: the generic level getter can choose an alternate component,
and the target's public level/presentation is not inferred from zero. Six focused
cases passed, including mutated payload rejection and unavailable preservation.

Receipt`artifacts/native-selected-target-20261107/runs/lab1/56d78bd7aa174f48b7048931ef962071/samples.json`,
SHA256`93E3F4260B084ADE7DD883A60B44B50FE8EB029E34515814B1F6ACBFF99346BC`.
Existing target HP/XYZ capture remained available. Reader117495648 bytes, SHA256
`5843EF6E58EA0E43CB3C08732934561476D3E726FF367E3C2DAC9B6BF19CD803`,
at`artifacts/native-target-context-20261107/publish/`. No self-owner substitution,
public combat/level agreement, input, passive freshness or restart claim.

## Target numeric level branch —13:18 Eastern

Fresh target level selector2F58270 resolved a nonnull alternate component.
Its primary pointer+64 value was-1, selecting secondary pointer+64, which
returned **50**. This is a numeric-getter candidate; target public presentation
may still differ. Raw0294 owner level remains0 and combat byte0. The reader
brackets the selector, entity slot/table, alternate pointers/values and usual
target identity; unreadable level leaves an explicit unavailable result.

Receipt`artifacts/native-selected-target-20261107/runs/lab1/6ad64e06cec24fbfa2e06122d2127728/samples.json`,
SHA256`E2864EF9D935DDA3EE266B886DC31CF6EA51457039E6F68C1A6C21BB12DEEC8B`.
Eight focused cases passed, including alternate primary/secondary and mutation.
Reader117499744 bytes, SHA256
`6479EF0959FA6BE36B3B27D0586DE8C0E1625E0011DED53FCFECD2226674F970`,
at`artifacts/native-target-level-20261107/publish/`. No input or getter calls.

## Self name and zone seed —14:57 Eastern, November7

Fresh Lab1 direct-name branch yielded **Trio**, raw decorationDWORD1704, with
independent self/health/owner and consumed-byte rechecks. The name reader is the
existing selected-target branch logic shared unchanged with the new self command;
nine focused self/target cases passed. This is an undecorated base-name candidate,
not API/shard agreement. Receipt
`artifacts/native-player-name-20261107/runs/lab1/520a0de19ed14a94b814b048e01a9f25/samples.json`,
SHABF900EA2052A26FEAA70783A9531109CED084A83186D8BCECB94A972276CDB6B.
PID11672/start639296016581575957; same pinned game SHA as above. Reader
0E7014C8CAA14F0D09152EDD856E55615CEF02EC29941B5D9897B319D28E4142,
117589856 bytes,`artifacts/native-player-name-20261107/publish/`.

Zone source is typed0294 owner+150. Lab1 raw key1216123138 and Lab2 raw key12
were captured while reading the WRONG provider RVA337EBF8. On15:53 the exact
producer's four references proved336EBF8; the earlier NULL results do not
establish actual provider absence. Raw owner keys remain supported. No
initializer/getter was called. The typed0073/hash route originally had seven
focused synthetic cases but no live typed hit. Lab1 receipt
`artifacts/native-zone-seed-20261107/runs/lab1/52956b1b9c3047008325a19d53ebb876/samples.json`,
SHA007294609B8EFDF7D82DEA876E89A2A0FFD6DF93498CA014BEAF125309EC2460;
Lab2`runs/lab2/fc869831d4af40fd9c0d39795874e436/samples.json`,
SHA142161FA963807DA74EC24FBF7F0F24F18E3D788DD2F7DDBDD6CFB65BFBDE864.
The corrected A96508FE963E4DFDE6EABD50889FD0432A72C0309AEC562E35CBF87B584F49D9
reader (117704544 bytes, native-zone-provider-fix-20261107/publish) passed12
focused cases including a wrong-address trap; its first capture succeeded below.
Do not equate raw keys across worlds or assume API correspondence. Full-game
restart/freshness remain unverified. Keep wrong-address receipts as superseded
evidence, not cold-provider findings.

Lab2 independent self-name read also yielded **Bolinao**, direct branch/raw
decoration1704. Receipt
`artifacts/native-player-name-20261107/runs/lab2/ba92ad859fe54d4caba95bdd137a9ce1/samples.json`,
SHA1AEDC1655637E05CC69959363F2C96EE442C2DC8A4A8A976BBA897736AA728EF.
PID9752/start639294897826627677, same game and name-reader SHA. No API/shard
agreement is established by matching a previously reported human-readable name.

## Calling source —15:00 Eastern

Unit.Detail9BA078 uses5E36D0 to read DWORD[typed0294owner+168]; formatterA0E100
maps1warrior,2cleric,3mage,4rogue,7primalist. Unknown values stay unmapped.
The existing self-context reader now exposes that anchored field and mapping.
Lab1 raw3 gave **mage** in9.17ms with usual self/owner/process rechecks. Receipt
`artifacts/native-player-calling-20261107/runs/lab1/b8f791e2937c4cf2909261eb3b084a1d/samples.json`,
SHA9140D2BCE87C54F352D64D9A90B7674554C4BFB91EE13F08B65BC971F6FF84C9.
Reader1C57C5311062CF6F41E6492AF988BC2378A29E52BC6D84A4FA1E10600BADC654,
117589856 bytes,`artifacts/native-player-calling-20261107/publish/`.
Sixteen focused cases include known/unknown mapping and mutation rejection.
Lab2 independent raw4 mapped to **rogue** in15.05ms. Receipt
`artifacts/native-player-calling-20261107/runs/lab2/e2eec314d6f54f2ea328afe503983c31/samples.json`,
SHA576604D27F6BA842C8375AAD4235714C35CCE2B32A53E1F89E7245F03DC41A2A.
Lab2 target stayed guarded zero; Lab1 selected target remained separate.
Static producer correspondence is not independent current API/UI comparison,
changed-state freshness or restart acceptance. No resource-availability inference.

## Raw race-referent seed —15:02 Eastern

Lab1 independently bound H+48 yielded raw DWORD+30 key1, referent vtable
module+0x2A75CA8 and getterRVA0x1CD58F0 (raw fingerprints, type unknown).
Race provider336F1F8 is resident; its typed0718 cache lookup/text is the next
bounded read. Do not interpret key1 as a race name. Receipt
`artifacts/native-player-race-20261107/runs/lab1/9009e7b1f7fd4331b7dcfc812c4e7418/samples.json`,
SHA5F1E8E1002AB32520179FDD88F17070EA44440A42E1C944498626DC4948B263C.
Raw readerAFA473BD8C69B0AE6D8BE9D2BD781E375007512703ADD6DC27DFD2EBC2664B58,
117602144 bytes,`artifacts/native-player-race-20261107/publish/`.
Three focused cases cover self mismatch/null/mutation. No race type/text/API,
freshness or restart qualification; no native getter/refcount/write performed.

## Typed race token and current shard name —15:17 Eastern

Both labs yielded raw key1 through the resident race provider336F1F8, selector1817,
TLSindex20 and profile-verified0718 record: text candidate **mathosian**. This is
separate from localized raceName. The observed referent's static type is0282;
the sampler still labels it raw rather than assuming its type. All consumed
provider/cache/text anchors and final self/context/thread epochs were checked.
Nine focused race cases cover the added localized seed as well. Lab1's localized
seed subsequently captured mode1, typed1E17 key74456494, empty fallback and a
dictionary locale1 candidate **Mathosian**. Public raceName remains unverified.
Receipt`artifacts/native-player-race-localized-20261107/runs/lab1/4077f295a39a4e4d9365ec56ec561a84/samples.json`,
SHA28436A4DA1EDF093C521118FB9F4D547408EFAC20AA75CD77683645309747DD3.

- Lab1`artifacts/native-player-race-name-20261107/runs/lab1/4a9250e7d74b4b269040861687052a97/samples.json`,
  SHAD2D3848FE97D64F2B29919F8FC70AAEA5512C5030328377A07B80054C5C46C20.
- Lab2`artifacts/native-player-race-name-20261107/runs/lab2/72629ea30ce54a63a540b727129cb87b/samples.json`,
  SHA97961E9AB0E42E974FAB0F9A929976C64A5C6460E97764B8182D065F8E3DE42C.

Reader3DAD7030355FB1694538BEBE6CA91153294C3A25D54B82393319EC58B83CD43D,
117618528 bytes,`artifacts/native-player-race-name-final-20261107/publish/`.
Current source also exposes raw localized key/fallback/dictionary inputs via
separate594D9D9E07EB86B0D928842B4A572863D2EC03D54DEA7937BD03BAD881B40184,
117630816 bytes,`artifacts/native-player-race-localized-20261107/publish/`.

Static registration9B3A6D..9B3AA9 binds Inspect_Shard to9B4230; it reads manager
key+46C and map+4B8 via552630 and emits name/pvp/rp. This proves the named
producer route, independently of a historical documentation field-shape match.
Fresh bounded name lookup yielded **Deepwood** in BOTH labs, raw lookup key1704.
This key is not a documented public shard ID. Three focused shard cases passed.

- Lab1`artifacts/native-current-shard-20261107/runs/lab1/225c92dde56a4f93b64e5187a09884d5/samples.json`,
  SHA429A521DE98B75E50BF01F0999A547BBE30547A3881274C69C348BCFF7CC750E.
- Lab2`artifacts/native-current-shard-20261107/runs/lab2/b9fdcd771ffe4962b959c9b6ff5cb955/samples.json`,
  SHA7836DAE6DB91ECE257B092FF4CE6F24875933E46D442573DFE6AEE2BAEDCC0A2.

Shard readerD44A45B15BE5592BD3BD56A9C7BB7606BA0D0F675AA3B0230DA409BE5C1C49CD,
117626720 bytes,`artifacts/native-current-shard-20261107/publish/`.
Lab1's separate decoration read found1704==manager1704, so producer adds no
suffix; it did not look up or fabricate decoration text. Receipt
`artifacts/native-player-decoration-20261107/runs/lab1/4cffbcb84955418cbd34295d874cd3a5/samples.json`,
SHA4F2D28C8ED948848ABAD68D31A90297BB2844821D8FB69C14EF821C280B9D940.
Decoration reader04BE241818DEC5057180B55C0AEEF45AAFA248F1C4940378D2A02C08E7A28E07,
117610336 bytes;3 focused cases. No game input/init/getter/refcount writes.
Independent current API/UI agreement, passive freshness and restart remain open.

## Experience raw seed —15:20 Eastern

Lab2's independent self/health/component back-references, owner/vector and selected
record anchors passed. Owner observed VT2A46738/getter1C48CC0 has static type02AE;
selected VT2BD4388/getter201A050 has static type0736. Index0 selects the first
of40 raw reference entries. Raw int64+18=3507422, DWORD+24=43, float+20=0,
ownerDWORD+160=3. These are inputs, **not current XP, cap or rested amounts**.
The needed dataset, cap profile and baseline calculation are a separate next read.

Receipt`artifacts/native-experience-seed-20261107/runs/lab2/29fdbbd8eb3e45b0ada03664b9d25349/samples.json`,
SHACA045A66681C1038EC713AACADED1BDE828C44D8BB8FFA152793AC3C0A8DF918.
Reader723C499D90FA10B02AC22E85441DE132E525650178DA4CF841C73C9B6781448E,
117647200 bytes,`artifacts/native-experience-seed-20261107/publish/`.
Two focused cases cover the plain branch and mutation rejection; special index-1
is emitted as raw pointers, never guessed as an empty progress list. No native
getter/refcount/write/API call, freshness or restart acceptance.

## RRE historical reference —15:19 Eastern

Joey explicitly authorized direct cross-chat coordination. RRE supplied
`C:\work\rre\artifacts\rre-rr2-reference-20261107-1512\api-reference.json`,
SHAD26FE63D90BD8D6B1A71E18C7DBD27B9192DF01A4BB4F1DD98B4A90081CE8420.
RR2 verified all7 retained source hashes, self/session/sequence and54 ability
rows/10 field-presence counts without discrepancies. Verification:
`artifacts/rre-peer-reference-20261107/verification.json`.
Seq5 manual image clock14:38:30 Eastern, snapshot19:43:07.529..626Z, same Lab2
PID/start/build: Bolinao/rogue/43. Race/raceName/zone/decoration were NOT PROJECTED;
absence in that document is not API absence. This is historical consistency,
not current native/API agreement or advancing freshness. New RRE field expansion
needs a separately granted exclusive window; none granted at this checkpoint.

## Optional UI comparison stopped

The first Lab2 screenshot attempt was rejected before admission because its
output path was outside the helper's canonical directory. The corrected attempt
stopped during dependency admission with SessionError after30.26s, before capture
or a screenshot lease: `artifacts/e2e-latency-20261106/lab2-context-1794071148899/run-failure.json`.
No image or UI agreement was accepted. No accepted recovery/task receipt was
retained. Later read-only status showed connected/disarmed-idle, supervisor
initial cleanup verified and an existing console reservation held; it was not
cleared. Do not turn optional screenshot recovery into a discovery prerequisite.

Static source details are retained in
`artifacts/discovery-20261107-cast/player-context-triad-next-step.md`.
The raw definition condition4 consumer uses the same combat getter: when its
EFFECTIVE vector contains4 it rejects nonzero combat. Context can replace the
definition vector; raw4 alone is not overall eligibility. See
`artifacts/discovery-20261107-cast/ability-condition-next-step.md`.
