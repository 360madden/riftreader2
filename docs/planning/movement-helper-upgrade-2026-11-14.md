# Movement helper upgrade — November 14, 2026

Goal: deliver a working CLI-first movement helper with an RR2-owned click
destination view and continuous forward travel, while retaining the current
helper as a usable fallback. Host for this work: AMD-DESKTOP only. The local
controller owns motion; AI is development/temporary scaffolding as needed.

## Current status — implementation, acceptance and restoration complete

The replacement path is implemented in the working tree and its focused offline
checks pass. A physical short destination, a STOP during a planned 23.1018-unit
route and a corrected explicit Resume now establish useful scoped held-forward
route behavior. A live owned-map projection and `move pick` then arrived through
the same continuous backend without changing the loaded route, and a separate
ten-unit single-leg out-and-back arrived in both directions. The preserved
fallback also passed a hidden no-input startup/status/close smoke. This is
**not** an unlimited movement claim: the
accepted runs used one previously verified clear strip and do not establish
arbitrary terrain, obstacles or unattended reliability. The implementation uses
an owned, continuously held **W** key with feedback steering; it does not start,
observe or cancel RIFT's Num Lock autorun latch. The actual GUI checkbox and
owned-map pointer-click path has also passed through the shared backend after
correctly refusing an initial stale click. Final restoration returned within
0.166 units of the original start. The current v1.2 helper was idle and visible
with continuous movement selected, click-to-move off, STOP latched, no input
release fault, overlay off and the original clean six-point route unchanged.
Source Git delivery is handled by the root workflow; this record does not invent
a commit identifier.

| Milestone | Offline status | Remaining evidence |
| --- | --- | --- |
| 1. Preserve the `a4711ed` fallback | **Implemented and no-input startup-smoked.** `artifacts/movement-upgrade/legacy-a4711ed/` retains the source, source archive, separate immutable user-state archive, hash inventory, original native runtime and preservation record; `Waypoints-Legacy.cmd` targets that isolated source. The preserved v1.1.0 helper opened withdrawn, published its exact session/status, bound its reader to physical PID 21672 without input, and the returned session was explicitly closed with owned workers released. | This proves hidden Tk/reader startup and exact-session close, not a mapped screenshot, visible-window layout, Qt overlay or compact-radar path. Preferred Qt behavior still needs its absent pinned environment; the native presenter remains the preserved fallback. |
| 2. Owned-map picking and CLI-first control | **Implemented and scoped CLI/GUI live acceptance passed.** The map inverse projects canvas pixels to X/Z without desktop input; stale origin, owner, nonfinite and outside-map cases fail closed. On the live 411x182 owned view, projection selected X 7421.230/Z 2944.614 and CLI `move pick`/`map-go` arrived 0.2033 units from that goal through the continuous backend. The actual GUI checkbox/pointer-click path first refused a stale click, then an explicit fresh click arrived 0.2644 units from its goal and visibly reported the saved run receipt/new pose. Both paths left the original clean six-point route at revision 1 with point 6 selected. | Retain the shared CLI/backend semantics and observed refusal checks. The GUI is now accepted as a dispatcher over that backend, not a separate movement implementation. |
| 3. Continuous native destination movement | **Implemented; scoped physical cases passed.** `follow-route` pins host/process/start/build/window/player and parent owner, holds W across pose observations, steers with A/D, watches STOP/owner/pose/progress/corridor/height/time, releases all owned keys and emits one strict receipt. A three-unit physical run arrived 0.1123 units from its goal with verified releases and no desktop inputs down. A distinct route STOP released W/A/D and two post-STOP native poses had zero XYZ and yaw drift. A separate clear-strip run arrived after one 10-unit outbound leg (0.2433-unit error) and one 9.7568-unit return leg (0.2523-unit error); both released successfully with no desktop inputs down, and the final two-pose stationary check had zero XYZ/yaw drift. Pulse movement remains selectable. | Retain these exact cases and expand only from demonstrated need. They do not establish arbitrary bearings/terrain, obstacles or long-duration reliability. |
| 4. Route, progress and Resume integration | **Implemented; scoped physical STOP/Resume passed.** Continuous playback visits real route points without synthetic four-unit stops, retains one reservation/deadline, uses the existing playback checkpoint and preserves the unfinished real-waypoint cursor. A planned 23.1018-unit nine-point route reached its first point, STOP interrupted its second point, and the checkpoint was retained. After the steering correction, explicit Resume completed only the seven remaining legs, advanced the cursor to 9/9, finished 0.2402 units from the endpoint, passed two-pose stationary verification and retained successful release with no pressed desktop inputs. | This was repeated travel over one previously verified approximately 2.89-unit clear segment with 180-degree turns, not one 23-unit leg or arbitrary terrain. Diverse corners, terrain and restart/reload recovery remain separate evidence if later needed. |
| 5. Focused verification and physical acceptance | **Scoped acceptance passed.** On November 14, 202 focused Python cases and 114 focused native/legacy tests passed. Release and Debug builds completed with zero warnings and zero errors. Physical evidence covers a short arrival, the nine-point STOP/Resume route, live CLI and GUI owned-map picks, and the clear-strip 10-unit out-and-back above. | Preserve the exact evidence and limits. Broader terrain, collision and duration claims remain unmade. Optional Qt presentation remains unavailable because PySide6 is absent; it is not required for the accepted native-presenter slice. |
| 6. Correct, document and restore | **Complete for this milestone.** The exact-session final move returned within 0.166 units of the original start. The v1.2 helper was restored idle and visible with continuous engine, click-to-move off, STOP latched, no input-release fault, live pose at range 10, overlay off and the original six-point route clean at revision 1 with point 6 selected. | Source Git commit/push is performed by the root delivery workflow; no commit identifier is claimed in this task record. |

