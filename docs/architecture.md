# Architecture

Status: selected foundation, authorized 2026-10-18.

Joey authorized an improved, modular, organized, and configurable RiftReader2
foundation. The .NET stack and project boundaries below are implementation
choices made under that authorization; they were not individually prescribed
by Joey. V1 remains evidence and reference material, not an architecture to
copy.

## Shape

RiftReader2 starts as one command-line process with four production modules and
one test project. This preserves strong boundaries without paying the operating
and debugging cost of services, plugin discovery, a custom scheduler, or a
dependency-injection framework before any of them solve a measured problem.

| Project | Responsibility | May reference |
|---|---|---|
| `RiftReader2.Domain` | Sample and analysis meaning, units, options, and result concepts. | .NET base libraries only. |
| `RiftReader2.Application` | Use cases and streaming derived-motion analysis. | Domain. |
| `RiftReader2.Infrastructure` | Strict versioned JSON configuration, capture input verification and reading, and atomic JSON result writes. | Domain. |
| `RiftReader2.Cli` | Argument handling, explicit composition, commands, help, and process exit behavior. | Domain, Application, Infrastructure. |
| `RiftReader2.Tests` | Focused behavior and boundary tests. | Production projects as needed. |

The dependency direction is deliberate:

```text
                         +----------------+
                         |      CLI       |
                         +-------+--------+
                                 |
                +----------------+----------------+
                |                |                |
                v                v                v
       +-------------+   +----------------+   +--------+
       | Application |   | Infrastructure |   | Domain |
       +------+------+   +-------+--------+   +--------+
              |                  |
              +------------------+
                         |
                         v
                    +--------+
                    | Domain |
                    +--------+
```

Domain does not know about files, JSON, command lines, processes, RIFT memory,
or V1. Application does not know which file format or future capture adapter
supplies samples. Infrastructure handles external representations without
deciding what observations mean. CLI contains composition and presentation,
not analysis rules.

## First operation

The first implemented path is deterministic offline analysis:

1. CLI loads a versioned configuration.
2. Infrastructure loads a capture manifest, resolves its plain sample filename
   beside the manifest, verifies the declared SHA-256 digest, and then streams
   JSON Lines from the same open file handle.
3. Application validates the ordered sample stream and derives movement deltas,
   horizontal distance and interval-average speed, shortest-path yaw change and
   interval-average yaw rate, and sample-gap diagnostics. Shortest-path yaw
   assumes the body turns less than half a revolution between observations.
4. Infrastructure writes the result as JSON through a same-directory temporary
   file followed by a no-overwrite move.

Raw observations remain distinguishable from derived values and semantic
claims. A successful calculation on a synthetic capture does not qualify a RIFT
field or reproduce a V1 conclusion.

The supported entry points are:

```powershell
dotnet run --project src/RiftReader2.Cli -- analyze --manifest samples/demo/capture.json --config config/default.json --output artifacts/demo-analysis.json
dotnet run --project src/RiftReader2.Cli -- validate-capture --manifest samples/demo/capture.json
dotnet run --project src/RiftReader2.Cli -- --help
```

The demo dataset is synthetic and illustrative. It proves the local pipeline
and its contracts, not RIFT behavior.

## Versioned boundaries

Configuration schema version 1 contains an `analysis` object with
`maxGapSeconds` and `maxSamples` JSON properties. Its top-level
`maxCaptureBytes` input limit defaults to 268,435,456 and has an accepted
ceiling of 8 GiB. Configuration parsing is strict: malformed input, unsupported
schema versions, missing, duplicate, or unknown properties, and invalid ranges
fail clearly instead of silently changing behavior.

Capture manifest schema version 1 records:

- `sourceKind`: declared `synthetic` or `rift-recording` origin;
- `buildSha256`: the producer's declared identity for the observed RIFT build,
  where applicable;
- `sessionId`: identity shared by every sample in the capture;
- `positionUnits`: the declared nonblank position unit;
- `coordinateFrame`: declared `xz-horizontal-y-up` axes;
- `clockBasis`: declared `session-monotonic-seconds` timestamp basis;
- `timingUncertaintySeconds`: finite nonnegative uncertainty, or `null` when the
  producer does not know it;
- `samplesFile`: a plain filename located beside the manifest;
- `samplesSha256`: SHA-256 identity of the exact sample bytes.

The reader validates the `buildSha256` representation but cannot prove which
executable produced it. `samplesSha256` binds the exact saved sample bytes; it
does not establish executable provenance or field meaning.

Each UTF-8 JSON Lines sample records `sessionId`, `sequence`,
`timestampSeconds`, `x`, `y`, `z`, and `yawRadians`; a line may be no longer than
16,384 characters. Readers reject missing, duplicate, or unknown JSON members
and incompatible identity, sequence, timestamp, numeric, count, size, and digest
conditions. Version 1 is the only accepted schema version. New meanings require
a new schema version and an explicit compatibility decision.

The repository pins the .NET 10 SDK (`10.0.302`) with SDK roll-forward disabled
and pins test package versions. Product projects use base-library dependencies
only. Package lock files make restore drift visible.

Analysis reports include input provenance, the effective configuration, and the
meaning of derived values. Provenance includes `toolVersion`, SHA-256 identities
for the four product assemblies, `samplesHashVerification: verified`, and
`buildIdentityVerification: declared-only`. The manifest's source, units,
coordinate frame, clock basis, and timing uncertainty remain producer
declarations; the foundation has no live capture result that independently
confirms them. Output is optional. When requested, a new report is written
through a same-directory temporary file and moved into place without
overwriting; an existing destination is an explicit failure.

## Extension policy

Add capability through a bounded adapter or use case while preserving the
dependency direction. Extract an interface when the next real adapter or test
seam requires it; do not create speculative abstractions for imagined variants.
Explicit construction in CLI should remain easy to read while there is one
composition path.

Expected later additions are:

- a read-only Windows capture adapter with process and build identity;
- independent import or replay of selected V1 evidence;
- a durable catalog for field meaning, locator, applicability, validation, and
  invalidation evidence;
- guarded experiment support for controlled movement and turning tests;
- optional SQLite indexing only after file-based evidence demonstrates a query,
  scale, or integrity need that JSON artifacts cannot meet cleanly.

Navigation, combat, and player automation remain outside RiftReader2. Networked
services, runtime-loaded plugins, background scheduling, and multiple processes
need evidence of a concrete requirement before adoption.

## Change rules

- Keep Domain free of adapters and external formats.
- Preserve source, build, session, schema, and content identity at evidence
  boundaries.
- Stream captures; do not require loading an entire large capture into memory.
- Write generated captures, logs, caches, and analysis output under
  `artifacts/` unless a small synthetic fixture is intentionally tracked.
- Add the narrowest meaningful test for changed behavior.
- Record material boundary, schema, storage, or process changes in a numbered
  decision record.
- Validate with [the development workflow](workflows/development.md).

The exact version-1 fields and validation rules are documented in
[the capture contract](reference/capture-format.md).

See [ADR 0001](decisions/0001-modular-offline-foundation.md) for the decision
and [the implementation roadmap](planning/implementation-roadmap.md) for the
increment order.

## Implementation references

Reviewed 2026-10-18:

- [Microsoft Learn: global.json overview](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json)
  defines `rollForward: disable` as requiring an exact SDK match.
- [Microsoft Learn: required JSON properties](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/required-properties)
  documents required-member deserialization behavior.
- [Microsoft Learn: unmapped JSON members](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/missing-members)
  documents rejecting properties absent from the target contract.
