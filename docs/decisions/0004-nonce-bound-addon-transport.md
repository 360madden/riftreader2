# 0004: Nonce-bound addon transport

Status: accepted, implemented, and verified in one identified RIFT-Lab session.

Date: 2026-10-18.

Authorized by: Joey explicitly requested actual-client validation followed by a
minimal live transport with reliable reload/session freshness. He authorized
reuse of the original V1 lab console path for this controlled validation.

## Context

The version-1 addon observation is now proven to load and advance in one
identified RIFT-Lab session. Its bare `RiftReader2_Frame` remains an unbound Lua
publication surface: local sequence and epoch can repeat after reload, and one
valid frame cannot identify the reader, process, or addon load.

## Decision

Preserve RR2A1 unchanged and wrap it in the versioned
[RR2L1 contract](../../contracts/addon/live-transport-v1.md). The external reader
creates a fresh 32-lowercase-hex-character nonce. The addon command
`/rr2bind <nonce>`
accepts one binding per load. UI reload clears the binding and requires a newly
generated reader nonce.

The RR2L1 envelope has its own version; it does not change the inner RR2A1
`addonVersion` 0.1.0 contract. Its offline validation command is
`decode-live-addon --frame PATH --session-id HEX [--output PATH]` and must report
binding as unbound and freshness as unverified.

Place strict wrapper decoding and freshness tracking in the application analysis
boundary. Keep Windows acquisition and the standalone guest-side collector in
the I/O boundary. Existing V1 loopback VNC and HTTP receiver components may be
reused as unchanged lab or transport infrastructure where useful; do not import
V1 application architecture or make the wire contract depend on them.

No deployment or automatic installation mechanism is selected by this record.
The actual-client addon was copied manually for validation.

## Consequences

A nonce match identifies one reader handshake, not authenticity by itself.
Verified freshness also requires advancing inner observations, stable target
process/binding, receiver timing, and invalidation on reload, restart, conflict,
regression, malformed data, or expiry.

The retained RR2L1 gate validates bind, advancement, stale receipt rejection,
reload clearing, reader restart with a new nonce, and rebinding in one stable
RIFT process. See the
[live transport record](../validation/live-transport-2026-10-18.md). Its host
gate is snapshot-only and conditional on a 250 ms guest/host UTC skew bound;
delivery remains `gameReady: false`.

The inner values remain addon API references. This decision establishes no
native pointer, derived motion meaning, combat availability, guest file hash,
or update survival. RIFT process restart and VM power cycle were not tested.
