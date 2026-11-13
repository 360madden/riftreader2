# Camera-motion overlay and beacon verification

Verified host: **AMD-DESKTOP**, physical RIFT PID40452, start ticks
`639301206978915233`, executable SHA256
`1935a05c9db6d468e34e0055014a4a99c1b5afceb1695884e24600f5c20a4be8`.
Live checks were performed November 12, 2026, approximately 20:30–20:57 EST.

## Result

The repeated freshness clears were primarily caused by restarting a short native
sampling child every burst. Camera-only baseline and updated 50-second trials:

| Measurement | Original | Continuous stream + direct Qt |
|---|---:|---:|
| Accepted scene requests | 273 | 1,513 |
| Non-cleanup visible clears | 24 | 0 |
| Mean accepted-update interval | 181.75 ms | 32.74 ms |
| Maximum accepted-update interval | 1,651.59 ms | 155.59 ms |
| Mean sample age at submission | 111.77 ms | 23.72 ms |
| Mean CPU scene submission cost | 15.91 ms | 1.22 ms |

The updated trial separately instrumented **1,513 actual Qt paint events**, mean
paint-handler cost 2.60 ms. Paint events are not monitor scan-out measurements.
The trials used camera pans in the same area, not an identical scripted motion
sequence. They are exercised-case evidence, not a universal performance bound.

The final normal **Show markers → camera pan → foreground change → Hide markers**
GUI run lasted 209.95 seconds and accepted 5,097 scene requests. Its authoritative
hide counter recorded one expected foreground/client-geometry clear and **no TTL
expiry clears**. It included a large left-button camera pan bringing an off-screen
landmark into view, then its reverse. The landmark pill remained outside the
top-center chat region. Idle pose refresh stayed paused while the helper lacked
focus and resumed on helper focus, removing duplicate-reader contention.

Native before/after entity-position bits and body bearing were identical in the
controlled trials; final camera raw bits also matched the pre-test camera. The
character was manually moved between trials while the user was explicitly free
to play; positions from different trials must not be compared as one continuous
stationarity claim. No movement keys, attacks or route playback were used. Two
friendly-NPC selection clicks did not yield an available native target; target
diamond/bracket styling is covered offline, not claimed as a live target result.

## Changes and retained limits

- A camera-only coherence retry accepts at most three attempts, only for dynamic
  camera payload races. Structural/process/owner failures remain fail-closed.
- One stream replaces frequent child restart. The original trials below used
  bounded runs; the GUI now explicitly requests continuous operation until an
  owned stop or pinned-process loss. Each cooperative lease wait retains its 30s
  limit and every row releases the session and lease before writing output.
- A stream-scoped executable pin verifies SHA256, denies file writes/deletion,
  and checks fresh path file identity. PID/start/path/module/player checks remain
  per row. Other native readers retain their original hashing behavior.
- Qt draws primitives directly, with matching 16px text metrics, antialiasing,
  stable label lanes, short beams and translucent label pills. The native bitmap
  fallback remains available. No new dependency or whole-app UI migration.
- NEXT is cyan with a chevron; selected landmarks are gold even when completed;
  explicit targets use magenta diamonds/brackets; ordinary points are quieter.
- Foreground, geometry, identity and .35s GUI frame-freshness guards remain.
  Neither interpolation nor stale-timeout inflation conceals invalid camera data.
- No terrain, occlusion, route-clearance or universal mixed-DPI qualification.
  The top-center label quiet zone matches the observed layout, not automatic HUD
  detection. Full Qt Quick migration/predictive tracking were unnecessary here.

## Retained evidence

- `artifacts/beacon-flicker-baseline-40452.json` and matching `-trace.jsonl`.
- `artifacts/beacon-flicker-stage1-v3-40452.json` and matching `-trace.jsonl`.
- `artifacts/beacon-polish-live-40452.json`: intermediate normal-refresh run
  exposed duplicate-reader contention; not substituted for final GUI acceptance.
- `artifacts/waypoint-markers-summary-8079c1ffff0f4985be7b6c8ad6846c35.json`.
- `artifacts/beacon-gui-final-before-native.json` / `beacon-gui-final-after-native.json`.
- `artifacts/beacon-final-gui-landmark.png`: actual reviewed game/overlay image.
- `artifacts/beacon-flicker-final-preservation.json`: basis, active progress and
  last-route cache remained byte-identical.

Final focused checks: **53 native tests** (camera/facing/stream/file pin),
**93 Python checks** (feed/presenter/marker launcher), and **8 withdrawn GUI
marker-playback checks**, all passed. Native TRX:
`C:\Temp\rr2-overlay-final-20261112\results\overlay-final.trx`.
Deployed single-file native build SHA256:
`afa4113149b422f04af88d770932057a74c6d7f915ec530608da493654094f8b`.
Intermediate failed launch trials exposed the inherited 30s lease-wait bound;
the final long stream caps each wait separately. They are excluded from results.

## Continuous marker sessions — 21:19 EST follow-up

