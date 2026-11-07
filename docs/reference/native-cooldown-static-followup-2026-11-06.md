# Cooldown static follow-up — 2026-11-06

## Public field gate clarified — November7,13:20 Eastern

Detail's5AFEE0 gate first calls5A5E40(context,key,null). For ordinary finite
values it succeeds only when returned timerT is nonzero AND greater than game
clockC. WhenT==0, Detail SKIPS all currentCooldown fields; it does not publish
remaining0. Both retained raw-map baselines have only primary+0.0/secondary-1.0
and empty second maps. They show no active cooldown, not an accepted API result.

After a successful gate, a second producer call returnsT and durationD. Finite
nonpaused field construction uses float32 begin=T-D, remaining=max(T-C,0), and
expired=-remainingRaw only when T-C<0. Begin>1e30 instead emits paused=true and
skips the other setters. Secondary-1 is a sentinel that SKIPS duration replacement,
not a duration. Equality in second-map competition does not replace duration.
The two producer calls can race; no snapshot atomicity is inferred.

Validated public full IDs initially supply their high DWORD as key. A first
primary input of type078A can select a different variant/key before the gate;
empty vector or VERIFIED non078A primary leaves the original key. Unknown type
is not a false078A check. Existing typed0648/0650 primaries cover106 Lab1 and
116 Lab2 rows, without proving all other Detail eligibility branches.

One sufficient49FAB0 eligibility branch checks definition DWORD vector+588/+590
against six initialized global DWORDs3362430/38/40/48/50/58. Match returns true;
nonmatch can enter a player-context branch, so it is not false. Those vector and
initialization inputs were not captured; no per-record eligibility is claimed.
No getters were called. Detailed exact-build trace and retained baseline receipts:
`artifacts/discovery-20261107-cooldown/cooldown-public-value-next-step.md`.

Status: **exact-build instruction evidence, not a live cooldown locator**. This
independent follow-up corrects two incomplete descriptions in
[native-current-client-code-map.md](native-current-client-code-map.md). It does
not establish that any of these objects belongs to the current player, that the
values are deadlines, or that any process memory can be read safely through a
fixed chain.

## Source and reproduction

Read-only copy `artifacts/lab2-rift-exe-20261027-01-copy.exe`, 60,493,640
bytes, SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
PE section mapping and x86-64 Capstone disassembly were applied offline; no code
was executed in RIFT. RVA slices and independent SHA-256 of raw bytes:

| RVA and length | File offset | Slice SHA-256 |
| --- | --- | --- |
| `0x129043C`, `0x138` | `0x128F83C` | `19166b8cfbe3aa3506b10b5dfbb71809fb10fe20785b7e6067813975ec20eefc` |
| `0x5A7450`, `0x100` | `0x5A6850` | `79e47a6d31a8b961b2a8449d519225bfea564568de30e94e673b4010fa885e0f` |
| `0x5A9440`, `0x240` | `0x5A8840` | `df9ab9eeb3e9bdffa852f7f4cc9ca8bef33fd38f7b8054d75d6363ce542415e6` |

These bounded slices are not complete behavioral proof. All offsets and
instructions are specific to this executable hash.

## Result has a separate starting candidate

At `0x5A950E..0x5A9565`, the producer starts with zero, invokes `0x58C790`
with `context+0x1C0`, tests its returned iterator against the collection end,
and on a present entry loads `entry+0x10` into the result register `XMM6`.
At `0x5A9592..0x5A9632`, it iterates 32-bit IDs in the resolved object's
`[+0x4B8,+0x4C0)` span, calls `0x5A7450(context, id)`, and replaces `XMM6`
only when `COMISS`/`JBE` considers the returned value greater. Therefore,
for ordinary ordered finite values, the result is the maximum of the optional
`context+0x1C0` entry's value and the looked-up ID values, with zero as the
initial fallback. It is **not necessarily solely the maximum over the ID vector**.
The entry's key is traced in the November7 section below; its relationship to
the ability remains unresolved. The iterator
comparison and NaN cases must not be simplified into a production reader.

Duration is coupled to branches, not a universal fixed field: the initial duration
uses `0x5A8E00` and conversion; a present initial entry may replace it from
`entry+0x14` or resolved `+0x54` (`0x5A956A..0x5A9590`, `0x5A9662..0x5A9673`);
and a strictly larger ID timer can replace it using the resolved child `+0x18`
(`0x5A95DC..0x5A9610`). Equality does not trigger that last replacement.
No unit or pause semantics are established by this observation.

