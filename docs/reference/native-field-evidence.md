# Reproducible native field candidate review

The optional `scripts/native-field-evidence.py` tool replays saved
`native-field-discovery/1` lab reports into deterministic
`native-position-candidate-review/1` or `native-health-hit-review/1` artifacts. This is an evidence-checking
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
heap addresses, or automatically qualify fields because they matched after a
restart. Meaning, locator, restart survival and update survival must be
independently reviewed through the [field catalog](field-catalog.md).

## Bounded health-hit review

Pass **one** complete field-lab report that includes a `healthScan:true`
plan. This is a read-only offline review of already retained evidence, not a
new game-memory scan or a health-field decoder:

```powershell
python scripts/native-field-evidence.py --health-hits `
  --report artifacts/field-discovery/runs/RUN_HEALTH/report.json `
  --root-rva 0x32E0200 --level-hint 45 `
  --output artifacts/field-discovery/health-hit-review.json
```

The optional `--level-hint` comes from separate visual evidence and is
**not** verified by the typed Lua API. Omit it if the character level is
unknown. The reviewer validates the recorded PID/start/build, the root/owner
bytes, stable typed Lua player and source-sequence identity, exact context
SHA-256, recorded health and encoding flags, scan bounds and incomplete reads.
It groups neighboring exact health hits into bounded session-address groups
and notes nearby typed raw-power numbers; a group is not an authoritative
health field or reproducible pointer path. The output records the hit limit,
byte budget, current/max health ambiguity and missing changed-state evidence.
Reports from separate process epochs must be reviewed individually in this
mode. Every output is `candidate-only`, with restart/update unassessed.

## Cross-epoch same-build observation

When position reports from **different PID/start epochs** have the same
executable hash and player ID, the reviewer compares each root reread and
native position independently against its own fresh Lua reference. If both
have a stable root reread and tolerable XYZ, it records
`restartSurvival: same-build-candidate-observed`. It also preserves each
pair's `ownerSessionAddressChanged` and the original evidence identities.
This means the candidate **was reobserved after the game restarted**. It
does **not** qualify a native field's meaning, a game update, or old-epoch
request rejection; the catalog still requires separately reviewed
assessment evidence. The report's `qualification` remains `candidate-only`.
`withinEpochMovementComparisons` remains independently scoped to same-epoch
movement; differing player identities cannot be combined as restart evidence.

## Retained October 19 result

Three same-process captures, from 05:45:07, 05:57:46, and 06:00:00 UTC, showed
native XYZ near typed Lua positions before and after one earlier supervised
forward movement. The latter two windows include successful root rereads;
the first does not. The retained replay report is
`artifacts/field-discovery/candidate-review-20261019.json` (ignored),
SHA-256 `4EBC1409422AB97AF5C5895DBB6AEF4A3F88047F1E76A0369323ED09A34FCAC5`.
It reports `movement-consistent-stability-unverified`, one process epoch,
and `candidate-only`. A later scan and ordinary RIFT restart produced a
new-epoch native report with the same root RVA and moved heap owner. Five
captures across two game process epochs re-evaluated to
`same-build-candidate-observed` and remained `candidate-only`. The first
health review grouped 126 hits into 104 neighboring groups; the restarted
health review grouped 128 hits into 111. Neither changed health nor power,
and no health/resource field was qualified. See the
[chronological live record](../validation/native-player-fields-2026-10-19.md).

The regression suite is `python -m unittest tests.test_native_field_evidence`
and runs with the repository-wide validation gate.
