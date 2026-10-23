# October 23 RIFT guest typed-readback recovery

## Verified state

The native position pointer compatibility test **succeeded** for the
unchanged game executable SHA-256
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`,
current RIFT PID `2768`, process start ticks `639282812576974124`.
The existing read-only native reader followed root RVA `0x32E0200`,
returned a complete 816-byte terminal read, and decoded candidate
float32 XYZ `(7459.142, 863.7189, 2973.08)`.
Native report SHA-256 was displayed inside the guest as
`40351546D62620736D40BA89B487EA8157E75DFA713B7B1E1D71F1790E0896AE`.
The full native report is guest-local; only screenshots and its digest
were retained by the host. An independent current-epoch Lua coordinate
comparison remains **incomplete**, so native XYZ retains candidate status.
See [the pointer recovery record](rift-position-pointer-recovered-2026-10-23.md).

## GuestObserver recovery and remaining limitation

A previously installed passive GuestObserver had stopped. The original
`C:\RIFT_TRANSFER\GuestObserver\RiftReader.GuestObserver.exe` was
restarted once, and the guest-local
`%LOCALAPPDATA%\RiftReader\GuestObserver\latest.json` began advancing
against the current game process. That older installation contains no
`readback.typedApi`, so it cannot validate XYZ.

The old observer was gracefully closed after verifying its exact process
and executable path. The already installed newer binary
`C:\RIFT_TRANSFER\GuestReadback\GuestObserver\RiftReader.GuestObserver.exe`
was started once, only after checking there were no remaining observer
processes. Its guest-side SHA-256 was observed as
`DFEB9ED1CFC7E9D79B8B7D23696CD41A370B0ADF8B110E2F3449557228E6C3F`.
The new observer supplies fresh local JSON with current RIFT PID `2768`
and the correct build, but its `readback.status` is `blocked` and
`readback.reason` is `scan-byte-budget-exceeded`.
It does not publish `typedApi` coordinates when the pass is incomplete.
The screenshot evidence is retained under ignored
`artifacts/update-recovery-20261023-01/guest-readback-block-settled/`.

The older HTTP GuestObserver delivery endpoint was configured for
`192.168.56.1:49712/observation`. That port is now used by the
coordinated native control host, so the observer reports outbound delivery
failure. Its local JSON writer is independent of network delivery and
continues running. Do not seize port 49712 or replace the control host
solely to force a Lua observation.

## Code-level explanation

Existing V1 source, inspected read-only:
`C:\rift modding\RiftReader\reader\RiftReader.Reader\GuestReadback\GuestReadbackContracts.cs`
sets default `ByteBudget = 4 GiB`, `PassTimeBudget = 10s` and
`ChunkSize = 1 MiB`. The installed observer creates a
`GuestReadbackService` with only `EnableTypedApi` overridden.
`GuestReadbackService.ScanRegion` returns
`scan-byte-budget-exceeded` when its remaining budget is zero.
`GuestReadbackService.Capture` refuses **any incomplete pass**
before invoking `TypedApiFreshnessTracker.Evaluate`.
The extractor looks for bounded frames with the `RRAPIVAL`
prefix and a complete `RRAPIVALEND` suffix, and the freshness tracker
requires independent source sequence/time advancement.

This is a valid fail-closed behavior for the current broad scan, but it
is incompatible with proving typed Lua data when the game's readable
private-memory footprint exceeds the configured bound.
**Do not infer the Lua frame is absent**: the scan did not complete.
Do not label unavailable coordinates as zero. The on-disk game binary
has not changed, but runtime allocation patterns are not qualified.

## Reuse-first next repair

Before changing or increasing the global budget, investigate the already
installed typed frame producer and historical successful reports. Design
a bounded, process-epoch-bound selection of memory ranges or a saved
reproducible locator for the API frame, while retaining the existing parser,
producer version checks, complete-frame checks, freshness tracking, and
strict PID/start/build/owner validation. Prove that a bounded positive
capture contains a fresh, uniquely selected typed API frame and that
malformed, conflicting or stale copies are rejected. Require independent
advancement and compare fresh Lua XYZ against the native snapshot from
the exact game epoch. This is a plan, **not** a completed field fix.
Do not edit the separate V1 tree without a dedicated, reviewed
compatibility patch; do not blindly expand scanning to more gigabytes.

## Maintenance cleanup

The PowerShell diagnostic shell was closed, the readback observer was
left running but minimized, and RIFT was visually restored to foreground.
The coordinated native host V7 was restored with a newly pinned one-use
launcher and shutdown marker (PID `34352`, Windows session 2), and
verified connected with coordinator ready, supervisor running, RIFT
PID `2768`, foreground `true`, disarmed and no held desktop inputs.
No RIFT input, memory write, game restart or VM setting change occurred
in this readback investigation. The durable navigation queue and
previously uncommitted navigation/control work were preserved.

This record represents completed root-cause diagnosis and runtime
restoration; it **does not** establish a fresh Lua/native XYZ match.
