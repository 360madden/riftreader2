# Physical waypoint prototype

Launch on the physical game's owning host with an explicit PID:

```powershell
pythonw scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092
```

The window reads the current position and facing. **Save Current** adds a point;
**Add X / Z** adds entered coordinates. Select a point and choose **Go Selected**,
or choose **Run Route** to visit the list in order. **Load** and **Save Route**
use a small JSON file containing `{"waypoints": [["name", x, z]]}`.
Use `--route PATH` to open the window with a saved list; loading does not start movement.

Each leg is limited to 6 world units, six pulses, 900 ms total key hold and
12 seconds. Arrival requires two settled observations within 0.30 units.
This is a supervised open-ground prototype: it does not route around obstacles.
The measured W/S/Q/E speeds are rotated using the current entity body facing;
the native position/facing fields remain candidates, with restart qualification
still pending. The included movement basis is pinned to its measured process
epoch, player and executable. A restart requires a new basis via `--basis PATH`.

**STOP** latches cancellation. The current pulse is allowed to finish its bounded
release; another pulse is never sent. Closing the window waits for that cleanup.
Only the first pulse can request RIFT foreground. Losing foreground stops the
run, including between pulses or route legs. Do not manipulate the RIFT window
while moving. Each native pulse retains the existing exclusive input owner,
process/start/build checks, held-input refusal and unconditional key release.

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
