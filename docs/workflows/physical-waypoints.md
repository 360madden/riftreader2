# Physical waypoint prototype

Launch on the physical game's owning host with an explicit PID:

```powershell
pythonw scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092
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
Use `--route PATH` to open the window with a saved list; loading does not start movement.

**Face Selected** turns toward a waypoint without walking. **Face, then walk**
aligns to each waypoint and uses W for travel. Unchecked, the existing W/S/Q/E
controller approaches the point with the current facing. Facing uses the retained
same-epoch settled A/D measurements as seeds and checks the observed response
after every release. Alignment allows eight 20–150-ms presses and 20 seconds,
stopping within 4 degrees. It refuses unexpected XYZ movement during a turn.
Turns share the trip's hold/pulse budget; facing mode uses segments up to 3.5
units long. The existing translation controller retains its own limits.

For a requested facing without walking:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092 --face-bearing -4.7 --execute
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
total key hold and 120 seconds overall. Long waypoints are split into targets
at most 4 units apart. Each target retains the existing controller's six-pulse,
900-ms hold, 12-second and 6-unit radius limits. Input ownership and the trip
budget span every target and waypoint; only the first actual pulse can focus
RIFT. Arrival requires two settled observations within 0.30 units.
This is a supervised open-ground prototype: it does not route around obstacles.
The measured W/S/Q/E speeds are rotated using the current entity body facing;
the native position/facing fields remain candidates, with restart qualification
still pending. The included movement basis is pinned to its measured process
epoch, player and executable. A restart requires a new basis via `--basis PATH`.

**STOP / F8** latches cancellation. F8 is registered only during a trip and does
not change foreground. The waypoint window uses `WS_EX_NOACTIVATE` during the
trip so an ordinary STOP click also preserves foreground; editing is disabled
until cleanup. The current pulse finishes its bounded release; another pulse
is never sent. Closing waits for cleanup, and STOP checks for actual stationary
native XYZ and body bearing. Only the first actual pulse can request RIFT foreground.

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
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092 --go 7422.455078125 2948.04931640625 --execute
```

Successful CLI runs retain the native input receipts under `artifacts/waypoint-run-*.json`.

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
prevented the next pulse. These are current-epoch open-ground observations,
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
