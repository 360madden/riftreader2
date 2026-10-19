# RiftReader2 addon

This directory contains the minimal in-game Lua producer for RiftReader2. It
publishes a bounded API-reference observation for later acquisition by the
external .NET application. It does not read native memory, calculate motion,
persist SavedVariables, send network traffic, or accept commands.

## Package

`RiftAddon.toc` loads three modules in order:

| File | Responsibility |
|---|---|
| `wire.lua` | Strict bounded ASCII/JSON encoding for the version-1 frame. |
| `producer.lua` | API acquisition, validation, sequence/epoch state, throttling, and publication. |
| `main.lua` | Minimal RIFT startup/update event hookup and error containment. |

The manifest uses `Environment = 4.4`, the value observed in the V1 addon
reference. Current-client compatibility remains unverified until a controlled
RIFT load test. Nothing in this repository automatically installs or deploys
the addon.

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
and epoch are local producer counters and can repeat after reload. A future
acquisition adapter must bind process/load identity and prove advancement and
age before reporting freshness.

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

The next live-facing increment is a bounded acquisition adapter that turns the
publication surface into a process/load-bound transport and fails closed until
freshness is independently established.
