# RR2 P1 handoff — Workbridge quarantine recovery and live WGC frame (2026-11-16)

**Last verified:** 2026-11-16 18:50 EST (23:50 UTC). **Machine:** `AMD-DESKTOP` only, independently confirmed through Workbridge and PowerShell. **Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`. **Scope:** physical RIFT, read-only observations; no gameplay input, mouse clicks, window focus changes, casting, or movement.

## Verified results

1. **Workbridge desktop quarantine cleared by reviewed archival, not deletion or action replay.** After the previous owner exited and no unknown script host/session owner remained, `C:\work\workbridge-mcp\scripts\Archive-DesktopQuarantine.ps1` passed read-only review and a one-shot SHA/lease/request-pinned `-Execute` archive. Evidence archive: `C:\work\workbridge-mcp\.tools\desktop-evidence\recovery-archives\rr2-p1-gui-archive-20261116-b`. Operation returned `mode=archived`, `newActionPerformed=false`, original LuaPad outcome `unknown_outcome`. Guard SHA-256 `31e6b1491d737af55fab45dbbb1f23c60d504bc379e09001b1b197f1404a4e85`; sidecar SHA-256 `d15c07065f8e70e8423b8dc52e0f97a3fa6ea92bf469a6c44c34200f1e0baf24`. Postcheck: no guard/sidecar/admission lock. The unrelated orphan `powershell.exe` PID 25016 disappeared on its own; **none was terminated**. Workbridge was healthy, v0.16.5-dev, tunnel ready.
2. **Physical RIFT identity reverified locally:** PID `77704`, start UTC `2026-11-16T14:47:31.6074064Z`, HWND `399711986`, window title `RIFT`, executable `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe`, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. These are historical pins; refresh all identity values before new work.
3. **First focus-neutral WGC/native frame attempt** at 23:46:49 UTC returned `gpu-capture-image-size-invalid`; it did not output a valid frame or send input. Root cause was directly confirmed: C# `PhysicalWgcProbe` imposed **8 MiB** maximum PNG size, while `scripts/physical_turn_visual_pair.py` already accepts **12 MiB**. The actual next image was 8,780,743 bytes (over 8 MiB but under 12 MiB).
4. **Scoped fix** to `tools/physical-wgc-probe/Program.cs`: align PNG cap to 12 MiB and add boundary regression to standalone self-test. `.NET 10` build of `PhysicalWgcProbe.csproj` passed with 0 warnings/0 errors; self-test passed **21/21**. Patch journal ID: `rr2-p1-fix-wgc-png-limit-20261116-a`. No other source files were edited by this lane.
5. **Single post-fix focus-neutral WGC/native capture succeeded** at 23:49:43 UTC via `C:\Python314\python.exe scripts\observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --physical-pid 77704 --native-facing --physical-capture-backend wgc`. Status: `verified-awaiting-visual-review`; image **2560×1392**, PNG **8,780,743 bytes**, SHA-256 `BF3D8D71703C9032CAD3C507BF97D2E15F1CB669D3458939E0806158458382B6`; WGC call ~383.6 ms; nonblank sample (96 quantized colors, 0.0042 very-dark fraction). Client-to-frame mapping is `available-candidate`: left 0, top 23, client 2560×1369. Receipts explicitly report `inputSent=false`, `focusChangedByProbe=false`, and target identity stable before/after; RIFT was **not foreground**.
6. **Stable native/frame bracket candidate:** native facing status `stable-bracket-candidate`; player entity position `(7218.976074, 873.204041, 3026.446777)`; body bearing ~-71.37°, camera aim ~-72.71°, optical camera bearing ~-71.37°, pitch ~-12.39°. Player projected in frame ~`(1280, 899)`, inside client. Native source was identity-stable across bracket. **Neither camera yaw nor body heading is qualified**; there is no target projection (`target-position-unavailable`). This is not an occlusion, collision, route or movement proof.

## Retained evidence (local only; ignored artifacts are not in Git)

- PNG: `C:\work\riftreader2\artifacts\observe-wgc-27d58645e80e4880aa48faacb04ff743\image.png`
- PNG receipt: same directory, `image.png.json`; SHA-256 of receipt `D4FAFC4BB56A365B6A41CF76229E7CBF2A9BB03867C558CA8601C06E977B4D6`.
- Native before/after: `C:\work\riftreader2\artifacts\physical-native-facing-bf8006fadcf04512a338a90ef534976e.json` and `physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json`.
- Workbridge command jobs: `rr2-p1-postquarantine-wgc-native-20261116-a` (8 MiB blocked); `rr2-p1-build-wgc-size-20261116-a` (pass); `rr2-p1-wgc-selftest-20261116-a` (21 passed); `rr2-p1-post-sizefix-wgc-native-20261116-a` (capture pass).
- Guard archive as above remains the durable evidence of earlier uncertain GUI action; never replay that old LuaPad request.

## Next practical steps

1. **Visual review and P1 qualification:** review the SHA-pinned WGC screenshot without a new game action. Distinguish player, healer/shrine, pillar, walls, fence and occlusion candidates near Sanctum Watch. Do not use an image/world mapping as collision proof.
2. **Read-only pixel/world comparison:** reuse the existing `scripts/physical_pixel_surface.py` ambiguity-preserving selection path and the native camera bracket to test a few explicitly selected high-value pixels. Keep depth and occlusion marked as candidates when unverified.
3. **Reconnect to RiftWorld Silverwood collision evidence:** only include verified HKX obstacle geometry in Detour; compare with screenshot silhouettes, and prioritize healer-to-shrine short routes once clearance is real.
4. **No movement authorization yet:** `movementEligible=false` until physical-world calibration, collision and control ownership checks genuinely pass. Never focus RIFT or send movement/casting from a screenshot analysis.
5. Preserve other developers' dirty files: on this pass unrelated modifications/untracked files were present under `scripts/`, `tests/`, `docs/reference/`, `.playwright-cli/` and `output/`. Commit/push only `tools/physical-wgc-probe/Program.cs` and this handoff.

**Important:** The Workbridge quarantine is recovered, and live screenshot acquisition now works. The native/screen-world/occlusion portion of P1 remains candidate-level pending visual and geometry qualification.

## Post-push P1 continuation — rendered-pillar/OBJ negative control (18:56 EST)

The SHA-verified WGC screenshot was **visually reviewed** at 960-pixel preview width. Atank, Quicksilver Medic, the right healer, tent, tree/rock backdrop, decorative plaza floor and two very large foreground stone pillars are clearly visible. This is a manual scene reading, not an automatic instance ID or depth measurement.

Using only the already retained screenshot, its stable native-camera-after report (SHA-256 `88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f`), the RiftWorld courtyard OBJ (SHA-256 `9638697914900f3098fbae11d3b6cabe95c663c954898fa6ca589ee759861dec`) and the **candidate-only identity-registration hypothesis** (SHA-256 `53528eba13ed3a1d9bf9e0322c3086372396d2fb55dc5daa46d8f47391c83248`), four pixels were replayed through `physical_pixel_ray.pixel_ray` and `physical_pixel_surface.intersect_prepared`. All four inverse rays forward-reprojected with error under `4e-11` pixels. Their first candidate intersections:

| Visually identified pixel (physical frame) | Hypothetical OBJ first group | Ray distance | Triangle |
| --- | --- | ---: | ---: |
| Left foreground pillar `(850,530)` | `world_terrain_7168_2816_nif_mesh_1` | 55.1519 | 32506 |
| Right foreground pillar `(2200,500)` | same terrain group | 46.2630 | 30874 |
| Open path `(1100,640)` | same terrain group | 32.8338 | 31737 |
| Decorative plaza floor `(1280,1200)` | same terrain group | 11.5240 | 31498 |

A radius-2 cardinal footprint replay (9 rays per point) returned **9/9 first candidate hits in that terrain group** for both visually pillar-occupied pixels and 9/9 for the open-path control. No missing hits or within-footprint mesh-group ambiguity was reported; ray depth ranges were left pillar `54.5306–55.7799`, right pillar `46.1959–46.3304`, open path `32.6039–33.0670` native units. Commands retained in Workbridge jobs `rr2-p1-live-frame-mesh-four-pixels-20261116-a` and `rr2-p1-live-frame-three-footprints-20261116-a` (both exit 0). This is a **negative visual/coverage observation**, not proof of a specific missing mesh: registration, clipping, source scope and object-instance identity remain hypotheses.

**Engineering decision:** a locally consistent terrain raycast or even a unanimous 9-pixel group vote must **never** be promoted to visible surface, walkable floor or collision clearance when scene imagery contains an intervening object. Next P0/P1 payoff: qualify source-mapped pillar/shrine geometry and Havok collision channels/instance transforms, or independently establish rendered-depth/occlusion evidence for those exact pixels; retain `occlusionQualified=false`, `obstacleQualified=false`, `movementEligible=false` meanwhile. No new screenshot, game memory acquisition or gameplay input was required for this continuation.
