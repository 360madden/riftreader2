# Native wheel zoom validation

Date: 2026-10-20. Joey confirmed that the physical mouse wheel zooms RIFT when
controlling RIFT-Lab-1 directly in VMware, and requested the native zoom fix.
That is user-reported evidence; the native trials below were separately observed.

## Diagnosis and selected fix

The old `SendInput(MOUSEEVENTF_WHEEL)` path correctly encoded signed deltas in
multiples of 120 and used the correct x64 input layout. A fresh one-notch
positive trial still produced no visible zoom after a 700 ms observation delay.
See `before/`, `baseline-result.json`, and `baseline-after/` in the artifact root.
Successful Windows insertion therefore did not establish RIFT wheel consumption.

A targeted `WM_MOUSEWHEEL` message produced reversible visual zoom in the same
game process. Native wheel actions now use this path; keyboard and camera-drag
input remain on the existing insertion path. No fallback or retry sends a
second event. The precise internal reason RIFT ignores the old injected wheel
path remains unknown; this change does not claim hardware/raw-input equivalence.

Implementation follows Microsoft's [wheel-message contract](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-mousewheel)
and [bounded message-dispatch API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw).
The adapter:

- Verifies exact process/build/window, foreground, and reviewed client geometry.
- Requires the cursor inside the client and rejects sampled held bounded keys,
  modifiers, or buttons.
- Packs signed screen coordinates and signed wheel delta; rejects out-of-range
  coordinates instead of truncating them.
- Dispatches exactly once with a 100 ms timeout and BLOCK, ABORTIFHUNG,
  ERRORONEXIT flags. Timeout/failure is an unknown delivery outcome and disarms.
- Records `wheelMessageDispatched` only after successful dispatch. Both the
  response and panel distinguish dispatch from independently observed zoom.

The host remains capped at one notch per action. The synchronous Windows call
cannot be interrupted mid-call; it has no held input to release and its timeout
is bounded. No settings, bindings, V1 source, firewall, or VM configuration changed.

## Identities and reproducibility

Artifact root: `artifacts/native-zoom-20261020/`.

| Field | Value |
|---|---|
| VM | RIFT-Lab-1; `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx` |
| VMware | PID 39056; start ticks 134369666367568339 |
| Guest | DESKTOP-8632QPL; 192.168.56.128 |
| RIFT | PID 3400; start ticks 639280390564351086; HWND `0x401F2` |
| RIFT path | `C:\RIFT_TRANSFER\RIFT\rift_x64.exe` |
| RIFT SHA-256 | `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD` |
| Client geometry | 1211 × 686 at desktop (0, 23) |
| Candidate native SHA-256 | `F0609D87D74FB1EF47A373BBBD99F93A1CAE25171AB9FD0D91564E4708EA581C` |
| Final native SHA-256 | `DB43907B986D719976810CF0DC764731A729A454C5470CD755F348469845EF94` |
| Final receiver instance | `668442eca490471cbdd7563cd37b6500` |

`candidate-deployment.json` and `deployment.json` distinguish the two builds.
The final executable came directly from the full-gate published output.
`evidence-index.json` pins selected artifacts/source; the frozen
`host-evidence-snapshot.jsonl` retains command and capture identity without
depending on later writes to the running host journal.

## Live checks

All input followed review of a fresh in-world frame with text entry closed.
Each trial used a standalone one-notch action and no movement/camera-button input.

| Trial | Evidence | Result |
|---|---|---|
| Old native wheel +1 | `baseline-result.json`, before/after frames | Inserted, but no visible zoom. |
| Candidate message +1, +1, -1 | `message-before/`, `message-up-after/`, `message-up2-after/`, `message-down-after/` and corresponding results | Modest zoom inward, then opposite zoom outward; all dispatched successfully. |
| Browser wheel gesture | Host command `37d4e9cd712447b184aabd866080aefa`; `panel-wheel-result.png`, `panel-after/` | Exactly one +1 action, correct wheel-dispatch feedback, visible zoom, then explicit stop. |
| Final binary -1 | `final-before/`, `final-down-result.json`, `final-down-after/` | Visible zoom out; successful dispatch, no recovery required. |
| Final binary +1 | `final-up-result.json`, `final-up-after/` | Reversed the preceding zoom-out; successful dispatch, no recovery required. |

Read-only image patch matching independently supports the final reversible
change. Four ground-texture patches moved toward the view center after -1:
pixel offsets (+4,0), (-4,0), (+5,-6), and (-5,-6). After +1, all four matched
their original positions at (0,0). `compare_frames.py` and
`pixel-comparison.json` preserve the method and results. This is screen-space
visual evidence, not a numerical camera distance/angle or qualified memory field.

The final command envelopes took 163.18 ms for the zoom-out with cursor
repositioning/settling and 44.71 ms for zoom-in without repositioning. These are
whole-handler times, not message-only latency or a performance distribution.

## Gate and handoff

Full gate passed: **358 C# tests** (274 portable, 84 Windows), **173 Python
tests**, 108 Lua assertions, 22 Lua/C# cases, locked restore, zero-warning Release
build, formatting/dependency checks, deterministic replay, and published native
smoke. Evidence: `artifacts/validation/20261020T131932Z-22b4af08` and
`full-gate.log`. All 255 final documentation links passed. The final panel also
shows the wheel-use instruction; its focused checks passed after that copy edit.

`final-stop.json` and `final-status.json` record connected, foreground, disarmed,
idle, no pending recovery, and no sampled input down. The temporary bootstrap
server is stopped; the native panel remains available.

Zoom is visually verified for this identified windowed RIFT session. Numerical
zoom calibration, other game builds, fullscreen behavior, and sustained human
usability remain separate qualification work.
