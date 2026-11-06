# Bounded native numeric-value scout

`scout-values-native` performs one exact-process, read-only search for a small
set of numeric reference values. Its intended use is to seed a changed-state
experiment, then replace broad scanning with small `snapshot-native` rereads.
It does not identify authoritative gameplay fields or create a durable pointer
locator by itself.

## Request and command

Use a fresh `inspect-native` identity after every full RIFT launch. The example
identity is illustrative; never reuse a PID, start time, or absolute address
from another game process.

```json
{
  "schemaVersion": 1,
  "evidenceKind": "native-value-scout-request/1",
  "target": {
    "processId": 1234,
    "processStartUtcTicks": 639000000000000000,
    "executableSha256": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  },
  "startAddress": "0x10000",
  "references": [
    { "name": "health", "type": "int32", "value": "18208" },
    { "name": "health-double", "type": "float64", "value": "18208", "tolerance": 0 },
    { "name": "power", "type": "int32", "value": "100" }
  ],
  "contextBeforeBytes": 16,
  "contextAfterBytes": 64,
  "maxScanBytes": 1073741824,
  "maxDurationMilliseconds": 30000,
  "maxRegionCount": 32768,
  "maxMatchCount": 128
}
```

```powershell
.\RiftReader2.Live.exe scout-values-native `
  --request .\value-scout.request.json `
  --output .\value-scout-run-001
```

The output directory must not exist. The command retains the exact source
request, `index.json`, and one standard `native-memory-snapshot/1` request and
snapshot pair per retained match. Output is published with a final
no-overwrite directory rename only after the process identity is revalidated.

## Fixed bounds and interpretation

- References are little-endian `int32`, `float32`, or `float64`; at most eight
  are allowed. Numeric starts are tested only at 4-byte-aligned addresses.
  Float tolerance is finite and nonnegative; integer tolerance is zero.
- Only committed, readable, non-guard `MEM_PRIVATE` regions at or after
  `startAddress` are eligible. `MEM_IMAGE` and `MEM_MAPPED` are excluded.
- A pass is limited to 1 GiB, 30 seconds, 32,768 eligible regions, 128 unique
  matching addresses, and a 4,096-byte context read per match. Failed and
  partial reads remain explicit; they are never filled with zeroes.
- `index.json` records eligible, attempted and examined bytes, covered spans,
  holes, and `nextAddress`. A partial pass can resume from that cursor; it can
  overlap up to seven bytes, so deduplicate by exact PID/start/build/address.
  The cursor advances from actual forward scan progress rather than returning
  to an early permanent hole; holes remain listed for explicit review.
  Repeating the same completed scope adds no negative evidence.
- Exit 0 means the bounded scan completed. Exit 3 means partial coverage or an
  invalidated identity. Exit 2 means the request, identity open, or publication
  failed. Read the retained status and reason rather than inferring from exit
  code alone.

## Practical health/resource workflow

Run one current-epoch seed pass using independently observed Lua values. Build
one small `snapshot-native` request from promising retained contexts and reuse
that same request before and after a controlled value change. A current-health
candidate should track more than one Lua health change while health maximum
stays fixed; a resource candidate should track the raw Lua resource change
without following health. Replicated/static matches remain possible caches.

Only after changed-state correlation should pointer discovery begin. After a
candidate locator is found, fully exit RIFT, acquire a new PID/start identity,
reject the old request, resolve the locator again, and repeat one changed-state
check. Executable updates remain a separate, currently deferred scope.
