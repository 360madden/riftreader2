# Passive cast topology candidate — November 6, 2026

P5 delivers a small offline-testable passive topology reader in
`scripts/native_cast_candidate.py`. It accepts an existing identity-pinned memory
read callback and the entity resolved by the common player-key lookup; it opens
no process and invokes no game function. It is now wired into the existing
player probe through `--cast-record`; both-lab raw capture is recorded below.

## Ownership and available inputs

The [existing exact-build code map](native-current-client-code-map.md#verified-exceptionunwind-ranges-and-value-producer-clues)
records the retained November 1 disassembly: castbar marshallers `0x9B8300` and
`0x9B86B0` pass a unit key from `0xA1AAA0` to producer `0x91DED0`; this resolves
manager `0x4A4750`, key-to-entity `0x6A0040`, and dynamic component selector at
module RVA `0x2F57260`. The common probe already implements the corresponding
entity component-table layout (`probe_native_unit_manager.py`, entity slot
`+0x18+index`, table pointer `+0x78`, slot stride eight). This slice reuses the
resolved entity boundary rather than adding a competing player lookup.

| Passive input | Supported interpretation |
| --- | --- |
| Signed selector at module `+0x2F57260` | Component index, conservatively bounded to `0..0x5F` like the existing probe |
| Entity byte `+0x18+index` | Component slot; `0xFF` is absent |
| Entity pointer `+0x78`, then table `+slot*8` | Cast-associated component candidate |
| Nullable pointer at component `+0x280` | First child; accessor `0x5A75C0` obtains its DWORD `+8` via `0x58B30` |
| Nullable pointer at component `+0x290` | Second child; accessor `0x5A7570` obtains the same-shaped DWORD |
| Either child DWORD nonzero | Producer prerequisite, **not** established `isCasting`, ability identity, or cast phase |
| Component DWORD `+0x2B8` | Copied to producer output `+0x3C`; unknown semantics, read and rechecked as `rawComponentDword2B8` |

`0x5A9940` copies a smart reference from `+0x280/+0x288` and changes a reference
count. The new code only reads the pointer, never calls this helper or copies its
mutation. It preserves the two child IDs independently and rechecks every read
anchor after acquisition. Changed pointers/IDs discard the partial record and
return explicit unavailable status. Stable bytes do not exclude ABA changes.

## Explicit limits and state hypotheses

`candidate-component-absent` and `candidate-no-nonzero-child` report raw absence
and zero observations. Neither is qualified semantic idle. A nonzero child is
`candidate-nonzero-child`; `isCasting`, `begin`, `duration`, `remaining` and
`uninterruptible` stay null. No synthetic fixture is labeled an actual cast.

Start, progress and stop require a synchronized changed-state series on the
same independently identified unit. A zero-to-nonzero transition is only a start
hypothesis; unchanged IDs while time passes cannot establish progress; a return
to zero is only a stop hypothesis. Existing retained native evidence does not
identify passive timer/flag input offsets, component type/vtable, or distinguish
channeling, queued abilities, completed casts, interruption and cache retention.
November7 disassembly narrowed the selected-child floats: producer uses first
child `+0x30` or fallback child `+0x34` and game-clock float
`*(module+0x33DC2B0)+0x18` in `duration - (clock - selected_float)`. This is
a start-time candidate, not a qualified timer field. Duration remains virtual
through child `+0x20/+0x28`, not a direct passive offset. Fallback selection
also depends on the `+0x298` control pointer. The retained trace is
`artifacts/discovery-20261107-cast/static-followup.md`; never call the smart
reference or virtual helpers. Both castbar marshaller paths map producer
output `+0x28` to named `begin`, `+0x30` to `duration`, and `+0x2C` to
`remaining` (clamped at zero, with negative values also feeding `expired`).
The raw `+0x2B8` DWORD goes to output `+0x3C`, which has no direct read in
either decoded marshaller; `abilityNew` uses DISTINCT output `+0x40`.
These static mappings are not live changed-state qualification. Casting addon's
`Inspect.Unit.Castbar` observation omits `uninterruptible`, so independent flag
validation needs another reference.

The `abilityNew` input now traces to the selected child's DWORD `+8`, after
the child-ID gate and a nested-pointer guard: child must be non-null and
`byte(*(child+0x10)+0xC8)` must be zero. First child wins when present;
fallback requires the second reference's control pointer. The producer's
`0x58B30` leaf reads the DWORD, and the marshaller performs another lookup
(`0x49FA20`) before emitting abilityNew. Existing raw IDs are therefore
candidate keys only under this selection/guard, not arbitrary qualified ability
IDs. No reader invokes these functions.

## Checks and next useful use

### First live capture — November 7

`probe_native_unit_manager.py --lab lab2 --cast-record` now supplies this
helper from the existing identity-pinned read session and brackets it with the
probe's player/entity/root and final process checks. The first run completed at
`2026-11-07T12:54:58.1959684Z`, PID9752/start639294897826627677, on the exact
build above. Native self key `u035400012DFEB5BC` resolved entity
`0x1B0693C1410`; selector0/slot0 selected component `0x1B0793AE810`. Both
`+0x280` and `+0x290` child pointers were zero. Anchor rereads and source
stability checks passed; output is `candidate-no-nonzero-child`, with all
semantic cast/timer fields still null. These are session addresses, not locators.

Raw receipts: `artifacts/native-unit-manager/lab2/001cf7a517da4dc38971a0041e1f05b8/`;
`review.json` SHA256
`38292BDB6D178B73C99636A14E6EB51A8AA919DF8E8F36CAC70F9D660C238C95`.
An earlier fresh screenshot/native-vitals pair in
`artifacts/e2e-latency-20261106/discovery-1794055884095/` showed the AFK player
and HP10635/10635, Energy100/100. It is context, not a simultaneous independent
cast observation. No game input, addon bind/reload, restart or ownership change
occurred. This establishes a working live raw topology read, not idle/casting,
changed-state, passive freshness or restart qualification.

An independent Lab1 run completed at `2026-11-07T13:00:03.8395761Z`,
PID11672/start639296016581575957, same build, native self key
`u035400012FA2D678`. It also found selector0/slot0 with both child pointers
null; source stability, process and ownership checks passed. Receipts are in
`artifacts/native-unit-manager/lab1/3c1fb6acef4f4f6c9aa7098532d49d99/`.
This checks the raw locating route on a second player/process, without
establishing cast semantics or full-game restart recovery.

A follow-up Lab2 capture completed at `2026-11-07T13:04:16.0835872Z` in the
same pinned game epoch: `rawComponentDword2B8=0`, both child pointers null,
all bracketed anchors and source checks passed. Receipts:
`artifacts/native-unit-manager/lab2/b2d1ef50f22049c8a94030dd7aa21ecd/`.
The helper now retains this unknown raw field and clears it if any consumed
anchor changes. Seven focused helper cases passed, including raw-field mutation
rejection; no full suite was run for this small discovery slice.

On November 6 the physical installed executable was read-only SHA-256 checked:
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, matching
the existing map. No new instruction disassembly, live memory acquisition,
gameplay input, binding, reload or restart was performed. This work's ownership
claims derive from that existing map, not a newly verified live component.

Seven focused unittest cases passed: raw nonzero without semantic promotion,
zero without idle promotion, absent slot without component reads, wrong build
without reads, selector/pointer rejection, changed ID/owner rejection and short
read failure. These are synthetic failure/arithmetic-layout checks, not native
semantic or restart qualification.

The coordinator can supply the existing exact-PID/start/SHA read session, add
acquisition timestamps and process/player identity to its normal sample envelope,
resolve/recheck entity ownership on both sides, and collect this bounded raw
topology. The standalone helper cannot establish epoch/player ownership from an
arbitrary callback. Full-game restart and passive freshness remain separate
qualification work. No new Lua producer dependency is required.
