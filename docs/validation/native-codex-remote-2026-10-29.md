# Native Codex device connections - 2026-10-29

Status: **both guest hosts connected; main-PC pairing and execution unverified.**

Joey authorized native device pairing for Lab-1 and Lab-2, autonomous setup and
verification, and SSH consideration only if the native route does not work.
No SSH was installed or used. No RIFT input or VM/game restart was performed.

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
host dialog. Its generic message does not establish the underlying failure or
which machine displayed it. Read-only inspection of the shipped app confirms
the two different handlers; no matching current native error was found in the
retained logs. Do not assign the message to MFA, network, or rollout without
the actual failing request.

See the [sanitized UI-flow investigation](../../artifacts/native-codex-pairing-20261029/capabilities/main-set-up-failure-20261029.md)
and [native-client capability report](../../artifacts/native-codex-pairing-20261029/capabilities/main-windows-native-client.md).

## Outstanding acceptance

Complete main-PC controller authorization, then generate and claim fresh
short-lived guest pairing codes sequentially. No codes have been generated.
Require each matching native host connection and client association, then a
small execution test in each actual guest. Creating user-facing verification
chats awaits the separately requested explicit authorization. Do not describe
guest relay enrollment as completed main-PC pairing or execution acceptance.

Official reference: [Remote connections](https://learn.chatgpt.com/docs/remote-connections).
