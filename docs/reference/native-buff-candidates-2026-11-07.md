# Native buff candidates — November7,2026

The read-only seed command is
`python scripts/sample_current_native_buff_seeds.py --lab lab1`.
It binds the independently looked-up self key/entity, health component+10,
player-system cached entity+3F8, and the same entity's2F57260 context+10. The
embedded circular list sentinel is context+310. Traversal bounds256 nodes,
rejects nonsentinel cycles, rereads consumed fields/owners and revalidates the
exact process/build before publication. No getter, initializer, refcount or
memory writes. Three focused reader cases passed; host rejected broken chains.

## First live seed —13:53:56 Eastern

Lab1 returned **28 raw nodes** in12.2917ms. All28 object/state/clock seeds were
readable. Descriptor DWORD+38 was1 on27 nodes and4 on one. Native Buff.List
excludes kind1 before an additional visibility predicate, so raw node count is
NOT API-visible buff count. The kind4 node had definition-key candidate
2109856446 and raw ID-format candidate`b80000003086737D6`.

Receipt`artifacts/native-buff-seeds-20261107/runs/lab1/a47a249a4bce478e903d6d24c864f5e3/samples.json`,
SHA256`5F8D6632011BCC660B3760DD13F96317471B72BC0CDA3F5BE67FC9382F3DEF69`.
Reader117544800 bytes, SHA256
`3747822638FEC0F1035187C7142E7A7A0AC84B8D9C6100106AE1BF21A2BFD8A2`,
at`artifacts/native-buff-seeds-20261107/publish/`. Exact game SHA remains
1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.
Object VT26BC5C8, descriptor VT28DC6A8 were observed, not fully typed profiles.

## Timer and name leads

Timer is QWORD object+68, whose first qword is its vtable. Observed profiles:

| Count | Timer VT | Duration slot30 | Remaining slot38 | Begin slot48 |
| --- | --- | --- | --- | --- |
|22|26BCE50|72B040|72B3C0|09D680|
|5|26BC950|72AE00|72B3C0|09D680|
|1|26BC9A0|72AE70|72B3C0|09D680|

Static code reads begin float32 timer+18. Remaining is float32 duration minus
float32(clock-begin), without an internal clamp. The wrapper first checks
DWORD`[object+20]+88`==5 for a sentinel; all28 captured raw states were1.
The five/single duration profiles read typed06ED/06CE signed ticks. The22 use a
dynamic property lookup. No timer values or remaining-time semantics have yet
been captured/qualified; do not reuse a casting wrapper's meaning merely because
its leaf getter matches. Trace:`artifacts/discovery-20261107-buffs/buff-clock-profiles.md`.

Ordinary definition lookup uses object DWORD+3C and the SAME ability provider
33624C8/common composite-cache/TLS route. A special0743+110 key can select an
alternate name path. Name decode must remain an ability-definition candidate
until that branch is bound. Native List formats object QWORD+48 as lowercase b
plus16 uppercase hex digits; grouping uses different fields and can aggregate.
Visibility720630 and grouping remain separate qualification work.
Static notes:`artifacts/discovery-20261107-buffs/passive-buff-next-step.md`,
`buff-name-time-next-step.md`, `buff-visibility-next-step.md` in that directory.

## Definition names resolved —14:00 Eastern

The fresh follow-up resolved all22 distinct DWORD+3C keys to typed0051 records
and name candidates while rechecking the complete28-node seed before AND after.
All node order/duplicates/kind1 relationships remain in output; lookup alone is
deduplicated. The kind4 node maps to **Rested**. Kind1 examples include Warlock
Soul Gift, Natural Awareness, Lightning Rod, Healing Balance and Natural Power.
These are ability-definition name candidates;0743+110 alternate name selection
and visibility are not inferred from matching text.

