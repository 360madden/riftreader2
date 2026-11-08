# RR2 named navigation anchors — offline catalog v1

A named anchor is a saved *reference destination*, never a live player
location fix, verified world-instance match, or movement authorization.

- Axes: **X/Z planar; Y vertical**. Coordinate units and native-cache
  world-frame portability remain unqualified.
- Allowed source kinds: `addon-feedback-receipt` and `native-cache-candidate`.
  They identify the *declared* capture kind; the catalog validates a hash's
  syntax but does **not** authenticate the underlying capture file.
- Every anchor uses `qualification: "offline-reference-only"`. Resolver output
  always includes `movementEligible: false`.
- `zoneLabel` is informational; it is NOT a same-world or same-instance gate.

## Start with the empty catalog

In PowerShell, from `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe -B scripts\navigation_anchors.py --catalog config\navigation-anchors.example.json
```

The tracked template is intentionally empty. Make a separate personal copy
before storing coordinates.

## Add an anchor

Insert an object into the top-level `anchors` list, with these exact fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable 1–64 character letter-started ID with letters, digits, underscores, hyphens; unique ignoring case |
| `label` | Nonempty readable label |
| `position` | Finite numeric `x`, `y` and `z` |
| `zoneLabel` | String or null; metadata only |
| `source.kind` | One of the two declared source kinds |
| `source.gameBuildSha256` | 64 hex characters from the capture game build |
| `source.evidenceSha256` | 64 hex characters from the capture evidence |
| `source.capturedAtUtc` | UTC capture timestamp |
| `qualification` | Exactly `offline-reference-only` |

This object contains **fictional XYZ** and intentionally invalid hash
placeholders. Replace both digests with the real 64-character values:

```json
{
  "id": "North_Gate",
  "label": "North gate",
  "position": { "x": 12.5, "y": 3.0, "z": 47.25 },
  "zoneLabel": null,
  "source": {
    "kind": "native-cache-candidate",
    "gameBuildSha256": "<64-hex-from-source>",
    "evidenceSha256": "<64-hex-from-source>",
    "capturedAtUtc": "2026-11-08T13:00:00Z"
  },
  "qualification": "offline-reference-only"
}
```

## Import from a retained scoped receipt

The importer creates one new offline catalog directly from a historical raw
receiver receipt. It checks the stored reader nonce, matching scoped sequence
and epoch, completed scan, selected `fresh-scoped` addon XYZ, finite coordinates,
source build hash, and UTC capture time. It binds the **SHA-256 of the exact raw
receipt bytes** to the saved anchor. A historical fresh label is not current
player location or permission to move.

From PowerShell in `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe -B scripts\navigation_anchor_capture.py --receipt artifacts\receiver-migrations\lab1-strict480-observer-d\raw\initial-receipt.json --id Lab1_Old_Reference --label "Lab 1 historical reference" --output-catalog artifacts\receiver-migrations\lab1-strict480-observer-d\anchors.json
```

Omit `--output-catalog` to inspect the JSON result without creating anything.
The output path must not exist: the importer **never overwrites or merges** a
catalog. This retained sample is old reference evidence, not a current-game fix.
A saved anchor can be passed via `--anchor-id` and `--catalog` to the existing
offline `plan_steered_waypoint.py next` command using a separately measured W
calibration from the same executable build. That planner does not emit a live
runner command for a saved anchor. Live movement requires new position feedback,
world compatibility, fresh session admission, and reviewed controls.

Focused importer tests:

```powershell
C:\Python314\python.exe -B -m unittest discover -s tests -p test_navigation_anchor_capture.py -v
```

## Resolve by name

```powershell
C:\Python314\python.exe -B scripts\navigation_anchors.py --catalog config\my-anchors.json --anchor-id North_Gate
```

Returns the stored XYZ and a `planarGoal` containing X/Z only.
IDs match case-insensitively. Unknown IDs, duplicate JSON keys, malformed
SHA-256, nonfinite numbers, unsupported coordinate frames, and attempts to
store a live-navigation admission are rejected.

This module never accesses RIFT, VMware, controllers, game memory or input.
Its goal can be passed to the existing **offline**
`scripts/plan_steered_waypoint.py`, which still requires a separate current
movement calibration. Actual movement retains independent fresh addon
feedback, identity/zone compatibility, controller admission and STOP.

Focused tests:

```powershell
C:\Python314\python.exe -B -m unittest discover -s tests -p test_navigation_anchors.py -v
```
