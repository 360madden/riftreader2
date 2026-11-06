# Native self-key / API player correlation — November 6, 2026

The retained Lab-2 vitals and fresh `RRAPIVAL2` reports contain the same player
identifier in two independently acquired representations. This closes the
previously documented **identifier-format link** for these artifacts, but it is
not a synchronized vitals comparison and does not qualify HP or Energy meaning.

## Exact retained match

Both reports pin RIFT PID `9752`, process-start ticks
`639294897826627677`, and executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

| Source | Native/API value | Canonical bare unit ID |
| --- | --- | --- |
| Native vitals, 10:33:28.701–10:33:28.709 UTC | `unitKey = 239816685224113596` | `u035400012DFEB5BC` |
| Advancing API pair, 12:12:11–12:12:21 UTC | `playerUnitId` | `u035400012DFEB5BC` |

The conversion is deterministic: render the unsigned 64-bit native key as
exactly 16 uppercase hexadecimal digits and prefix `u`. Decimal
`239816685224113596` is hexadecimal `035400012DFEB5BC`. The retained exact-build
parser evidence independently establishes that a bare `u` plus 16 hexadecimal
digits is parsed as that 64-bit key. Dotted unit expressions must not use this
simple conversion.

Source hashes are native vitals `samples.json`
`3E3668875838F49072900C1F6B5DBB291D37157518759A3B9C3E005A909DD743`
and typed-reference assessment `summary.json`
`7D4317ABF51F1FD9762412E97E4ED2274E4E5E364CD5D345E426FC5FC6C43936`.

## What this proves

For the retained reports, the native self-key and independently decoded API
player ID agree exactly under the same process/build epoch. This is stronger
than numeric HP agreement and supplies a practical join key for later paired
observations. The API side also independently advanced sequence
`145708 -> 145727` and source frame time
`74147.8359375 -> 74157.421875`.

It does not prove that the earlier native HP/Energy values correspond to the
later API frame state. The native acquisition precedes the first reference scan
by **5,922.8400349 seconds** (about 98.7 minutes), so there is no declared
pairing window, synchronized clock proof, or bracket around the native sample.
The exact identifier can survive unchanged while resource values change. The
match therefore does not establish changed-state semantics, passive freshness,
continuity, or restart durability.

## Reproducible next comparison

For a qualification attempt, retain the same exact process/build identity and:

1. Acquire an advancing API pair and select its exact bare `playerUnitId`.
2. Acquire the native vitals sample within a declared short host-observed window,
   preserving its `unitKey`, acquisition interval, owner/type rereads, and source
   report hash.
3. Require `"u" + unitKey.ToString("X16") == playerUnitId`; reject dotted IDs,
   process-epoch changes, non-advancing API frames, or a missed time window.
4. For field semantics, repeat around an independently observed HP/resource
   change and require coherent before/after native values. Identifier equality
   alone is not changed-state evidence.

This method needs no new Lua contract and no native getter invocation. The
coordinator still owns any action used to create a resource change.
