# Lab-2 native Codex startup - 2026-10-29

Status: **automatic user-logon start verified after a Windows reboot.**

Lab-2 has one scheduled task, `RiftReader2-CodexRemote-Lab2`, triggered at
`RIFT-LAB-2\mrkoo` interactive logon after a 20-second delay. It runs with a
limited token and hands an existing shortcut to the signed-in Explorer shell.
Explorer starts the native Codex worker outside the task's process-lifetime
job. The earlier unsuccessful Startup-folder entry was removed.

The installed guest files live in
`C:\Users\mrkoo\AppData\Local\RiftLabTools`; tracked exact source copies are
[`Dispatch-Lab2CodexRemote.ps1`](../../scripts/guest-lab2-codex/Dispatch-Lab2CodexRemote.ps1)
and [`Start-Lab2CodexRemoteAtLogon.ps1`](../../scripts/guest-lab2-codex/Start-Lab2CodexRemoteAtLogon.ps1).
Their respective SHA-256 values are
`6B3E7B4C88663F829E316116965BE695DB6C785A87315D8023F3502FF654024A` and
`013868E215D2E5EF9F5CB8802D009AE580E71FEA10E1234F2613CDA3E3058CA5`.

After the final boot at `2026-10-29T16:01:04.500Z`, the task fired at
12:01:40 EDT and ended Ready with result 0. Fresh automatic dispatcher and
worker receipts showed Session 1, non-admin, native exit 0, `connected`,
`serverName=RIFT-LAB-2`, and the existing environment
`env_e_6ae3592b79408321aa1a8cb7dfc2d81a`. No manual Codex start occurred
after that boot. A main-PC exact-host thread read succeeded afterward.
[Sanitized verification evidence](../../artifacts/native-codex-pairing-20261029/preflight/lab2-native-autostart-verification.json).

This starts after the user logs in and Explorer is available; it is not a
pre-login service. The worker's alternate handling for an already-online server
was not exercised by this successful reboot. RIFT and its guest control agent
were absent after the test; this does not verify game-control readiness. No
re-pairing, game input or login was performed.
