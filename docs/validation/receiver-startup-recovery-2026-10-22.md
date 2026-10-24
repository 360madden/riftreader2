# Receiver startup recovery — tested source, guest deployment incomplete

Date: October 22, 2026. **PARTIAL / NOT INSTALLED IN THE GUEST.** This is not a completed reboot-recovery milestone. Do not describe a future VM restart as autonomously recoverable on the strength of this work.

## Goal and delivered source

Joey identified that he, not the automation, restored the receiver after restarting guest Windows. The objective is to remove that manual receiver command without extending gameplay automation.

`scripts/guest_receiver_startup.ps1` implements explicit Install, Run, Status and Remove modes. It requires the expected guest machine, current-user SID and interactive session, pins the launcher/receiver/configuration/game files, and installs only a current-user Startup shortcut. Run waits up to twelve hours for one matching game/window, starts the already installed receiver once, and refuses mismatched or ambiguous processes. An existing matching receiver is retained. The launcher never starts RIFT, elevates, logs Windows in, clears uncertain input, arms controls or sends game commands. A successful process launch is explicitly not connection verification.

The shortcut design uses the logged-in user's Startup folder, not a Windows service or host-PC startup change. It is not a pre-login solution or a receiver-crash watchdog. Removal checks the owned shortcut, removes it and disables waiting launchers while retaining evidence and leaving a running receiver alone. The configuration token is not copied into the manifest or telemetry.

Three Python regression cases exercise the real Windows PowerShell 5.1 entrypoint. A disposable PowerShell contract runs 38 checks, including COM shortcut creation in redirected temporary directories, installation/repeat/conflict/removal, hash changes, absent games, session/identity mismatches, duplicate prevention and unchanged files. Process observation/launches are faked in that contract; no guest receiver was executed by those offline tests.

## Verification actually completed

The final isolated full gate passed **364 C# and 444 Python tests**, **108 Lua checks and 22 shared cases**, zero-warning Release, synthetic native smoke, deterministic replay and 323 relative links. Three new Python cases include the 38 PowerShell checks; these counts overlap.

Job: `rr2-receiver-startup-fullgate-20261022-a02`.
Candidate full-gate evidence: `artifacts/receiver-startup-20261022-01/candidate/artifacts/validation/20261022T070000Z-1bb60d4f`.
Main-checkout focused tests: `rr2-receiver-startup-main-tests-20261022-a01`, **3/3 passed**. A new main-checkout full gate is not claimed.

Two failed validations were retained and corrected: Windows PowerShell 5.1 required an explicit null-string value for File.Replace; nested PowerShell inherited an incompatible module search path from PowerShell 7, so the launcher now imports its own inbox modules explicitly. The correction did not change global policy or module settings.

Hash-guarded source promotion changed exactly four files: the new launcher, its PowerShell contract, its Python test module, and the existing validation test list. Native control runtime modules and guest binaries were not modified. Review was performed by the implementing assistant, not an independent reviewer.

## Independent recovery route and deployment outcomes

The exact VM was freshly detected before native status or console access. VMware Tools reported running, and the existing saved encrypted-VM credential made the previously rejected host-side Tools queries work. That credential stayed in memory and short-lived local vmrun arguments; it was not printed or copied into normal reports. Guest process enumeration still requires a separate Windows login. No credentials were guessed, changed or harvested from guest Windows.

A read/write runtime GuestInfo probe succeeded from the host. This proves host-side variable access, not successful execution or acknowledgment inside the guest. Existing shared folders were disabled; their settings were not changed, and no file server, listener, firewall rule or Windows service was added.

Two bounded installation attempts used the existing exact-VM console bootstrap and hash-pinned package. Both stopped before the installer phase because the expected guest acknowledgment was not observed. The first used a direct setup command; the second staged the command and used a shorter launcher. The exact cause remains unproved. A sent keyboard command or a host-side variable readback was not counted as guest execution success.

A separate diagnostic opened Windows Run, captured it, and sent Escape without typing command text. The retained low-resolution image was visually inspected and showed the Run dialog; that confirms this specific shortcut observation, not successful earlier PowerShell execution. A subsequent proposed visible guest diagnostic was blocked by the tool safety check and **did not execute**. It was not retried through an alternate route.

**No guest Startup shortcut installation or receiver-restart acceptance test was reached.** No full guest Windows logoff/reboot test was attempted. The staged payload/metadata and unsuccessful evidence remain for diagnosis; do not blindly rerun the one-use installers or replace an existing partial destination.

## Maintenance restoration and actual current host

Each of the three executed maintenance windows first requested orderly native-host shutdown and observed its exit; no native host was force-killed. The exact VM console mutex was then used for that window, and the same tested coordinated runtime was restored with the original configuration and canonical queue. The VM, RIFT and receiver identities remained unchanged. No native ARM/action command was requested by this workflow. Windows bootstrap keystrokes and supervisor STOP/release verification did occur; do not label this zero input or zero commands.

At **2026-10-22T07:33:00.941243Z / 3:33 a.m. EDT**, the final read-only observation found:

- Native host **6560**, process start ticks **134371277545443317**, coordinator ready and watchdog running.
- VMware **52872** and RIFT **5076**, with the same start identities and receiver `8b9468f7712941f487a232b6cf7c5329`.
- Connected, disarmed, idle, no recovery requirement, and no sampled held inputs.
- **RIFT not foreground**. Do not authorize movement from this observation or claim it was foreground.
- Canonical queue free, no queued/active/cleanup requests, and the previous succeeded capture/history retained.

Current host receipt: `artifacts/receiver-startup-20261022-01/evidence-a03/restored-host-process.json`.
Current single-use host wrapper: `artifacts/receiver-startup-20261022-01/run_restored_host_a03.py`.
Current absent shutdown marker: `artifacts/receiver-startup-20261022-01/STOP-NATIVE-HOST-A03`.
Canonical queue, unchanged: `artifacts/native-coordination-live/queue.sqlite3`, resource `vm:rift-lab-1`.
Original configuration, unchanged: `artifacts/native-usability-20261020/host.json`.

Older host PID 54952 and older shutdown markers are historical, not current operating instructions. Detect the actual process/VM on resume. Do not create the current shutdown marker as a status query; it requests a verified shutdown.

## Checkpoint and next necessary work

Evidence root: `artifacts/receiver-startup-20261022-01/`.
`evidence/` retains source promotion, tests and first attempt; `evidence-a02/` retains the shorter-command attempt; `evidence-a03/` retains the Run-dialog diagnostic and current restored host. `evidence/final-live-observation.json` distinguishes the observed foreground change from a game restart. The first final verification rejected that change rather than silently claiming a matching foreground state.

The remaining work is to establish a permitted, observable guest setup channel, install the already tested startup helper, exercise the actual shortcut while checking that exactly one receiver reconnects, and separately verify a real guest logon/restart. Do not build another control framework or declare end-to-end recovery complete based on unit counts. No guest deployment is currently certified.

See [current status](../status.md), [native controls](../reference/native-vm-controls.md), and [the original coordinated-host activation](navigation-coordinated-host-2026-10-22.md). Git staging, HEAD, original host configuration, prior work and native runtime source were preserved. No commits, pushes, dependency changes, credentials changes or global settings changes were made.

Model: GPT-6 Astra Pro. Reasoning level:
