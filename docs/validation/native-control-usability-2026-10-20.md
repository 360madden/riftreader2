# Native control panel usability pass

Date: 2026-10-20. Joey authorized Computer Use inspection of RIFT-Lab-1,
browser movement/camera checks, repository-native fixes, and local commits.

## Scope and evidence

Artifact root: `artifacts/native-usability-20261020/`. The final native host
uses the private configuration in `artifacts/native-usability-20261020/host.json`.
Neither that configuration nor its operator token belongs in tracked evidence.

Windows Computer Use read the VMware console and accessibility tree. Its
initial observation and subsequent active tab disagreed; RIFT-Lab-1 was
reselected before further inspection. Later focus, Escape, and menu-click
attempts did not visibly open the game menu. This pass therefore does not
qualify Computer Use input through VMware. The existing repository-owned,
VMX-bound console helper successfully opened and inspected the menus instead.
Browser automation exercised the actual operator panel.

The native receiver was freshly checked: instance
`668442eca490471cbdd7563cd37b6500`, guest DESKTOP-8632QPL, RIFT PID 3400,
start ticks 639280390564351086, HWND `0x401F2`, client 1211 by 686 at (0,23).
VMware PID 39056/start ticks 134369666367568339 and the RIFT executable
SHA-256 match the [zoom validation](native-zoom-2026-10-20.md).
That was the initial receiver. The final deployed receiver is
`d26484f41ed34c9da6911d465530bdf9`, using executable SHA-256
`70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E`
in `C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad`.
`deployment.json` pins the bundle and executable. The executable is identical
to the final full-gate publication. The game process/build did not change.

## Observed game configuration

The retained `bindings/`, `settings/`, and `camera-settings/` screenshots show:

| Setting | Observed value |
|---|---|
| Move forward/backward | W / S; up/down arrows as alternatives |
| Turn left/right | A / D; left/right arrows as alternatives |
| Strafe left/right | Q / E |
| Look behind / alternate zoom | Alt+S / Alt+Z |
| Mouse look speed | 2 |
| Smart Camera | Enabled |
| Invert Y, camera shake, water collision | Disabled |

Settings were inspected and cancelled without applying changes. Menus were
closed before reviewing an in-world frame for any movement/camera trial.
This visible binding page did not expose a separate mouse-wheel binding;
the earlier physical-wheel report and native zoom observations remain the
evidence for wheel behavior.

## Findings and changes

The initial browser strafe changed the scene, and a small right-button drag
changed the camera. Their final pulses were cancelled by release, with
successful key/button cleanup. The panel correctly distinguished cancellation
from an uncertain release.

Code review identified races around arming, capture, STOP, and stale responses.
The resulting fixes are native to this repository:

- Serialize capture, arm, STOP, and recovery; disable duplicate submissions.
- Stop an active session before replacing its screenshot; clear all queued
  keys, deltas, wheel input, timers, and pointer capture on invalidation.
- Reject stale action/release completions and late Pointer Lock grants from
  older sessions. Keep status snapshots separate from action evidence.
- Release active input when focus leaves the control surface; suppress
  Ctrl/Alt/Meta movement shortcuts and zero-vertical wheel events.
- Stop immediately on focus loss during pending ARM, then stop again after
  that request settles. The native agent also invalidates the old capture on
  STOP, recovery, and replacement capture, including failure paths. Thus a
  later-sequenced ARM cannot reuse pre-STOP authorization.
- Keep RELEASE separate: it cancels the current pulse while preserving a
  still-valid arm session.
- Send every STOP with `fetch` keepalive. A live navigation test exposed why
  setting keepalive only in `pagehide` was insufficient: an earlier blur or
  visibility callback could start a non-keepalive STOP, clear local state, and
  prevent the later callback from replacing that request.

The default-binding help now distinguishes movement, turning, and strafing;
camera Off explicitly says keys and zoom remain available. No game settings,
V1 source, VM configuration, firewall rules, or global settings changed.

## Final live checks

`trial-summary.json`, `host-evidence-snapshot.jsonl`, and retained capture BMPs
correlate actual input with later observations. `baseline-journal.jsonl` retains
the earlier trials made before the new receiver was deployed. Sequences restart
on host reconnect; command IDs and UTC times disambiguate them.

