# Cooldown static follow-up — 2026-11-06

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
the lookup owner passed to `0x129043C`. Null roots trigger initialization in
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

## Next discriminating work

Resolve the relevant game-thread TLS collection passively, or label an
owner+0x200 snapshot as fallback-only. Reconstruct `0x128CCB0` before treating
a cache miss as absence. Then, under the coordinator's normal
fresh identity and controlled-action gates, compare independent ability/API
observations with bracketed native candidate changes. Full-game restart and
freshness checks remain necessary before any live telemetry claim. This work
performed no game, VM, controller, process-memory or addon operation.