### Preserved fallback static verification — November 14

This verification opened no GUI, changed no focus, read no physical RIFT state
and sent no input.

- The preserved `RiftReader2.Live.exe` exists in its self-contained Debug
  `win-x64` directory. Its SHA-256 is
  `0E16656AE970A61BE8FFC27E45AFC2D9C9DB721410D695A58876E7A9998876DA`,
  exactly matching `preservation.json`; input-free `--help` returned normally.
- `Waypoints-Legacy.cmd` resolves to the preserved launcher. Global Python and
  `pythonw.exe` are Python 3.14; the preserved launcher `--help`, Waypoints CLI
  `--help` and CLI `--version` all returned normally. The preserved CLI reports
  `Joey D's Waypoints 1.1.0`. Top-level launcher/Waypoints imports, Tk 8.6 and
  Pillow 13.0.0 are available.
- The extracted snapshot contains five waypoint-progress JSON files, both
  `courtyard-legacy.json` and `courtyard-tagged.json`, and
  `waypoint-last-route.json`. All 24 tracked baseline paths whose names contain
  route/progress/checkpoint are present.
- `source.zip` passed its ZIP integrity test but, by itself, contains none of
  those ignored route/progress JSON files. The gap is closed by the separate
  read-only `user-state.zip`, SHA-256
  `704C1805652AD50456015234A298230F4E5D62ABE1366D27F2E9516D897F2E51`.
  It contains the five progress files, two saved routes, last route, marker style
  and radar style under their original `artifacts/` paths.
- Read-only `fallback-inventory.json` records the source archive size/SHA-256,
  user-state archive size/SHA-256 and entry count, native runtime size/SHA-256,
  and the size/SHA-256 of every preserved state file. Reopening the ZIP verified
  all ten ordered entries byte-for-byte against both the inventory and preserved
  snapshot originals. Neither old archive nor preservation record was overwritten.
  The later legacy startup normally rebound the extracted snapshot's mutable
  radar `statusPath` to its smoke session; the read-only user-state archive and
  inventory retain the pre-smoke bytes and hash.
- The isolated `.local/overlay-venv` is absent and global Python has no PySide6.
  The preserved code deliberately falls back to its native presenter when that
  environment is absent, so the core Tk launcher and native-presenter path have
  their required interpreters. Preferred Qt overlay/compact-radar behavior is
  not available from this fallback bundle without restoring its pinned overlay
  environment; this does not block the root's core no-input GUI smoke.

### Preserved fallback no-input startup smoke — November 14

`artifacts/movement-upgrade/legacy-smoke.json` retains the preserved helper's
successful `app.open` and exact-session `status`. Version 1.1.0 opened hidden as
a withdrawn Tk window, selected physical RIFT PID 21672, began its normal reader
startup and reported `inputSent=false`. The root then used the returned session
ID for explicit `app close`; the close reported `ownedWorkersReleased=true`.
No current Waypoints app was running during this smoke, and no movement input was
sent. The retained JSON contains the open/status result; the close outcome is the
root's observed exact-session result. This is startup/reader/transport evidence,
not visual screenshot proof that the window mapped or that overlay presentation
worked.

## Ranked follow-on roadmap

The movement-helper milestone above is complete. These are later capabilities,
not blockers for this accepted slice, ranked by practical project value:

1. **Add the local travel/combat handoff before unattended long travel.** One
   local action owner must release and settle movement before combat acts, keep
   the current route leg/checkpoint unchanged during the encounter, and reacquire
   identity/pose/context before ordinary automatic continuation. Operator STOP,
   safety latch, death or uncertain release stays latched and requires explicit
   Resume/new run. Build this through shared CLI/state behavior first; the GUI
   should expose the same state rather than own a separate decision loop.
2. **Use actual runs to select the next movement improvement.** Prioritize a
   demonstrated terrain/collision, steering, braking or route-context failure.
   Do not add obstacle planning, autorun machinery or map polish speculatively.
3. **Qualify autorun separately only if actual project value warrants it.** The present
   backend continuously holds W and can release that owned key; this does not
   establish whether Num Lock autorun is off, whether an external autorun latch
   is active, or how to cancel it deterministically. Before enabling an autorun
   backend, observe known off/on transitions and prove that STOP cancels known
   owned autorun without blindly toggling an unknown state. Until then, refuse
   autorun ownership and report that limitation explicitly.

## Mechanism decisions and evidence limits

- The user's selected interface is an RR2-owned map/view. The first version uses
  the existing player-relative top-down map and its exact inverse X/Z transform.
  Perspective pixels do not establish a terrain hit without depth/geometry;
  slopes, floors, collision and obstacle avoidance remain separate work.
- The supplied game bindings show Toggle Autorun = Num Lock. This is a valid
  alternative forward-motion mechanism. Its latch state and deterministic cancel
  behavior are not qualified. The implemented continuous path is held-forward,
  not autorun: W key-up can release RR2's owned W state but cannot prove or cancel
  a separately latched game autorun state. Never blindly toggle Num Lock on STOP
  or treat a held-W receipt as autorun-cancellation evidence. Qualify autorun
  independently before enabling it as an optional backend.
- Existing pulse movement and its evidence remain intact. New continuous
  execution is a distinct path with its own receipts and live acceptance.
- A working-product claim requires successful real movement and STOP behavior;
  simulated/controller tests alone establish offline behavior only. If a live
  prerequisite is unavailable, retain honest status and continue independent
  work instead of weakening identity, freshness or ownership checks.
