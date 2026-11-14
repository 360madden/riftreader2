# Safe-to-hunt-to-safe mission CLI

`scripts/hunt_mission.py` is the CLI entry point for one bounded mission:

1. leave a verified safe anchor over a recorded route;
2. handle one already selected, exact target inside a bounded hunt area; and
3. return to the safe anchor over the native path actually walked outbound.

The orchestrator and its focused integration checks are implemented offline.
Physical mission acceptance is pending. Do not treat the existence of this
command as evidence that a particular corridor, target, profile or current game
session is suitable.

## Commands

Use absolute paths for operational runs. `dry-run` is file-only and does not
construct a physical adapter. `preflight` reads current state but sends no game
input. `run` and `resume` require the explicit `--execute` flag.

```powershell
$mission = 'C:\path\to\hunt-mission.json'
$route = 'C:\path\to\verified-outbound-route.json'
$profile = 'C:\path\to\survival-profile.json'
$checkpoint = 'C:\path\to\hunt-progress.json'
$riftProcessId = Read-Host 'Current physical RIFT PID'

python scripts/hunt_mission.py dry-run `
  --mission $mission --route $route --profile $profile

python scripts/hunt_mission.py preflight `
  --mission $mission --route $route --profile $profile `
  --expected-host AMD-DESKTOP --physical-pid $riftProcessId

python scripts/hunt_mission.py run `
  --mission $mission --route $route --profile $profile `
  --expected-host AMD-DESKTOP --physical-pid $riftProcessId `
  --checkpoint $checkpoint --execute

# Only after an operator has reviewed and resolved the prior halt:
python scripts/hunt_mission.py resume `
  --mission $mission --route $route --profile $profile `
  --expected-host AMD-DESKTOP --physical-pid $riftProcessId `
  --checkpoint $checkpoint --execute
```

The host is not intrinsically fixed to AMD-DESKTOP; the CLI accepts the physical
hosts supported by the current build. Always bind the command to the host and
PID of the intended current client.

## Mission document

```json
{
  "schema": "rr2-hunt-mission/1",
  "name": "Watch Stalker out and back",
  "mode": "explicit-selected-target",
  "binding": {
    "routeSha256": "UPPER_OR_LOWER_HEX_SHA256_OF_EXACT_ROUTE_FILE",
    "profileSha256": "UPPER_OR_LOWER_HEX_SHA256_OF_EXACT_PROFILE_FILE"
  },
  "safeAnchor": {
    "x": 7134.519043,
    "y": 871.776184,
    "z": 3034.791992,
    "planarTolerance": 0.5,
    "heightTolerance": 0.75
  },
  "hunt": {
    "expectedTargetId": "u800000020502E041",
    "centerX": 7179.7798,
    "centerY": 871.776184,
    "centerZ": 2986.95996,
    "radius": 5.0,
    "maximumSeconds": 120,
    "maximumKills": 2
  },
  "return": {
    "mode": "reverse-verified-walked-corridor"
  },
  "maximumMissionSeconds": 1800
}
```

The coordinates above illustrate the shape only. Reacquire and review the
current safe anchor, hunt area and exact target before any physical run.

The validator requires:

- schema `rr2-hunt-mission/1` and mode `explicit-selected-target`;
- an exact `u` plus 16-hex-character target instance ID;
- SHA-256 bindings to the exact route and survival-profile files;
- finite X/Y/Z coordinates;
- safe-anchor planar tolerance greater than zero and at most 1 unit;
- safe-anchor height tolerance greater than zero and at most 2 units;
- hunt radius greater than zero and at most 50 units;
- hunt time from 1 through 120 seconds;
- kill bound of 1 or 2; and
- an overall mission limit from 1 through the shared trip limit of 1,800
  seconds.

The outbound route must begin within the safe-anchor tolerances and end inside
the hunt radius. The return mode must be
`reverse-verified-walked-corridor`. The initial exact-target implementation can
process one selected encounter; it does not search for or select another target
to satisfy a two-kill upper bound.

## Evidence and result meaning

The encounter endpoint rechecks the selected target, current position and hunt
radius before deliberate actions. A target disappearing, selection clearing or
target death by itself does not count as a kill. `killCount` advances only for
a fresh, qualified `player-kill-confirmed` receipt for the exact pinned target.

A verified round trip with no qualified kill returns:

```json
{"status":"returned-no-qualified-kill","safeReturned":true,"killCount":0}
```

`status: "completed"` requires both a verified safe return and at least one
qualified kill. Neither status claims general nearby-target selection. The
result states `additionalTargetSelection` as
`unsupported-explicit-selected-target-only`.

The return document is derived from bounded native samples retained from the
outbound walk. Every outbound leg must have arrived, have a continuous path and
show verified input release with no desktop inputs down. This proves only the
walked corridor retained in that run; it is not general pathfinding or a claim
that all future traversals are safe.

## STOP, deadline and Resume

Ctrl+C/F8 and the existing STOP path share one latch. The same deadline-aware
STOP object is used by preflight, outbound travel, the encounter and return.
Expiry of the overall mission budget latches STOP; the hunt deadline cannot
extend it. The orchestrator does not clear STOP automatically.

Return movement is refused when encounter input release is unverified. Progress
is checkpointed before the encounter begins. If execution ends after that point
without a trusted result, the checkpoint remains `encounter-started` and Resume
refuses it as ambiguous—there is no automatic retry and no inferred kill.

An operator may run `resume --execute` only after reviewing the halt, resolving
the STOP/safety condition and deliberately starting a new invocation. Route
checkpoints resume completed movement; they do not manufacture encounter proof.

## Current qualification

Offline focused and neighboring integration checks cover validation, file-only
dry-run, exact kill credit, safe return without kill credit, release refusal,
ambiguous Resume refusal, discontinuous native paths and the shared mission
deadline. A physical safe-to-hunt-to-safe mission has not yet been accepted.

See also [Waypoints survival integration](waypoint-survival-2026-11-14.md) and
the [physical waypoint workflow](../workflows/physical-waypoints.md).
