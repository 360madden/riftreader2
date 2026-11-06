# Two-lab Codex reboot check

On 2026-10-29 the VMs were restarted orderly, one at a time, to test the
native Codex connection after Windows logon. No Codex server was manually
started and no re-pairing, game launch, game input, or forced app closure was
used.

| Lab | Verified boot (UTC) | Automatic connection (UTC) | Settled observation | Main-app host read |
| --- | --- | --- | --- | --- |
| RIFT-LAB-1 | 16:29:22 | 16:29:49 | 116 seconds after boot; zero warnings/errors or HTTP 409 rows | Passed |
| RIFT-LAB-2 | 16:37:30 | 16:38:08 | 143 seconds after boot; zero warnings/errors or HTTP 409 rows | Passed |

Each scheduled task ran successfully, and each non-administrator worker
connected using its existing distinct environment ID. The remote daemon was
present, the packaged desktop app was absent during the settled observations,
and the main app could read an existing chat through each exact remote host.

Lab-2's first boot at 16:32:36 UTC did connect, but the packaged desktop app
subsequently started another server. Six HTTP 409 rows appeared. Its per-user
`OpenAI.Codex` package startup task `App` was disabled (state 2 to 1), matching
Lab-1's prior adjustment. The installed app remains available for manual
launch. A second orderly Lab-2 reboot produced the passing result above.
Manual desktop launch and longer-term operation were not tested.

The scheduled startup requires the configured Windows user to log on and
Explorer to run. RIFT and the guest game-control agent were absent after the
checks, so these results do not establish game readiness. Sanitized local
evidence is retained in the ignored
`artifacts/native-codex-pairing-20261029/preflight/two-lab-reboot-autostart-verification-20261029.json`;
SHA-256 `d99afe5b7791d23db72ff339f7e25aa4c6e849a0340d755521a1aae685563fa2`.
