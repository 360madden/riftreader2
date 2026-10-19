# RiftReader2 addon

This directory contains the minimal in-game Lua producer for RiftReader2. It
publishes a bounded API-reference observation for later acquisition by the
external .NET application. It does not read native memory, calculate motion,
persist SavedVariables, or send network traffic. Its only command is the
one-load reader binding described below.

## Package

`RiftAddon.toc` loads four Lua modules in order. Together with the manifest, the
current package contains five files:

| File | Responsibility |
|---|---|
| `wire.lua` | Strict bounded ASCII/JSON encoding for the version-1 frame. |
| `producer.lua` | API acquisition, validation, sequence/epoch state, throttling, and publication. |
| `live.lua` | One-load nonce binding and the version-1 live envelope. |
| `main.lua` | Minimal RIFT startup/update event hookup and error containment. |

The manifest uses `Environment = 4.4`, the value observed in the V1 addon
reference and verified in one controlled current-client session. Nothing in
this repository automatically installs or deploys the addon.

`main.lua` constructs the producer with `intervalSeconds = 0.5`. The constructor
accepts finite intervals from 0.05 through 60 seconds and rejects unknown options.
The schema fixes the six field names; changing the field set requires a contract
revision and corresponding fixtures. Sampling and serialization retain only the
current observation.

## Observation contract

The exact frozen contract is [documented with its shared fixtures](../contracts/addon/README.md).
Addon version `0.1.0` publishes schema 1 as one ASCII frame no larger than 4096
bytes:

```text
RR2A1|<JSON object>|ENDRR2A1
```

The observation covers frame clock, player identity, coordinates, health,
maximum health, and combat state with explicit `ok`, `unavailable`, or `invalid`
status. These values are addon API references. They are not native evidence, a
complete motion sample, or proof of an atomic game snapshot.

The current frame is assigned to global `RiftReader2_Frame`. That global is a
publication surface inside the Lua runtime, not a transport to .NET. Sequence
and epoch are local producer counters and can repeat after reload. The bare
RR2A1 producer loaded and advanced in one identified RIFT-Lab session; see the
[actual-client record](../docs/validation/addon-live-client-2026-10-18.md).

## Live binding

The external reader generates a new 32-character lowercase hexadecimal nonce.
Enter it once during the current addon load:

```text
/rr2bind <nonce>
```

An accepted command enables `RiftReader2_LiveFrame`, which wraps the unchanged
RR2A1 frame as `RR2L1|<nonce>|<RR2A1 frame>|ENDRR2L1`. A second bind with a
different nonce is rejected. `/reloadui` clears the binding, so the reader must
generate and submit a new nonce and rebuild freshness state after every reload.
The RR2L1 envelope has its own version; the inner `addonVersion` remains `0.1.0`.

The exact [RR2L1 contract](../contracts/addon/live-transport-v1.md) requires the
reader to validate the nonce, observe advancement, apply receiver timing, and
invalidate stale state. A valid wrapper alone does not prove process identity,
authenticity, or freshness. The implementation passed one identified RIFT-Lab
runtime gate, including reload clearing and reader restart/rebinding; see the
[live transport record](../docs/validation/live-transport-2026-10-18.md).

## Offline decoder

Decode one exact frame file without asserting source binding or freshness:

```powershell
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame PATH
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame PATH --output artifacts/addon-observation.json
```

Input must be the exact ASCII frame bytes, at most 4096 bytes, with no BOM,
bytes outside the markers (including a trailing newline), or concatenated frame.
JSON whitespace inside the markers is accepted. A saved report includes the
frame SHA-256, `bindingStatus: "unbound"`, and `freshnessStatus: "unverified"`.

Validate a saved RR2L1 envelope against its expected nonce offline:

```powershell
dotnet run --project src/RiftReader2.Cli -- decode-live-addon --frame PATH --session-id HEX
dotnet run --project src/RiftReader2.Cli -- decode-live-addon --frame PATH --session-id HEX --output artifacts/live-addon-observation.json
```

This command checks exact envelope framing, nonce equality, and the inner RR2A1
contract. Its report remains source-unbound and freshness-unverified because a
saved file cannot establish the live reader/process relationship or age.

## Validation

Lua and cross-language tests are mandatory in the repository gate. From the
repository root, prepare a repository-local Lua 5.1 Python runtime if needed:

```powershell
python -m venv artifacts/tools/lua-python
artifacts/tools/lua-python/Scripts/python.exe -m pip install -r requirements-lua-tests.txt
pwsh -NoProfile -File scripts/validate.ps1
```

`lupa==2.8` supplies the Lua 5.1 module used by the mocked producer tests. The
gate also sends every shared producer fixture through the C# decoder. These
checks prove contract agreement and lifecycle behavior against mocked APIs;
they do not prove current RIFT API availability, live publication, transport,
or reload freshness.

The completed gate exercised the nonce lifecycle through the actual Lua
producer, .NET decoder/tracker, Windows reader, standalone guest collector, and
a delivery-only host receiver. It did not test RIFT process restart, VM power
cycle, or a production remote consumer.
