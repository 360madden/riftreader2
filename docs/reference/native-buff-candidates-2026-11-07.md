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
