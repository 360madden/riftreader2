# Read-only memory discovery

Use the existing Windows Live executable to acquire memory on the machine
running RIFT. Use the portable CLI to search those saved bytes repeatedly.
These commands generate candidates for field investigation, not qualified
navigation, combat, casting, or stat data. They add no game writes, injection,
debugger attachment, or autonomous player actions.

## Acquire

First inspect the current process. Every request binds its exact PID, process
creation time, and executable SHA-256. Reinspect after a restart; never carry
an old absolute address into a new session.

```powershell
$live = '.\RiftReader2.Live.exe'
$inspection = & $live inspect-native --output artifacts/target.json | ConvertFrom-Json
$target = $inspection.suggestedRequest.target
$request = @{
    schemaVersion = 1
    evidenceKind = 'native-memory-snapshot-request/1'
    target = $target
    maxDurationMilliseconds = 10000
    ranges = @(@{ addressKind = 'module-relative-rva'; address = '0x0'; byteLength = 4096 })
}
$request | ConvertTo-Json -Depth 8 | Set-Content artifacts/header.request.json -Encoding utf8
& $live snapshot-native --request artifacts/header.request.json --output artifacts/header.json
```

The header is a reproducible smoke example. For useful field discovery, select
explicit regions containing candidate objects. `map-native` lists committed,
readable, non-guard regions using the same read-only process handle:

```powershell
@{ schemaVersion = 1; evidenceKind = 'native-memory-map-request/1'; target = $target;
   maxRegionCount = 32768; maxDurationMilliseconds = 10000 } |
    ConvertTo-Json -Depth 8 | Set-Content artifacts/map.request.json -Encoding utf8
& $live map-native --request artifacts/map.request.json --output artifacts/map.json
```

Snapshot ranges use `module-relative-rva` (main executable only) or
`absolute-session-address`, canonical uppercase hex (`0x1B8`, no leading zeroes),
and byte length. Limits: 256 nonoverlapping ranges, 64 MiB total requested bytes,
16,384 chunks of at most 4,096 bytes, 30-second acquisition budget, 64 KiB request,
96 MiB report. Select several bounded regions instead of silently scanning the
whole process. Reads are sequential and may observe object changes between
chunks. Map enumeration and initial executable hashing are not an atomic snapshot.

Reports retain exact process/build/mapping identity, request hash, executable
tool identity, UTC endpoints, per-chunk success/partial/unavailable status,
actual bytes and hashes. Failed bytes are never filled with zeroes. The loader
searches only complete chunks, joins adjacent successful chunks, and preserves
holes and coverage warnings. Identity-invalidated captures cannot be searched.
Keep the request alongside the report: its hash is producer-declared; the
offline loader verifies each byte hash and hashes the exact report file.

## Search and compare

```powershell
$cli = 'src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll'
dotnet $cli search-memory --snapshot artifacts/sample.json --type float32 --value 7298.37 --tolerance 0.02 --output artifacts/value-hits.json
dotnet $cli find-pattern --snapshot artifacts/sample.json --pattern '48 8B ?? ??' --output artifacts/pattern-hits.json
dotnet $cli compare-memory --before artifacts/before.json --after artifacts/after.json --type int32 --mode decreased --output artifacts/changes.json
dotnet $cli find-pointers --snapshot artifacts/sample.json --target 0x12345678 --max-depth 4 --max-offset 4096 --output artifacts/chains.json
```

Types: `int32/uint32/int64/uint64/float32/float64`, little-endian; searches inspect every byte
position. Floats require finite values and allow an absolute tolerance.
Patterns accept exact byte pairs and `??`. Comparisons support `changed`,
`unchanged`, `increased`, and `decreased`; both captures must have the exact
same process identity and successful-byte layout. A hole cannot become a
zero-valued or unchanged field. Results retain query, source hashes, identity,
coverage warnings, and truncation. A match is not a semantic field name.

Pointer search indexes 8-byte-aligned x64 little-endian pointer slots in the
selected coverage. It works backward from a target through nonnegative offsets
and returns main-module roots as RVAs. Search limits are explicit: up to four
dereferences, 4,096-byte offsets, one million indexed pointers, 100,000 frontier
entries, and 10,000 returned candidates, plus a two-million-edge work bound. Pattern matching also stops after 64 million byte comparisons. Truncated
searches are not exhaustive. Negative offsets, encoded/compressed pointers,
other-module roots, and pointers outside the selected bytes are not discovered.

## Recheck a chain

`follow-pointer` resolves a root against the freshly inspected main module,
then repeats `address = read_u64(address) + offset` for every offset. It retains
raw hops and terminal bytes and rechecks identity. Build applicability comes
from the discovery report and the request's exact executable hash.

```json
{
  "schemaVersion": 1,
  "evidenceKind": "native-pointer-follow-request/1",
  "target": { "processId": 1234, "processStartUtcTicks": 123456789, "executableSha256": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" },
  "rootRva": "0x1000",
  "offsets": ["0x20", "0x10"],
  "terminalByteLength": 16,
  "maxDurationMilliseconds": 10000
}
```

The example identity and chain are illustrative; replace them with retained
candidate data and a fresh target. Run
`RiftReader2.Live.exe follow-pointer --request chain.request.json --output chain.json`.
Success proves only that this chain resolved in this session. Recheck after a
game restart, then record separate update evidence when the executable changes.
Exit codes: 0 complete, 3 retained incomplete read, 2 rejected request/publication,
130 cancelled. Existing outputs are preserved.

## Discover useful game fields

Start with one observed quantity: position/facing, health/resource, combat flag,
cast progress, cooldown, or an ability identifier. Prefer an available Lua API
observation as reference. Capture a small candidate region, observe a controlled
change, repeat the capture, and intersect value/change evidence. Use a supervised
[experiment](guarded-experiments.md) for movement when helpful. Combat/casting
observations can come from ordinary user gameplay; the discovery tool does not
perform those actions.

Find pointer roots for promising addresses, follow them again, and compare
against the API across several changes and a restart. Save field meaning,
units, locator/build applicability, contrary evidence, and limitations through
the [field catalog](field-catalog.md). Copies, cached values, UI representations,
and coincidental numbers are common candidates; a scan hit alone establishes
none of these meanings. Lua/API, native bytes, and derived conclusions retain
separate provenance.

For saved field-lab position comparisons, use the reproducible
[native field evidence reviewer](native-field-evidence.md) rather than manually
reinterpreting each raw capture. It does not qualify restart/update survival.

For strict source-contract discovery in **two already saved** memory snapshots,
see [offline typed-wire inspection](typed-wire-snapshot.md). A scoped positive
result still requires independent live source and native-field comparison.

See [runtime validation](../validation/memory-discovery-2026-10-19.md).
