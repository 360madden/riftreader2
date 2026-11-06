# Camera tracking and real browser focus loss

Date: 2026-10-20 (America/New_York). Joey authorized smoother camera tracking,
actual focus-loss verification on RIFT-Lab-1, fixes, and local commits.

## Changes and scope

Camera-only panel actions now request the existing native minimum of 20 ms
instead of 100 ms. Actions containing movement keys retain 100 ms. Incoming
camera movement is coalesced into at most one pending action, bounded to
±200 per axis. Fractional movement survives until integer emission. Release,
blur, and STOP discard pending deltas immediately; the panel never drains
old camera movement after release. This removes an avoidable hold delay and
limits lag without introducing a persistent guest-held button or new protocol.

The host was restarted to load the revised HTML (it reads the file at startup).
No V1 tools, Codex runtime dependency, game settings, or VM settings were added.

## Identity and retained evidence

- VM: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, RIFT-Lab-1;
  VMware PID 39056, start ticks 134369666367568339, VNC 5905.
- Guest: DESKTOP-8632QPL; native instance
  `d26484f41ed34c9da6911d465530bdf9`.
- RIFT: PID 3400, start UTC ticks 639280390564351086, HWND `0x401F2`,
  client 1211×686 at (0,23), foreground during the qualified control trials.
- RIFT executable SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- Active host configuration: `artifacts/native-usability-20261020/host.json`;
  restarted host PID 43936. Tokens remain ignored, local operator data.
- Raw evidence: `artifacts/camera-focus-20261020/`; frozen journal
  `control-host-snapshot.jsonl`, status JSON, physical window screenshots,
  and `final-panel.png`. Capture BMPs remain in the journal's recorded paths
  under `artifacts/native-usability-20261020/host-evidence/captures/`.

The control guest executable is unchanged from the preceding usability pass
(SHA-256 `70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E`).
The later full gate also builds a separate native-capture exit-check fix
described below; that new executable was not deployed to the game guest.

## Observations

| Trial | Observed evidence |
|---|---|
| Right yaw/pitch, 17:35:07–09 UTC | Twelve browser movements of +3 pixels produced nine native 20 ms actions totaling +36. All delivered and released successfully. Measured button-down to button-up intervals: 21.84–38.73 ms. First action included cursor preparation; whole-handler time is not hold time. |
| Left orbit | Twelve movements of −3 pixels produced nine actions totaling −33. All delivered and released successfully; intervals 22.31–37.60 ms. The unsent −3 tail was discarded on release, as intended. |
| Real window blur while armed, 17:36:22–24 UTC | Physical Edge ARM followed by Computer Use Alt-Tab produced visible `window blur: controls released; disarmed.` Native STOP `c66cbed22fa34fafa5f4a9bd5d16263e` was acknowledged 0.610 seconds after ARM, well before its 15-second expiry. Status: disarmed, idle, no recovery, `desktopInputsDown: []`. |
| Real window blur during a held browser drag, 17:36:56–17:37:08 UTC | A +12 right-camera action completed while the browser mouse button remained held. Physical Alt-Tab produced RELEASE then STOP `8f11f49de32648d8a5f51c0426a201ac`; STOP request-to-response was 24.44 ms. Screenshot shows window-blur feedback. Status again disarmed, idle, no recovery or sampled input down. |

The right-drag before/after captures are
`fbbf7d7ae16945b18350ba80b67bc5ba` and
`041a96e699244be0be76bfa6abd20ce6`.
Left-orbit captures are `78eecf328e5249e08278ea49d3e8d563` and
`2a314491241345e7a9fdc606f5f4536d`.
Visible world geometry changed in the expected directions. These are visual
observations, not numerical camera-angle measurements.

The earlier 100 ms sample measured 101.97–113.96 ms button intervals. The
shorter intervals above establish removal of the extra hold delay in these
trials, not a fivefold improvement in frame rate or perceived smoothness.

Initial automation attempts were inconclusive: browser automation focus and
the physical Edge window disagreed, a few attempts reached arm expiry, and
one stale-review ARM was rejected. Those attempts do not count as blur passes.
The qualifying trials selected the actual Edge window, disabled debugger focus
emulation for the test, used physical Alt-Tab, and correlated visible feedback
with native STOP/status records. Early in the pass, guest overlays were visible;
the VM-bound repository console helper closed menus before control trials.

## Repeatable verification

1. Start the repository host/guest; reacquire exact VM/game identity and confirm
   idle state. Reload the panel from its launch URL after restarting the host
   when HTML changes.
2. Use a visible ordinary browser window. If a debugger is attached, ensure
   focus emulation is disabled. An in-app tab switch alone is not a blur test.
3. Capture and visually review in-world state with text entry closed. Select
   right or left camera mode, confirm review, and arm.
4. Drag a small distance over about half a second, then release. Check native
   action holds are 20 ms, button-up succeeded, and no queued action starts
   after release. Repeat the other camera mode from a fresh review.
5. From a fresh arm, Alt-Tab to another host window before expiry. Repeat with
   the browser drag held. Check explicit window-blur feedback, STOP journal
   acknowledgement, and disarmed/idle/no-recovery/no-input-down status.
6. Stop before leaving. Retain screenshots and exact journal identities; never
   equate input insertion with game consumption.

Offline regression command:
`node tests/control_panel_async.js scripts/control_panel.html`.
The full gate runs it through the Python panel contract suite. Four new
scenarios cover camera cadence/backlog, unchanged movement duration, release
discard, and blur discard. Eighteen async scenarios now run in total.

## Gate and limitations

Full gate passed at `artifacts/validation/20261020T173733Z-c655e828`:
364 C# tests, 174 Python tests, 108 Lua assertions, 22 Lua/C# cases, locked
restore, zero-warning Release, native publish smoke, formatting, module checks,
and deterministic replay. Documentation links were rechecked after this record.

Two earlier gates exposed independent native-capture test failures. A disposable
process could exist before Toolhelp exposed its module; its fixture now waits
only for that specific initialization error. Separately, revalidation once
returned success after an awaited process exit. The precise kernel timing was
not measured. Native capture now checks the process handle's zero-time signaled
state as well as its existing timestamps and identity. The handle adds only
non-mutating synchronization access. Repeated exited-process tests and the
full gate passed. This capture fix is separate from camera input.

These remain bounded pulses, with native inspection and network overhead
between them. Long-session comfort, frame-by-frame continuous tracking,
one-to-one camera calibration, fullscreen, and hard-crash cleanup remain
unqualified. Combined movement/camera actions intentionally retain 100 ms.
The live blur trial's native action had already completed: guest focus loss
mid-pulse was not exercised. Continuous foreground checks and unconditional
release on target loss retain automated executor coverage.
