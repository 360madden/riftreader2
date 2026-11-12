# Physical waypoint prototype

Double-click **`Waypoints.cmd`** in the repository root to open the window for
the single local physical RIFT client. If RIFT is absent or still loading, the
default window opens in a waiting state and retries unique selection while idle.
It validates the current host, process, movement basis and live pose before use;
it never starts movement on launch. `--check` and an explicit PID remain strict.
If several clients are running, use `Waypoints.cmd --physical-pid PID`.
The default single-client launcher reconnects while idle after the old game
process has truly exited and a new unique client has loaded the same player on
the same host and executable build. It freshly pins the new process and native
owners/facing. An explicit `--physical-pid` remains pinned to that process;
changed builds or players and ambiguous processes are refused. Reconnection
does not resume an interrupted trip or start movement.
The launcher defaults to **Face, then walk**. `--route PATH` opens a saved route.
For a read-only readiness check, run `python scripts/launch_physical_waypoints.py --check`.

Cold-start behavior passed a live AMD-DESKTOP case on November 12: the same app
opened with RIFT absent, waited through character selection, then bound the new
Atank process and restored readiness without movement. Its completed route stayed
loaded and the movement basis was unchanged.

For explicit CLI calls, obtain the current PID with the read-only readiness
check. An old PID remains deliberately pinned and is refused after it exits.
Use the default `Waypoints.cmd` launcher for automatic idle reconnection.

```powershell
$riftPid = (python scripts/launch_physical_waypoints.py --check | ConvertFrom-Json).pid
pythonw scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid
```

The window reads the current position and facing. **Save Current** adds a point;
clicking the local route preview adds a waypoint, and **Add X / Z** adds entered
coordinates. The preview faces forward, shows 5/10-unit rings, selected points
and the route distance. Each click checks a fresh pose; if the player moved or
turned, it refreshes the preview and requires another click. It shows waypoint
geometry only, without terrain or obstacle information.

Select a point and choose **Go Selected**,
or choose **Run Route** to visit the list in order. **Load** and **Save Route**
use a small JSON file containing `{"waypoints": [["name", x, z]]}`.
GUI Save Route and completed recording publication write a synced sibling
temporary file before replacing the destination, reusing checkpoint persistence.
A failed write or replace leaves the previous saved route intact and reports the
error; closing during passive recording discards that unfinished recording.
Use `--route PATH` to open the window with a saved list; loading does not start movement.
**Up / Down** reorder the selected point; **Clear** empties the list. A completed
run reports the number of visited waypoints and final distance explicitly.
**Add Target** saves the selected entity's freshly read ground position as a
fixed waypoint. It does not follow a moving entity or start a trip. An unavailable
or expired target position, or a target more than one unit above/below the player,
is refused. The point uses the same native candidate source as the target reader.

**Record** passively observes the player's movement without sending input.
After moving along a short open-ground path, choose **Stop Recording** to finish,
save a new `artifacts/recorded-route-*.json`, and load its points into the window.
**STOP** cancels recording without saving; capture or identity errors also leave
the recording incomplete. Passive GUI recording passed one live two-corner
open-ground case on AMD-DESKTOP: 732 samples became four actual points across
10.2944 units. The reusable
[passive route](../validation/passive-recorded-route-2026-11-12.json) retains its
original provenance; review fresh position and terrain before replaying it.
Paced native capture can reacquire a changing pose payload up to three attempts
within 100 ms, retaining the same owner/epoch checks and reporting
`captureAttempts`. In that live capture, two rows needed a second attempt and
730 completed on the first. Interrupted work and the reusable taught route are preserved
in [the recorded-route handoff](../handoff-2026-11-12-recorded-routes.md).

