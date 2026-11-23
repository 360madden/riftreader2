# RR2 movement CLI (disposable C# helper)

This manual, one-shot helper sends a bounded Windows scan-code hold through RR2's C# input engine. No VMware, addon chat-focus synchronization, PowerShell input, or legacy RiftReader runtime.

**Failure and recovery record:** [Why previous RR2 focus implementations failed, and how the known-good RiftReader A/B test resolved the blocker](validation/move-key-focus-failure-postmortem-2026-11-11.md).

Run from the RR2 checkout on the verified local Windows host that owns RIFT.
[Publish or select the local reader](workflows/development.md#publish-the-local-native-reader)
and set `$rr2PublishedReader` to its executable. List the current RIFT clients
and set `$riftPid` to the exact client you intend to select.

```powershell
$rr2Host = [Environment]::MachineName
Get-Process -Name rift_x64 | Select-Object Id, ProcessName, StartTime
```

With `$riftPid` set, prepare the preview. The arguments pin the process lifetime,
executable and window so a client restart requires fresh selection.

```powershell
$selection = python -B scripts/physical_rift.py --expected-host $rr2Host --physical-pid $riftPid | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $selection.status -ne 'ready' -or $selection.target.hwnd -le 0) {
    throw 'The selected local RIFT process and window could not be verified.'
}
$target = $selection.target
$identityArgs = @(
    '--pid', [string]$target.processId,
    '--expect-start-ticks', [string]$target.processStartUtcTicks,
    '--expect-sha256', $target.executableSha256,
    '--expect-hwnd', [string]$target.hwnd
)
& $rr2PublishedReader move-key @identityArgs --key w --hold-ms 1000 --json
```

For a separately authorized move, choose one action with the verified local
calibration and controller in place.

```powershell
# Bounded one-second W pulse.
& $rr2PublishedReader move-key @identityArgs --key w --hold-ms 1000 --execute --json

# Measure native XYZ before and after the pulse on the supported RIFT build.
& $rr2PublishedReader move-key @identityArgs --key w --hold-ms 1000 --execute --measure-xyz --xyz-settle-ms 250 --json

# Compatible simultaneous keys.
& $rr2PublishedReader move-key @identityArgs --key 'w,e' --hold-ms 1200 --execute --json
```

For an actor-pose measurement preview:

```powershell
& $rr2PublishedReader move-key @identityArgs --key a --hold-ms 500 --measure-actor-pose --json
```

- `--execute` is mandatory to emit input. Without it, only preview output.
- Default hold **1000 ms**; accepted **20–3000 ms**.
- Supports `w,a,s,d,q,e`, including compatible simultaneous combinations. Conflicting `w,s`, `a,d`, `q,e` are refused.
- Exact `--pid` is mandatory. The examples also pass `--expect-start-ticks`, `--expect-sha256` and `--expect-hwnd` from local process selection.
- With `--execute`, the helper **focuses the selected RIFT game window by default**. It follows the successfully tested legacy RiftReader C# order: attach the foreground and target GUI input threads, call `SetForegroundWindow`, wait 250 ms, detach, and reverify the pinned window before input. It restores only a minimized window (never unmaximizes a visible game) and reports focus-thread results on an attempted focus. If Windows denies focus, **no input is sent**. Use `--no-focus` to manage focus yourself; `--focus` remains accepted. This is game-window focus, **not** addon chat focus. Preview without `--execute` never changes focus.
- The helper uses the same RR2 control-agent semaphore, checks the target epoch/build/window, monitors foreground while holding, and always attempts key-up on normal completion or cancellation.
- The screenshot approval journal belongs to the AMD-DESKTOP `scripts/physical_one_pulse_runner.py` workflow.
- `--measure-xyz` optionally reads the exact-build native player XYZ before and after this single pulse. `--xyz-settle-ms 250` optionally delays only the after-sample if release/target state is clean. The first read must succeed or **no input is sent**; a failed second read is reported without repeating input. It reuses the existing C# native memory reader and lease; no addon, PowerShell movement, extra report file, or additional service.
- `xyzFeedback.planarDisplacementCandidate` is distance in X/Z; `movementCandidate` is true at 0.03+ units with the same owner and a valid capture gap. Cached native XYZ may be stale; the reading is **not independent proof the game consumed input**.
- `--measure-actor-pose` (new, offline-tested Nov 11) optionally reads the current-build actor/model matrix candidate and same-player bracketed XYZ **before and after** a bounded pulse. A missing/failed before-read prevents sending input; a failed after-read never repeats input. `poseFeedback.actorPlanarDeltaDegreesCandidate`, `modelPlanarDeltaDegreesCandidate`, `actorMatrixBitsChanged` and capture timestamps are candidate evidence only. `poseFeedback.actorHeadingQualified=false` and `gameResponseVerified=false` deliberately remain false. For A/D, use independent before/after screenshots to distinguish actual viewpoint movement; precise actor yaw is still unqualified. If both XYZ and pose are requested, reads are sequential, not atomic; XYZ settling (if requested) precedes the after-pose acquisition.
- For a single `a` or `d` with `--measure-actor-pose`, `turnRateCandidate` now computes signed and absolute **actor-matrix angle change per second using the midpoint of measured SendInput key-hold bounds**, not the requested hold or the entire executor duration. It refuses missing/unchanged/ambiguous angle, incorrect pose owner, excessive capture gap, failed insertion/release, inconsistent UTC/monotonic timing, or implausible hold duration. Both `turnRateCandidate.actorHeadingQualified` and `navigationEligible` remain **false**: the value is a research candidate, not an accepted steering rate.
- Executed `move-key` receipts include `inputCallTiming` for the bounded executor, plus `keySendEvents` (start/return UTC times and success of each Windows key-down/key-up call, including watchdog release) and `keyHoldWindows` (monotonic minimum/maximum/midpoint hold estimates). The actual Windows insertion occurs somewhere inside each call, **not at an exactly known timestamp**. Missing/failed/duplicate release events never produce a valid hold estimate. A UTC clock jump is marked inconsistent; key insertion cannot be undone or treated as absent. Historical receipts cannot be upgraded to exact key timings.
- `scripts/physical_move_key_calibration.py` offline-imports all three receipt generations: original executor-only, executor with UTC call envelope, and new per-key event windows. The resulting `holdMeasurementSource` field identifies the precision; only validated new per-key windows replace the executor duration as the velocity denominator. All outputs remain candidate-only.
- **49/49 focused .NET 10 tests and 28/28 focused Python tests passed** for this timing/import change. A physical RIFT `move-key` **preview-only** run returned `inputSent=false`. **No live pulse with the new key-send timeline was executed.** It is not an automatic navigation loop.
- "Input inserted" is **not proof the character moved**. Use candidate XYZ alongside observed gameplay movement, especially when the cached position does not refresh.

**AMD-DESKTOP live result (2026-11-11 08:53 EST):** RIFT PID44888/HWND `0x911EC`; legacy-style focus from Edge succeeded (both thread attachments true), one 750 ms W completed with release and 770.2 ms observed duration; same-unit native position shifted **4.6516 X/Z units** after 250 ms settle. This is strong candidate movement feedback, but an independent RIFT gameplay/Lua confirmation is still pending; do not reuse the run-specific PID or HWND.

Offline checks (never send game input):

```powershell
& $rr2DotNet test .\tests\RiftReader2.Live.Tests\RiftReader2.Live.Tests.csproj --no-restore --filter 'FullyQualifiedName~MoveKeyCommandTests'
python -m unittest discover -s tests -p test_physical_one_pulse_runner.py
```

### Delayed actor-pose observation

Use `--measure-actor-pose --actor-pose-settle-ms 500` to wait 500 ms after a successfully completed and released pulse before reading the after-pose. The optional delay accepts 0..1000 ms and defaults to zero. Receipts report `actorPoseSettleMilliseconds` and `actorPoseSettleApplied`. When XYZ settling is also requested, the pose delay follows the XYZ observation.

This is a fixed observation delay. Check repeated read-only pose samples when evidence of stability is needed. The physical November 11 trials showed roughly 4–5 degrees of further actor-matrix change after the immediate sample. Turn rates continue to use the measured key-hold window. A failed release or lost target withholds the after-pose.