`0x5A7450` uses a hash-selected bucket: `context+0x240` base, `+0x248` stride,
`+0x250` divisor/count, then checks key at `+0x08` and a low-bit-tagged linked
chain (`0x5A747D..0x5A74E8`); a matched value is at `+0x10`. The hash routine
is an indirect imported call and its full semantics remain unverified. A raw
linear array walk cannot be substituted without more evidence.

## Conditional owner lookup

The wrapper entry is `0x129043C`; its call targets **`0x1290458`**, not
`0x129045C` (the latter is inside an instruction). The callee saves a 16-bit
selector and 32-bit key, calls an indirect function using `owner+0x274`, and
uses the returned collection when non-null or `owner+0x200` otherwise. It calls
`0x128FFA4` with an output hit flag (`0x1290468..0x12904B5`). On miss, it
selects **`owner+0x110` when dword `owner+0x04` is zero**, or **`owner+0x20`
when nonzero**, and calls `0x128CCB0` (`0x12904BB..0x12904E0`). It updates
reference counts and calls `0x128F3D8` against the selected collection before
returning (`0x12904E5..0x1290560`). This behavior is static instruction
analysis: it does not identify those collection types or prove numeric key
provenance. Native calls have side effects and must not be invoked by a reader.

## Key provenance and candidate roots — November 7

The initial `context+0x1C0` map key is now traced: producer `0x5A9440`
saves its incoming EDX at entry RSP+0x10. After its 0xA8-byte stack adjustment,
`0x5A951C` passes that saved DWORD as R8 to `0x58C790` at `0x5A952C`.
The lookup hashes DWORD[R8] and compares entry DWORD+0x08. Thus the initial
key is the producer's original second 32-bit argument.

Caller/selector `0x5A6F20` obtains candidate keys from resolved child DWORD
`+0x18`, through an object's `+0x5F0` reference span. The same key uses resolver
`0x1274AD8`; `0x1353620` tests a resolved first child for type `0x078A`.
This narrows an ability-related keyspace but does not establish public API
`abilityId`, learned/template/variant identity, cooldown units or player ownership.

Two passive root candidates are concrete: `[module+0x33624C8]` returns an
object whose word `+0x40` supplies the selector; `[module+0x3372C18]` supplies
an eight-byte wrapper passed to `0x129043C`. That wrapper's first qword supplies
the actual owner: `0x1290442` executes `mov rcx,[rcx]` before `0x1290458`.
Null roots trigger initialization in
game code, which a reader must never call. Conditional collection traversal
remains unresolved. Bounded exact-build disassembly and call-site details are
retained in `artifacts/discovery-20261107-cooldown/key-provenance.md`.

**Live root observation:** `probe_native_unit_manager.py --lab lab2
--cooldown-roots` completed at `2026-11-07T13:01:40.3337790Z`, exact build above,
PID9752/start639294897826627677. Both root pointers were non-null and selector
was **83**. Roots, selector, player anchors, source and process checks passed.
Receipts: `artifacts/native-unit-manager/lab2/03b0475a18ff461b95184e55b28228d8/`.
`review.json` SHA256 is
`EEE38CD490E89FEA145F061306E739DACC1CB1CC38095BD0CA780DABD892C514`.
This validates the raw root route, not player ownership, ability ID or cooldown.

The indirect collection selector is now identified from the PE import table:
IAT RVA `0x25EF748` is **KERNEL32!TlsGetValue**. Owner DWORD `+0x274` is the
TLS index. The calling game thread's non-null TLS value selects collection C;
otherwise C is owner+0x200. The external reader's own TLS is irrelevant.
Cache C+0x20 uses a selector-word/ID-DWORD composite key, tagged bucket/chain
links and node+0x10 -> result-holder+0x18. A cache miss enters a separate
unreconstructed fallback, so neither a fallback-only scan nor a cache miss
proves an ID absent. No game TLS function or resolver was invoked.

### TLS writer and passive selection

Owner initialization `0x128EF3C` calls TlsAlloc, stores the index at owner+0x274,
then `0x128EF84..0x128EF8D` calls TlsSetValue(index, owner+0x200) for the
initializing thread. Its unchecked return does not establish other threads'
values. Cleanup calls TlsFree and destroys the collection, so its lifetime must
be bracketed. A bounded setter search found no additional owner-linked writer,
but does not exclude indirect writes. Full trace:
`artifacts/discovery-20261107-cooldown/collection-followup.md`.