**Play Forward** starts near the recorded first endpoint; **Play Reverse** starts
near its last endpoint. Playback checkpoints each confirmed waypoint to
`artifacts/waypoint-current-progress.json`. After stopping or restarting the app,
the window can restore the checkpoint's route; choose **Resume** explicitly to
continue the unfinished leg. A fresh stationary pose must be near that leg, and
the host, build and player must match. Reconnection never starts or resumes a trip.
Loading or explicitly opening the same waypoint names/coordinates/heights restores
matching progress; changing the route invalidates it. Backend identity/checkpoint
validation still runs before any input. A live saved-file restart/Load/Resume case
preserved its 2/4 cursor and finished within 0.18620 units with four released W
pulses. Existing route and input limits
still apply, and routes have no obstacle avoidance.

On AMD-DESKTOP, a controlled taught route retained four points from 30 observed
samples across 9.998 units with 19 released pulses. Reverse playback completed
with 25 pulses and ended 0.09917 units from its endpoint; an earlier forward CLI
playback ended 0.10648 units from its endpoint
(`artifacts/waypoint-run-b4c277aafd324c988564fcf60556790e.json`).

A later GUI reverse playback was stopped by clicking **STOP** and settled with
three of four waypoints confirmed. Closing and reopening the app without
`--route` restored that reverse checkpoint. RIFT then fully exited (PID 31696)
and was normally relaunched through Glyph into Atank (PID 3820, start ticks
639300839889408581). The same app (PID 75780) reconnected without changing the
movement basis. An explicit **Resume** completed only the final leg, ending
0.0679574 units from its endpoint after eight released pulses and 963 ms of
requested hold. The interrupted and resumed run receipts are
`artifacts/waypoint-run-dc32b7e0c93747ccbe11baca1e305f79.json` and
`artifacts/waypoint-run-8d88bf44e6034217ba570b18b6dfd731.json`. This covers
that same-build/player restart case. Later direct GUI reverse/forward replays of
the passive-recorded route ended 0.15947/0.28199 units from their endpoints, with
26/17 released pulses. The forward case used fixed-facing S/E/W travel, exercising
the slow-direction segmentation. These are specific open-ground cases, not a
qualification of arbitrary routes or terrain.

**Face Selected** turns toward a waypoint without walking. **Face, then walk**
aligns to each waypoint and uses W for travel. Unchecked, the existing W/S/Q/E
controller approaches the point with the current facing. Facing uses the retained
settled A/D measurements as numerical seeds and checks the observed response
after every release. Alignment allows eight 20–150-ms presses and 20 seconds,
stopping within 4 degrees. It refuses unexpected XYZ movement during a turn.
Turns share the trip's hold/pulse budget; facing mode uses segments up to 3.5
units long. Fixed-facing W/S/Q/E routes use shorter intermediate legs when the
slowest calibrated direction needs them, targeting 600 ms of requested travel
per segment and capping segment distance at four units. The existing translation
controller retains its six-pulse, 900-ms and 12-second limits.

