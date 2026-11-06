# Guest launcher and transfer benchmark — 2026-10-25

## Result

The managed guest agent launcher is deployed. A deliberately wrong executable
hash was rejected without changing the running agent. A staged release update
then stopped the old agent cleanly and authenticated a new process, while host
V23 and RIFT remained running. A repeat completed through the CLI in about
15 seconds. These were same-binary replacement rehearsals, not game patch tests.

Managed root: `C:\RIFT_TRANSFER\RiftReader2Control\managed`.
Active release: `agent-54e134baa692-rehearsal`.
Executable SHA-256:
`54E134BAA69255CBA0B03E9CDE1CFA7C158A199675DE3E52DCA949B51007670F`.
Launcher SHA-256:
`981E31C061CAFCEE1546DAC4FE6E68A49BF7C2010E0D5D810B2172688A013746`.
The cached guest Windows login was reused without another prompt.

The initial launcher exposed a Windows PowerShell 5 issue: passing `$null` as
the backup filename to `File.Replace` became an invalid empty path. Using a
unique backup filename fixed atomic state updates; a regression test executes
both writes under Windows PowerShell. The initial agent still shut down cleanly.
The first successful replacement completed after the original 65-second client
deadline. Its result and clean-stop receipt were recovered rather than treating
the timeout as failure. The bounded client wait is now 95 seconds, and the
repeat returned success normally. The cause of that first delay is unconfirmed.

## File transfers

Three repetitions per size and direction, synthetic random payloads, all six
round trips matched SHA-256 (12 individual transfers). No build/test workload
ran concurrently with these timings.

| Size | Host to guest median | Guest to host median |
|---|---:|---:|
| 512 KiB | 1.688 s / 0.296 MiB/s | 1.671 s / 0.299 MiB/s |
| 8 MiB | 5.679 s / 1.409 MiB/s | 5.719 s / 1.399 MiB/s |

These are real `vmrun` command wall times, including identity and process
overhead, not pure network throughput. The result supports keeping small
related files bundled instead of issuing many separate copies.

The temporary HTTP server bound to the existing host VMnet8 address
`192.168.56.1:8765`, but the guest download failed with “Unable to connect to the
remote server.” No HTTP performance claim is supported. The server was closed;
NAT, adapters, firewall and shared-folder settings were not changed. No network
configuration change is needed to retain the verified VMware Tools route.

## Evidence and scope

- Launcher/migration: `artifacts/guest-launcher-20261025-01/`.
- Rejected update: `reject-bad-hash/result.json`; agent PID/run stayed unchanged.
- First completed update: `graceful-update/result.json`, `shutdown-complete.json`,
  `ready.json`; the host-side timeout is retained separately.
- CLI repeat: `graceful-update-repeat/` with before/after identities and lease receipt.
- HTTP failure: `artifacts/guest-transfer-benchmark-20261025-02/524288-1-error.json`.
- Completed measurements: `artifacts/guest-transfer-benchmark-20261025-03/results.json`.
- Shareable evidence: `artifacts/exports/guest-launcher-and-transfers-20261025-01/`.

RIFT PID `1224`, start ticks `639285359295548343`, and executable SHA
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`
stayed unchanged. The VM also retained its prior process/start identity.
Startup registration does not prove a fresh Windows logon or VM reboot;
neither was performed. The initial launcher readiness window expects the host
within 30 seconds. Agent failure recovery and rollback are explicit/manual.
Patch recovery, health-change testing and direct ChatGPT Computer Use remain
deferred. No spell or movement test was part of this work.

See [operating instructions](../reference/guest-agent-launcher.md).

## Checks

The full repository gate passed: 487 .NET tests; 819 Python tests collected
(817 passed, two skipped); formatting, Lua/C# contracts, deterministic examples
and 606 relative links. Evidence:
`artifacts/validation/20261026T002832Z-e7e0f433` and
`artifacts/guest-launcher-20261025-01/validation-final.log`.
Focused coverage includes shutdown acknowledgement after cleanup, uncertain
input release, stale requests, changed executable hashes, PowerShell atomic
replacement, and one-use HTTP routes with upload-byte validation.
Final live state was disarmed/idle with no held input and a clear queue.