`--cooldown-collections` queries bounded thread metadata using query-only
Windows handles in a small query executable, then uses the existing exact-epoch native reader for each TEB's
TLS slot. It supports x64 inline and expansion slots, validates TEB self/PID/TID,
and rereads consumed bytes. Before/after thread IDs, creation ticks and TEBs must
match with complete query coverage; roots/selector/TLS index and process identity
are also rechecked. Per-thread non-null TLS selects that pointer; zero selects
owner+0x200. The output observes enumerated threads and does not identify which
one executes the resolver. No target thread is suspended or called.

**SUPERSEDED wrong-owner trial:** Lab2 run
`artifacts/native-unit-manager/lab2/59472c4dca2445daaf8dc87f57d49963/`
completed at `2026-11-07T13:18:26.2367288Z`, PID9752/start639294897826627677,
on the exact build above. Both metadata passes covered all **26 threads** with
no query failures and matching thread ID/start/TEB rows, but incorrectly read
wrapper+0x274 instead of actual owner+0x274. Its observed zero slot values and
computed collection `0x1B0212E6660` DO NOT establish resolver selection. The
Lab1 follow-up `1b0bb8a9ca324babbfa28ef74351a404/` rejected out-of-range
index3866674 at the same wrong offset, exposing the missing dereference.
The chain was corrected before further selection claims. The raw evidence is
retained; neither trial is acceptance evidence. Lab2 `review.json`
SHA256 `F3B90D276D0A02A4F83998E4210F4536AAF108E86454DA0C468656D05E4FEF76`.