| Trial | Evidence | Observed result |
|---|---|---|
| Pre-STOP review rejection | `deployed-before/`, `revoke-review-stop.json`, `revoked-arm.log` | Freshly reviewed capture, then STOP, then ARM was rejected with `Review missing, stale or target changed.` No action was sent. |
| Right yaw/pitch | `d075da7eee244ff88151f3b53d4b500a`; capture `21b9bdf8c0c646cf9ca1c73342def929` | Visible view change; inserted delta (20,5); pointer release cancelled the remaining hold and button-up succeeded. |
| Left orbit | `478413cadd9143258fa6da7bf06101ea`; capture `b844eab279444ea2a513199f18d3f46c` | Visible orbit change; inserted delta (-10,0); release cancelled the hold and button-up succeeded. |
| Horizontal then positive wheel | `c960c93047a74154b5e962772a1eff1b` | Exactly one +1 wheel action for the subsequent vertical gesture; no action from horizontal scrolling. |
| Negative wheel | `6997ec958b3b476bb3a4546e9d04ce96` | Successful -1 dispatch and visible reversal of zoom. |
| Q strafe and key release | `6759171cca7147c58cf0ae53f03594f1`; capture `3372a1987d534a74a171c4781f3068c5` | Visible scene change, successful insertion/release; measured key interval about 104.47 ms for this single pulse. |
| Status after movement | `status-preservation.json` | The displayed action JSON remained byte-for-byte unchanged after Status completed. |
| Navigation before keepalive correction | ARM `1333c40fa02f451ea10db3b78cc53ff9`; `page-exit-status.json` | No STOP reached the host; 14.52 seconds later the guest was still armed with 0.48 seconds left, idle with no sampled input down. Explicit cleanup followed. |
| Navigation after correction | ARM `0ea73c69e9394fcdbb6fc358a26d2e20`, STOP `fc9ed6b3a99a4cd7b710f8cabc5ee7cc`; `page-exit-fixed-status.json` | STOP acknowledged 0.481 seconds after ARM response; subsequent status disarmed/idle, no recovery or sampled input down. |

The read-only `compare_zoom.py` comparison corroborates reversible zoom:
three unobstructed ground patches moved outward after +1 and returned to
(0,0) pixel displacement after -1. A fourth sampled region overlapped moving
foreground content and is not used as camera evidence. This is screen-space
evidence, not numerical camera calibration.

Opening a second in-app browser tab did not produce the expected blur/visibility
transition in this automation environment; the original panel expired normally.
That attempt does not establish live window-blur handling. Page navigation was
verified separately above. Pending-arm blur, same-document focus release, stale
responses, and modifier handling are covered by executable regression tests.
Rapid drag release intentionally discards unsent deltas; delivered deltas can be
smaller than the full browser gesture. This pass does not claim one-to-one drag
distance or smooth continuous camera tracking.

## Validation and handoff

Final full gate: `artifacts/validation/20261020T161445Z-98004030`,
with log `keepalive-full-gate.log`: **364 C# tests** (274 portable, 90 Windows),
**174 Python tests**, 108 Lua assertions, 22 Lua/C# cases, locked restore,
zero-warning Release build, formatting/module checks, deterministic replay,
and published native smoke. Node was available and the Python panel test
actually executed all 14 asynchronous JavaScript scenarios; it was not skipped.
Six guest authorization tests cover invalidation and cancellation transitions.

`final-stop.json` and `final-status.json` record connected, foreground, disarmed,
idle, no recovery required, and no sampled control input down. The temporary
bootstrap server is stopped. The native host remains available with its PID
in the artifact root. `evidence-index.json` pins sources and retained evidence.
The new tests require no Codex, Computer Use, browser extension, or V1 runtime.

## Limitations

This is a bounded agent-operated usability pass in one windowed game session.
It does not establish long-session human comfort, calibrated camera angles or
distance, fullscreen behavior, other builds, or cleanup after an OS/hypervisor
hard failure. Pointer Lock remains optional; the tested browser uses bounded
drag. Game response remains separate from native input delivery acknowledgments.
