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

## Consolidated P1 follow-through — 2026-11-16 19:56 EST

### Offline implementation, independent checks, and provenance

- The independently retained second camera frame (`observe-wgc-f37599014aaa422a94682503abb6d532`) passed its own before/WGC/after SHA and stable-camera bracket (2.211218 seconds). The 27-ray boundary has terrain at `(1950,400)` and temple candidate at `(1970,400)` near the right pillar; `(2200,1000)` intersects temple behind UI and correctly stays `visibleSurfaceQualified=false`. This is a negative visibility control, not optical proof.
- Source code now requires both SHA-pinned native reports, matching process/player/orientation/camera observations, temporal bracket, actual PNG dimensions/quality, and exclusive-create preview output. Rejects mismatched but self-consistent PNGs, changed camera, bad bracket, and existing output.
- An exact-parity, dependency-free BVH lives in `scripts/physical_pixel_mesh_accel.py` and is enabled only with `--accel bvh` on `scripts/physical_pixel_composite.py`; default `off` is unchanged. Query and footprint payloads remain candidate-only, `visibleSurfaceQualified=false`, `movementEligible=false`. Do not infer clearance or make live input from them.
- Offline screen-to-world suite: `C:\Python314\python.exe -m unittest discover -s tests -p 'test_physical_pixel*.py' -v` => **80/80 passed**. Separate BVH parity included 200 seeded fuzz rays with zero mismatches, all 64 pin-based per-layer rays matching, and independent CLI exact-JSON comparison across seven workloads.
- Key pushed milestones: `f6d54882` second retained view; `912fcb8c` provenance/race fixes; `5af9d48f` immutable BVH; `bf0addd4` opt-in CLI integration. See each commit for tests and changed files.

### AMD-DESKTOP end-to-end runtime evidence (single paired executions)

| Workload | `--accel off` | `--accel bvh` | Result |
|---|---:|---:|---|
| 1 pixel | 2.068 s | 4.603 s | off faster |
| 8 pixels | 4.798 s | 5.050 s | off faster |
| 9 pixels | 5.403 s | 4.823 s | BVH 1.12x |
| 10 pixels | 5.721 s | 4.522 s | BVH 1.27x |
| 26 pixels | 13.382 s | 4.905 s | BVH 2.73x |
| 32 pixels | 16.188 s | 4.799 s | BVH 3.37x |
| 1 pixel + radius-2 footprint | 6.161 s | 8.331 s | off faster |

The observed batch crossover on this pinned scene was **8–9 pixels**, including full process launch and BVH building. Peak working set was about 163 MiB (off), 270 MiB (regular BVH), and 462 MiB (radius-2 BVH). Keep the `off` default, opt into BVH for repeatable 9+ pixel batches; rerun measurements for any other mesh/hardware.

### P0 physics/route gate remains STOP

- RiftWorld's existing source HKX temple has native collision shape/MOPP/filter qualification, but not a current physics-step timestamp or live obstacle response; 20 stored manifold observations were unchanged over approximately 1h49m. Stored contact data must not be presented as fresh blocking evidence.
- A **read-only** Atank pose at approximately 19:27 EST was `(7220.81055, 872.28076, 3034.23047)`. Earlier proposed side faces 46–48 were now about 9.89 units from the player; new nearby candidates #231/#215 were approximately 3 units away, underfoot #221 0.082 unit. Treat all as snapshots, not a collision qualification or movement permit.
- Existing waypoint bridge scripts (`waypoint_destination_plan.py` and `waypoint_candidate_adoption.py`) and viewer already exist; reuse rather than replace. If displaying this composite, label pixels as **advisory candidates only**.
- Next meaningful external gate: supervised bounded contact/visual confirmation at the latest verified physical client identity **only after separate explicit user authorization**. No keyboard, mouse, click-to-move, casting, or navigation input was used during this work. Keep `STOP=true` until proven.

## 2026-11-16 20:25 EST — second-wave implementation, QA, and release handoff

**AMD-DESKTOP verified; physical RIFT was not controlled.** This checkpoint follows the earlier first/second WGC candidate work and has been selectively committed/pushed to `codex/modular-foundation` without staging other developers' dirty files.

### P1 deliverables now merged