Removed the GUI's ten-minute lifetime limit on AMD-DESKTOP. The owned overlay
now uses `--duration 0`, forwarding `--duration-ms 0 --samples 0` to the native
reader. There is no elapsed-time or sample-count deadline. Hide, helper close,
route replacement/STOP and pinned RIFT process loss retain their existing owned
shutdown behavior; foreground and freshness checks still withhold invalid frames.
Repeated continuous-mode failures back off from 1s to a maximum of 5s, reset
after a healthy row, and diagnostic reason maps retain at most 64 labels plus
an overflow bucket.

Focused checks passed: **46 native tests** and **93 Python tests**. Injected
clocks beyond 600s verified continuous acquisition/cancellation and the outer
GUI feed path without a ten-minute wall-clock wait. A 125.07s live continuous
session accepted 2,837 presentations, then stopped on Hide; all three owned
overlay/native processes exited. This count measures accepted presentations,
not monitor frames. Receipt:
`artifacts/waypoint-markers-summary-97161f81218e49afbe7990a46a8fd878.json`.
The final source was reloaded, markers enabled again, and the gold Olaf beacon
was visually confirmed with RIFT foreground. Reviewed screenshot:
`artifacts/beacon-continuous-final-20261112.png`. No gameplay input was sent.

Continuous-stream native TRX:
`C:\Temp\rr2-facing-continuous-20261112\test-results\continuous-stream.trx`.
Deployed single-file native SHA256:
`8bdc04de9048c59d02922d847461538d6f48f01b2768d77dbfb31a6bb6ada029`.

## Live appearance controls — 21:35 EST follow-up

The Scene & beacons panel now exposes size, opacity, label visibility and Reset.
On AMD-DESKTOP/PID 40452, the default appearance was compared with **200% size,
39% opacity, labels off** using the actual sliders and checkbox. The game showed
larger translucent rings without label pills at the same projected locations;
the owned overlay processes (58920/58652) stayed running. Reset restored 100% size,
100% opacity and labels on. No gameplay input was sent. Reviewed images:
`artifacts/beacon-style-default-20261112.png`,
`artifacts/beacon-style-tuned-20261112.png`, and
`artifacts/beacon-style-ui-final-20261112.png`.

All **110 focused Python checks** passed, including live-feed preference changes,
corrupt-file fallback, no-restart GUI callbacks, close flushing, renderer anchor
preservation, label removal and rendered Qt alpha. The final slider theme also
passed all five appearance GUI checks. Default-window pixels were reviewed;
980px layout coverage uses actual withdrawn widget requests, not a claimed mapped
minimum-window screenshot. Qt appearance was verified live; the native fallback's
size/labels/opacity wiring was checked offline.

## Waypoints-focus preview — 21:55 EST follow-up

On AMD-DESKTOP, RIFT PID 40452 remained genuinely unfocused while the exact owning
Waypoints window held focus. A native window snapshot reported `foreground:false`
and `displayAllowed:true`. Moving the UI sliders changed visible beacons from
137%/100% to 200%/46% without leaving Waypoints. Both Olaf's gold landmark and the
selected target's magenta beacon remained visible. Focusing an existing Explorer
window hid them and reported `displayAllowed:false`; returning to Waypoints
restored them. RIFT identity/geometry/freshness checks and movement foreground
rules remain unchanged. Companion minimization does not suppress RIFT-foreground
display. Duplicate GUI idle reads now pause for the whole marker session.

All 112 focused feed/presenter/GUI lifecycle checks passed. Reviewed images:
`artifacts/beacon-companion-baseline-20261112.png`,
`artifacts/beacon-companion-sliders-20261112.png`, and
`artifacts/beacon-companion-other-app-hidden-20261112.png`. Native display-state
receipt: `artifacts/beacon-companion-focus-state-20261112.json`. No game input was
sent. The user's seven-point edits were saved separately as
`artifacts/waypoint-user-edits-before-focus-preview-20261112.json`; by their choice,
the two-point measured route remains open. Original 137% size / 100% opacity /
labels-on preferences were restored, with markers enabled and Waypoints focused.

## Map-click beacons with estimated heights

On AMD-DESKTOP/PID 40452, the user's saved seven-point route now renders all seven
marker candidates: two measured heights and five nearest-measured display estimates.
The actual RIFT overlay showed **Point 7 · 10.7u · est. height** with its gold beacon,
plus the other visible route pips and the optional selected-target beacon. Reviewed
image: `artifacts/beacon-seven-points-live-20261112.png`. The 63.60s session accepted
1,948 presentation requests and stopped on Hide; its receipt records all seven
effective display XYZ values and their height kinds:
`artifacts/waypoint-markers-summary-22b00031173b4fa8be359fdbec2fb543.json`.

The saved seven-point document remained byte-identical (SHA256
`03f4b7470a10ea84546277922f9b952ae2e3898b5d9a9d780cf9e0317598afe7`), with all five
unknown heights still null. No measurement receipts or game input were fabricated.
All **136 focused checks** passed. Offline checks also covered an entirely
unmeasured route, using the first owner-validated fresh native player Y once and
keeping it fixed even if later player Y changes. The strict measured-route parser
and movement/progress logic are unchanged. Marker estimates approximate a ground
level; terrain and multi-floor placement remain unqualified.

