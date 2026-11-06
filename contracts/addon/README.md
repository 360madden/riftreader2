# Addon observation contract, version 1

This RR2A1 contract is frozen. Package 0.2.0 adds the separate
[RR2R1 API reference contract](reference-v1.md) for current discovery and native
comparison, preserving RR2A1 and RR2L1 meaning and version allowlists below.

Status: implemented producer/decoder contract and verified in one actual-client
session. The selected nonce-bound wrapper is specified separately in
[the RR2L1 contract](live-transport-v1.md).

The producer is `RiftReader2` addon version `0.1.0`, using the observed RIFT Lua
5.1 API shape. All observations are **addon API references**, not native evidence
or complete motion samples. No yaw, units, UTC timestamp, process identity, or
freshness is inferred. The decoder accepts only this schema/producer pair.

## Wire format

One exact ASCII frame, at most 4096 bytes including markers:
`RR2A1|<JSON object>|ENDRR2A1`. No BOM, bytes outside the markers (including a
trailing newline), or concatenated frames. JSON property order and whitespace
are insignificant. Duplicate, unknown, and missing
properties are rejected, including inside fields. JSON depth is limited to 8.
The envelope is framing, not authentication or a checksum.

Required root properties:

| Property | Type and meaning |
|---|---|
| `schemaVersion` | Integer `1`. |
| `addonVersion` | String `0.1.0`. |
| `sequence` | Integer 1 through 9007199254740991, advances for each publication. |
| `epoch` | Integer in the same range, starts at 1 and advances on source-clock regression or recovery after clock loss. |
| `clock` | Number field, successful value finite and nonnegative, from `Inspect.Time.Frame()`. |
| `player` | String field from `Inspect.Unit.Lookup("player")`. Successful ID: 1..128 printable ASCII characters (0x20..0x7e). |
| `fields` | Object containing exactly `coordX`, `coordY`, `coordZ`, `health`, `healthMax` (number fields), and `combat` (boolean field). |

Each field is exactly `{"status":"ok","value":...}`, or
`{"status":"unavailable"}`, or `{"status":"invalid"}`. An unavailable or invalid
field must have no `value`. Successful number values must be finite doubles;
zero and negative coordinates are valid. False is a successful boolean value.
Absent API values/functions and failed calls are unavailable; present values
with the wrong type, nonfinite numbers, bad IDs, or changed player identity are
invalid. Missing wire fields are malformed, not automatically unavailable.

If clock is not successful, player and all six fields must be unavailable.
If player is not successful, all six fields must be unavailable. A stable player
with missing/failed detail lookup has unavailable fields. The producer brackets
`Inspect.Unit.Detail(id)` with player lookups and requires matching IDs. This
reduces identity races but does not claim an atomic game snapshot.

## Producer lifecycle and bounded work

Separate Lua modules own encoding, acquisition/state, and RIFT event hookup.
The default sampling interval is 0.5 seconds; a validated constructor option
allows 0.05..60 seconds. Only the six declared fields are acquired in this schema.
One current frame is published in `RiftReader2_Frame`; no history, file/network
access, SavedVariables or unbounded scans are implemented by the producer.
The separate [manual guidance receiver](../../docs/reference/addon-guidance.md)
accepts bounded calculated results outside this observation schema; it does not
change RR2A1 fields or execute gameplay actions.
The event callback returns no values. API errors do not escape the callback.
Startup/update events use the API shape observed in V1 and verified in one
identified actual-client session on 2026-10-18. The global is a publication
surface, not a transport by itself.

Clock loss/invalidity publishes a clearing observation once per status change;
repeated identical failure status is throttled without needing a clock. Recovery
or regression starts a new epoch and publishes immediately. Sequence never
resets within one producer instance. Counter exhaustion clears publication and
stops the producer. Serialization failure clears publication. Normal unchanged
time does not republish. Lua reload creates a new instance and resets counters.

## Freshness and identity

Sequence and epoch are **local counters**, not globally unique load IDs. A reload
can reproduce exactly the same frame; old strings can survive elsewhere. Decoding
one frame cannot prove currentness, source authenticity, process identity, or
reload identity. Offline reports always say `bindingStatus: "unbound"` and
`freshnessStatus: "unverified"`, plus SHA-256 of the exact frame bytes. The hash
identifies content; it does not authenticate the producer. Frames must not enter native correlation or motion
analysis as bound live observations.

A live acquisition adapter must establish target/process lifetime and addon
load identity independently, timestamp receipt using a receiver monotonic clock,
invalidate binding on reload/restart/regression/conflicting sequence payloads,
and demonstrate advancing observations and an age policy. Until it can detect
reload reliably, it must withhold verified freshness. Epoch alone is insufficient.

The selected live design preserves this version-1 frame unchanged inside RR2L1
and adds a reader-generated, one-load nonce. RR2L1 has its own version; the inner
addon version remains 0.1.0. The transport passed one identified RIFT-Lab gate;
see the [RR2L1 contract](live-transport-v1.md) and
[validation record](../../docs/validation/live-transport-2026-10-18.md).

## Shared executable fixtures

`fixtures/cases.json` supplies scenarios to real Lua 5.1 and C# tests. Each case
has `name`, `clock`, `beforePlayer`, `afterPlayer`, `detail`, and `expected`.
Input `null` means missing Lua value. Each scenario starts a fresh producer at
sequence/epoch 1. Test-only `{"special":"nan"}`, `positiveInfinity`, and
`negativeInfinity` values represent nonfinite input; they never appear on wire.
Expected wire JSON is semantic, so whitespace/order/number spelling may vary.
`fixtures/rejected.json` holds complete wire strings the decoder must reject.

The validation script executes Lua tests, encodes every shared case through the
actual producer, then decodes those emitted frames using the C# CLI and compares
their observations to the same expected objects. Mocks establish contract and
lifecycle behavior only; they do not establish actual RIFT API availability.
