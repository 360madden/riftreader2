# Current-build native XYZ tracking

This workflow reads **candidate cached coordinates**, not qualified live player
position, heading or passive freshness. Run commands in PowerShell from
`C:\work\riftreader2`. Acquisition uses the configured lab and checks the
current game process ID, start epoch and exact executable SHA; it sends no game
input. A blocked result is not a fresh coordinate.

## Acquire, then project

```powershell
python -B scripts/sample_current_native_xyz.py --lab lab1 --samples 15 --interval-ms 400
```

The JSON summary provides `sourceReport`, its SHA-256 and the ordered `track`.
Use the **absolute** `samples.json` path returned by that run in the separate,
offline projection:

```powershell
python -B scripts/project_xyz_track.py <absolute samples.json> --max-gap-seconds 5 --max-speed-3d 100
```

Replace `<absolute samples.json>` with a quoted actual path; do not type the
angle brackets. This command reads only the retained report and prints JSON.
The example thresholds are **illustrative, not validated RIFT speed limits**;
choose them explicitly for the investigation. The source uses stopwatch
milliseconds within one sampling run, not a shared clock across runs or machines.
Do not join separate runs or infer current age from these offsets.

The projection provides ordered raw coordinate deltas, X/Z planar and 3D
distances, and velocities when the declared gap and speed limits permit. Y is
the vertical axis under the candidate convention. Gap or excessive-speed
boundaries withhold motion for that pair; a speed boundary does not prove a
teleport. Coordinate units, same-unit/world/zone continuity, zone transitions,
and underlying source freshness remain unverified. No facing, compass heading,
or navigation readiness follows from these numbers.

## Fresh acquisition evidence

The active host pin now uses the new immutable .NET reader at
`artifacts/native-xyz-unit-20261107/publish/RiftReader2.Live.exe`, SHA-256
`BE252929D846AA0BB696D003116AB9D8ACAA23E5D411D68F913A92CD08919A5E`.
A fresh **5/5** Lab1 run returned the same sampled unit key
`u035400012FA2D678` (decimal `239816685251647096`) at each observation,
with XYZ `7450.3677,864.3101,2984.6113` and maximum gap **533.3391 ms**.
The source receipt is
`artifacts/native-current-sampler-20261105/runs/lab1/7d5b868c40664a0cb95e2c6ce0892cfb/samples.json`,
SHA-256 `FC9DC02D1692BECA28ACF9F7F7A8B492D2AEC04A23FB87CC4CFF4495A4009772`.
The new host validator requires every row to carry a canonical lossless
64-bit key and matching unit ID from the anchored owner; changed, missing,
or malformed sampled keys fail closed. Equal sampled keys do NOT establish
uninterrupted owner continuity or passive coordinate refresh. No game input
occurred. The previous published B8A725E6... binary remains untouched.

An earlier Lab1 acquisition returned **15/15 samples** and the offline projection
completed with zero observed coordinate deltas. This confirms acquisition and
calculation for that run, not that the cached source was changing or fresh.
Receipt:

- `C:\work\riftreader2\artifacts\native-current-sampler-20261105\runs\lab1\16afd9a6486a450e92d174555e510fb6\samples.json`
- SHA-256: `98AA5218CF7995CBEEB2D76A29C435A40275850DFE75BBA6409740917CA7E229`
- PID 6820, start ticks 639296903905448486; game SHA-256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
  Maximum observed start gap 523.5209 ms and read duration 90.6729 ms are
  acquisition timings, not producer-freshness proof.

## Reuse and limits

`scripts/xyz_track_reduce.py` is a pure pairwise reducer for explicitly supplied
process/build/session/world/zone identities and one monotonic clock domain. It
withholds motion across identity/zone changes, gaps, stale receipt age and
speed-limit boundaries. Receipt age alone does not prove the game source advanced.

`scripts/xyz_relative_candidate.py` is a separate pure self-to-selected-target
geometry helper. It requires independently supplied matching process, session,
world, zone, self/target binding and clock domain plus bounded receipt age and
skew. Even the newly identity-bearing self reports do not supply authenticated
shared world/zone or a synchronized target clock domain. Therefore a real
target-relative result remains **unavailable** until these are established. Its
coordinate bearing is not player facing or compass heading.

Do not substitute the historical-build `scripts/run_xyz_workflow.py`,
`scripts/xyz_capture.ps1` or `scripts/review_native_motion_pair.py` profile
for this current-build sampler. `Inspect.Unit.Detail` can itself refresh the
XYZ cache: agreement after an API call may be circular and does not establish
passive freshness. Independently changed-state evidence and native-before/API/
native-after comparisons are needed before a stronger claim.
