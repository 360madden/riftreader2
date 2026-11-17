# RR2 P1 handoff — pinned WGC terrain + temple screen ray candidates

Updated: 2026-11-16 19:38 EST (America/New_York)
Machine: **AMD-DESKTOP** verified through Workbridge (not LEGION)
Repository: `C:\work\riftreader2`, branch `codex/modular-foundation`
Scope: **offline, read-only physical RIFT screenshot replay**; no gameplay input or camera manipulation

## Delivered

- `scripts/physical_pixel_composite.py`: single CLI combines terrain and Sanctum Watch temple **render** triangle candidates at a supplied WGC pixel; it now requires a SHA-pinned, unchanged-player/orientation/camera **native-before → WGC → native-after** bracket of at most 5 seconds, reuses the existing strict PNG/receipt validator, orders candidate ray depths, preserves ambiguity, and explicitly refuses optical visibility, physical blocking, floor safety, or navigation.
- `tests/test_physical_pixel_composite.py`: synthetic depth/tie/no-hit controls, wrong process and tamper controls, real historical WGC frame and source anchoring, displacement negatives, cardinal 9-ray pixel footprints, safe annotated preview with exclusive-create race protection, horizontal pillar candidate transitions, and negative controls for stale native brackets, unstable camera, incorrect PNG dimensions, and preview collision.
- Optional `--preview-png` creates an annotated **new** PNG copy via exclusive file creation (never overwrites the screenshot or a concurrent writer's output). Verified preview: `artifacts/rr2-p1-watch-composite-20261116-1919.png` (SHA256 `e26f70b36bad140a5873ad26ee4fd626a7f5e243feb9e056c458fd8f0ef69c51`). It is an ignored local artifact, **not** in Git.
- Existing ray, terrain-surface, WGC frame, and renderer sources were reused; no competing framework or renderer was introduced.

## Verified historical source pins (do not silently substitute)

| Source | Path (relative to C:\\work unless noted) | SHA256 |
| --- | --- | --- |
| WGC image | `riftreader2/artifacts/observe-wgc-27d58645e80e4880aa48faacb04ff743/image.png` | `BF3D8D71703C9032CAD3C507BF97D2E15F1CB669D3458939E0806158458382B6` |
| WGC receipt | same folder, `image.png.json` | `d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6` |
| Native facing, before | `riftreader2/artifacts/physical-native-facing-bf8006fadcf04512a338a90ef534976e.json` | `609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7` |
| Native facing, after | `riftreader2/artifacts/physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json` | `88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f` |
| Terrain OBJ | `RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj` | `9638697914900f3098fbae11d3b6cabe95c663c954898fa6ca589ee759861dec` |
| Terrain registration | `riftreader2/artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json` | `53528eba13ed3a1d9bf9e0322c3086372396d2fb55dc5daa46d8f47391c83248` |
| Temple render OBJ | `RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1/geometry.obj` | `7e0a0900fbb7f7334129990086f1ed0bf2338c8b3685c9eea18a962b68126fcd` |
| Temple exact anchor | same temple folder, `atank-source-floor-anchor-exact-r2.json` | `6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525` |

The WGC/native receipt identifies historical Atank PID `77704`, start ticks `639304372516074064`; these are **not** a license to act on the current game process.

## Reproducible ray candidate observations

| Screenshot pixel (2560×1392) | First triangle layer | Ray distance (native units) |
| --- | --- | ---: |
| left pillar `(850,530)` | temple-render | 13.8198 |
| right foreground pillar `(2200,500)` | temple-render | 6.0409 |
| plaza `(1280,1200)` | temple-render | 8.6406 |
| open path `(1100,640)` | terrain | 32.8338 |

For the four points above, radius-2 cardinal footprints are **9/9** same first layer, but remain *candidate-only*. Moving temple render source +10 native units in X or Z invalidates the recorded pillar intersections.

Bounded 26-pixel horizontal edge replay (2026-11-16 19:23 EST):
- At y=530 the first layer changes from terrain at x=835 to temple at x=850, and temple at x=950 to terrain at x=980.
- At y=500 the first layer changes from terrain at x=2150 to temple at x=2200, continuing temple through x=2500.
- These transitions roughly match the pictured pillar silhouettes, especially the large right foreground pillar, but **do not** establish actual scene depth/visibility or collider contact.

## Run this offline replay on AMD-DESKTOP

From PowerShell in `C:\work\riftreader2`, with all sources present:

```powershell
$temple = 'C:\work\RiftWorld\artifacts\p0-watch-temple-source-render-20261116-agent-iso-r1'
$wgc = 'C:\work\riftreader2\artifacts\observe-wgc-27d58645e80e4880aa48faacb04ff743'
& 'C:\Python314\python.exe' '.\scripts\physical_pixel_composite.py' `
  --image "$wgc\image.png" --receipt "$wgc\image.png.json" `
  --receipt-sha256 d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6 `
  --native-before '.\artifacts\physical-native-facing-bf8006fadcf04512a338a90ef534976e.json' `
  --native-before-sha256 609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7 `
  --native-after '.\artifacts\physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json' `
  --native-after-sha256 88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f `
  --expected-host AMD-DESKTOP `
  --terrain-obj 'C:\work\RiftWorld\artifacts\geometry-workflow-courtyard-20261114-r1\geometry.obj' `
  --terrain-registration '.\artifacts\pixel-surface-p1-20261116\courtyard-identity-hypothesis.json' `
  --temple-obj "$temple\geometry.obj" `
  --temple-anchor "$temple\atank-source-floor-anchor-exact-r2.json" `
  --temple-anchor-sha256 6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525 `
  --pixel 850 530 --pixel 2200 500 --pixel 1280 1200 --pixel 1100 640 `
  --pixel-selection-radius 2
```

New preview files require a fresh path: append `--preview-png '.\artifacts\NEW-unique-name.png'`. A preexisting file now fails the exclusive-create check even if a race occurs after the precheck. JSON output is deliberately `candidate-only`.

## Independent second camera view (19:36 EST)

- New independent WGC camera pose: `artifacts/observe-wgc-f37599014aaa422a94682503abb6d532/image.png` (SHA256 `5f09703eca7639f583e68bd40aea19d36d20483e3752ae743b776c90133c4c75`), same historical Atank epoch; `tests/test_physical_pixel_composite_second_view.py` replays eight pixels, with two focused tests passed.
- Annotated preview: `artifacts/rr2-p1-watch-composite-second-view-20261116-1936.png` (SHA256 `e8a93fb4d46c01f3a9b63d494b3e4037b50017b027fddf49f06d26c5211368a1`). Results remain render candidates, never visibility or collision proof.

## Strengthened provenance — independently replayed retained frame

The pinned before/after native reports have identical process/build, player keys, orientation raw bits and optical camera values; both reports declare stable camera-within-target reads. The strict timestamp sequence is **before completed → WGC started → WGC completed → after started**, with a **2.337266-second** total bracket, under the enforced 5-second maximum. Existing `physical_turn_visual_pair.verified_frame()` checks real PNG dimensions (**2560×1392**), image byte count, SHA, quality and receipt consistency. All analysis still returns candidate-only data.

## Test result and safe continuation

`C:\Python314\python.exe -m unittest discover -s tests -p 'test_physical_pixel*.py' -v` => **74 tests, all passed** at 19:37 EST. The run is offline only. The Git branch was in sync with origin before this handoff; other workers' dirty and untracked files were left untouched.

P0/P1 unfinished:
1. **RiftWorld owner**: obtain *actual* physics collision/contact response and source collision-channel/shape identity at Sanctum Watch. Temple render triangles do not imply a physical obstacle; retain `STOP=true` until accepted.
2. **RR2 P1**: qualify visible surface via independent optical evidence (depth-buffer/fragment identity or supervised screenshot-pixel segmentation with explicit uncertainty), not by equating nearest triangle with what the frame displays.
3. **RR2 integration**: if consuming candidate results now, expose them as advisory visualization only, with hard `movementEligible=false` and no automatic route clearance.
4. For any live test later, reverify current PID/start time/executable hash/camera, obey AGENTS STOP/GO, and request distinct authorization before keyboard/mouse/gameplay actions.

Do not clear blockers based on ray overlap, image alignment, or historical process identity alone.