For a requested facing without walking:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --face-bearing -4.7 --execute
```

Add `--face-waypoints` to a CLI `--go` or a GUI launch to enable forward walking.

**Live pose (2 s)** refreshes position, facing and the preview while idle. It is
read-only, pauses during GUI actions and preserves entered waypoint coordinates.
The current pose has a separate timestamped readout. A control request waits for
an in-flight observation; closing waits for it as well. Before starting a route
or facing action, two fresh observations must show settled XYZ and bearing.

Repeated ownership checks use the native helper's read-only `move-key --inspect`
mode, which verifies the pinned process, executable hash and window without
focusing RIFT or sending input. On AMD-DESKTOP the measured identity-check time
fell from 411 ms through PowerShell to 230–234 ms through the native helper.

Live updates were checked against an independently issued facing command: the
preview updated to the new -16.51-degree bearing while an edited X coordinate
remained unchanged.

Each route is limited to 20 world units of planned travel, 64 pulses, 9 seconds
total requested key hold and 120 seconds overall. Actual Windows insertion-time
bounds remain in the native pulse receipts. Long waypoints are split into targets
at most 4 units apart. Each target retains the existing controller's six-pulse,
900-ms hold, 12-second and 6-unit radius limits. Input ownership and the trip
budget span every target and waypoint; only the first actual pulse can focus
RIFT. Arrival requires two settled observations within 0.30 units.
This is a supervised open-ground prototype: it does not route around obstacles.
The measured W/S/Q/E speeds are rotated using the current entity body facing;
the native position/facing fields retain their candidate labels. On the same
host, executable build and player, the measured
speed/turn model can be reused as a seed across process epochs without manually
rebuilding the basis. The original basis and measurement provenance retain
their original epoch; they are never retagged as new measurements. The live
adapter always pins the current process afresh and reads its native owners and
facing. Every pulse using a reused seed must pass signed direction, speed and
drift consistency checks before another pulse is allowed. A different basis can
still be supplied via `--basis PATH`. Same-build full-game restart recovery was
exercised on AMD-DESKTOP as described below.

Live restart acceptance, November 12: physical RIFT fully exited and relaunched
as PID18092 → PID79012 → PID31696, on the same executable build and Atank player
identity. After the reader's signed-zero decoding fix was loaded, the same
waypoint app (PID69060) stayed open across the latter full restart, reconnected
automatically and retained its route and entered coordinates. The original
basis bytes were unchanged (SHA256
`9A556D85DE26258D94E5A438BBC37D5938CCE762C67BC9B2E693602FDAB39251`).
No separate movement calibration or basis rewrite was performed.

The retained three-point triangle then completed in forward-facing mode,
finishing **0.08265 units** from its final waypoint. All 27 pulses (14 W, 9 A,
4 D; 3,781 ms requested hold) passed the reused-seed checks and native release
checks, with no target loss. Five subsequent D turns restored the starting
bearing within **1.248°**, with unchanged XYZ. The CLI facing receipt retains
each turn's timing/model comparison and before/after native source paths:
`artifacts/waypoint-run-04b0b0e8cab74168ad7dfae2f0c8e86b.json`.
Before/middle/after binding and settled route results are in
`artifacts/waypoint-restart-8f221c26b1994205bea0375d3323b889/`.

The first restart exposed native negative-zero matrix entries serialized as JSON
integer zero. The decoder now accepts that zero-sign equivalence and still
rejects other bit mismatches. Native `move-key --expect-hwnd` also pins the
current window before focus/input; passing the old window was refused without
input. Focused checks passed: 98 Python waypoint/reader tests and 75 native
move-key tests. These observations cover this same-build/player restart case,
not arbitrary patches, character changes or obstacle routing.

**STOP / F8** latches cancellation. F8 is registered only during a trip and does
not change foreground. The waypoint window uses `WS_EX_NOACTIVATE` during the
trip so an ordinary STOP click also preserves foreground; editing is disabled
until cleanup. The current pulse finishes its bounded release; another pulse
is never sent. Closing waits for cleanup, and STOP checks for actual stationary
native XYZ and body bearing. Only the first actual pulse can request RIFT foreground.
An already dispatched child may still be performing identity/focus checks when
STOP arrives; it finishes that one bounded pulse and release. GUI run receipts
retain the existing two post-STOP observations in `stopVerification`, including
source paths, candidate poses, XYZ/yaw drift and pass/movement-detected/unavailable
status. This is separate from native key-release evidence in the pulse receipts.
Each GUI input operation has its own `waypoint-input-*.jsonl` path; run receipts
include `inputReceiptPresent`. A refusal before input leaves that path absent.
After playback becomes idle, the preview and Resume button reconcile with the
saved checkpoint, including when an entry request is refused.

Foreground loss aborts the run. The native helper sends unconditional global
key-up, then may additionally post one release-only `WM_KEYUP` to the exact
focused RIFT HWND observed before this pulse's successful key-down. The pinned
process must remain alive, with matching window owner/thread/root ancestry.
Observed blur is latched through the action result. The fallback never sends
key-down or restores foreground. Windows queue acceptance and observed game
motion remain separate evidence. All GUI pulse receipts, including failures,
are retained as `artifacts/waypoint-input-*.jsonl`.

For explicit recovery of a key owned by an interrupted action, `move-key`
accepts `--release-only` with one key and the normal exact identity/foreground
guards. It cannot also request a hold or movement measurement. Each normal pulse
retains exclusive native input ownership, held-input refusal and bounded release.

For the same backend without the window:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --go 7422.455078125 2948.04931640625 --execute
```