The guest's script-file policy refused the first staged PowerShell query before
TLS acquisition (`0a86f0c1c46940aca1881aa3fccdd09e/diagnostic/error.json`).
The working route builds a small .NET Framework console executable on the host,
verifies its SHA before each guest invocation, and leaves that policy intact.
It changes no helper owner or service. Compile/query timeouts and no-overwrite
artifacts remain bounded. The Windows x64 TEB layout is based on the published
[Microsoft TEB structure](https://learn.microsoft.com/en-us/windows/win32/api/winternl/ns-winternl-teb),
with observed self/PID/TID validation; this is not a portable OS-independent layout.

### Corrected live selection — November 7

Lab2 run `artifacts/native-unit-manager/lab2/44b1eeb84b434b6d9c01fd4db810a6a0/`
completed at `2026-11-07T13:23:28.2190105Z` on the same exact game epoch.
Wrapper `0x1B0212E6460` dereferenced to actual owner `0x1B021337AB0`;
the true TLS index was **20**. Thread5604 explicitly held `0x1B021337CB0`,
the owner's embedded collection; the other25 observed threads held zero.
All26 therefore selected the SAME collection. Both complete metadata passes,
TEB identities, TLS/owner/root/header rereads, source and process checks passed.
The selected map header had stride24 and bucket count3444, not 3444 abilities.
`review.json` SHA256
`03D72B81837E0538192BBF0BC7FE86F5B44F5EDBB8FCE522A928F06371A426A3`.
Root independently checked `48 8B 09` at `0x1290442`, the missing owner
dereference. These sequential observations do not exclude ABA or qualify
ability IDs, cooldown math or future collection selections.

Independent Lab1 run
`artifacts/native-unit-manager/lab1/effd113dbaf040fc9d4856abd5c8ec2a/`
completed at `2026-11-07T13:25:06.9925639Z`, PID11672/start639296016581575957,
same exact build. Its true TLS index was also20: one thread held embedded
collection `0x268BF957B20`, and the other27 held zero. All28 selected that
collection. Complete matching thread metadata passes and all byte/source/process
checks passed; map stride24/bucket count3444 matched the shape independently.
This establishes the passive selection route across two current process epochs,
without proving cache-key meaning, cooldown values or full-game restart recovery.

## Next discriminating work

### Accepted raw cache inventory — November 7

`--cooldown-cache` now walks the unanimous selected collection, follows tagged
collision chains and reads nullable result-holder slots. Header H+0x18 is the
current entry count (insertion `0x1294C34` increments it; removal `0x1294B83`
decrements it). Completion requires unique nodes to equal that count, bounded
reads, stable consumed bytes and the usual final owner/process/source checks.
One initial page set is independently recaptured for verification; verification
never reuses initial bytes. Unused padding is not a semantic anchor.

Lab2 `artifacts/native-unit-manager/lab2/d7008a54e6774bacaff7837df90e0a1a/`
completed at `2026-11-07T13:55:17.3240961Z` on PID9752/start639294897826627677,
same exact build: **1162 occupied heads +886 chain nodes =2048 entries**,
matching the bracketed header. Selector83 matched **380 records**,379 with a
non-null result pointer. All thread, TLS, wrapper/owner/header, source and
process checks passed; `threadSelectionVerified=true`. Cache snapshots used
56 pages and7 guest snapshot calls. This is a raw cache inventory, not a
spellbook, player ownership, named ability identity or cooldown reading.
`review.json` SHA256
`A978758603D79F98477EC04C11865947C5AE6530A1D166777F9105946E7BEA6E`.

Earlier per-node reads hit the fixed240s budget; a later paged walk completed
its byte checks but lost a thread before the final TLS reread. Those runs remain
incomplete. The working route batches page reads while separately verifying
the exact node fields. When thread membership changes, the all-thread selection
gate remains unavailable. Only a fully byte-verified **embedded owner+0x200**
inventory may survive as `collection-only-candidate`, with
`threadSelectionVerified=false` and final wrapper/owner/header/process/source
checks still required. A thread-private TLS pointer cannot use that fallback.

Static cache-miss work identified `SELECT value FROM dataset WHERE datasetId = ?
AND datasetKey = ?`, followed by blob materialization. In this observation,
ownerMode0/kind2 selects owner+0x110 with compression enabled: the constructor
can populate this memory store using a conditional SQLite-style backup from
owner+0x20. Compressed values begin with a base128 decoded-size header and a
frequency-derived bitstream, but tree/record decoding remains incomplete.
The current path global was not valid UTF8; adjacent UTF16 assets strings are
not accepted filenames. Retained instruction evidence:
`artifacts/discovery-20261107-cooldown/fallback-followup.md`.

Reacquire owner/thread/TLS selection for each new observation; never retain
these session addresses. Traverse the selected bounded cache and correlate
known candidate keys, while reconstructing `0x128CCB0` before treating
a cache miss as absence. Then, under the coordinator's normal
fresh identity and controlled-action gates, compare independent ability/API
observations with bracketed native candidate changes. Full-game restart and
freshness checks remain necessary before any live telemetry claim. The original
November6 static pass performed no live operation; the November7 captures above
read process memory without game input or owner transitions.

## One-process player-map sampler — November7

The actual player-associated producer context is selected from the self entity
using module selector0x2F57260, not the global definition registry. The cached
entity at `[module+0x33623E0]+0x3F8` must match the independently resolved self
entity. Context+0x1C0 has40-byte buckets; context+0x240 has24-byte buckets.
Both headers include entry counts. Raw node keys/floats and an independently
bracketed, nondecreasing process game clock are exposed as candidates.

The new command reads both maps within one read-only native process:

```powershell
python scripts/sample_current_native_ability_maps.py --lab lab1
python scripts/sample_current_native_ability_maps.py --lab lab2
```

It reuses a SHA-checked per-build guest copy and fresh process/VM identity,
without replacing active reader/controller bundles. Contract:
`native-current-ability-maps-candidate-sample/1`. The new experimental reader
SHA256 is `BF3EFA6508E4AFDE2C0201BF7B193EE5AE7955E5BE6C5A386B9B625BD33979C7`.

| Live run | First/second map entries | Native acquisition |
| --- | --- | --- |
| Lab1 `artifacts/native-map-command-20261107/runs/lab1/b298d5bce2d545c2a4a4fbbfa016f68a/` |122/0|10.013ms|
| Lab2 `artifacts/native-map-command-20261107/runs/lab2/3d71f71a0f2a4f9f8eecf5f1a2af248c/` |134/0|17.146ms|

Both matched the earlier Python captures' context address, keys and primary/
secondary raw float bytes exactly within each process epoch. These durations
are native acquisition windows, not complete VM/tool latency. Raw reports:
Lab1 SHA `227356C0E470311ABB6AFAC11887B29D553CF067533923D53CD1B94D4C74BE2A`;
Lab2 SHA `30E97EA76EBE9B26FA000B5B98FE5FD7004EEE5AACDC74C1882BC22CF3AB2C27`.
Nine focused .NET reader tests and four host validator tests passed. This does
not qualify the raw key sets as learned abilities or the floats as API cooldowns;
the List path additionally resolves typed definitions and filters record+0xC9.
No game input, helper-owner transition, reload or restart was performed.
