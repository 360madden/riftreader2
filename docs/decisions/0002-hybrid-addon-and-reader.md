# 0002: Hybrid Lua addon and external reader

Status: accepted architectural requirement; addon and live transport not yet implemented.

Date: 2026-10-18.

Authorized by: Joey explicitly reminded the project that RIFT has a Lua addon
system and RiftReader2 must be hybrid.

## Decision

RiftReader2 consists of a first-class Lua addon running inside RIFT and the
modular .NET application running outside it. The addon is part of the product,
not temporary scaffolding scheduled for removal when native reads exist.
The existing four-project .NET foundation remains the external half.

| Part | Responsibility |
|---|---|
| Lua addon | Collect fields/events exposed by the current RIFT addon API; report capability and availability; produce bounded typed reference observations with source identity. |
| External acquisition adapters | Acquire addon observations through an explicitly validated transport, bind them to the target/session/reload generation, and acquire native evidence separately when needed. |
| External Application/Domain | Compare independently identified observations, apply freshness/alignment rules, analyze captures, and qualify field meanings. |
| External storage/CLI | Preserve evidence, configuration, reports, local computation, and consumer outputs. |

Prefer supported addon API data for fields it exposes. Native research addresses
gaps and independently qualifies native fields where those are useful. Keep
addon API observations, native readings, and derived values distinguishable in
contracts and reports. API agreement alone does not establish a native locator
or restart/update survival.

## Boundary requirements

- Version producer, schema, and supported capabilities explicitly. Use contract
  fixtures consumed by actual Lua and C# implementations when they are built.
- Preserve valid zero/false; represent unavailable, invalid, and absent values
  explicitly. Missing body yaw must not be fabricated to satisfy the current
  complete-motion replay schema.
- Bind observations to a target process/session plus an addon-load generation.
  Sequence, source time, receiver time, and clock uncertainty serve different
  purposes. Reload, restart, clock regression, stale copies, and conflicting
  payloads require explicit invalidation/recovery rules.
- Keep the addon workload bounded and configurable: selected fields, sampling
  or event frequency, output size, and diagnostics. Heavy analysis and retention
  belong outside the game.
- Do not assume the addon sandbox permits arbitrary file writes, sockets, HTTP,
  or other ordinary Lua host capabilities. Inspect the actual supported RIFT API
  and validate the chosen bridge. SavedVariables are retained snapshots and must
  not be silently presented as current live telemetry.
- Transport is an adapter concern. A selected transport must prove framing,
  bounds, freshness, process identity, and behavior across reloads/restarts.
  A valid serialized payload by itself is insufficient.

The exact addon API subset, wire encoding, transport, compatibility matrix, and
deployment method remain implementation choices requiring evidence. This record
does not select V1's memory-string scanner or observer as the V2 transport.

## Repository and next increment

Reserve `addon/RiftReader2/` for the game package, `contracts/addon/` for versioned
boundary specifications/fixtures, and `tests/lua/` for producer tests when those
components are implemented. These are planned locations, not existing packages.
The .NET adapter belongs at the external Infrastructure boundary; split that
project further when actual adapter size or dependencies warrant it.

Next foundation increment: specify one minimal typed addon observation and
freshness contract, independently implement its Lua producer and C# decoder,
and verify compatibility with shared fixtures. Then validate one transport in
the real client. Mocked Lua tests do not establish live API support.

## Evidence and limits

Read-only local references reviewed on 2026-10-18:

- `C:\rift modding\RiftReader\addon\RiftReaderApiProbe\README.md`:
  typed API observations, capability diagnostics, and unavailable/invalid values.
- `C:\rift modding\RiftReader\docs\workflow\addon-wire-roadmap.md`:
  bounded framed decoding and why wire validity does not establish freshness.
- `C:\rift modding\RiftReader\docs\workflow\typed-acquisition-three-roadmaps.md`:
  later recorded acquisition, advancing observations, reload recovery, stale
  receipts, and real Lua producer/consumer checks. This later report supersedes
  the older README's claim that typed observations were not yet transported.

These are V1 source/report observations, not rerun tests or V2 capabilities.
V2 continues to use V1 as reference only.

## Supersedes

Clarifies [ADR 0001](0001-modular-offline-foundation.md): its single-process choice
describes the external application, not the entire hybrid product. The .NET
module graph, offline contracts, and existing validation remain applicable.
