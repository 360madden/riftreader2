# Reusable XYZ Courier and guarded evidence transfer

The Courier coordinates an explicitly operated restart trial. It installs a
pinned reader into a new guest directory, captures before/absent/after evidence,
opens the position panel, packages originals, and offers separate Declare and
Upload buttons. It never exits, relaunches, moves or otherwise controls RIFT.
An operator performs normal game exit and relaunch.

This version replaces per-trial constants with a strict run configuration.
The [earlier corrected trial](../validation/position-panel-corrected-restart-2026-10-25.md)
validated the original Courier; a new build's host checks do not establish its
guest/UI behavior. Direct ChatGPT Computer Use inside RIFT remains deferred.

## Prepare and preflight locally

First use [payload preparation](xyz-workflow-tools.md) to retain an explicitly
pinned reader and profile. Then build a new Courier bundle:

```powershell
python scripts/prepare_xyz_courier.py --bundle ABSOLUTE_PREPARED_BUNDLE --run-id xyz-trial-new --output NEW_ABSOLUTE_COURIER_DIRECTORY
```

The command uses the installed Windows .NET Framework compiler and repository
Courier source. It does not install a compiler, launch the reader, touch VMware
or start a network service. Keep its source and output manifests with the trial.
Never overwrite a previous run's directory or silently replace its binary pins.

The generated `courier-config.txt` uses a bounded ASCII record:

```text
RR2XYZCOURIER1|run-id|reader-sha256|reader-bytes|profile-sha256|profile-bytes|game-sha256
```

Hashes are uppercase SHA-256 values. The run ID determines the guest destination
`C:\RIFT_TRANSFER\XYZ\<run-id>`; it cannot supply an arbitrary destination path,
command or URL. Claim/upload endpoints remain fixed to the existing lab host
and port. The configuration belongs beside the generated Courier and payloads.

The supported raw-pointer recipe is explicitly limited to root RVA `0x32E0200`
and float32 offsets `0x320/0x324/0x328`. A different profile is rejected instead
of being paired with the old independent pointer request. This is reuse of the
known recipe, not patch recovery.

Adjacent configuration hashes establish content consistency, not software
authenticity. Before guest use, independently pin the reviewed bundle manifest
and verify the Courier, configuration, reader and profile against that retained
pin. An arbitrary executable does not become trusted merely by listing its hash
in an editable configuration. Preflight never executes that input executable.

```powershell
.\ValidationCourier.exe --preflight
```

Preflight validates the configuration and source payloads without constructing
the window, installing files, executing the reader or contacting a network
endpoint. A successful preflight is readiness of the local bundle only.
Installation, actual buttons and restart behavior need separate guest evidence.

## Prepare the host transfer plan

The host wrapper accepts an explicit `xyz-transfer-plan/1` JSON object. Its exact
top-level fields are:

| Field | Meaning |
|---|---|
| `schemaVersion` | Integer `1`. |
| `contractVersion` | `xyz-transfer-plan/1`. |
| `runId` | The bounded lower-case run identifier. |
| `target` | Exact guest `processId`, `processStartUtcTicks`, `executableSha256` for the declaration. |
| `readerSha256` | Reader hash expected in the guest's declaration. |
| `maintenancePlan` | Absolute `path` and `sha256` of the reviewed successor host plan. |
| `priorProcess` | Absolute `path` and `sha256` of the previous host's process receipt. |
| `priorExit` | Absolute `path` and `sha256` of its normal exit receipt. |

Paths and outputs stay under repository `artifacts/`. The plan is local control
data, not an authentication token. Use fresh, independently checked target
identity and the reviewed maintenance transition; do not reuse historical PIDs
as current state. Nothing in plan preparation stops a controller or changes
queue ownership. It neither creates STOP markers nor launches a successor.

```powershell
python scripts/run_xyz_transfer_service.py --plan ABSOLUTE_PLAN --phase claim
python scripts/run_xyz_transfer_service.py --plan ABSOLUTE_PLAN --phase upload
```

Without `--serve`, these are **static previews**. They validate their inputs and
phase prerequisites, but do not query the live VM, inspect live processes or
open a listener. A preview does not establish current maintenance readiness.
Upload preview also requires a completed claim phase and a matching declaration.

## Explicit, bounded serving

Serving uses the existing independent Windows `pythonw.exe` lifecycle: signed-in
session 2, outside a job. Add `--serve` only for the reviewed live phase; the
wrapper does not launch itself, create a scheduled task, or persist a service.
The timeout is bounded to 30–600 seconds.

Before serving, the wrapper checks the normal previous-controller exit, exact
VM identity, pinned host configuration/runtime, unstarted successor, and blocked
unheld canonical queue. It holds the established VM-control mutex throughout
the listener. Consequently, automation cannot concurrently claim that console;
an operator may use the guest's Declare/Upload buttons manually during this
phase. An existing controller owner causes a refusal, not a forced takeover.

The fixed host address is `192.168.56.1:8765`; the only accepted guest address is
`192.168.56.128`. The old pointer-named routes are transport identifiers only.
They do not classify a received XYZ archive as pointer evidence. The unchanged
receivers enforce one-use declarations and exact-content uploads, with a 16 MiB
ceiling. Upload requires the claim service to have ended successfully and its
process/receipt identity to match. Separate process, result and exit evidence
preserves the phase outcome; existing phase outputs cannot be reused.

Exit **0** means the requested phase received its expected result; **3** means
its bounded lifetime expired without that result; **2** means refused or failed.
Successful completion also requires the receiver to close, the VM/service
identities to remain consistent, and the control mutex to release. Failed final
checks cannot produce a successful claim receipt that unlocks upload. The
listener applies an absolute deadline to accepted sockets, including stalled
headers, in addition to the reused handlers' own bounds.

A guest address and matching hash are not cryptographic sender authentication.
After receipt, use [archive verification and session export](xyz-workflow-tools.md)
and retain the original transfer receipts. The service does not qualify fields,
prove a complete game restart, or verify Lua agreement.

## What remains separate

Media creation/mounting, actual guest deployment, the authorized maintenance
handover and successor restoration retain their existing reviewed procedures.
Do not start the transfer service while another controller owns the VM console.
Patch recovery, direct in-game Computer Use, VM/host restart claims and broader
gameplay automation are not resumed by these tools.
