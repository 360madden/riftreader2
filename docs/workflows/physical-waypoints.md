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
native positions. Only the first actual pulse can request RIFT foreground.

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