Command:`python scripts/sample_current_native_buff_definitions.py --lab lab1 --seed ABSOLUTE_SEED_SUMMARY_PATH`.
Receipt`artifacts/native-buff-definitions-20261107/runs/lab1/66b24cd5c8a741e989d4bf6ef4f42bb1/summary.json`,
SHA256`DFF1FA6E0F159A4267FBFA515714EDBCB9B558456AFD8992BD22BAA296BCEF9D`.
It pins the374 seed reader andF86 definition reader separately, same VM/game
epoch, source/reader hashes, complete parent-list checks and bounded chunks.
No new publication or input was needed for this named result.

## First timing capture —14:05:41 Eastern

`python scripts/sample_current_native_buff_timing.py --lab lab1` captured all28
finite begins and verified all three referenced types. ClockBefore/After73485.67;
begin57.492565. Six typed06ED/06CE raw tick inputs were0, giving duration0 and
UNCLAMPED remaining candidate-73428.18 at the sampled clock. They are hidden
kind1 nodes; no positive-duration active timer or API publication is demonstrated.
The22 remaining references matched065A object VT28EC200/getter194CCE0/storage
leaf4F180, but duration stayed unavailable in this first published reader.

Receipt`artifacts/native-buff-timing-20261107/runs/lab1/f0e050c9c0c84ebcb88aae21ac79ed74/samples.json`,
SHA256`956D28F826F356DC2455D7F6AD7B506437AE88221CCB4C02709479B002C6093C`.
Reader117552992 bytes, SHA256
`BDE40E279E0E6CB22B167A9A3CF98B425B4380E6BF21B53C78B5AB18D50659FE`,
at`artifacts/native-buff-timing-20261107/publish/`. Six focused reader checks
passed, including signed ticks, sentinel, mutation and reference storage slot.
Old374 seed andF86 definition workflows remain pinned and functional.

Static next field is now applicable to the observed065A profile: float32ref+24,
property`!6b50761c`, index4/kind2, storage base is the object. Initialized
descriptor3462A70/VT28F5968/type method1978670, field303E7E0/VT28ED1E8,
kind/offset methods194DCC0/194DD00, name bytes345DE38 must be verified and
anchored before exposing it. No tick conversion for this profile.

## Loaded field order corrected; both labs pass —14:23 Eastern

The first direct-float reader withheld22 durations. A bounded repeat-bracketed
metadata diagnostic found exactly ONE bad expectation: the loaded table's
index4 referenced Boolean field303E828, while the retained file's index4 held
duration field303E7E0. Every other checked metadata pointer and inline property
name matched. Native lookup SEARCHES the loaded table by name; file ordinal is
not runtime identity. No duration was fabricated from that failed observation.

The corrected reader anchors the complete five unique known descriptors plus
null terminator in ANY order, checks all five ten-byte inline property names,
then retains the exact target type/kind/offset/storage checks. A regression uses
the observed permutation and rejects missing/duplicate fields. Seven focused
checks passed. Diagnostic:
`artifacts/native-buff-timing-20261107/lab1/64162bad7cf546b68770cd3e65d2ab45/summary.json`,
SHA256`DE31C84275B5DBC423AA171DBD709EB86CFFA36F03C1F016C1468F14636EF634`.

Lab1 subsequently captured **28/28** timing candidates, including22 direct065A
floats. All durations were0. Lab2 independently captured **24/24** timing
candidates, also duration0, with24 raw kind1 descriptors and21 distinct
definition-key candidates. These are passive effects, not demonstrated active
positive-duration timers. No API publication/freshness/restart qualification.

- Lab1`artifacts/native-buff-timing-20261107/runs/lab1/2e9669be691c4b01a0ce5ebe61c12105/samples.json`,
  SHA256`BE8C5E414BB468EC2B8E5047186DACD51A41EDD29429E88D197A46B723431B14`.
- Lab2`artifacts/native-buff-timing-20261107/runs/lab2/69c5f7e5f3f14580a9f8e208bf5647f4/samples.json`,
  SHA256`30E470DD7C3CF8E688349366EE14490579C9E159530F12722E02AFECDB62497A`.