1. **Fail-closed navigation gate** (`7922948`): `waypoint_candidate_adoption.reject_review_route()` rejects the precise `rr2.retained-wgc-composite-candidates/1` schema even if someone adds plausible-looking `waypoints` and `heights`. A malformed wrapped screenshot candidate previously passed ordinary validation; the new 5-case regression went red first, then 5/5 green. Existing adoption/destination/Waypoints tests remained **85/85 passed**. Raw genuine composite reports never contained executable waypoints. Actual `--run-route --execute` was never invoked.
2. **Numerical and client-rect regressions** (`e140fe8`): independent analytic handedness/edge/tie checks passed 3/3, and second-view WGC tests passed with the surrounding 36/36 suite. Both 2560x1392 screenshots have 2560x1369 client rectangles with `clientTop=23`; the true second-view temple candidate onset is pixel **x=1967 at y=400**. Deliberately omitting the offset shifts the onset ~4–5 pixels and the ray by ~0.736 degrees; current production mapping is correct.
3. **Measured screenshot optical evidence** (`63d637b`, `da7a578`): optional `scripts/physical_pixel_optical_edge_evidence.py --view both [--dark-gradient]` validates exact frame/pose/geometry hashes, compares visible pixel brightness with projected render candidates, and includes real RRE/ability-HUD false-positive probes. First-view bright-interior edges differ only +0.5px. Second-view bright-interior differences +31.5/+38.5px are **not** proven transform errors: a separate dark-gradient candidate lies +3.5px from each projected edge (row 400 drop16.30 luminance, row500 drop44.14), potentially shaded object/texture. Gradient is not a qualified outer silhouette/depth. **10/10 optical tests passed; default analyzer output unchanged.** All optical, collision, navigation, and movement flags remain false.
4. **Bounded large pixel batches** (`b9d71c9`): CLI `--accel bvh --max-pixels 256` opts into 33..256 rays with one mesh/index build; default remains 32 and requests above 32 without BVH are rejected before file reads. First-view64 direct CLI 4.509–5.059s; second-view256 4.684–4.729s, exact cached-index full report parity, independent eight-ray brute/BVH second-view confirmation. The new batch tests passed 4/4; subsequent composite suite passed 24/24.
5. **Large-result transport correctness** (`6b0c1fe`): Workbridge retains at most ~1MiB process output; 16px radius3 yielded75,181 JSON bytes, so 256px radius3 was projected at ~1.21MB and could be truncated. Opt-in `--output-json NEW.json` now stages, flushes/fsyncs, checks saved SHA/length and atomically publishes via exclusive same-directory hardlink; stdout carries a short path/SHA/size candidate-only receipt. Existing small stdout JSON is unchanged. Without an output file, results over 512KiB explicitly block **before** PNG preview creation; no overwrite or partial successful receipt. Full real Windows64 report: 91,502 saved bytes, 463-byte stdout receipt, exact hash. New transport tests **10/10 passed**, independently audited, and final combined `test_physical_pixel_composite*.py` suite **34/34 passed** (81.49s).

### P0 native physics proof gate (RiftWorld evidence, read-only)

- Fresh qualified physical RIFT session on AMD-DESKTOP: Atank PID **77704**, process start ticks **639304372516074064**; player-world/proxy/phantom/component ownership reverified using existing native reader and exact hashes. Previous stored temple contact changed from shape key **207 to 221** after player pose changed; face221 source point/normal agreement ~7.15e-6 from collision margin, MOPP source matches. This is stored-contact evolution, not current-frame blocking.
- Three owner-bound no-input native snapshots (20:11 EST) showed `component+0xE8=0x57`, `+0x13C=0.0`, `+0x144=1`, `+0x1D0=0`, `+0x184=0.0155718`, manifold count1 with no changes between reads. They **did not** resample the contact point itself; key221 remains historical. Conditional timer gate0 explains its stasis. No positive physics-step refresh witness; no reason to upgrade collision/nav.
- Exact-build Ghidra traces show `FUN_1400CDB40` refresh invokes phantom+0x80 query and proxy+0x18 `FUN_1400CE408`; the proxy writer manages 64-byte contacts in array `+0x88` / count `+0x90` / capacity `+0x94`. No per-contact generation timestamp in that verified ABI. Two subordinate helpers (`FUN_1400CC998`, `FUN_1400CC9E8`) are pending targeted static side-effect review. Stay `currentFrameContactQualified=false`, `physicalBlockingQualified=false`, `navigationQualified=false`, `STOP=true`.
- Passive evidence directories: `C:\work\RiftWorld\artifacts\native-watch-atank-proofgate-passive-owner-20261116-2010et-r1\` and `...\native-watch-atank-proofgate-passive-substeps-20261116-2012et-r1\`. These are ignored artifacts, not committed project inputs.

### Next practical continuation

- **P0 first:** Find a genuine step-correlated native contact-generation witness, then obtain separately authorized supervised bounded obstacle-response evidence before admitting any HKX wall to Detour/RR2 navigation. No keyboard, movement, click-to-move, or route execution is authorized by the present artifacts.
- **P1 second:** Independently qualify an actual visible fragment/outer silhouette; the current bright and dark screenshot measures are appearance-only heuristics, not optical depth or physical clearance. Use additional unobstructed retained views or a separate depth/silhouette channel.
- For safe manual review, existing Waypoints `view open ABSOLUTE_EXISTING_PNG --session EXISTING_ID --json` opens the candidate PNG with Windows file association without route or RIFT focus calls. **Avoid click-through overlays** because underlying RIFT can receive mouse clicks. Neither viewer launch nor route input was executed in this checkpoint.
- **Operational:** Continue using the selective-commit workflow and keep unrelated dirty/untracked RR2 files untouched. The default CLI 32-point output path remains backward-compatible; use `--output-json` for footprint-heavy batches; verify full receipt SHA before consuming saved data. No cleanup/deletion of user artifacts was performed.


