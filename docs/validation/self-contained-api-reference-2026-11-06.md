# Self-contained reference implementation — 2026-11-06

Result: offline implementation and independent review complete; **installed and
live acceptance pending**. No game input, addon installation/disable/reload,
receiver replacement, VM/game restart, old-checkout edit or Git index change.
The existing Mana/casting work remains uncommitted and preserved.

The [migration note](../reference/self-contained-api-reference.md) records the
consumer/field audit, current commands and exact removal boundary. The
[RR2R1 contract](../../contracts/addon/reference-v1.md) is additive; RR2A1 and
RR2L1 meanings remain frozen. Current capture requires RR2R1 plus an explicit
nonce and reviewed reader hash. Historical probe parsing remains replay only.

## Actual checks

- Release solution tests: **670 passed** (377 core/CLI, 293 Live), after the
  duplicate-sequence/different-clock regression was added.
- Focused reference Python tests after final source-conflict fixes: **89 passed**.
- Final complete Lua-enabled Python discovery: **1,586 run, 1,584 passed and
  two skipped**. The earlier 1,579-test run also passed with two skips before
  the last review regressions were added.
- Lua 5.1 contract gate: **165 lifecycle/encoder assertions**, 11 addon and 11
  live-envelope Lua-to-C# cases, two Lua/C#/Lua guidance round trips, plus actual
  RR2R1 producer output through the strict .NET snapshot-pair inspector and
  Python Mana extraction; foreign nonce rejected.
- Full-solution formatting verification passed after formatting only this
  change's C# files. `git diff --check` passed.
- Published native smoke passed on its **own synthetic host process**, including
  bundle identity, PE header, stale process epoch and no-overwrite behavior.
- Published RR2R1 scout/copy trial passed for two bounded own-process captures,
  each preserving seven 4 KiB pages. The archive verifier recovered eight files
  and checked original/embedded/returned marker closure. This proves marker
  acquisition, **not a valid Lua frame or game readiness**. Archive SHA-256:
  `718A4E51075A285DD1E3091C57AD2BA2EC279D5CC739966E406EB821A159405E`.
- Separate reviewer found no remaining blocker and independently reran 56 focused
  Python tests, then 13 resource-inspector tests after the last two edge fixes.
  Review covered producer lifecycle, marker closure, foreign sessions, mixed
  epochs/players, same-sequence conflicts, clearing states, ASCII/framing,
  cross-snapshot aggregation, receiver receipt compatibility and source ownership.
- Bounded `scripts`, `src`, `tools` searches found no operational old-checkout
  paths or adapter imports. Historical probe names remain in replay parsers.

`scripts/validate.ps1` exited 1 at its final repository-wide whitespace scan:
`docs/validation/lab1-controller-recovery-incident-2026-10-30.md` has preexisting
trailing whitespace. That file is unchanged by this task. Build, 670 .NET tests,
formatting, native smoke, Lua contracts, Python discovery, deterministic demo,
relative-link checks and Git diff checks had completed before this failure.
**This is not a full-gate PASS.** The unrelated historical file was preserved.

Reviewable reader: `artifacts/validation/rr2-selfcontained-20261106-reader/RiftReader2.Live.exe`,
117,270,368 bytes, SHA-256
`1A97D39BB0769E450B80E9EE0D802447713195AA682C0858CEB6F96F114319F6`.
Cross-language evidence: `artifacts/validation/rr2-selfcontained-20261106-contract-02/`.
Published capture evidence: `artifacts/validation/rr2-selfcontained-20261106-published-capture/`.
Full-gate log: `artifacts/validation/rr2-selfcontained-full-gate.log`.
The task review receipt lists the exact changed-file inventory and source/addon
hashes under `artifacts/validation/rr2-selfcontained-20261106-review.json`.

## Pending operational gate

No claim is made that the running games loaded package 0.2.0, that the old probe
is disabled, that RR2R1 is live/fresh on the current build, or that native fields
have gained semantic/changed-state/restart qualification. Existing old-source
receiver ownership fails closed; the new source does not silently replace it.

After specific authorization, use the Lab-1-only backup-first seven-file addon
candidate, disable the old probe, perform the separately reviewed reload and
nonce entry through a permitted route, and retain same-player advancing RR2R1
observations under fresh process/build identity. Verify the consumers on those
bytes. Each target needs its own acceptance before removing its old probe;
restart qualification additionally requires an explicitly authorized real game
restart. The prior rejected GUI-bind route remains unavailable.