Reader117565792 bytes, SHA256
`EAEAC37834DBCEA377BD73BA1974D00432397FCFC03887E70CE152524A2CE060`,
at`artifacts/native-buff-loaded-field-table-20261107/publish/`. All earlier
publications, failed-case receipts and seed/definition workflows remain intact.

## Native visibility candidate —14:19:54 Eastern

The separate visibility command rechecks identical raw seeds before/after and
uses the exact0052 descriptor and three shared config fingerprints. Lab1
returned27 excluded-first-guard rows and ONE predicate-pass candidate:
`b80000003086737D6`. Its typed0743 name-special key differed from the buff's
definition key, proving the ordinary name-source branch. The independent
definition-name observation gives candidate **Rested**, not API/UI agreement.

The native grouping trace keeps the first passing object per composite group
and then deduplicates QWORD+48 IDs. With only one passing object here, grouping
cannot suppress this ID. That supports a sole native List ID candidate for this
snapshot, not a generally qualified API count or freshness claim.

Receipt`artifacts/native-buff-visibility-20261107/runs/lab1/53601925e0414937bc347d9559e1a27f/samples.json`,
SHA256`CC6ADC63786A4BBBD061C9CEC5642422EE00E3AED8C6D536E36F68F8DD199235`.
Reader117565280 bytes, SHA256
`A7C9676FEAE82FC94C7FB7F9C6AC05000C5AB29E69209D8A5D9BE5FCB827B383`,
at`artifacts/native-buff-visibility-20261107/publish/`. Four focused native cases
passed; host rejects an ID leaked from an unresolved row. Stateful/nonempty
qualifier and special-config paths remain unresolved. Static grouping receipt:
`artifacts/discovery-20261107-buffs/buff-list-grouping.md`.

## Lab2 definition followup —14:57 Eastern

After verified clean RRE control return, fresh passive capture preserved all24
raw node relationships before/after and resolved all21 distinct typed0051
definition keys. **11 name candidates**,10 unavailable (key0/missing name child),
not21 names. Examples include Rising Flare, Steady Hand, Rejuvenate, Legacy of
the Shade, Doubleshot, Total Recall, Lucky Penny and the three calling masteries.
All24 descriptorKind values remain1, excluded by the native List path; these
definition names do not establish visible/API-selected buffs.

Receipt`artifacts/native-buff-definitions-20261107/runs/lab2/e43352d04e3e4850be3b113eb3e18198/summary.json`,
SHAA35EFAAB9CC26E6470B6BBDE80F1BB0287159F73840C78B4C496FAF931227CC3.
PID9752/start639294897826627677, pinned game SHA unchanged. The helper now
accepts the verified EAE timing source and reuses that exact reader for seed,
record and dictionary commands; the374/F86 route remains available. Only timing
outputs are excluded from raw-list equality; object/owner/definition anchors stay
exact. No controller restart, queue reset, game input or API/freshness claim.

## Raw caster and stack seed — Lab 1, 2026-11-07

The first read-only `sample-current-buff-details` capture completed at **21:37:24 UTC** for PID `11672`, start ticks `639296016581575957`, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. The receipt is `artifacts/native-buff-details-20261107/runs/lab1/05ca154aa51e4007a25a6f66a301b3c1/samples.json`, SHA-256 `B7EBDECBDC81F9375DD0E66BD19B09E0CB9D8033C368FECEECF5DA8B3DAD2285`. It used the existing C3DD reader cache.

All **28 raw list rows** had a nonzero raw caster key equal to the independently bound self unit key, with formatted candidate `u035400012FA2D678`; no caster was null or zero. All **28 stack paths reported `sentinel`**, with raw getter bits **`0xAB9AACF9`**, state DWORD `1`, and no numeric timer/stack value. The sentinel is an input-path observation, **not an API stack count or proof of API stack omission**. This raw list is not the API-visible or grouped buff list; caster ownership, stack presentation, API correspondence, changed-state freshness and restart behavior remain unqualified. Sequential captures cannot exclude ABA.
