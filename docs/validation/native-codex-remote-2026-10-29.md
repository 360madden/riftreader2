# Native Codex device connections - 2026-10-29

Status: **both native device connections paired and remote reads verified.**

Joey authorized native device pairing for Lab-1 and Lab-2, autonomous setup and
verification, and SSH consideration only if the native route does not work.
No SSH was installed or used. No RIFT input or VM/game restart was performed.

## Main-PC pairing and remote-read acceptance

Joey clarified that the main PC had reached the Add PC code-entry prompt;
the failing `Allow devices to control this computer?` dialog was inside a VM.
The host/controller instructions had not identified that location correctly.
Use the already-running native CLI host to generate the code rather than
repeating the VM desktop app's failed Allow operation.

Exactly one `codex remote-control pair --json` response was generated per lab.
Each code was privately passed to the installed main app's shipped pairing
URI; no code was printed or placed in command arguments. Main-PC registration
and successful full remote-thread reconciliation completed at:

| Lab | Pairing URI invocation (EDT) | Successful reconciliation (EDT) | Remote threads |
| --- | --- | --- | ---: |
| Lab-1 | 11:02:19 | 11:02:25.822 | 2 |
| Lab-2 | 11:11:58 | 11:12:03.423 | 4 |

The main catalog contains two distinct `remote-control` host rows for the
environment IDs below. Both completed their initial full synchronization,
persisted auto-connect and had no failed scan checkpoint. Immediate
host-not-found errors were transient registration races before those successful
reconciliations; no later matching error was retained.

At 11:14 EDT, main-app `list_threads` returned records from both remote hosts
with no unavailable hosts. Separate `read_thread` calls explicitly addressed
one observed thread on each exact host; both returned valid thread/page/turn
responses without tool errors. This verifies native main-PC-to-guest remote
reads using existing chats. No new chat, model job, guest shell command or
remote write was part of this acceptance.

Evidence: [combined pairing receipt](../../artifacts/native-codex-pairing-20261029/capabilities/two-lab-native-pairing-receipt.md),
[native app read verification](../../artifacts/native-codex-pairing-20261029/native-app-read-verification.json),
and [private-code cleanup](../../artifacts/native-codex-pairing-20261029/private-code-cleanup.json).
Both protected private pairing-response files were deleted after registration.
Tokens, authentication files and private keys were not copied between machines.

## Accepted guest-host checkpoint

At 10:47 EDT, both installed native hosts answered the idempotent
`codex remote-control start --json` with exit 0, `connected`, and daemon
`alreadyRunning`. A separate daemon-version query returned `running`.

| Lab | Native environment ID | App-server PID at checkpoint |
| --- | --- | --- |
| Lab-1 | `env_e_6ae359123e7c83218b3d11753a7278b4` | 11904 |
| Lab-2 | `env_e_6ae3592b79408321aa1a8cb7dfc2d81a` | 10804 |

Both ran in signed-in Session 1 with a non-administrator token. Both use
CLI `0.165.0-alpha.1.2` and app-server `0.165.0`. The executable is
`C:\Users\mrkoo\AppData\Local\OpenAI\Codex\bin\0ab0e7a8f3779036\codex.exe`,
SHA-256 `0C09E45BC76433756EB2D492F6DB0CE6F269967E6618F4A6AE73E2FA239694B8`.
PIDs remain session evidence, not durable locators. Both cloned Windows names
are `DESKTOP-8632QPL`; route by the distinct environment IDs until native
display labels can be set after pairing.

GuestOps initially ran elevated, which the native daemon refused. Limited
interactive scheduled tasks removed elevation but their process-lifetime job
still prevented the daemon's background process from escaping. Launch through
the existing signed-in Explorer shell resolved both issues. Native managed
daemons remain running; exact temporary scripts, shortcuts and owned tasks
were cleaned. This does not establish recovery after a future VM/PC reboot.

Evidence: [refresh summary](../../artifacts/native-codex-pairing-20261029/preflight/explorer-link-refresh-summary.json)
and [native process identities](../../artifacts/native-codex-pairing-20261029/preflight/native-process-identity-summary.json).
An attempted read-only app-server proxy query timed out. Client-list and
installation-ID results were not recovered; a custom controller was not built.

## Keep host and controller setup distinct

- Inside each VM, **Control this PC** uses the host dialog:
  `Allow devices to control this computer?`, followed by `Allow`.
- On the main PC, **Control other devices** uses controller setup:
  `Control other devices from this PC`, followed by `Authorize on chatgpt.com`.

The uploaded `Couldn't enable remote control. Try again` screenshot shows the
host dialog; Joey subsequently confirmed it was inside a VM. Its generic
message does not establish the underlying cause. Read-only inspection confirms
the two different handlers; no matching current native error was recovered.
Do not assign the message to MFA, network, or rollout without the failing
request. The working CLI pairing route removed this dialog as a prerequisite;
it does not prove that the desktop Allow failure itself was repaired.

See the [sanitized UI-flow investigation](../../artifacts/native-codex-pairing-20261029/capabilities/main-set-up-failure-20261029.md)
and [native-client capability report](../../artifacts/native-codex-pairing-20261029/capabilities/main-windows-native-client.md).

## Usage and remaining boundaries

On the main PC, open **Settings > Connections > Control other devices** to use
the paired hosts; use its built-in Refresh if the device list is stale. Both
initial display names may still be the cloned Windows name. The distinct native
environment IDs, not that label, establish the lab mapping.

Starting and steering new remote jobs, guest-side command execution, UI control,
and PC/VM-reboot recovery have not been verified by these read-only checks.
The separate optional verification-chat request has not been answered; no
user-facing chats were created. Existing RIFT controls are a separate system:
a final status query reached both host APIs but reported no visible top-level
game window, so current game-input readiness was not accepted by this trial.

Official reference: [Remote connections](https://learn.chatgpt.com/docs/remote-connections).
