# Native Codex two-lab teamwork — 2026-10-29

Joey authorized a small native remote-chat teamwork test. The main-PC Codex
sent instructions to existing Codex chats on both remote hosts, without the
VMware-dispatched job workflow. Each ran a read-only local command, reported
its Windows computer name, and returned a calculation for player (10,20) and
destination (13,24). Both gave dx=3, dz=4 and planar distance=5. The main
coordinator independently checked the arithmetic.

| Lab | Remote environment | Initial turn | Local identity |
| --- | --- | --- | --- |
| Lab-1 | `env_e_6ae359123e7c83218b3d11753a7278b4` | `01a188ab-3972-75c2-8f03-2b65ec2d65a4` | `RIFT-LAB-1` |
| Lab-2 | `env_e_6ae3592b79408321aa1a8cb7dfc2d81a` | `01a188ab-523e-78f0-a35f-fa75ae08070c` | `RIFT-LAB-2` |

The initial turns ran concurrently (17:18:05–17:18:18 UTC for Lab-1 and
17:18:11–17:18:23 UTC for Lab-2). Their command outputs confirmed each
machine name; Lab-2 also computed the values in PowerShell. Lab-1 computed
the arithmetic in its response. The main PC then passed Lab-1's answer to
Lab-2, which confirmed agreement and gave a valid example of stale position
causing a false arrival. This was a coordinator-relayed handoff, not direct
lab-to-lab messaging.

Lab-1's process check found no process name containing `rift`. Lab-2's first
check used the exact name `rift`, which could miss `rift_x64`; a follow-up
checked names containing `rift` and found none. These checks describe only the
sampled moments. No RIFT process was started, no game input was issued, and
the tasks requested no file or settings changes.

This verifies sending, executing, monitoring, reading, and relaying simple
tasks through existing native Codex chats. It does not verify automatic file
transfer, a shared guest repository, multi-lab game control, unattended
recovery, or sustained discovery throughput. The main-PC checkout remains the
authoritative project; review guest findings before integrating them.
