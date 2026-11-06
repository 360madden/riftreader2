# Native cast owner follow-up — November 6, 2026

This follow-up tightens the exact-build cast producer boundary and its direct
helper ordering without opening RIFT or invoking native code. It uses the saved
60,493,640-byte executable with SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

## Bounded producer evidence

The PE32+ exception directory assigns producer entry `0x91DED0` to exactly one
unwind range: **`0x91DED0..0x91E2B6`** (end exclusive), with unwind metadata at
`0x2E49B74`. `scripts/scan_native_cast_owner.py` searches only this range for
E8-relative byte patterns that resolve to the retained cast allowlist. The scan
reproduced the following ordered candidates:

| Call site RVA | Target RVA | Retained role |
| ---: | ---: | --- |
| `0x91DF13` | `0x4A4750` | manager |
| `0x91DF2D` | `0x6A0040` | key to entity |
| `0x91DF88` | `0x5A75C0` | component `+0x280` child ID accessor |
| `0x91DF92` | `0x5A7570` | component `+0x290` child ID accessor |
| `0x91DFB0` | `0x5A9940` | smart-reference copy that changes refcount |
| `0x91DFC9` | `0x5A6CB0` | downstream cast-state producer |
| `0x91E093` | `0x49F960` | downstream field helper |
| `0x91E0A4` | `0x49D440` | downstream field helper |
| `0x91E0AB` | `0x49DFE0` | downstream field helper |
| `0x91E148` | `0x49D210` | downstream field helper |
| `0x91E154` | `0x4948E0` | downstream field helper |
| `0x91E1F1` | `0x4A4750` | second manager lookup |
| `0x91E20C` | `0x6A0040` | second key-to-entity lookup |

The first lookup, child-accessor and downstream-helper sequence is followed by a
second manager/key-to-entity sequence inside the same unwind owner. This is a
precise candidate control-flow order; it does **not** prove that the second lookup
is a freshness recheck, or that both sequences operate on the same unit key.
Every reported E8 remains an instruction-boundary candidate in this scanner,
although the prior retained disassembly independently established these helper
relationships. The bounded scanner is useful as a reproducible exact-image
anchor, not as a substitute for instruction decoding.

## Ownership result and remaining timer edge

The strongest supported ownership route remains:

`unit key -> manager -> entity -> dynamic selector 0x2F57260 -> component -> children +0x280/+0x290`.

This is enough for the existing passive topology candidate to expose stable raw
child IDs. It is not enough for semantic cast state. The producer itself calls
`0x5A9940`, which changes a reference count, so an external reader must continue
to avoid invoking the producer or that helper.

The shortest unresolved edge is now concrete: decode the values returned by
`0x5A6CB0`, `0x49F960`, `0x49D440`, `0x49DFE0`, `0x49D210`, and `0x4948E0`, then
map their uses to the caller-owned output buffer before the two Lua castbar
marshallers consume it. Until that def-use trace is complete, no component
offset is supported for `begin`, `duration`, `remaining`, `expired`, `channeled`,
`ability`, or `uninterruptible`. A direct child ID is a producer prerequisite,
not an ability ID or `isCasting` value.

## Verification and limits

The focused cast scanner and passive topology suites pass **9/9** tests. The
scanner rejects a wrong executable before PE parsing, requires one exact unwind
owner, bounds the producer to less than 4 KiB, and keeps the mutating helper
distinct in its allowlist. Python compilation and `git diff --check` also pass.

No live process, VM, guest credential, addon, controller, game input, native
function call, reload, or restart was used. This is static exact-build evidence;
live meaning, changed-state behavior, passive freshness, same-player correlation,
and full-game restart durability remain unqualified.
