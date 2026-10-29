# Lab Codex workflow validation — 2026-10-29

Status: **two-lab read-only batch passed.**

This checkpoint validates the main-PC workflow described in
[`lab-codex.md`](../workflows/lab-codex.md). The authoritative source was clean
commit `47f8f2b55bcdd7d0dd9b3810946f0688c345da45`; guest reports remain evidence
for main-host review, not authority to change source or operate the game.

Evidence is under
[`artifacts/lab-codex-validation`](../../artifacts/lab-codex-validation/) and
[`artifacts/lab-codex`](../../artifacts/lab-codex/).

## Real two-lab batch

The sample batch exited **0** and its persisted index reports `succeeded`:
[`batch.json`](../../artifacts/lab-codex/batch-b241a27f-174d-479d-a905-63250cedb08e/batch.json).
Both jobs used the same frozen three-file snapshot and distinct job, lab and VM
identities:

- Lab 1 job `cc890609-4b16-44a4-9913-1a8f0baa8f30` ran from
  `09:38:27.875Z` to `09:39:18.898Z`. Its schema-valid source review correctly
  described load order and three concrete guidance-result acceptance groups:
  command/binding shape, bounded and advancing numeric fields, and current
  observation/player/epoch/age/displacement checks.
- Lab 2 job `4ec2d9e7-a76e-4569-97a7-32cdcbfbb0ca` ran from
  `09:38:30.092Z` to `09:39:46.357Z`. It reported all three installed files
  readable with SHA-256 and byte lengths matching the frozen source snapshot.
  This is a guest-reported disk comparison; it does **not** prove which bytes
  the running RIFT process loaded.

The overlapping intervals establish actual parallel execution. Both workers
used signed-in `codex-cli 0.165.0`; separate real `doctor` runs for both labs
also succeeded. The independent review found both reports schema-valid and the
source claims accurate within their stated limits. See
[`summary.json`](../../artifacts/lab-codex-validation/live/summary.json) and
[`independent-review.json`](../../artifacts/lab-codex-validation/independent-review.json).

## Repeatability and isolation

- Repeating `collect` returned semantically identical dictionaries for both
  completed jobs without rerunning them.
- Repeated Lab 2 `status` remained `succeeded`.
- Cancelling the already-terminal Lab 1 job was a no-op; no cancel request was
  sent.
- Both native control hosts, guest agents, VM identities and game identities
  matched their baselines afterward. Both hosts remained connected, ready,
  disarmed and idle, with no recovery required or sampled input down.
- The coordination queue was idle. The jobs issued zero control commands, and
  whole-journal review found zero arm/action/recover operations.

The first Windows helper attempt exposed collisions with the short PowerShell
aliases `H` and `R`. The helpers were renamed uniquely, tests were added, and
the corrected scripts passed on real Windows. Nine focused worker tests also
exercised real timeout, cancellation and owned-process-tree cleanup using a fake
CLI.

## Repository gate

The final gate passed:

- **539 .NET tests**;
- **999 Python tests run: 997 passed and two skipped**;
- **110 Lua lifecycle/encoder checks** plus the shared Lua/C# cases and guidance
  round trips;
- native publication smoke and **720 relative links**.

Evidence: [`artifacts/validation/20261029T093914Z-54d40fbc`](../../artifacts/validation/20261029T093914Z-54d40fbc/)
and [`full-gate.log`](../../artifacts/lab-codex-validation/full-gate.log).

## Limits

The batch supplied only the selected addon snapshots; it did not provide a
writable repository mirror. It performed no game input, native-memory work,
addon reload, source application, control-host action or authentication export.
Guest-generated patches and source synchronization remain unimplemented and
require a separate reviewed contract.
