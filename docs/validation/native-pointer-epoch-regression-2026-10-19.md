# Native pointer-follow stale-epoch regression — 2026-10-19

Scope: **host-side Windows synthetic/disposable-process testing**, not RIFT game
field qualification. This work extends the existing follow-pointer rejection
gate without changing the live game's process, memory, or UI.

## Implementation

The file src/RiftReader2.Live/WindowsNativeMemorySession.cs now compares the
expected process creation timestamp immediately after obtaining it from the
opened read-only process handle. It rejects an incorrect start epoch before
hashing the executable or enumerating its modules. It also rejects an incorrect
expected executable SHA-256 before module enumeration. The existing second
process-start and executable-path read remains after module enumeration to
detect identity changes during session opening.

The tests/RiftReader2.Live.Tests/PointerFollowEpochTests.cs suite uses the real
Windows read-only process API and NativeCommandRunner.RunAsync through the actual
follow-pointer request contract. It checks:

- A valid current PID with a deliberately stale start tick is rejected
  (exit 2) and no report is created.
- When both start tick and build SHA-256 are wrong, the stale start identity is
  rejected **first**; the file is not published.
- An incorrect executable hash with the correct PID/start is rejected and an
  existing output file remains unchanged.
- A disposable PowerShell process that has exited is rejected using its
  previously recorded PID/start/build, without producing an output file.

Temporary test files are created in unique system-temp subdirectories and
removed by the tests; the exited process is created only for the test and
terminated explicitly. There is no dependency on the live RIFT process.

## Evidence and limitations

The focused Windows suite passed **4/4** with exit 0 under .NET 10:
Workbridge job rr2_native_failfast_final_focused_20261019_57.
The complete repository gate passed with exit 0 (job
rr2_native_failfast_full_gate_20261019_58): **242 C# tests**
(225 portable and 17 Windows), 73 Python tests, 108 Lua assertions,
22 actual Lua-to-C# contract cases, locked restore, a zero-warning Release
build, synthetic native publishing smoke, deterministic replays, and 215
relative documentation links. Local ignored validation evidence:
artifacts/validation/20261019T124121Z-4bffda95.

Run focused verification from C:\work\riftreader2:

    dotnet test tests/RiftReader2.Live.Tests/RiftReader2.Live.Tests.csproj -c Release --no-restore --filter FullyQualifiedName~PointerFollowEpochTests

A passed test establishes Windows identity-check and no-publication behavior
for the tested synthetic/disposable processes. It does **not** establish that
the same field locator resolves in a particular live RIFT epoch or survives a
new game update.

The separate October 19 [player-field handoff](native-player-fields-2026-10-19.md)
has already observed the position root in two real RIFT process epochs.
An initial field-lab attempt was not evidence of old-epoch rejection:
oldPid, oldStartTicks and oldEpochRejected were absent in its returned
report. The modified plan had not been loaded.

The later [two-scenario live guest record](native-field-old-epoch-live-2026-10-19.md)
now establishes (1) failure to open the retired PID 11620 and
(2) an explicit process-creation-tick mismatch when using current PID 8356
with the former process's start ticks. Both raw capture reports retained
their exact requested and observed identities, stable native root rereads
and advancing typed Lua references. The temporary original plan was restored
after the tests. These exercise the common native-session open primitive,
not a direct live follow-pointer CLI invocation, and neither qualifies
native health/resource meaning or survival of game updates.

This test file is independently owned from the concurrent
docs/planning/movement-control-parity-roadmap.md lane. It does not modify
the movement experiment code, that roadmap, or the legacy RiftReader repo.
