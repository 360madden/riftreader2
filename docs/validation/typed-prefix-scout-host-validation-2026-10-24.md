# V2 typed-prefix scout: host-side .NET validation

Date: **October 24, 2026** (America/New_York). Tested on Joey's Windows 11 x64 host with pinned .NET 10 SDK; **no RIFT guest deployment, live game scan, movement, native field qualification, or VM/coordinator manipulation**.

## Implementation checked

- Commit `c6908c8` introduced `TypedApiPrefixScout`, a pure bounded 64 KiB streaming scanner, a separate `WindowsNativeMemorySession.ReadScanChunk` using the existing exact-process read-only handle, candidate-overflow cursor, region/byte coverage and read holes.
- Commit `2e73b9a` integrated `scout-typed-native --request PATH --output PATH`, versioned input/output, hash-bound evidence, identity revalidation, explicit partial/invalidated statuses and no-overwrite publication. Both commits changed **V2 only**.
- Source: `src/RiftReader2.Live/TypedApiPrefixMatcher.cs`, `TypedApiPrefixScout.cs`, `WindowsNativeMemorySession.cs`, `MemoryDiscoveryCommand.cs`, `NativeCommandRunner.cs`; focused tests under `tests/RiftReader2.Live.Tests/`.

## Actual Windows-host results

| Gate | Result |
| --- | --- |
| Streaming matcher + scout focused | **23/23 passed** |
| CLI/contract focused | **4/4 passed** |
| Complete `dotnet test RiftReader2.slnx --configuration Release --no-restore --verbosity quiet` | **410/410 passed**: 117 Live + 293 core |
| Scoped `dotnet format whitespace RiftReader2.slnx --verify-no-changes --no-restore --include ...` | Exit 0 |
| `git diff --check` | Exit 0 |
| Explicit Python list from `scripts/validate.ps1` | **475/475 passed** (48.656 seconds) |
| Full Python `unittest discover -s tests -p test_*.py` | **514/514 passed** (50.645 seconds) |
| Lua 5.1 contract runner (`lupa==2.8`) | **108 Lua lifecycle/encoder checks and 22 real Lua-to-C# shared cases passed** |
| Full `dotnet format RiftReader2.slnx --verify-no-changes --no-restore` | Exit 0 |
| Release `dotnet build RiftReader2.slnx --configuration Release --no-restore` | **0 warnings, 0 errors** |
| Single-file `dotnet publish` and executable help | Exit 0; includes `scout-typed-native` |
| Published-bundle native host smoke | **Passed**: own PID/start/SHA, main-module `MZ` bytes, exact bundle SHA, stale-epoch refusal and no overwrite |
| Composite `pwsh -NoProfile -File scripts/validate.ps1` | Not launched: PowerShell 7 absent from Workbridge process environment; equivalent component gates above ran separately, but the composite itself is **not** claimed |

The read-only **real Win32** tests used `Environment.ProcessId` with an explicitly allocated in-process marker buffer: `ReadProcessMemory` found the exact `RRAPIVAL2|` address, `scout-typed-native` wrote a schema/version/request-hash/implementation-bound JSON file, a repeated output path was rejected without overwrite, and a stale process-start identity produced no file. Separate synthetic tests covered 64 KiB read boundaries, overlapping resume cursors, unreadable holes, partial reads, match caps, zero/invalid budgets, wrong region types, failed enumeration inputs and time-cap semantics. These are **not observations of a current game Lua frame**.

## Published executable prepared, not transferred

Host validation bundle (ignored artifact path):

`artifacts/validation/rr2-scout-publish-20261024-01/RiftReader2.Live.exe`

- File size **74,209,699 bytes**; SHA-256 **`C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C`**.
- Published executable `help` reports the new scout command. The independent, no-BOM Windows host smoke verified `single-file-bundle` implementation identity matching this SHA, successfully read the test process's PE header, refused stale process-start ticks and preserved an existing report.
- The older PowerShell 5.1 script attempt failed on its own UTF-8-BOM `Set-Content -Encoding utf8` output (reported `0xEF` at JSON byte zero); this is **not a game/bundle regression**. PowerShell 7's full runner was unavailable, so the successful no-BOM host smoke ran separately.
- **No guest binary install or transfer** occurred. A fresh VM/queue preflight and legitimate exclusive console handover remain mandatory before a guest trial.

## Live environment unaffected

At the most recent read-only preflight for this task (**2026-10-24T15:29:33Z**), authenticated V12 native coordination was **connected/ready**, supervisor running with initial cleanup verified, guest RIFT PID **6940** foreground, guest **disarmed/idle**, no desktop inputs down, VMware PID **38044** same log epoch. The scanner tests did **not** open that VM, use its console, change its queue or touch the game process. Future guest acquisition requires a fresh live preflight and coordinated handover.

## Unresolved and next step

There is no current-epoch `RRAPIVAL2|` address yet; all positive command tests targeted the **test process**. Prepare a new SHA-pinned guest bundle and request, then perform **one bounded guest trial** only under exclusive coordinator release. Preserve a lossless report on the host. Qualify complete, advancing typed-wire source frames with independent snapshots before any native/Lua XYZ comparison. See the [command reference](../reference/typed-prefix-scout.md) and [scout research](../research/typed-prefix-scout-reuse-2026-10-24.md).
