# Guest Codex project workflows

Authorized October 29, 2026: plan and implement main-PC coordination of the
existing Codex CLI installations in both RIFT labs, with timely local commits.

**Completed:** the plan, guest worker and host commands are committed as
`861355c`, `9596b7f` and `47f8f2b`. Both real guest jobs succeeded in parallel,
repeat collection/status and terminal cancellation passed, existing control
hosts stayed ready/disarmed, and the full implementation gate passed. See the
[live acceptance](../validation/lab-codex-workflows-2026-10-29.md) and
[operator guide](../workflows/lab-codex.md). Active timeout/cancellation cleanup
was exercised with disposable Windows CLI/child process fixtures. The initial
PowerShell alias collision was fixed before the successful live batch.

## Outcome and approach

Keep the authoritative repository and integration on the main PC. Dispatch a
precise task plus selected source files to a fresh guest job directory. Use the
installed, signed-in `codex exec`; return a structured report and execution
receipt. The existing VMware GuestSession route already works, so new SSH
servers, listeners, account setup and a persistent agent service are unnecessary.

The first version supports read-only diagnostic/analysis jobs. It does not send
game input, change live addons, apply guest-generated source edits or use native
memory recipes. Main-PC Codex reviews returned claims before accepting them.
Existing control-host ownership remains intact throughout verification.

## Implementation checkpoints

1. **Plan and contract:** commit this plan, an example two-lab configuration,
   report schema and complementary example tasks. Baseline: 47 existing guest
   session/native identity tests passed in the isolated worktree.
2. **Working commands:** implement `scripts/lab_codex.py` with `doctor`,
   `dispatch`, `status`, `collect`, `cancel`, `run` and `batch`; reuse
   `vmware_guest_session.py` and fresh VM identity collection. Implement one
   short-lived PowerShell worker, with owned-process timeout/cancellation and
   atomic state publication. Commit after focused lifecycle checks and review.
3. **Actual use:** run complementary jobs inside both guests, collect and
   validate reports, verify task/input/VM provenance and unchanged control-host
   readiness. Exercise worker failure/timeout/cancellation with disposable
   process fixtures. Run the repository gate, document exact live evidence and
   remaining limits, then commit the verified result.

## User-facing commands

The default ignored config is `.local/lab-codex.json`, copied from
`config/lab-codex.example.json`. Every job uses a unique directory under
`artifacts/lab-codex/`; credentials remain in the existing VM-specific stores.

```powershell
python scripts/lab_codex.py doctor --lab lab1
python scripts/lab_codex.py run --lab lab1 --task tasks/example.md --input addon/RiftReader2/guidance.lua
python scripts/lab_codex.py dispatch --lab lab2 --task tasks/example.md
python scripts/lab_codex.py status --run ABSOLUTE_RUN_DIRECTORY
python scripts/lab_codex.py collect --run ABSOLUTE_RUN_DIRECTORY
python scripts/lab_codex.py cancel --run ABSOLUTE_RUN_DIRECTORY
python scripts/lab_codex.py batch --plan samples/lab-codex/two-lab.json
```

The batch plan contains `schemaVersion: 1` and `jobs`, each with `lab`, `task`,
`inputs` and `timeoutSeconds`. Paths are repository-relative. One active batch
job per lab keeps the two VMs useful without competing local jobs.

## Small execution contract

Configuration has `schemaVersion`, `vmrun` and `labs`; each named lab has `vmx`,
`vncPort`, `cliPath`, and `guestRoot`. There are no connection tokens in this
configuration. Host receipts pin config bytes, job/request and input hashes,
source Git revision/dirty state, worker hash and the current exact VM epoch.
Status/collection must reject a changed VM instead of presenting an older
report as current guest execution.

Guest request fields are `schemaVersion`, `jobId`, `lab`, `cliPath` and
`timeoutSeconds` (5 through 1800). The guest job directory contains
`request.json`, `task.md`, `report.schema.json`, `workspace/`, and the verified
worker. The worker reads the task through stdin and uses read-only,
non-interactive, ephemeral Codex execution with its existing authentication.
No model setting or global configuration is changed.

`state.json` contains `schemaVersion`, `jobId`, `lab`, `requestSha256`,
`workerSha256`, `status`, `workerPid`, `workerStartUtcTicks`, `cliPid`,
`cliStartUtcTicks`, `cliSha256`, `cliVersion`, `cliExitCode`, `errorCode`,
`startedAtUtc`, `updatedAtUtc`, `completedAtUtc` and `report`. Status is one of
`starting`, `running`, `succeeded`, `failed`, `timed-out`, `cancelled`. Nullable
values are permitted before their observation. The report reference is null or
`{path: "report.json", byteLength, sha256}`. Host collection checks bytes and
the report schema; CLI exit zero alone is insufficient. `cancel.request`
contains only `jobId` and `requestSha256`.

Results are evidence from a guest worker, not authorization to run reported
commands. Raw authentication, CLI event streams and stderr are not copied back.
Cancellation targets only the worker-owned Codex process tree. One guest job
never terminates RIFT, a control agent or a different Codex installation.

## Acceptance

- One command successfully completes a real task in each guest and retrieves
  a schema-valid report with distinct lab/job/VM identities.
- A batch completes both complementary tasks and keeps the main repository
  authoritative; supplied inputs are byte-identical to their recorded snapshot.
- Status and collection are repeatable without rerunning a completed task.
- Meaningful tests cover changed VM/config, missing/invalid/mismatched reports,
  nonzero CLI exit, timeout, cancellation, process cleanup and cross-lab paths.
- Both native control hosts remain ready/disarmed after guest jobs.
- The full repository gate passes after integration; commits preserve the plan,
  working implementation and final live verification separately.

Official CLI behavior: [OpenAI non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
