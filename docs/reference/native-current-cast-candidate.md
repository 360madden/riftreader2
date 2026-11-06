# Passive cast topology candidate — November 6, 2026

P5 delivers a small offline-testable passive topology reader in
`scripts/native_cast_candidate.py`. It accepts an existing identity-pinned memory
read callback and the entity resolved by the common player-key lookup; it opens
no process and invokes no game function. It is not wired into a live command.

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
Downstream functions `0x5A6CB0`, `0x49F960`, `0x49D440`, `0x49DFE0`,
`0x49D210`, `0x4948E0` remain the targeted static follow-up. Casting addon's
`Inspect.Unit.Castbar` observation omits `uninterruptible`, so independent flag
validation needs another reference.

## Checks and next useful use

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
