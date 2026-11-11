# Physical RIFT A/D visual-turn verification and steering continuation — 2026-11-11

**Host:** independently checked AMD-DESKTOP. **Repository:** `C:\work\riftreader2`, `codex/modular-foundation`. **Target:** physical `rift_x64.exe`, PID `44888`, process-start UTC ticks `639299470183328173`, HWND `0x911EC`, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. These identities are **historical run pins**, not future defaults. No LEGION or VMware access.

## Outcome

**New verified capability:** The repaired RR2 .NET 10 `move-key` helper inserted, held and released **A** and **D**; independent actual RIFT screenshots show **visible viewpoint rotation** after A, and opposite rotation after D, returning close to the initial view. This resolves the earlier missing **visual-turn helper verification**. It does **not** establish a measured body-yaw angle or actor/camera separation.

**Next navigation finding:** A separate W 400 ms run produced **2.467855 units** of candidate native horizontal displacement. The planned *post-A W* directional comparison was **blocked by the tool before execution** and has not been measured. Do not claim a complete steering calibration.

## Game screenshots and exact evidence

| Stage | Event/receipt | Result |
| --- | --- | --- |
| Before A | `rr2navbeforeturna20261111b`, UTC 14:48:56.411 | Verified RIFT PNG, 1920x1032; player, plaza and tents visibly present |
| A input | `rr2-nav-physical-a500-20261111a` | Requested 500 ms, **517.0 ms observed**, insertion=true, release=true, targetLost=false, cancelled=false |
| After A | `rr2navafterturn20261111a`, UTC 14:50:55.017 | Viewpoint visibly rotated; changed stationary landmarks behind player |
| D input | `rr2-nav-physical-d500-20261111a` | Requested 500 ms, **513.7 ms observed**, insertion=true, release=true, targetLost=false, cancelled=false |
| After D | `rr2navafterturnd20261111a`, UTC 14:51:52.715 | Visible reverse rotation; plaza/tent perspective returns close to first image |

All three original PNGs were copied **byte-identically** to the **local ignored evidence directory** `artifacts/physical-turn-visual-20261111/`, with SHA-256 verification after the copy:

| Image | SHA-256 |
| --- | --- |
| `before-a.png` | `B3D88418A0526621C0AB678D08E7D6FD4821BBA83061A385741BF6C271465684` |
| `after-a.png` | `FFFCA23E0987E6EB8951EA25178A27F62057D605C5BFF02AC3709C17848CAB50` |
| `after-d.png` | `5AE2F9306DDFAE7FB40F45F6D96E55ABFF8261850866255CFD30824F12472C31` |

The original Workbridge capture records live under `C:\work\workbridge-mcp\.tools\desktop-evidence\capture-<request-id>.png`. No screenshot pixels were committed to the public Git repository because the images include game UI/chat content.

**Supporting offline pixel check:** Pillow 13.0.0 compared a central scene crop `(500,140)-(1610,810)` resized to `555x335`. Mean absolute RGB differences: initial-to-after-A **32.718**; initial-to-after-D **18.095**; after-A-to-after-D **32.505** (0–255 scale). Thus the after-D scene was more similar to the original than after-A was. Values are **image difference**, not degrees or proof of actor orientation. Exact calculator output: `artifacts/physical-turn-visual-20261111/visual-comparison.json`.

**Limits:** Images were captured several seconds after each bounded pulse and the game world contains moving NPCs, UI updates and animations. A visible viewpoint change alone may reflect camera rotation rather than validated actor facing. No independent Lua yaw, exact degrees/second, or gameplay-server evidence was collected.

## Additional forward and actor-pose observations

After A/D visual verification, the helper performed one W action to establish a before-turn movement vector:

- `rr2-nav-steering-w400-baseline-20261111a`: requested 400 ms, observed **408.2 ms**; insertion, bounded completion and release true; no target loss.
- Native same-owner before: `(7432.7607, 863.586, 2966.6145)`; after: `(7430.312, 863.586, 2966.3079)`.
- Delta X/Z: `(-2.44873046875, -0.306640625)`; planar displacement candidate **2.46785521890669**; `gameResponseVerified=false` because cached native XYZ is not independently validated.
- Followed by an A 500 ms `rr2-nav-steering-a500-20261111a`, observed **513.1 ms**, insertion and release successful. The attempted subsequent W command was **refused by the tool before execution**; no post-turn W vector was captured and no alternate injection method was used.
- Read-only physical native actor-pose `rr2-nav-readonly-actor-pose-after-a-20261111a` then returned **3 stable samples** of an **actor planar matrix-angle candidate 10.22806184°**, model 0°, with the same player identity and stationary bracketed XYZ. Data: `artifacts/physical-native-actor-pose-2b9d3158a901402283306cb4ff877fb8.json`. **`actorHeadingQualified=false`** and no before-A actor-pose sample, so no measured turn delta is claimed.

## Practical continuation

1. **Do not repeat the old XYZ-only mistake for A/D.** The helper's A/D insertion and visible viewpoint response are now observed; actor yaw remains distinct from camera yaw.
2. When input is available and explicitly authorized, acquire tightly paired **same-epoch actor-pose before/after** for one A and one D action, alongside screenshot confirmation, to qualify the current-build matrix candidate. Use existing `physical_rift.py --read-native actor-pose --include-position`; no new framework needed.
3. Finish the minimal **W before/after turn** vector comparison with small bounded pulses and reliable release; do not extrapolate from the missing second W.
4. For actual navigation, combine independently verified facing/turn response with candidate X/Z calibration, then test only a nearby single waypoint before expanding to route planning. Keep exclusive input ownership, precise process/build identity and STOP/release.
5. Preserve unrelated concurrent developer edits; return an honest blocker when a tool refuses an operation rather than bypassing it.

**Milestone boundary:** Correct A/D **visual response** verified on physical RIFT; **quantitative actor-yaw calibration and post-turn forward vector pending**. No source edits or new broad architecture were required for this test.