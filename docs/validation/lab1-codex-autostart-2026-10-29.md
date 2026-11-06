# Lab-1 native Codex startup - 2026-10-29

Status: **automatic user-logon start verified without the observed duplicate.**

Lab-1 uses the same scheduled-task and signed-in Explorer handoff architecture
as Lab-2. Its `RiftReader2-CodexRemote-Lab1` task runs for the interactive
`RIFT-LAB-1\mrkoo` user with a limited token and a five-second logon delay;
the worker waits another five seconds. Lab-2 uses 20- and 15-second delays.
The separate identities, task names and receipts prevent cross-lab confusion.

The installed guest files live in
`C:\Users\mrkoo\AppData\Local\RiftLabTools`; exact source copies are
[`Dispatch-Lab1CodexRemote.ps1`](../../scripts/guest-lab1-codex/Dispatch-Lab1CodexRemote.ps1)
and [`Start-Lab1CodexRemoteAtLogon.ps1`](../../scripts/guest-lab1-codex/Start-Lab1CodexRemoteAtLogon.ps1).
Their SHA-256 values are
`C1743B5E20EC391B0D6055721C239B95E0A1D946B5D93C14A975667D176831FA` and
`48FEAC74D4C20FA74AA8D62B360A8AA7B20EB2E1AE7446D0B6E727DE77171620`.

Following the final boot at `2026-10-29T16:21:09.500Z`, the task ran automatically
at 12:21:29 EDT, ended Ready with result 0, and produced fresh dispatcher and
non-admin Session 1 worker receipts. The worker reported exit 0, connected,
`RIFT-LAB-1`, and the original environment
`env_e_6ae359123e7c83218b3d11753a7278b4`. No manual native start occurred
after reboot. Main-PC exact-host reads succeeded for both Lab-1 and Lab-2.
[Sanitized acceptance evidence](../../artifacts/native-codex-pairing-20261029/preflight/lab1-native-autostart-verification.json).

The Lab-1 worker does not stop an existing server on a 409 response; it records
the conflict for independent verification. That alternate branch was not
exercised in the successful reboot. After an earlier checkpoint, the packaged
ChatGPT app started a separate app-server and produced five 409 warnings. Its
MSIX `windows.startupTask` taskId `App` was identified and its per-user state
changed from 2 (enabled) to 1 (disabled by user); the installed app remains
available for manual launch. Following the final reboot, the native daemon was
connected and, at a 105-second settled check, the packaged app remained absent
and no 409 warnings or errors were observed. Manual later app launch and its
possible interaction with the daemon were not tested. Both labs require user
logon and Explorer; neither is a pre-login
service. RIFT and the guest control agent were absent after the test, so game
control readiness is not established.
