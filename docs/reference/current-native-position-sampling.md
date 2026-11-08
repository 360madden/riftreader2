# On-demand current-build native XYZ candidate sampling

The project now has a **read-only, no-addon-binding** fast candidate sampler for the RIFT executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
It reuses the exact player-unit manager/component lookup established by
`scripts/probe_native_unit_manager.py`. Native samples are **not automatically
player-position or passive-freshness qualified**. Never substitute these records
for the independently bound and advancing RR2 Lua reader when it is required.

## Preferred on-demand workflow

From `C:\work\riftreader2` in a **host Windows terminal**:

```powershell
C:\Python314\python.exe -B scripts\sample_current_native_xyz.py --lab lab2 --samples 30 --interval-ms 400
```

Use `--lab lab1` for Lab1. The CLI supports 1–30 samples, 0–2000 ms
post-read delays, and at most 60 seconds of requested delays. It discovers a
fresh, **unique** RIFT PID/start epoch in the guest every time and rejects a
different game executable. It does **not** start RIFT, touch controls or require
the in-game chat. VM authentication uses the existing per-lab cached credentials.

The script verifies the exact published host executable at:

`artifacts/native-xyz-unit-20261107/publish/RiftReader2.Live.exe`

with pinned SHA-256
`BE252929D846AA0BB696D003116AB9D8ACAA23E5D411D68F913A92CD08919A5E`
(117,757,792 bytes). The previous `B8A725E6...` published executable at
`artifacts/native-current-sampler-20261105/publish/RiftReader2.Live.exe`
remains intact as historical evidence and a rollback artifact; it is not the
current host pin.

It reuses a **hash-checked, content-addressed** copy in the individual guest's
`settings.guestRoot\current-native-BE252929D846AA0B\` directory, or copies
the host binary once if absent. A mismatched existing executable refuses the
run without overwriting the guest file. Every run gets a separate unique,
non-overwriting guest report and host artifact directory:

`artifacts/native-current-sampler-20261105/runs/<lab>/<random-id>/`

The host directory contains `identity.json`, `samples.json` (the original
typed .NET JSON report), and `summary.json` with source SHA, full game epoch,
per-sample timing, maximum read duration, maximum start gap and a
**candidate-only** qualification. Failure produces **no successful summary**.

## Evidence and scope

The .NET command is `sample-current-position --pid N --start-ticks N --output FILE
[--samples N] [--interval-ms N]`. It is part of `RiftReader2.Live.exe`
and enforces the exact game build; unlike the historical `sample-position`
command, it does **not** use the obsolete profile pinned to `7C356C9D...`.

Each sample uses one Windows read-only process handle, resolves player entity,
component selector and owner in the **current** process, bounds the collision
chain to eight nodes, rejects partial/nonfinite memory reads, checks all critical
owner links again, and revalidates process identity. It does not read/write game
controls, attach a debugger, invoke Lua, or copy an old absolute pointer.

The report's `continuousCadenceUnder4Point5s` compares measured native sample
starts and read durations only, requires at least two samples, and rejects
overlapping monotonic read intervals. `acquisitionSpanMilliseconds` measures
first-read start through final-read completion; it does not imply a 480-second
observation. These metrics describe acquisition only. A true cadence flag
**does not** establish current player position semantics, no-input provenance, movement responsiveness,
uninterrupted 480-second Lua freshness, or restored autonomous waypoint control.

## Current pinned-reader observations

The current reader and host validator require a lossless anchored unit key and
matching unit ID on every sample; missing, malformed or changed sampled keys
fail closed. Equal keys do not establish uninterrupted ownership or that the
cached coordinates refreshed. Lab1 read-only **5/5** and **30/30** runs saw
the same unit `u035400012FA2D678` and unchanged XYZ. The 5-sample run spanned
2.108 seconds with maximum start gap 533.3391 ms; its receipt at
`artifacts/native-current-sampler-20261105/runs/lab1/7d5b868c40664a0cb95e2c6ce0892cfb/samples.json`
has SHA-256 `FC9DC02D1692BECA28ACF9F7F7A8B492D2AEC04A23FB87CC4CFF4495A4009772`.
The 30-sample run spanned 19.3873 seconds, maximum start gap 778.9411 ms and
maximum read 375.6047 ms; its receipt at
`artifacts/native-current-sampler-20261105/runs/lab1/d2d11975e54b41bf9155a90269c6703b/samples.json`
has SHA-256 `254A4E86B80612A22957B46AE2E162FF9FA776779253115861B3AD2818B4E4AD`.
These were candidate acquisition checks, not changed-state, passive-freshness
or full-game-restart qualification. See [tracking details](current-native-xyz-tracking.md).

## Historical B8 reader validations

- Eight current-build C# synthetic tests and the complete 209-test
  `RiftReader2.Live.Tests` suite passed on .NET SDK `10.0.302`.
- Independent three-sample live Lab2 and Lab1 runs passed using the same
  published host binary, with read+identity timings around 82–98 ms.
- The on-demand Lab2 workflow completed two independent **30/30** candidate
  acquisition runs, including a second run with the SHA-checked guest reader
  reused. Maximum measured sample-start gaps were 532.3ms and 544.0ms;
  per-read durations were at most 120.9ms and 135.9ms, respectively. The
  Lab1 independently completed 30/30 with max read 104.9ms and start gap
  538.7ms. The original reports and summary source hashes were cross-checked
  against each current game PID/start/SHA. These are **not** qualified motion
  observations.

## Next qualification

Use a bounded longer stationary series to measure gaps and lag. For meaningful
player-motion qualification, later compare a fresh native-before sample,
independent same-unit game API/UI evidence and native-after sample around a
single separately authorized reviewed movement. Do **not** promote a constant
cached XYZ series or a stale Lua receipt to live movement telemetry. Never
increase the 4.5-second reader freshness or 12-second movement budgets merely
to make a test appear green.
