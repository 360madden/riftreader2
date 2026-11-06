# Ability owner follow-up — November 6, 2026

Status: **exact-build static ownership recipe, not a live ability reader**. This
follow-up reconciles the ability lookup described in
[the earlier ownership finding](native-ability-ownership-findings-2026-11-06.md)
with the independently decoded conditional lookup in
[the cooldown follow-up](native-cooldown-static-followup-2026-11-06.md). No game,
VM, process-memory, addon, input or native-function operation was performed.

## Resolved owner edge

The marshaller route is now bounded as follows for executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`:

1. `0x995E10` supplies its parsed 32-bit ability-like key to `0x54EB00`.
2. `0x54EB00` uses module context `+0x33624C8`; `0x1274AD8` uses registry
   `+0x3372C18`, the context's 16-bit selector at `+0x40`, and the 32-bit key.
3. Wrapper `0x129043C` delegates to `0x1290458`. The callee first obtains a
   collection through the indirect operation associated with `owner+0x274`,
   falling back to `owner+0x200` when that result is null. It queries this route
   through `0x128FFA4` with selector/key inputs.
4. On a miss, it selects `owner+0x110` when `DWORD(owner+0x04) == 0`, or
   `owner+0x20` when nonzero, and calls `0x128CCB0`. Both paths include native
   reference-management behavior and therefore must be reconstructed through
   passive reads rather than invoked by an external reader.
5. `0x18A3750` accepts only outer type fingerprint `0x0051` before publishing
   the caller-owned reference. The marshaller later enumerates that record's
   `+0x6D0` vector in eight-byte reference slots and dispatches child types
   `0x1E29`, `0x1E2A` and `0x1E2C` for Power, Mana and Energy cost production.

This closes the earlier ambiguity that treated `owner+0x200` as the lookup root.
It is only one fallback inside a two-stage conditional lookup. The outer ability
record type `0x0051`, child cost types and player resource types `0x072A/0x072B`
remain distinct.

## What the route establishes

The shortest supported passive recipe is now:

`module context -> registry -> selector + ability-like key -> primary/fallback
collection lookup -> type-0x0051 outer record -> +0x6D0 child-reference vector`.

This is a locating recipe for a record used by the native detail marshaller. It
does not show spellbook membership, ownership by the current player, the public
meaning of the numeric key, or a player-adjusted cost. The key enters through the
marshaller's argument parsing, so its presence alone cannot distinguish a known
ability from an arbitrary detail request. Cost calculation also consumes a
separate context obtained through `0x49A020` / `0x49A440`.

## Remaining discriminating edge

The marshaller calls `0x49FAB0` after the type-checked lookup and before it uses
the separate cost context. Retained unwind metadata places this routine across
adjacent ranges beginning `0x49FAB0`, `0x49FAD7`, `0x49FC78` and `0x49FCD4`.
The first range is only a prologue; treating it as the full routine would be a
false truncation. Its exact-build first-range bytes hash to
`c5e22fa5ae74a02507b89e43738b1fa3f7ace8a27e1d3901c8bca108cd11d915`.

A bounded REA instruction request for `0x49FAB0` opened and verified the exact
PE identity but returned no function result before the two-minute coordinator
budget. The request was stopped and the session closed. This is a provider
performance limit, not evidence that the function is absent or inert.

Until `0x49FAB0` is decoded, a passive reader must not assume the type-`0x0051`
reference remains unchanged before `+0x6D0` enumeration. The next useful static
step is bounded local disassembly of the chained ranges, followed by a retained
fixture that checks both collection branches and the outer type gate. Only then
does an identity-pinned, read-only ability-record inspector become justified.
Live semantic qualification still needs an independent same-ability reference,
a coordinator-owned controlled change, freshness evidence and restart recovery.
