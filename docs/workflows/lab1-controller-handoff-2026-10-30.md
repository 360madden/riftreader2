# RiftReader2 — Pre-reboot Lab-1 Controller Recovery Handoff

**Prepared:** 2026-10-30 America/New_York
**Owner:** Joey / main-PC native Codex recovery coordinator
**Scope:** Restart continuity after Joey manually reboots Windows 11 (both VMs will stop).
**Full incident report:** [Lab-1 controller recovery incident](../validation/lab1-controller-recovery-incident-2026-10-30.md)
**Authoritative movement status:** [docs/status.md](../status.md)

## Immediate state / exact disposition

- Repo C:\work\riftreader2, branch codex/modular-foundation; pre-report HEAD d56a328715ff3d2c1c86a80b264bdd79d3b95a9b; clean at audit. **Check newer HEAD for report/handoff commit.**
- No Git remote configured. Expected pre-reboot backup path: C:\work\riftreader2-pre-reboot-20261030.bundle. **Do not assume it exists; verify with git bundle verify.** It covers Git objects/refs only, not ignored artifacts/VM disks.
- Main-PC controller **not operational**. API 127.0.0.1:49811/api/status returned WinError10061. Previous Lab-1 host generation 11 PID63004 exited Oct30 04:52:45Z; reason unknown.
- Joey approved rollback of Lab-1 to snapshot baseline-codex-connected-lab1-20261029. VMware revert exit0 and resume exit0, complete. No need to repeat.
- Last postrollback VM PID6824/VNC5905/logEpoch 2026-10-30T10:35:46.154Z. **ALL of these process identities become stale on next boot.**
- Guest Codex CLI 0.165.0 ready/login available; 206 guest processes; RIFT absent after restore.
- Lab-2 was not operated during Lab-1 snapshot recovery. Its prior movement evidence includes two accepted fixed-goal planar arrivals (0.057 and 0.010 error), now recorded in docs/status.md.
- Both VMs were RUNNING during pre-reboot read-only audit; Lab-2 guest had RIFT running (172 processes, VMX PID56076 at 10:52:40Z). A guest shutdown will end that live RIFT session; memory snapshot/suspend is optional but not needed for committed movement evidence. Joey will handle manual PC reboot and VM shutdown. No automatic VM shutdown action from this handoff.
- No new Lab-1 controller recovery files were materialized. Intended artifacts/control-fleet-live/lab1-recovery-20261030-01/ directory existed but was empty.
- ChatGPT Workbridge file writes stalled 160–232s; no journal. Approval/card cause remains unproven. Native main-PC Codex is preferred for next host work.

## Do first after reboot — strictly ordered

1. Inspect AGENTS.md, this handoff, the linked full incident report and newest docs/status.md. Check git status, branch and latest commit.
2. Verify standalone Git bundle with git bundle verify C:\work\riftreader2-pre-reboot-20261030.bundle if present. Git remote is absent. Do not overwrite the bundle.
3. Start/read both VM labs only under Joey's requested workflow, with priority on Lab-1. Reacquire exact VMX PID, startTicks/logEpoch, VNC listener and guest identity; no cached pre-reboot identities.
4. Lab-1 diagnostics (read only):
   - python scripts/lab_codex.py doctor --lab lab1
   - python scripts/lab_guest_probe.py --lab lab1
   - python scripts/control_fleet.py --manifest artifacts/control-fleet-live/fleet.json
   - python scripts/control_client.py --config artifacts/control-fleet-live/lab1/host.json status
5. Find current host Python/Pythonw processes, ports 49810/49811, queue lease, Windows session 1 and console mutex. Do not assume a process is dead from an HTTP error alone.
6. If no valid controller host exists, build a NEW identity-pinned plan with current runtime/config SHA256 and unique absent stop/output paths. Historical plans pin VM PID49392 and stale hashes, so cannot be replayed.
7. Use artifacts/control_fleet_host_entry_20261029.py and scripts/control_host.py for detached Session1 pythonw.exe, inJob=false, one controller. Reuse canonical SQLite queue artifacts/native-coordination-live/queue.sqlite3 with vm:rift-lab-1 and --reconcile-existing. Never clear or replace queue DB.
8. Require host API connected/ready/disarmed/idle and no held input. Bring up authorized exact RIFT build and guest agent after revalidating current game/build/session identity. Then verify live reader/position freshness, independent release and Lab-2 isolation.
9. Resume only bounded reviewed movement trials when conditions are safe. Current data do not establish general navigation or 3-D arrival.
10. Save evidence, focused tests, Git commits and a new handoff. No code refactor without a proven code defect.

## Recovery acceptance checklist

- [ ] Fresh Lab-1 VMX identity and VNC5905 owner verified.
- [ ] Main-PC controller process exact identity, Session1 and inJob=false verified.
- [ ] 49810/49811 listeners owned by that host; authenticated status.
- [ ] Shared queue reconciled; vm:rift-lab-1 exclusive, no conflicting owner.
- [ ] Guest RIFT/agent current build/process identity verified.
- [ ] Controller connected, ready, disarmed, idle, no held keys.
- [ ] One bounded released input with independent fresh post-action evidence if tested.
- [ ] Lab-2 isolation verified.
- [ ] Reported findings committed, no credential leakage.

## Important pitfalls

- The October 29 memory snapshot predates the last working controller checkpoint and cannot restore the host-PC controller.
- Old launcher config paths/stop markers/outputs are stale. Do NOT disable identity/hashing guards to make them launch.
- Prior host PID63004 exit cause unknown (stderr empty); diagnose if reproduced, don't invent a cause.
- ChatGPT Workbridge approval interception suspected but not confirmed; do not bypass any active approval.
- There is no configured Git remote; a same-disk Git bundle is not a remote disaster-recovery backup.
- Private host.json, guest.json and stdout.private.log must remain private.
- Never treat guest Codex doctor success as game/controller success.
- The previous movement-resume prompt predates Oct30 Lab-2 accepted fixed-goal results; use current docs/status.md.
