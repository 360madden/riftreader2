# V2 offline typed-wire inspector — verified implementation checkpoint

Date: October 24, 2026 (America/New_York). This validation is **synthetic/offline**. No current RIFT PID 6940 native-memory snapshot, fresh Lua frame, or native-vs-Lua XYZ comparison was acquired by this work.

## Outcome

Created V2-owned, read-only `inspect-typed-wire` command for two retained `native-memory-snapshot/1` files, using the existing strict chunk/file verifier and contiguous-successful-segment normalization. Registered it in the CLI and documented the acquisition workflow in [typed wire reference](../reference/typed-wire-snapshot.md).

- Recognizes complete `RRAPIVAL2|{JSON}|RRAPIVALEND`, v0.6.0 producer frames; bounded to 8,192 JSON bytes and 128 candidates per input.
- Rejects nested duplicate JSON keys, invalid UTF-8/contracts, malformed complete frames, incomplete fragments, conflicting equal-ranked newest copies, missing or invalid coordinates, player identity change, stale or regressed producer clock/sequence, and input-overflow.
- Requires distinct saved files, *same complete process/module epoch*, nonoverlapping chronological capture windows, and independently advancing producer sequence **and** `Inspect.Time.Frame`. Frame addresses can relocate between samples.
- Reports source SHA-256, chunk/source identity, coverage/hole warnings, candidate addresses/versions/digests, selected source XYZ and delta. Publishes only to a new output path. Successful report publication with `blocked`/`unavailable` **is not** a positive source observation.
- Even positive `advanced-in-covered-scope` is explicitly *scope-limited*: a selected subset of memory is not an exhaustive search of current game memory or a field qualification.

## Actual tests and tooling

| Check | Observed |
|---|---|
| Focused `TypedWireSnapshotCommandTests` | **19/19 passed** (synthetic fixtures) |
| Full .NET 10 solution, Release/`--no-restore` | **383/383 passed** (293 core + 90 Live) |
| `dotnet format RiftReader2.slnx --verify-no-changes --no-restore` | **Exit 0**, after formatting only the two new C# files |
| `dotnet build RiftReader2.slnx --configuration Release --no-restore -v:q` | **Exit 0, 0 warnings, 0 errors** before final scoped formatting |
| CLI `--help` smoke | **Exit 0**, new command advertised |
| Preceding Python suite from temporal-frame checkpoint | **502/502 passed**, no new Python code in this milestone |

The new focused cases cover exact wire decoding across adjacent chunks, changing heap addresses, malformed complete and nested-duplicate frames, equal-rank conflict, hole/truncation (including a good copy beside an incomplete fragment), stale sequence and clock independently, identity change, invalidated snapshots, checksum tampering, no-overwrite output, candidate overflow, wrong addon version, missing frame and out-of-order capture windows.

The repository's composite `scripts/validate.ps1` was **not** run successfully here: PowerShell 7 remains unavailable through the current Workbridge terminal and Windows PowerShell 5.1 does not preserve the Lua inline-command quoting on this runner. Direct .NET and Python gates above are separately observed; no Lua/client deployment or full integrated gate claim is made.

## Identity and limits

- Pinned game executable in the last live V10 checkpoint: `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`, game PID **6940** and start ticks **639284177321390013**. These are **context**, not a fresh native observation.
- Historical positive V1 typed frames were from **another** game process (PID 3776, October 16) and move between absolute heap locations. They informed a selective contract rewrite; **V1 files were inspected read-only** and not changed.
- The current native coordinator/guest was not stopped, rebooted, reconfigured, or given gameplay input during this offline development. The canonical queue was not modified.
- **Next acceptance gate:** acquire same-epoch read-only `map-native` followed by strictly bounded `snapshot-native` ranges through authenticated, exclusive guest maintenance, retain actual guest reports on the host, run this new inspector, then compare selected Lua XYZ against a newly acquired native `follow-pointer` report. No positive live semantics are established before that experiment.
