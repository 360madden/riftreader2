# Physical world-to-screen markers

The existing native optical camera and combined projection matrix can project
arbitrary world XYZ into normalized client coordinates. Client/frame geometry then
maps those coordinates into a matching RIFT screenshot. This is separate from the
flat, player-facing map in the waypoint window.

Use the exact local host/process and a stationary camera. Capture through the
existing guarded observation path, saving its returned JSON in UTF-8:

```powershell
python scripts/observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --physical-pid PID --physical-capture-backend wgc --native-facing | Set-Content -Encoding utf8 artifacts/projection-observation.json
python scripts/plot_physical_waypoints.py --observation artifacts/projection-observation.json --route artifacts/waypoint-ready-route-69312.json --output artifacts/projection-preview
```

Replace PID with the freshly admitted process. The output directory must be new.
The renderer accepts only a stable native/frame bracket, verified image/geometry,
full native camera projection and complete recorded XYZ/height provenance matching
the snapshot's host, build and player. A historical recording process epoch is
allowed without rewriting its provenance. Missing heights are refused rather than
silently using a flat player-height plane.

`waypoints.png` adds numbered ground markers, +1.5-world-Y beacon lines and a cyan
player-position reference. `waypoints.json` retains exact input hashes/identities,
client/frame mapping, world/pixel projections, withheld-point reasons and limits.
The original screenshot and route remain untouched. Rendering itself reads only
saved files and sends no game input.

The reusable implementation is `physical_rift._project_world_point` plus
`physical_turn_visual_pair.client_frame_mapping` and
`project_client_point_to_frame`. No assumed FOV or newly invented camera model is
used. Behind-camera/near-zero-W and offscreen points are withheld from drawing.
Labels are clipped to the client so they cannot enter window chrome.

## First current-epoch observation

On November 12, AMD-DESKTOP/RIFT PID69312, a stable native-before/WGC/native-after
bracket projected all seven points from the actual recorded route. The cyan
player reference was at frame `(960.00,599.39)` and visually aligned with Atank's
feet. This is one stationary-view candidate, not a calibrated pixel-error claim.

- Observation: `artifacts/world-screen-observation-e5df35324a8541359d2a02d86bda9eb7.json`.
- Original image: `artifacts/observe-wgc-d3f297169731496d9133361407b27c82/image.png`.
- Annotated image/report: `artifacts/waypoint-screen-first-69312/waypoints.png`
  and `waypoints.json`.
- Focused renderer/projection/frame tests: 31 passed; the final seven renderer
  cases also passed after the worker's final simplification. Root reviewed the
  code and ran the real saved observation through it.

These are local artifacts; the portable measured route remains tracked under
`docs/validation/gui-taught-route-2026-11-12.json`.

## Off-center native unit check

A second read-only capture on PID69312 at 17:08 UTC bracketed WGC with two
bounded unit-manager scans. Both scans and all four optical-camera snapshots
matched, player position bits were unchanged, and the whole bracket took 2.88 s.
The scan examined 414 entries and found 152 position candidates; 18 nearby,
unchanged, in-view unit candidates were plotted. Root visually reviewed the
crosses against several dummy bases and soldier ground positions across the
image. This supports off-center geometric alignment in this view, without a
calibrated pixel-error or unit-type/name claim. Stored positions may be stale;
matching keys/bits alone do not prove visible presence.

Evidence: `artifacts/unit-screen-bracket-97090a9f867c4248bb8844f04b83778b/`
contains `bracket.json`, original `frame/image.png`, `units.png`, and
`projected.json`. No selection, casting, movement or focus change was sent.

Six serialized full camera/target reads took 0.282–0.698 s (median 0.474 s),
recorded in `artifacts/projection-read-latency-bbb7bc2180ed4d47b5a56d7a63e378e1.json`.
This motivated the bounded immediate-emission native stream below.

## Bounded camera stream and explicit focus

The native `sample-current-facing-stream` command accepts exact `--pid` and
`--start-ticks`, `--samples` (1–30), and `--interval-ms` (20–200). It emits each full
candidate immediately as NDJSON after strict process revalidation, then a count
receipt. It holds the existing read lease for at most a two-second acquisition
window; an individual synchronous operation may finish later. A deadline returns
`duration-limit` rather than claiming the requested sample count completed.
Each row retains capture timestamps and `captureElapsedMilliseconds`. Consumers
must check identity, age and current window geometry, and release between bursts.

On the current PID69312, 20 rows arrived about 95 ms apart, each 38–50 ms old at
emission. The Python feed then consumed a real 18-row duration-limited burst,
validated every projection and ended with a 0.160-second-old final frame. No keys
were sent. Evidence: `artifacts/projection-native-stream-3375b1ff3a514c8aac03a4301b2114ab.json`
and `artifacts/live-projection-provider-361e2912dbb740f0a6ee864bbc82c318.json`.

The existing native control command now has an explicit no-key focus action:

```text
RiftReader2.Live.exe move-key --focus-only --pid PID --expect-start-ticks TICKS --expect-sha256 SHA256 --expect-hwnd HWND --json
```

It requires every expected identity field, the existing exclusive control lock,
no held desktop inputs, and unchanged target geometry after activation. It cannot
be combined with movement, release or measurement flags. Root exercised it on
AMD-DESKTOP after checking desktop inactivity: RIFT became foreground, its client
remained at `(-1920,29,1920,1009)`, no inputs were held and `inputSent:false`.
Evidence: `artifacts/overlay-focus-only-first-69312.json`. Focus is an explicit
action; the projection feed itself never requests foreground. The stream and
existing/new focus-command tests passed 96 focused native cases; four stream
cases also passed after adding per-row elapsed metadata.

## Remaining qualification

This output is an annotation of a retained frame, not a live desktop overlay.
Camera pan, resize/DPI changes and full-game restart need current qualification.
Projection inside the viewport does not establish visibility: depth, occlusion,
terrain and obstacle clearance are not checked. World/zone identity is currently
unavailable, so matching host/build/player alone cannot establish the same world.
The next implementation uses a no-focus, click-through owned overlay window and
withholds expired camera/geometry evidence rather than showing stale markers.
