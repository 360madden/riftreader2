# Read-only native capture

The Windows Live executable supports finite raw-memory captures independently
of the Lua-addon transport. Capture bytes remain semantically unqualified:
successful acquisition does not establish a game field, units, or locator
stability. Native field discovery and the durable field catalog remain later
roadmap work.

## Commands

Run the published executable on the Windows machine running RIFT:

```powershell
RiftReader2.Live.exe inspect-native --output target.json
RiftReader2.Live.exe capture-native --request request.json --output capture.json
```

Inspection requires exactly one `rift_x64` process. Its `suggestedRequest`
provides a small module-header example bound to the observed PID, process start
ticks, and executable file SHA-256. Save that object as `request.json`; change
only the explicitly intended ranges and sampling settings. Inspection itself
does not read game memory. Both commands preserve existing output files.

The existing no-argument Live executable still runs the addon transport.

Exit codes are `0` for complete capture or inspection, `3` for an incomplete
capture report that was saved, `2` for invalid input/identity or publication
failure, and `130` for cancellation. An existing output is never replaced,
including on failure.

## Request contract

`native-memory-read-request/1` has these required fields:

| Field | Meaning |
|---|---|
| `schemaVersion` | Exactly `1`. |
| `evidenceKind` | Exactly `native-memory-read-request/1`. |
| `target` | Exact `processId`, `processStartUtcTicks`, and `executableSha256`. |
| `sampling` | `sampleCount`, `intervalMilliseconds`, and `maxDurationMilliseconds`. |
| `ranges` | Unique `id`, `addressKind`, hexadecimal `address`, and `byteLength`. |

An address kind is `module-relative-rva` or `absolute-session-address`.
Hexadecimal addresses use `0x` followed by uppercase digits without leading
zeroes, except `0x0`. An RVA must fit wholly inside the identified main module;
an absolute range must fit the supported 64-bit user address space. Absolute
addresses are valid only for the requested process epoch.

Requests are strict JSON, limited to 65,536 bytes. Limits are 32 ranges, 4,096
bytes per range, 32 samples, 4 MiB of requested raw bytes, and a capture budget
of at most 30 seconds. Interval settings must fit the requested schedule.
The serialized report is capped at 8 MiB. The capture budget covers sampling
and terminal identity validation; initial attachment and executable hashing
precede it. Blocking Windows calls cannot be interrupted mid-call; overruns
are detected after they return and cannot become complete captures.
Unknown versions/properties, duplicate properties, invalid addresses, null
entries, and inconsistent bounds are rejected.

## Evidence and consumption

Domain contains values; Application owns the capture operation and its
read-only session port; Infrastructure handles request/report JSON; Live owns
Win32 access and command composition. No process write, injected code,
debugger, or player-input capability is introduced.

The native session uses one process handle opened with query and VM-read
rights. Process creation time, exit state, image path, executable file hash,
and main-module mapping are checked around acquisition. The executable hash
identifies the on-disk file. It does not establish that every loaded module
byte matches that file.

Reports retain the exact request hash, effective request, tool identity,
capture UUID, sample sequence, UTC endpoints, monotonic elapsed time, requested
and resolved addresses, actual byte count, raw bytes, byte SHA-256, and read
status/error. Reads across ranges or samples are sequential, not an atomic
process snapshot. UTC alone is not a cross-machine freshness proof.

Tool identity distinguishes `assembly-files` (individual assembly hashes) from
`single-file-bundle` (the published executable filename and SHA-256, with no
fabricated assembly hashes). The full gate exercises the published executable
against a synthetic host process so packaging behavior is tested separately
from tests that load assembly files.

`captureContentSha256` binds serialized `requestSha256`, `request`, and
`capture` using the repository JSON settings. It is not a hash of the complete
report file; retain a separate file hash when transferring reports.

A consumer must inspect capture and range statuses. Partial/unavailable reads,
identity invalidation, and deadline failures must never be treated as complete
observations. Any retained partial bytes describe only their actual byte count;
unread bytes are not replaced with zeroes. Cancellation publishes no completed
report.

A process restart requires inspection and a new explicit request. This command
does not silently reuse session addresses or automatically rebind them. The
earlier addon restart gate is separate from native-field or update recovery.

See [current status](../status.md) for actual runtime qualification.
