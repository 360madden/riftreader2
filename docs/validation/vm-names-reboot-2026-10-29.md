# VM Windows names and reboot check - 2026-10-29

Joey requested distinct Windows names matching the VMware labs, then requested
another orderly reboot of both guests to investigate a native Codex error.

| Lab | Verified Windows name | Final guest boot (UTC) | Native Codex environment |
| --- | --- | --- | --- |
| Lab-1 | `RIFT-LAB-1` | `2026-10-29T15:44:08.500Z` | `env_e_6ae359123e7c83218b3d11753a7278b4` |
| Lab-2 | `RIFT-LAB-2` | `2026-10-29T15:45:07.500Z` | `env_e_6ae3592b79408321aa1a8cb7dfc2d81a` |

GuestOps confirmed the active and configured names and new boot times. Cached
guest credentials continued to work. The main app returned a successful
existing-thread read for each exact native host after the final reboot; no
new pairing was needed. Lab-1's app and Codex process auto-started. Lab-2's
native host required one non-administrator Explorer-session start after the
final reboot; it then reported `connected`, `serverName=RIFT-LAB-2` and the
same environment ID. The previous HTTP 409 `Remote app server already online`
error did not recur in that successful start. Automatic Lab-2 native startup
is not established.

Both main-PC control host and guest configuration templates were updated for
their new exact names. The original control hosts could not verify shutdown
cleanup after the guest restarts. Following checks that the relevant game and
guest agent were absent, their two exact host processes were stopped and new
hosts were started with `--reconcile-existing`, using separate new plans and
verified non-job Session 1 process identities. Forced handoff evidence:
[`lab1`](../../artifacts/control-fleet-live/lab1-host-rename-20261029/forced-handoff.json)
and [`lab2`](../../artifacts/control-fleet-live/lab2-host-rename-20261029/forced-handoff.json).

After the final reboots, neither RIFT process nor guest control agent was
running. Both main-PC successor hosts remained running, but guest control
reconnection, target qualification, cleanup and game-input readiness after the
final reboot remain unverified. Neither game was launched or logged in; no
game input was attempted. Preserve the blocked queue until reconciliation is
actually verified with a fresh game and agent identity.
