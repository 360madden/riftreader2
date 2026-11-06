# Run read-only Codex jobs in the RIFT labs

Use this workflow to send a bounded analysis task and selected repository files
from the main PC to the existing Codex CLI installation in either RIFT lab. The
main-PC checkout remains authoritative: a guest returns a structured report,
not source changes or permission to run suggested commands.

The first version is read-only. It does not interact with RIFT, change addons,
use native memory profiles, or apply patches produced in a guest.

## Configure the labs once

Copy the tracked example to the ignored local configuration:

```powershell
New-Item -ItemType Directory -Force .local | Out-Null
Copy-Item config/lab-codex.example.json .local/lab-codex.json
```

Review the VMX, VNC port, guest Codex CLI path and guest job root for each lab.
Keep machine-specific paths in `.local/lab-codex.json`; do not commit that file.
When a lab VMX moves, its prior guest-login cache may still use the original
VMX path as the Windows Credential Manager lookup key. Set the optional
`legacyGuestVmx` for that lab to its own previous absolute VMX path. On EVERY
login the current path's cache is checked first; only if missing is the explicit
old-path cache checked. Neither lookup copies, discloses, or rewrites credentials.
Never point this setting to another active lab's VMX path.

The labs already have authenticated Codex installations. This workflow neither
signs in nor copies authentication material.

Check one lab before dispatching work:

```powershell
python scripts/lab_codex.py doctor --lab lab1
python scripts/lab_codex.py doctor --lab lab2
```

`doctor` checks the configured VM and guest prerequisites without starting a
job. A successful check is a preflight result, not proof that a later job
completed.

## Run and collect one job

For the shortest path, use `run`. Supply a repository-relative task file and
only the tracked source files the guest needs. The task may be an untracked
ad-hoc prompt; every `--input` must already be Git-tracked:

```powershell
python scripts/lab_codex.py run `
  --lab lab1 `
  --task samples/lab-codex/review-guidance.md `
  --input addon/RiftReader2/RiftAddon.toc `
  --input addon/RiftReader2/guidance.lua `
  --input addon/RiftReader2/main.lua
```

Each run receives a unique directory under `artifacts/lab-codex/`. The host
records the current VM identity, source Git state, task hash and hashes of every
selected input. The guest sees copied snapshots in its fresh job workspace; it
does not work in or modify the main checkout.

All commands use `.local/lab-codex.json` by default. To use another local file,
add `--config C:\absolute\path\to\lab-codex.json` after the command name.
The same option also works before the command name. A task is limited to 256
KiB. A job accepts at most 32 distinct inputs, 2 MiB each and 16 MiB total.
`--timeout-seconds` defaults to 300 and accepts 5 through 1800 seconds.

Use the split commands when you want to dispatch and return later:

```powershell
python scripts/lab_codex.py dispatch `
  --lab lab2 `
  --task samples/lab-codex/check-installed-guidance.md `
  --input addon/RiftReader2/RiftAddon.toc `
  --input addon/RiftReader2/guidance.lua `
  --input addon/RiftReader2/main.lua

python scripts/lab_codex.py status --run C:\absolute\path\to\the\run
python scripts/lab_codex.py collect --run C:\absolute\path\to\the\run
```

`status` reads the current job state. `collect` copies back the completed report
and checks its bytes, hashes, schema, request identity and current VM provenance.
A zero Codex CLI exit code by itself is not acceptance.

To request cancellation of that job only:

```powershell
python scripts/lab_codex.py cancel --run C:\absolute\path\to\the\run
```

Cancellation targets the worker-owned Codex process tree. It does not terminate
RIFT, a native control agent or a different Codex installation.

## Run complementary jobs in both labs

The sample batch sends source review to Lab 1 and installed-file comparison to
Lab 2:

```powershell
python scripts/lab_codex.py batch --plan samples/lab-codex/two-lab.json
```

A batch plan has `schemaVersion: 1` and a `jobs` array. Each job names `lab`,
`task`, `inputs` and `timeoutSeconds`; paths are repository-relative. Keep one
active batch job per lab so jobs do not compete inside a guest.

## Review the result

Treat `report.json` as guest-produced evidence. Review:

- `summary` for the answer to the task;
- each finding's `claim`, `confidence` and cited `evidence`;
- `limitations` for missing inputs or runtime boundaries;
- the host receipt for the lab, job, VM, task and input hashes;
- the collected-state result, not merely CLI exit status.

Confidence values mean `observed`, `inferred` or `unverified`; they do not turn a
claim into repository truth. Confirm important findings on the main PC before
changing code, documentation or a live lab.

Raw authentication, the Codex event stream and stderr are not copied back. The
guest worker is short-lived and uses the existing VMware GuestSession path.
This workflow installs no SSH server, inbound listener, scheduled task or
persistent service.

## Current limits

- Jobs are read-only analysis and diagnostics.
- Guest-generated patches and source synchronization are not implemented.
- Inputs are selected snapshots, not a writable repository mirror.
- A changed VM/config or mismatched report fails collection instead of making a
  stale result look current.
- A returned recommendation is not authorization to execute it.

Future write/patch workflows need a separate contract and review step. Do not
extend this read-only workflow by copying guest edits into the main checkout.

See the [saved implementation plan](../planning/lab-codex-workflows.md),
[`config/lab-codex.example.json`](../../config/lab-codex.example.json), the
[`report.json` schema](../../contracts/lab-codex/report.schema.json), and the
[`samples/lab-codex`](../../samples/lab-codex/) tasks and batch plan.