CLI outcomes retain run receipts under `artifacts/waypoint-run-*.json`. Failed or
stopped runs retain the original reason, completed-leg events, checkpoint and
native pulse-file paths. STOP also retains the same two-pose `stopVerification`
as the window; missing observations remain explicitly unavailable. If the receipt
cannot be written, the final CLI JSON reports `receiptError` alongside the action
failure. Successful receipt contents retain their existing format.

Run a saved multi-point route through the same backend:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --run-route my-route.json --face-waypoints --execute
```

To save observations from an explicitly commanded `--go` or `--run-route`, add
`--record-to` with a new output path. This teaches from that bounded run; it is
not the passive window recording control. Replay and resume use `--play-route`:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --run-route my-route.json --record-to taught-route.json --face-waypoints --execute
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --play-route taught-route.json --reverse --progress taught-progress.json --face-waypoints --execute
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --play-route taught-route.json --reverse --progress taught-progress.json --resume --face-waypoints --execute
```

Omit `--reverse` for forward playback. Resume must use the saved direction and
checkpoint. Without `--progress`, the checkpoint uses the route path with a
`.progress.json` suffix. `--execute` is required for each commanded trip.
To resume a checkpoint created by the window, use the same loaded route and
`--progress artifacts/waypoint-current-progress.json`, with its saved direction.
Leave the window idle while CLI input runs. Afterward, **Refresh** or an idle live
pose update reloads matching saved progress without replacing the loaded route.

This requires explicit `--execute` and preserves every leg in one receipt. The
same ownership, progress, release and whole-trip limits apply. **F8** cancels CLI
execution without changing game focus; **Ctrl+C** also cancels. CLI input refuses
to start if its temporary F8 listener is unavailable. Omit `--face-waypoints` to
use the W/S/Q/E movement basis while keeping the current facing.

CLI Ctrl+C uses a temporary SIGINT handler that latches STOP instead of raising
inside `subprocess.run`; this lets the native child's key-up finish. An unexpected
F8-listener exit also latches STOP. Startup failure requests listener shutdown,
and cleanup restores the GUI's original window style even if shutdown reports
an error. Native listener checks covered registration conflict, owned hotkey
messages, unexpected exit, startup-timeout cleanup and subsequent re-registration.
A controlled live trial raised SIGINT during one native W subprocess: it finished
and released, no second pulse was dispatched, and separate native reads found the
player settled. This was a programmatic SIGINT test, not a physical Ctrl+C press.
Receipt: `artifacts/waypoint-cli-sigint-trial.json`.

A live two-point CLI route went one unit forward and returned home with one W
and two S presses (450 ms requested hold total). Outbound error was 0.0102 units;
return error was 0.00414 units. Bearing stayed unchanged and all three native
releases succeeded. The receipt retains both named legs:
`artifacts/waypoint-run-dba8ed0a046c4036a33437a61912766d.json`.

