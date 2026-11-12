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

## Remaining qualification

This output is an annotation of a retained frame, not a live desktop overlay.
Camera pan, resize/DPI changes and full-game restart need current qualification.
Projection inside the viewport does not establish visibility: depth, occlusion,
terrain and obstacle clearance are not checked. World/zone identity is currently
unavailable, so matching host/build/player alone cannot establish the same world.
The next implementation uses a no-focus, click-through owned overlay window and
withholds expired camera/geometry evidence rather than showing stale markers.
