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

## Compare static health structures across process restarts

Use `--compare-health-hits` with exactly two previously captured
`native-field-discovery/1` reports from distinct RIFT process epochs.
Both must have the same executable build and player identity. The same
root RVA and health-reference checks apply as for a single review:

```powershell
python scripts/native-field-evidence.py --compare-health-hits `
  --report artifacts/field-discovery/runs/OLD_RUN/report.json `
  --report artifacts/field-discovery/runs/NEW_RUN/report.json `
  --root-rva 0x32E0200 --level-hint 45 `
  --output artifacts/field-discovery/health-structures.json
```

The comparison verifies both reports and every retained matching context hash,
then examines only bounded int32 marker layouts near recorded health hits.
Markers represent available typed **health**, **health maximum** and **raw
power** values, plus the optional independently observed level hint. A group
needs at least three matching marker sites spanning two marker families;
unknown integers, pointers, and address offsets are never normalized into
game-field claims. Group addresses are process-local examples only.

The tool reports how many distinct groups share each layout in each process
epoch. Multiple groups with the same layout are explicitly labeled
`replicatedInEitherEpoch` rather than being treated as one durable field.
If typed values differ between epochs or change during either scan, static
shape comparison is withheld. This comparison **does not** follow a pointer,
prove current versus maximum health, validate health/resource changes, or
qualify restart/update survival. Its result remains `candidate-only`.

The retained October 19 replay found one shared layout with 8 copies in
the first epoch and 5 in the second. The layout has level hint 45 at -8,
three health-or-max matches at 0/+8/+16 and raw power 100 at +40/+44
relative to each group's first health hit. The report is
`artifacts/field-discovery/health-cross-epoch-shapes-20261019.json`
(ignored), SHA-256
`6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD`.
These repeated static copies are a useful narrow lead for changed-state
experiments, not identified health data.

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

## Validate a field-lab old-epoch rejection

The `--verify-old-epoch` replay requires **one probe report** containing
the field-lab's explicit old-process test and an independently captured
prior-epoch report from the same game executable build and character.

```powershell
python scripts/native-field-evidence.py --verify-old-epoch `
  --prior-report artifacts/field-discovery/runs/PRIOR_RUN/report.json `
  --report artifacts/field-discovery/runs/PROBE_RUN/report.json `
  --root-rva 0x32E0200 `
  --output artifacts/field-discovery/old-epoch-review.json
```

The verifier reuses the bounded raw-report, pointer-root stability and fresh
Lua XYZ validation. It checks independent source file hashes, chronological
process epochs, matching player/build, exact prior creation ticks, planned
old PID, explicit `oldEpochRejected:true`, and the mode-specific reported
Windows error. It distinguishes an **unopenable retired PID** from the
stronger **current PID with a deliberately mismatched old start time**.
Unrelated errors, omitted plan fields, stale references or unchanged
process identity cannot produce a success report. The JSON output is
candidate-only and is atomically published without replacing existing data.

This is an audit of the field-lab's
`WindowsNativeMemorySession.OpenAsync` test, not a direct in-game execution
of the public `follow-pointer` command. See the
[real live two-case record](../validation/native-field-old-epoch-live-2026-10-19.md)
and the separate [host command regression](../validation/native-pointer-epoch-regression-2026-10-19.md).
Neither qualifies field semantics or game-update survival.

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

The follow-on [targeted health snapshot planner](targeted-health-snapshot.md)
uses same-epoch validated candidate layouts and a fresh Lua receipt to
prepare a small, session-bound native snapshot request, without rescanning
memory or promoting cached health matches to gameplay fields.
