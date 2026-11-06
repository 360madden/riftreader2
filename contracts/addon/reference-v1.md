# RR2R1 addon API reference, version 1

The RiftReader2 package 0.2.0 emits a separate bounded API reference. It does
not change the existing RR2A1 observation or RR2L1 live wrapper. The exact
ASCII frame is `RR2R1|<JSON>|ENDRR2R1`, at most 8192 bytes including markers.
Objects have exactly the properties described here; duplicate, missing and
unknown properties are invalid. JSON order and whitespace are insignificant.

The root contains `schemaVersion` = 1, `addon` = `RiftReader2`,
`addonVersion` = `0.2.0`, `source` = `rift-api`, `sessionId` (the currently
bound 32 lowercase hexadecimal reader nonce), `sequence`, `epoch`, `clock`,
`player`, and `fields`. Sequence and epoch are positive integers at most
9007199254740991. Clock and player use the same status, value and validation
rules as [RR2A1](README.md). Fields contains exactly numeric `coordX`, `coordY`,
`coordZ`, `health`, `healthMax`, `mana`, `manaMax`, `power`, `combo`, `planar`,
`planarMax`; boolean `combat`, `dead`, `mounted`; and string `zone`. Numeric
values must be finite; zone is printable ASCII and at most 128 bytes (empty is
valid). Each status object is exactly `{ "status": "ok", "value": ... }`,
`{ "status": "unavailable" }`, or `{ "status": "invalid" }`. Missing API
values and failed calls are unavailable; malformed present values are invalid.
False and zero are valid values.

Clock failure makes player and all fields unavailable; a non-ok player makes all
fields unavailable. Player lookup brackets detail acquisition: an identity
change is invalid, and no field is retained. Failed or malformed detail produces
unavailable or invalid fields respectively. This reduces races but does not
make the observations atomic.

Reference counters are independent of RR2A1. The clock is sampled at the same
default interval (0.5 seconds); clock failure emits a clearing observation once
per status change. Recovery and regression advance the epoch and publish
immediately. Counter exhaustion stops publication. Frames exist only after
binding; successful rebind clears the old reference immediately and requires a
new publication with the new nonce. Reload clears globals and creates new
counters. `RiftReader2_ReferenceFrame` holds the current frame and
`RiftReader2_ReferenceFrames` retains at most eight; retention clears when epoch
or player identity/status changes. No frame alone establishes currentness,
process identity, native semantics or authenticity. Live acceptance needs
independent process identity and advancing observations.

The [fixture](fixtures/reference-v1.json) contains producer-emitted before and
after frames and their parsed JSON for cross-language offline checks.