Existing solutions were checked before adding this adapter. [TomTom Rift](https://www.curseforge.com/rift/addons/tomtom-rift)
already provides waypoint lists and guidance, but its last release was in 2013
and it does not know terrain obstacles. [DotRecast](https://github.com/ikpil/DotRecast)
provides reusable .NET navmesh generation/pathfinding and is the candidate for
terrain routing if suitable RIFT geometry becomes available. The prototype
reuses RR2's existing `WaypointController`, native reader, physical reservation
and `move-key` helper; no third-party source was copied.

Live use on AMD-DESKTOP, 2026-11-12: a two-pulse 2-unit outbound leg stopped
0.111 units from its waypoint. **Go Selected** returned within 0.097 units of
its waypoint. A subsequent three-point **Run Route** finished 0.00352 units
from the original position. A latched STOP after one released 150-ms pulse
prevented the next pulse. These are historical open-ground observations from
their recorded process epoch,
not restart or obstacle-routing qualification.

The longer-trip extension crossed an 8-unit open-road waypoint in two segments
and eight released 150-ms pulses, finishing 0.213 units from the target.

A GUI focus-loss STOP exposed a real release failure: Atank kept moving into
the barrier; Joey confirmed no manual movement in that incident. The interrupted
receipt was not retained, so the precise missed-release sequence is unknown.
The changes above address the demonstrated failure rather than treating Windows
`SendInput` acceptance alone as proof the game stopped.

After the fix, F8 stopped a moving trip after one pulse, and a clickable STOP
also left the character stationary. A targeted open-road blur trial interrupted
a 750-ms E hold at about 178 ms: native `targetLost=true`, Windows key-up accepted,
and the exact owned-window release message queued. Two native samples while
blurred showed zero displacement. Returning focus to RIFT without pressing a
key, then sampling again, also showed zero displacement. Receipt:
`artifacts/blur-release-008ba70a0329416fbceab819cd1607e7.json`.

The local preview was exercised by saving the current point, clicking a point
2.09 units to the right, and using **Go Selected**. Atank stopped 0.216 units
from that clicked point and the preview recentered from the new observation.
Returning to the saved start finished 0.023 units from it. The GUI's Save Route
dialog wrote both points to `artifacts/waypoint-map-demo-4c6a750f.json` for reuse.

Use the native helper for physical game focus and the WGC observer for game
screenshots. Generic Computer Use activation restored the maximized game into
its smaller normal window during a focus test, leaving fresh WGC frames
unavailable. Reusing the existing BlackBox recovery script on the verified
AMD-DESKTOP display (`DISPLAY5`), with a 1936×1048 normal window, restored fresh
1922×1041 WGC frames without restarting the game or sending movement input.
Keep Computer Use interactions on the waypoint window; avoid activating,
dragging or restoring the physical RIFT window through that API.

Facing live use on the same process epoch: **Face Selected** aligned to the
sideways waypoint within 0.98 degrees without XYZ movement. Forward mode reached
it with two W presses, 0.088 units away. A combined turn-around-and-W sequence
finished 0.122 units from its waypoint. An initial 12-second facing timeout
expired after a successful 0.28-degree alignment, before any W; the separate
facing phase now allows 20 seconds for process checks and settling while retaining
the eight-pulse, 150-ms per-press and shared trip input budgets. F8 interrupted
another facing phase before W; subsequent XYZ and bearing drift were both zero.
Resuming finished 0.037 units from the saved start. The separate facing command
restored the earlier bearing within 2.63 degrees without changing XYZ.

A longer three-point triangle covered 13.66 planned units using **Run Route**
with forward-facing travel. It completed in approximately one minute with
27 pulses (14 W, 9 A, 4 D), 3,700 ms total requested hold, all native releases
successful and no target loss. Atank returned 0.150 units from the saved start.
Separate settled observations confirmed the endpoint. Five subsequent D turns
restored the pre-route bearing within 0.361 degrees without XYZ movement.
Route input receipt: `artifacts/waypoint-input-7aaf3780a54e4a3da35eb9030dcf56d3.jsonl`;
facing receipt: `artifacts/waypoint-run-314b50d1257b4cce97ec8c9c98c5ad4b.json`.

**Add Target → Face Selected** was exercised against the selected practice dummy,
6.234 units away. The point was added without input; two subsequent A turns
faced it within **0.236 degrees**, with unchanged XYZ. A fresh WGC/native bracket
put the selected dummy at frame X962.105 versus player X961.000 in a 1922-pixel
frame, matching its visible placement directly ahead. Capture:
`artifacts/observe-wgc-fe6fe17cdf544e1488bf54ccfbde4935/image.png` and `.png.json`.
Restoring the prior bearing used two D turns, finishing within 1.434 degrees,
again with unchanged XYZ. No travel to or attack on the target was attempted.
