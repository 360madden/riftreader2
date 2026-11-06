# Native control follow-up: timing and browser camera input

Date: 2026-10-20. Continues the [initial native control record](native-vm-controls-2026-10-20.md)
under Joey's instruction to keep working. No game/VM settings, bindings, V1
source, or global configuration were changed.

## Changes and rationale

- The hold clock starts after the first inserted press. Later chord/button/move
  setup consumes the same budget; expired setup rejects further input and
  attempts release.
- The panel's camera pulses use 100 ms, allowing the post-press target check
  and delta delivery to fit within the same practical window as movement.
- Cursor preparation preserves a safely placed cursor. Repositioning verifies
  the center and allows 50 ms for it to settle before pressing, with cancellation
  and target checks. Undersized clients and existing mouse-button-down state
  are rejected. There is no post-action restoration, including after failed release.
- Status samples aggregate Windows key/button state without claiming ownership
  or game consumption.
- Camera mode is explicit: Off, Right yaw/pitch, or Left orbit. Default bounded
  drag uses pointer capture; optional Pointer Lock remains available.
- Review countdown, expiry/reset feedback, mode-change stops, and separate
  release/action feedback make the operator state visible. Same-session action
  responses arriving after RELEASE remain visible; STOP/new review invalidate
  old responses.

## Identity and artifacts

All local evidence is under `artifacts/native-control-followup-20261020/`.
The exact target remained:

| Field | Observed value |
|---|---|
| VM | RIFT-Lab-1, `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx` |
| VMware process | PID 39056; start ticks 134369666367568339 |
| Guest | DESKTOP-8632QPL, 192.168.56.128 |
| Game | PID 3400; start ticks 639280390564351086; HWND `0x401F2` |
| Game executable | `C:\RIFT_TRANSFER\RIFT\rift_x64.exe` |
| Game SHA-256 | `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD` |
| Client | 1211 × 686, desktop origin (0, 23), foreground |
| Final receiver | `bb61ea19bc70499a8dd694f0611dbc2c` |
| Final native SHA-256 | `4CBD62FF5B75418F862782E6CD57001A63A973292A167B4E7CCE5015C93DD2AD` |

`timing-deployment.json`, `cursor-first-deployment.json`, and `deployment.json`
identify successive trial binaries. Earlier trials are not retroactively
attributed to the final binary. `host-evidence/control-host.jsonl` retains exact
commands, responses, connection identities, and capture references. Private
bootstrap/configuration/arm files remain ignored.
`evidence-index.json` pins the selected artifacts and source files; its
`host-evidence-snapshot.jsonl` is a frozen copy of the active host journal.

## Live observations

| Trial | Evidence | Observed result |
|---|---|---|
| Button-only right, 100 ms, no delta | `button-only-before/`, `button-only-result.json`, `button-only-after/`; timing build | 101.97 ms down-to-up; no visible camera change. Does not demonstrate a recentering defect. |
| Right yaw +8, 100 ms | `camera-final-before/`, `camera-final-result.json`, `camera-final-after/`; first cursor build | 113.96 ms down-to-up; relative delta inserted; small visible viewpoint change; no warp or recovery required. |
| Browser bounded drag | Host command `b61274b1ab474f89a6b5bb6f0901880d`; first cursor build | Right delta +3 inserted, 101.74 ms down-to-up, release succeeded. Found the delayed-response display race, then fixed it. |
| Final browser bounded drag | Host log at 12:46:48–12:46:49 UTC; `panel-drag-result.png`, `panel-final-after/`; final binary | Right delta (+3,+1) inserted. Pointer release cancelled the active action; button-up succeeded after 97.72 ms, no pending recovery. Panel displayed cancellation and retained release outcome. |
| Expiry and stop | Host log and panel observations | An idle 15-second arm expired and rejected a later drag. Final explicit stop disarmed and retained the last action result. |

The 100 ms completed trials in this small follow-up sample were within the
proposed ±20 ms tolerance. This is not a latency distribution or a scheduler
guarantee. The final short drag was intentionally interrupted by release.
Windows insertion timestamps are not game-consumption timestamps.

The Codex in-app browser explicitly rejected Pointer Lock:
“The root document of this element is not valid for pointer lock.”
The default bounded-drag path was then exercised successfully in that browser.
Sustained human usability and optional Pointer Lock in other browsers remain
unqualified. The panel displays a reviewed still image, not live video; use it
beside the VM display.

## Wheel diagnosis and limitations

Read-only inspection confirmed W/S/A/D/Q/E movement bindings and Alt+Z alternate
zoom. Camera settings showed Smart Camera enabled, Invert Y disabled, camera
shake disabled, and mouse Look Speed 2. No zoom-disable control was found in the
inspected camera/mouse settings. Settings were closed with Cancel.

A single VMware RFB wheel-up comparison also produced no visible zoom, matching
the earlier native-wheel result. See `wheel-compare-before/`, `wheel-vnc/`,
`bindings/`, and the settings captures. This weakens a native wheel-encoding-only
explanation but does not establish the cause. No held modifiers/buttons were
sampled when the new native diagnostics connected.

Wheel zoom remains unresolved. A direct physical-wheel baseline in VMware is
the next discriminating observation; do not keep repeating the same injected
wheel trial or claim zoom readiness. Numerical camera angles, fullscreen
capture, and hard-crash cleanup remain unqualified.

## Verification and handoff

Full gate passed: **336 C# tests** (274 portable, 62 Windows), **172 Python
tests**, 108 Lua assertions, 22 cross-language cases, zero-warning Release build,
locked restore, formatting/module checks, deterministic replay, and published
native smoke. Evidence: `artifacts/validation/20261020T125211Z-934ab6e9`,
with console output in `full-gate.log`; all 251 documentation links passed.
Final review also tested cancellation with failed release: the panel reports
uncertainty and disarms instead of claiming release. This failure path was
checked offline; no live release failure was deliberately induced.

`final-status.json` records the final native host/guest connected, foreground,
disarmed, idle, no pending recovery, and no sampled input down. Temporary
bootstrap service is stopped. The native panel remains available for the user.
No remote push was performed.
