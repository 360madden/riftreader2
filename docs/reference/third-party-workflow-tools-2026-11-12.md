# Third-party tools selected for RR2

Checked November 12 on **AMD-DESKTOP**, following Joey's preference for mature
third-party tools where they materially improve the workflow. The immediate
benefits are reliable overlay lifecycle and persistent desktop capture.

| Tool | Decision | Evidence and fit |
|---|---|---|
| [Qt / PySide6-Essentials](https://github.com/pyside/pyside-setup) | Preferred overlay backend | Official Python bindings, active upstream; latest checked commit November 12. Installed/pinned 6.12.0 (Python 3.14 supported). Replaces custom window/paint/timer dispatch with QWidget, QPainter and QTimer, while RR2 retains its target/projection checks. |
| [DXcam](https://github.com/ra1nty/DXcam) | Adopt bounded capture diagnostic; next persistent-capture candidate | MIT, 0.3.0 release March 12 with an actual cp314 Windows x64 wheel. Real 30-frame pilot captured RIFT plus the Qt overlay, including the correct negative-origin monitor crop. |
| [Rerun](https://github.com/rerun-io/rerun) | Adopt optional offline visualization pilot | MIT/Apache-2.0; official 0.43.1 release November 11. Windows stable-ABI wheel installed successfully on Python 3.14 in a separate ignored environment. An actual route/native/WGC recording exported and passed the upstream file verifier. Useful for viewing recorded XYZ routes, actor poses and verified screenshots together. Upstream labels the package Alpha; pin the version and keep it outside live control. |
| [Recast / Detour](https://github.com/recastnavigation/recastnavigation) | Reuse when actual environment geometry is available | Established mesh generation/path queries, Zlib license. It consumes triangle geometry; screenshots and waypoint dots alone do not provide the required walkable surface. Installing it now would not supply obstacle avoidance. |
| [OpenCV](https://github.com/opencv/opencv) | Keep for a concrete vision task | Active Apache-2.0 project. Reuse its calibration/features/image processing when needed; current native camera/matrix projection already works, so replacing that path would add conversion work without a demonstrated gain. |
| [ClickableTransparentOverlay](https://github.com/zaafar/ClickableTransparentOverlay) | Keep as a .NET/ImGui alternative | Apache-2.0; latest checked release/default-branch commit 11.1.0, January 6, 2025. External Direct3D11 overlay, but no-focus setup needs a native adapter and this Python feed would need an additional bridge. Qt is a smaller fit here. |
| [GameOverlay.Net](https://github.com/michel-pi/GameOverlay.Net) / [Overlay.NET](https://github.com/lolp1/Overlay.NET) | Do not select | GameOverlay.Net is archived; Overlay.NET's checked default-branch commit is from 2019. Neither improves the maintained-toolkit choice. |

Qt's Windows implementation maps no-focus and input-transparent flags before
native creation and uses a no-activation first show. Configure flags before
creating/showing the widget. Physical negative-origin placement still uses RR2's
small own-window bridge; do not globally divide desktop coordinates for mixed DPI.
Sources: [Qt window flags](https://doc.qt.io/qt-6/qt.html#WindowType-enum),
[Windows implementation](https://github.com/qt/qtbase/blob/6.12/src/plugins/platforms/windows/qwindowswindow.cpp),
[high-DPI guidance](https://doc.qt.io/qt-6/highdpi.html),
[Python support](https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html).

## What worked locally

- Qt hidden construction preserved foreground. The first real six-second run
  displayed 26 frames, preserved RIFT foreground/geometry on every presentation,
  and withheld one expired sample. Evidence:
  `artifacts/qt-overlay-first-constructor-9f7bfc9701944e8f91c631d9abe48986.json`
  and `artifacts/qt-overlay-live-proof-481a3c1159914c9bb43ec738783beff6/`.
- The actual waypoint Show/Hide buttons launched the isolated Qt child, displayed
  685 frames over 156.2 seconds, then stopped it with `stop-requested`. A camera
  drag at a marker anchor changed optical bearing by 8.59424 degrees with zero XYZ
  or body-bearing change. Evidence:
  `artifacts/waypoint-markers-summary-9d8052b493ca451f82c2fb06293f37b1.json`,
  `artifacts/qt-camera-clickthrough-validation-69312.json`, and
  `artifacts/qt-camera-pan-desktop-69312.png`.
- DXcam selected **AMD Radeon(TM) Graphics**, adapter 1/output 0,
  `\\.\DISPLAY5`, desktop rect `(-1920,6)-(0,1086)`. Client crop was
  `(0,47)-(1920,1056)`. Cold initialization took 0.509 s; median warm wait for
  advancing frame ticks was **17.27 ms** (maximum 36.26 ms). Thirty measured frames
  plus warmup and target checks took 1.93 s before saving PNGs. Root reviewed
  actual RIFT/Qt pixels. Evidence: `artifacts/dxcam-first-69312/probe.json`,
  `first.png` and `last.png` in that directory.
- Focused checks passed 63 cases: presenter/feed/marker lifecycle, eight offscreen
  Qt tests and 14 injected DXcam tests. Tests did not capture or send game input.

## Local setup and use

The installed environment is repository-local and ignored by Git:

```powershell
python -m venv .local/overlay-venv
.\.local\overlay-venv\Scripts\python.exe -m pip install -r requirements-overlay.txt
# Optional capture diagnostic:
.\.local\overlay-venv\Scripts\python.exe -m pip install -r requirements-capture.txt
```

The waypoint window automatically chooses that environment and `--presenter qt`
when present; its existing native backend remains available without the optional
environment. The CLI also accepts `--presenter qt` or `--presenter native`.
See [world-to-screen usage](../workflows/physical-world-screen.md).

```powershell
.\.local\overlay-venv\Scripts\python.exe scripts/probe_dxcam.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --display '\\.\DISPLAY5' --output artifacts/new-dxcam-probe --frames 30 --timeout 10
```

DXcam currently produces an explicit **diagnostic desktop-composite** report,
not an authoritative WGC observation. Foreground does not exclude other overlaid
windows. Its advancing ticks can include mouse updates; timestamp age and native
camera bracketing remain unqualified. The pinned 0.3.0 adapter uses a small private
atomic nonblocking frame/tick peek because the public timestamp getter waits
indefinitely. Keep that version boundary explicit. Existing guarded WGC remains
authoritative while persistent-capture integration is qualified.

The newer `scripts/probe_dxcam_native_pair.py` diagnostic verifies direct integer
QPC compatibility with Python's monotonic clock, warms capture, fences out buffered
events older than the first native read, and compares native camera/player state
before and after the accepted desktop event. The first post-restart PID60384 run
completed in 2.225 s, with a 0.890 s native pair and backend-event age bounds
5.018–6.833 ms; stop/release succeeded. Evidence:
`artifacts/dxcam-native-pair-first-60384/pair.json` and `frame.png`.
Thirteen injected checks passed. Its result is explicitly
`stable-native-composite-event-candidate`: LastMouseUpdateTime fallback still
prevents a fresh-RIFT-render claim, and endpoint equality cannot exclude ABA
changes. This does not replace authoritative WGC receipts.

```powershell
.\.local\overlay-venv\Scripts\python.exe scripts/probe_dxcam_native_pair.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --display '\\.\DISPLAY5' --output artifacts/new-native-event-pair --timeout 10
```

No generic workflow/agent framework, detection stack or navigation mesh was added.
Those need a concrete next capability and usable environment geometry first.

## Follow-up GitHub review, November 12 afternoon

The highest-value new capture pilot is
[windows-capture 2.0.1](https://github.com/NiiightmareXD/windows-capture), MIT.
Its Python API accepts an exact HWND and its native frame handler recreates the
pool on a size change instead of unconditionally discarding every first frame.
The maintainer reports the first occluded-frame sizing fix in
[issue 197](https://github.com/NiiightmareXD/windows-capture/issues/197).
This directly relates to the observed WgcSharp failure: stage diagnostics received
frame one, discarded it, and received no frame two. It remains a candidate,
because a later RIFT window screenshot was black and DXcam also stopped
receiving advancing events. The new backend received that black window surface
too; a different wrapper did not restore game rendering. Normal RIFT exit/relaunch
restored visible pixels. The next exact-HWND run captured Atank successfully in
1.066 seconds with exact target/snapshot equality and clean stop/wait, without
focus changes or game input. Evidence: `artifacts/windows-capture-first-38136/`
(chrome-only image) and `artifacts/windows-capture-recovered-17212/` (reviewed
game image). The diagnostic now checks the central 80% interior as well as the
whole surface so colored chrome cannot qualify a black client. That heuristic
does not establish client mapping, native bracketing, render freshness or occlusion
behavior. Nine injected checks pass. It remains an isolated optional diagnostic,
not the default observation backend.

```powershell
python -m venv .local/windows-capture-venv
.\.local\windows-capture-venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-window-capture.txt
.\.local\windows-capture-venv\Scripts\python.exe scripts/probe_windows_capture.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --output artifacts/new-hwnd-probe --timeout 5
```

[Win32CaptureSample](https://github.com/robmikh/Win32CaptureSample) is a maintained
MIT reference for received-frame snapshots, but adopting its C++/WinRT sample
would add more build and adapter work than the Python candidate.

For future geometry work, use [trimesh](https://github.com/mikedh/trimesh) first
for loading, transforms and inspection of an actual validated mesh. Consider
[Open3D](https://github.com/isl-org/Open3D) for point-cloud registration or
reconstruction once measured depth/geometry is available, and Recast/Detour for
walkable mesh generation and path queries afterward. These packages do not
supply RIFT terrain from screenshots or sparse route/unit positions.
[uv](https://github.com/astral-sh/uv) is a suitable future Python environment
manager, but the existing pinned local environments work; migrating them does
not resolve the present capture or geometry gap.

## Optional offline Rerun evidence viewer

`scripts/export_physical_rerun.py` converts a complete recorded route and optional
retained native/WGC brackets into a local `.rrd` recording. It reuses existing
source, identity, native camera, PNG/hash/receipt and client-mapping validation.
The 3D route retains actual XYZ heights; actor position/bearing uses the native
sample timestamps, while screenshot and already-computed 2D projections use the
capture timestamp. No camera calibration or synchronization is invented.
Each capture has its own image/projection entity tree. Original source paths,
hashes, recording epoch and withholding reasons remain in the recording.

Root installed the separate environment using prebuilt wheels only, exported
`artifacts/rerun-first-60384.rrd` and ran `rerun rrd verify`: one file verified
without error, with ten entity paths including the screenshot, 2D projections,
route, actor/bearing and source metadata. Sixteen focused exporter/projection
checks passed. Root also reviewed the actual headless Viewer render:
`artifacts/rerun-layout-60384.rrd` and `rerun-layout-60384-preview.png` show the
3D route beside the retained screenshot and projected markers. Its embedded
blueprint follows latest evidence on `evidence_utc`; pause/scrub for earlier
samples. +Y is displayed upward without adding a camera transform. Metadata
is a separate tab. Viewer timeline carry-forward is display behavior, not evidence
of a new observation. This is an optional visualization pilot, not live mapping,
occlusion detection or navigation authority.

```powershell
python -m venv .local/visualization-venv
.\.local\visualization-venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-visualization.txt
.\.local\visualization-venv\Scripts\python.exe scripts/export_physical_rerun.py --route docs/validation/gui-taught-route-2026-11-12.json --observation artifacts/qt-restart-wgc-observation-60384.json --output artifacts/new-evidence.rrd
# Local viewer: process-scoped analytics opt-out, loopback binding only.
$env:CI='1'
Remove-Item Env:FORCE_RERUN_ANALYTICS -ErrorAction SilentlyContinue
.\.local\visualization-venv\Scripts\rerun.exe --bind 127.0.0.1 --port auto artifacts/new-evidence.rrd
```

Repeat `--observation` for more retained frames, omit it for route-only output,
or use `--no-images` to validate sources but omit PNG payloads. Output must be a
new `.rrd`. Export does not start a viewer or server. The viewer uses a local
loopback service; the headless preview exits after rendering. Analytics opt-out
follows the pinned upstream `CI`/`FORCE_RERUN_ANALYTICS` logic without changing
shared user settings. Sources: [release](https://github.com/rerun-io/rerun/releases/tag/0.43.1),
[SDK APIs](https://github.com/rerun-io/rerun/blob/0.43.1/rerun_py/rerun_sdk/rerun/recording_stream.py),
[package and dependencies](https://github.com/rerun-io/rerun/blob/0.43.1/rerun_py/pyproject.toml),
[analytics logic](https://github.com/rerun-io/rerun/blob/0.43.1/crates/utils/re_analytics/src/lib.rs).