## Automatic route-edit synchronization

On AMD-DESKTOP/PID 40452, one active marker session admitted a map-clicked Point 8,
showed its beacon in RIFT without Show/Hide, changed its label live to **Auto sync
check**, and removed that beacon when the temporary point was removed. The GUI
returned to the original seven points and Point 7 guide. Both overlay processes
(18796/62456) and the native sampler (74188) retained their process IDs throughout.
Reviewed screenshots: `artifacts/beacon-auto-sync-add-20261112.png`,
`artifacts/beacon-auto-sync-rename-20261112.png`, and
`artifacts/beacon-auto-sync-remove-20261112.png`. The original route file remained
byte-identical with SHA256
`03f4b7470a10ea84546277922f9b952ae2e3898b5d9a9d780cf9e0317598afe7`.
No game input was sent, and the temporary point was not retained.

All **90 focused checks** passed, covering the feed, owned launcher/GUI, empty-route
admission, mutation/guide revisions, invalid/foreign update rejection and recovery,
frozen display heights, Clear/Undo, persistent Hide and one native child across
multiple route changes. A single worker owns route replacement. Presentation checks
the matching revision under the same small lock, and saved progress uses that
frame's route rather than the startup document. File I/O stays outside the lock.
The active seven-point overlay is left enabled at the user's existing appearance.

## Shared live radar and player pose — November 13 follow-up

On AMD-DESKTOP, the actual Waypoints window consumed the running beacon reader's
pose file and displayed **Live pose (beacons)**, XYZ, facing and advancing original
sample times. The radar used the same display pose. RIFT identity remained PID
40452, start ticks `639301206978915233`, HWND `9246620`, executable SHA256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, player key
`239816685251645959`. The stopped session receipt
`artifacts/waypoint-markers-summary-411a506804ac4bc0bdce5df274955573.json`
records 603 fresh pose publications, five unavailable notifications and zero
pose-publication failures. Hide ended with `stop-requested`; the overlay/native
reader exited and the actual GUI resumed its two-second idle updates. Reviewed
UI image: `artifacts/live-radar-beacons-ui-20261113.png`.

The current three-point draft was preserved separately as
`artifacts/waypoint-live-radar-current-route-20261113.json`; the earlier seven-point
save was not overwritten. Appearance stayed at 137%, 100% opacity, labels on.
All 88 focused shared-pose, feed and GUI checks passed, including changing XYZ
and facing, stale/mismatched ownership, unavailable/child-exit handling and route
edit synchronization under frequent pose redraws. Feedback neither updates input
authority nor converts display heights into measurements.

Live movement/facing-change acceptance remains unverified: both the window and
DXcam desktop-composite captures showed a black RIFT game area, also after the
overlay and native reader fully exited. WGC returned no frame. No game input was
sent. The black composite is retained at
`artifacts/live-radar-composite-before-20261113/last.png`; this does not establish
whether the physical display was black. Existing native pose candidates remained
readable, but that alone does not prove a rendered, responsive game scene.

### Visible-scene movement acceptance — 01:58 EST

Joey confirmed the physical game remained visible and reported that the black
capture disappeared when the main monitor was powered back on. Fresh Sky capture
then showed RIFT normally on the same pinned PID/start/build/HWND, without a game
restart or capture-backend change. Monitor-power-related capture disruption is
the likely trigger, not a proven rendering failure; its mechanism was not isolated.
Do not infer a RIFT black-screen failure or restart the game from black captures
alone. Check display power and reacquire current window/geometry first.

The pending live check then passed on visible, open ground with one guarded
150 ms A pulse and one guarded 150 ms W pulse. Shared-reader facing changed
44.39871 -> 71.76206 degrees (+27.36335), with unchanged XYZ after the turn;
the actual GUI header and radar rotated to match. W changed X/Z from
7423.415039/2937.598145 to 7424.334961/2937.900879 (0.96845 horizontal units),
with Y and facing unchanged; the actual header and radar followed the new
position. Both native receipts confirm bounded completion and successful release.
The current client rectangle and foreground remained equal across each pulse.
Overlay PIDs 59616/34452 and native sampler PID 6016 stayed unchanged across both
checks. No continuous duplicate idle sampler was added. Atank was left at this
new position/facing; no compensating input or playback was sent.

Retained receipts: `artifacts/live-radar-turn-20261113.json` and
`artifacts/live-radar-step-20261113.json`. Reviewed before/after GUI and RIFT
screenshots use `artifacts/live-radar-motion-*-20261113.png`, including
`artifacts/live-radar-motion-after-turn-ui-20261113.png` and
`artifacts/live-radar-motion-after-step-ui-20261113.png`. The three-point route and
appearance preferences remain unchanged, with markers/shared pose enabled.
