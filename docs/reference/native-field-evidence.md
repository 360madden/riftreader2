# Reproducible native position candidate review

The optional `scripts/native-field-evidence.py` tool replays saved
`native-field-discovery/1` lab reports into one deterministic
`native-position-candidate-review/1` artifact. This is an evidence-checking
utility for the ongoing field-discovery experiment, not a new production
capture protocol or an automatic field qualifier.

## Use

Run from the repository root with the exact local reports and candidate offsets:

```powershell
python scripts/native-field-evidence.py `
  --report artifacts/field-discovery/runs/RUN_A/report.json `
  --report artifacts/field-discovery/runs/RUN_B/report.json `
  --root-rva 0x32E0200 --xyz-offsets 0x320 0x324 0x328 `
  --tolerance 0.02 `
  --output artifacts/field-discovery/position-review.json
```

Replace `RUN_A` and `RUN_B` with existing run IDs. Reports are ignored
local lab evidence and are not present in fresh clones. The output must not
already exist; its publication is atomic and refuses replacement. Omit
`--output` to print JSON. Exit 0 means the comparison ran, **not** that the
candidate is qualified; inspect `assessment`, each capture's
`rootWindowStability`, and `withinEpochMovementComparisons`.
Invalid files/identities or existing outputs return exit 2.

The tool bounds input size and count; rejects malformed/duplicate JSON,
unexpected report types, wrong build, changed process/observer/unit identity,
stale typed Lua, unadvanced sequences, and disagreeing root/owner bytes;
verifies SHA-256 for every selected owner byte window; and checks the pointer
hop when its stability reread was recorded. It decodes little-endian float32
XYZ and compares with fresh typed Lua before and after acquisition, preserving
reference drift, error values, source hashes, process epochs, and evidence
limitations. Only two captures from the **same process and character** may
form a movement-displacement comparison. Repeating one report is rejected.

The first historical field-lab capture did not retain a root stability
reread. The tool records that as `unrecorded`, never silently `verified`.
It does not interpret a matching number as player position, promote session
heap addresses, or automatically claim survival across game restarts or game
updates. Meaning, locator, restart survival and update survival must be
independently reviewed through the [field catalog](field-catalog.md).

## Retained October 19 result

Three same-process captures, from 05:45:07, 05:57:46, and 06:00:00 UTC, showed
native XYZ near typed Lua positions before and after one earlier supervised
forward movement. The latter two windows include successful root rereads;
the first does not. The retained replay report is
`artifacts/field-discovery/candidate-review-20261019.json` (ignored),
SHA-256 `4EBC1409422AB97AF5C5895DBB6AEF4A3F88047F1E76A0369323ED09A34FCAC5`.
It reports `movement-consistent-stability-unverified`, one process epoch,
and `candidate-only`. No restart, update, or health/resource field is
qualified. See the [live handoff](../validation/native-player-fields-2026-10-19.md).

The regression suite is `python -m unittest tests.test_native_field_evidence`
and runs with the repository-wide validation gate.
