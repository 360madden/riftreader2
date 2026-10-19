# Nonce-bound addon transport contract, version 1

Status: implemented and verified in one identified RIFT-Lab session. See the
[live transport record](../../docs/validation/live-transport-2026-10-18.md).

This contract binds the existing RR2A1 observation frame to one reader-created
addon-load handshake. It preserves the complete
[observation contract](README.md) as an opaque inner frame.

## Wrapper

One exact ASCII wrapper has this form:

```text
RR2L1|<reader nonce>|<complete RR2A1 frame>|ENDRR2L1
```

- The reader nonce is exactly 32 lowercase hexadecimal ASCII characters.
- The inner value is one complete, unchanged RR2A1 schema-1 frame, including its
  `RR2A1|` and `|ENDRR2A1` markers.
- Bytes outside the outer markers, truncation, concatenation, malformed nonce,
  and malformed or unsupported inner frames fail closed.
- The wrapper adds binding evidence; it does not authenticate the addon, game,
  process, or executable.

The existing RR2A1 decoder and semantics remain unchanged. API fields remain
addon references rather than native evidence or derived motion.

Offline validation uses:

```text
decode-live-addon --frame PATH --session-id HEX [--output PATH]
```

`--session-id` supplies the expected 32-hex reader nonce. Decoding proves exact
framing, nonce equality, and inner-contract validity only. Offline output remains
source-unbound and freshness-unverified.

## Binding lifecycle

The external reader generates a new nonce and submits it through:

```text
/rr2bind <nonce>
```

The addon accepts one nonce per load and publishes nonce-wrapped frames for that
binding. A UI reload clears the binding. The reader must generate and submit a
new nonce after reload; it must not carry the old nonce or freshness state into
the new load.

A reader may treat a wrapper as belonging to its handshake only after validating
the exact nonce and the complete inner contract. Freshness additionally requires
advancing observations and receiver-side timing within one stable target process
and binding. A nonce match or one valid wrapper alone is insufficient. Process
change, reload, nonce conflict, regression, malformed data, or expiry invalidates
the binding and requires a new handshake.

Exact age policy and transport-specific process identity belong to the reader
configuration and validation evidence, not the Lua observation schema.

The current Windows reader scans only its declared readable, committed
`MEM_PRIVATE` domain. A scan is complete only when that entire planned domain
finishes within all configured byte, time, read, map, candidate, and region
budgets. Incomplete scans cannot produce a fresh observation. Malformed byte
ranges are counted and rejected without advancing freshness. Unrelated garbage
or freed Lua strings do not invalidate an otherwise unique strict match; no
valid match is unavailable, and fully valid same-sequence conflicts invalidate.

Target executable SHA-256 identifies the file at the process MainModule path,
with PID, start time, and path checked around hashing. It does not prove the
already-loaded module bytes. Freshness age and remaining budget are computed in
the guest reader on each result. Any external receiver is delivery-only; receipt
alone never establishes freshness or game readiness.

## Ownership

- Lua owns the bounded RR2A1 producer, one-load bind command, and RR2L1 wrapper.
- Application analysis owns strict wrapper decoding and freshness tracking.
- Windows I/O owns read-only acquisition and a standalone guest-side collector.
  It may reuse the existing V1 HTTP receiver as an external transport component,
  but the wrapper contract does not depend on that receiver.

The original V1 loopback console tooling is test and lab infrastructure, not
part of the RiftReader2 runtime contract.

## Verified evidence and future qualification

The retained gate covers exact framing, nonce mismatch, stale replay, conflict,
regression, reload clearing, reader restart, advancement, expiry, malformed
input, output provenance, the actual Lua producer, the .NET decoder/tracker, and
one guest-to-host delivery path. RIFT process restart, VM power cycle, loaded
module verification, and production remote consumption remain separate future
qualifications.
