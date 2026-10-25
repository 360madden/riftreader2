# Start / Read / Stop position window

The Windows Live executable includes a small native Windows Forms interface
around the [existing exact-build XYZ sampler](known-position-sampling.md).
It reads the game on the same Windows machine where the executable runs; a host
process cannot use this window to read memory inside a guest VM.

```powershell
.\RiftReader2.Live.exe position-panel
```

The default profile is `position-candidate-profile.json` beside the executable.
Each launch creates a new evidence session beneath
`%LOCALAPPDATA%\RiftReader2\Position\`. Explicit paths are also supported:

```powershell
.\RiftReader2.Live.exe position-panel --profile .\position-candidate-profile.json --output-directory C:\RIFT_TRANSFER\position-session-new
```

An existing evidence directory is refused. The profile is strictly loaded and
hash-pinned once at startup; changing it requires a new panel launch.

## Buttons and freshness

- **Start:** monitor for at most ten minutes per activation. Reads are serialized,
  at most one per second between read starts, with no queued overlap. Every read
  discovers the current process and uses the unchanged pointer sampler.
- **Read:** take one fresh sample, including when monitoring is stopped. A
  one-shot read does not start monitoring.
- **Stop:** cancel the current read, stop scheduling, and immediately clear XYZ.
  A late result cannot refill the display. If an old read is still finishing,
  another physical read must wait, even after Stop/Start.

Each read clears previously displayed XYZ before starting. Unavailable, failed,
nonfinite, canceled and expired reads do not display coordinates. Values expire
after three seconds measured from both read start and completion using a
monotonic clock; a slow completion is not relabeled fresh. The cadence and
freshness window are operational bounds, not a claim of synchronized Lua/native
sampling. The user should enter the world before interpreting XYZ.

While monitoring, a closed game produces unavailable reads with no current XYZ;
later reads rediscover the new process after normal relaunch. Exact executable
SHA guards remain mandatory. A changed build fails closed; no automatic patch
rediscovery or offset fallback occurs. [Patch recovery remains deferred](../decisions/0008-full-game-restart-durability.md).

## Evidence and scope

`panel-session.json` records the profile, source hash, operational bounds and
candidate-only status. `panel-events.jsonl` records buttons, state transitions,
read report references and hashes. Each completed attempt preserves a new
`read-NNNNN.json` using the existing `native-position-samples/1` contract; failed
open/discovery attempts are retained in the event journal without invented
coordinate reports. Closing the panel stops monitoring and closes its journal.

This presentation does not add input control, process writes, a debugger, a
background service, heap scanning, Lua transport or field promotion. Native
candidate labels remain unchanged. The self-contained Windows publish includes
the Windows desktop framework; installing it separately in the guest is not
required. The existing console acquisition commands remain available.

Follow the [implementation and live acceptance plan](../planning/position-panel-roadmap.md).
See the [host implementation checkpoint and pending live gate](../validation/position-panel-host-2026-10-25.md).
Host tests and actual guest restart validation must be recorded separately;
the earlier sampler restart alone does not establish this new UI's behavior.
