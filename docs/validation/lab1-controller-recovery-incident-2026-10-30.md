# RiftReader2 — Lab-1 Controller Recovery Incident Report

**Prepared:** 2026-10-30 (America/New_York)  
**Repository:** C:\work\riftreader2  
**Affected machine:** VMware RIFT-Lab-1  
**Status:** Lab-1 guest restored; main-PC controller NOT recovered  
**Purpose:** Durable evidence and instructions for the next AI recovery coordinator.  
**Evidence class:** Confirmed observations are distinguished below from hypotheses and recommendations.

## 1. Executive summary

The October 30 investigation confirmed that the **VM guest and the controller host are different components**. Lab-1 runs Windows, RIFT and guest Codex inside VMware. Its Python controller host runs separately on Joey's main Windows PC. That host uses VNC and a guest control-agent connection, exposes an authenticated operator API, and coordinates exclusive input access with a shared SQLite queue.

The controller system was verified working on October 29 at 22:02:53 UTC: both lab control hosts were connected, ready, disarmed, idle, and holding no sampled input. Later Lab-1 host generations exited, VMware epochs changed and the main-PC API stopped listening.

Multiple VM interventions did not restore the main-PC host. They included suspend/resume, soft stop/cold start, a guest OS reboot, and a user-authorized memory-inclusive VMware snapshot revert. The final revert and VM resume **succeeded**. Post-revert guest diagnostics passed: 206 processes, guest Codex CLI 0.165.0 ready and logged in. RIFT was absent and HTTP 127.0.0.1:49811/api/status still refused connections (WinError 10061).

Recovery-file writes through ChatGPT Workbridge hung and were interrupted without a verified write or patch journal. The intended recovery directory remained empty. A hidden ChatGPT approval card is one possibility, but **was not observed or proven** for these requests.

**Working diagnosis, not established root cause:** The host service exited and was never relaunched successfully against the fresh VM identity. Existing launch plans are stale. There is no present evidence requiring a rewrite of controller movement logic.

## 2. Architecture and endpoints

| Element | Location or value | Role |
|---|---|---|
| Main Git repository | C:\work\riftreader2 | Authoritative code, tests and evidence |
| Lab-1 VMX | C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx | Windows/RIFT/Codex guest |
| Lab-1 console | VNC 5905 | Guarded display and input access |
| Guest control-agent endpoint | 192.168.56.1:49810 | Host/guest control connection |
| Main-PC operator HTTP API | 127.0.0.1:49811 | Authenticated controller status/control |
| Main-PC controller | Windows Session 1 pythonw.exe | Persistent host process |
| Canonical queue | artifacts/native-coordination-live/queue.sqlite3 | Exclusive ownership |
| Lab-1 queue resource | vm:rift-lab-1 | Lab-specific lease key |

Lab-2 has independent controls (historically 49920/49921 and VNC 5962). No action in the final snapshot rollback targeted Lab-2. Its state must nevertheless be reverified after the host reboot.

## 3. Repository and current evidence

At audit time: branch **codex/modular-foundation**, HEAD **d56a328715ff3d2c1c86a80b264bdd79d3b95a9b**, git status clean, no nonignored untracked files. The latest commit recorded the second independent Lab-2 fixed-goal arrival at 02:14:23 EDT on October 30. There are **no configured Git remotes**, so local Git history has no automatic remote backup. Workbridge version 0.16.4-dev; C:\work is its workspace root.

Latest significant development changes:
- 4e91cac — anchored fast observations;
- 7448e17 — feedback headroom;
- 1c353db — observation anchor before action;
- 3253ece — stalled-VNC cleanup, live checked on Lab-2 only;
- 8d2860b — first accepted Lab-2 fixed-goal arrival;
- d56a328 — second independent accepted Lab-2 fixed-goal arrival.

Read docs/status.md lines 1–97 for the newest movement truth. The older docs/workflows/movement-resume-prompt-2026-10-29.md predates these Lab-2 successes.

## 4. Timeline (UTC, 2026)

| Date and time | Confirmed event |
|---|---|
| Oct 29 15:34:20 | Earlier exact-identity forced handoff of host PID 52064 after graceful release could not be verified; guest absence and input conditions were checked. |
| Oct 29 15:39:49 | Replacement host PID 13760 started; later exited at 19:08:08. |
| Oct 29 17:03:25 | Lab-1 baseline-codex-connected-lab1-20261029 disk+memory snapshot taken. |
| Oct 29 22:02:53 | Last documented two-lab controller cleanup: both connected, ready, disarmed, idle, no held sampled inputs. |
| Oct 30 03:58:00 | Later Lab-1 host generation 11 began as Session 1 pythonw.exe PID 63004; pinned old VMX PID 49392. |
| Oct 30 04:52:45 | Host PID 63004 exited; exited.json records the exit but not its cause; stderr.log is empty. |
| Oct 30 04:57:30 | Lab-1 VM suspend/resume attempt changed VMX PID 49392 to 41284; no game input. |
| Oct 30 05:00:22 | Lab-1 soft-stop/cold-start changed VMX PID 41284 to 40160; no game input. |
| Oct 30 05:12:17 | Third cold-game guest audit reported RIFT absent. |
| Oct 30 later | User-directed guest Windows reboot succeeded; guest Windows, Codex and temporarily RIFT were observed; host operator API still refused connections. The VMX process stayed PID 20120 during that guest-only reboot. |
| Oct 30 later | New identity-pinned controller plan/wrapper was reviewed but Workbridge writes stalled; nothing verified written. |
| Oct 30 10:35:04 | User-authorized VMware snapshot revert completed with vmrun exit 0. |
| Oct 30 10:36:02 | Restored VM successfully started/resumed; new VMX PID 6824. |
| Oct 30 10:37 | Lab-1 guest doctor and process inventory passed; RIFT absent; controller API refused connections. |

The late October 29 working record is **historical**. Later exits/resets and snapshot restore supersede its process identities. The exact reason host generation 11 exited is **unknown**. The later VM resets happened after that recorded exit and cannot be asserted as the original cause.

Key timeline sources:
- docs/status.md lines 78–139
- docs/validation/automated-movement-two-lab-2026-10-29.md
- artifacts/two-lab-movement-20261029/root-final-host-status.json
- artifacts/practical-movement-20261029/host-lab1-11/process.json
- artifacts/practical-movement-20261029/host-lab1-11/exited.json
- artifacts/practical-movement-20261029/lab1-console-reset-02/summary.json
- artifacts/practical-movement-20261029/lab1-cold-console-reset-01/summary.json
- artifacts/practical-movement-20261029/lab1-cold-game-audit-01/result-03.json

## 5. Exact snapshot rollback findings

The single Lab-1 snapshot was named **baseline-codex-connected-lab1-20261029**, VMware UID 1, with memory and virtual disks (RIFT-Lab-Snapshot1.vmsn). The .vmsd timestamp decodes to 2026-10-29T17:03:25.138Z, about five hours **before** last controller-ready evidence; it was never independently proven a known-good main-PC controller checkpoint.

The user explicitly ordered the revert. The exact VMX and snapshot were checked before executing VMware revertToSnapshot. It returned exit 0. Lab-1 was then not listed running, consistent with suspended memory snapshot semantics. A separate VMware start returned exit 0 and the VM list included both labs. Lab-2 was not operated.

Durable Workbridge job IDs:
- rr2-lab1-pre-revert-list-20261030-01 — exact inventory, exit 0;
- rr2-lab1-revert-snapshot-20261030-01 — exact revert, exit 0;
- rr2-lab1-post-revert-powercheck-20261030-01 — Lab-1 not running immediately afterward;
- rr2-lab1-resume-snapshot-20261030-01 — start/resume, exit 0;
- rr2-lab1-resume-side-inventory-20261030-01 — Lab-1 running, two VMs total;
- rr2-lab1-postrollback-doctor-20261030-01 — doctor ready, exit 0;
- rr2-lab1-postrollback-probe-20261030-01 — guest list, exit 0;
- rr2-lab1-postrollback-controller-api-20261030-01 — connection refused.

Post-rollback observed identity (REACQUIRE AFTER EVERY FUTURE RESTART):
- VMX C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx;
- VMX PID 6824, VM log epoch 2026-10-30T10:35:46.154Z;
- VNC 5905;
- 206 guest processes;
- Codex CLI 0.165.0, login available, doctor ready;
- RIFT process absent;
- HTTP API 127.0.0.1:49811/api/status: WinError 10061.

A snapshot of the guest cannot restore a Windows host-side process, the external queue or ChatGPT approval state. The restored guest memory may contain stale network sessions. Do NOT repeat this revert as the next default recovery step.

## 6. Stale host launch plans and hard blockers

Historical:
- artifacts/control-fleet-live/lab1/plan.json
- artifacts/control-fleet-live/lab1/process.json
- artifacts/control-fleet-live/lab1-host-rename-20261029/plan.json
- artifacts/practical-movement-20261029/host-lab1-11/plan.json

Old plans pin VMX PID 49392 and an October 29 VM epoch. Current restored VM PID was 6824 at check time. Original lab1 plan pins controller PID 52064 in process.json, a historical process; host generation 11 PID 63004 was later recorded exited.

Old lab1/plan.json configuration SHA A119A357... differs from current host.json SHA:
0EFBDC1307EA47A4DAE33F96AA3C09774D9F80FD9914F965D73D2F9CCA55200C

Both old plans pin scripts/vm_console_native.py SHA 1761F284..., whereas current source was SHA:
5B6863660F23712C14C9548DFF96A10FC0E7BF1DEE95CF3B3D3362E35A4E6990

The other eight checked source hashes matched historical pins during the audit. Old shutdown-marker paths already exist and old process/log output files have exclusive creation semantics. Blind plan reuse must fail multiple guards. **Recalculate all hashes and VM identity in a new unique plan; do not weaken checks.**

The reviewed but uncreated recovery target directory was:
artifacts/control-fleet-live/lab1-recovery-20261030-01/
It was independently observed empty.

## 7. Workbridge failed-write investigation

ChatGPT Workbridge write_file and patch_apply requests during recovery hung for roughly 160–232 seconds before interruption. There was no success receipt, the planned recovery directory stayed empty, and patch_status for rr2-lab1-recovery-patch-apply-20261030-02 returned INVALID_ARGUMENT; patch-list inspection found no corresponding journal.

Workbridge continued to handle read-only actions and bounded terminal diagnostics. The failure was specifically an unconfirmed write/publication request, **not** evidence that all Workbridge services were offline.

C:\work\workbridge-mcp\docs\chatgpt-approval-visibility.md records that ChatGPT approval cards can be hidden beneath collapsed Previous activity even when Workbridge's app preference says Allow all actions. No particular approval card was confirmed displayed or denied for these attempts. A client approval interception, interruption, or transport issue remains possible. Do not blame Joey for a card no one observed. Do not evade pending approval using a different tool. Native Codex has a separate local execution path and its own permissions.

## 8. Controller code and movement findings

68 focused controller/console Python tests passed during the unsuccessful recovery investigation. A code reviewer independently accepted the proposed new identity-pinned plan/wrapper; the files were not actually created. Passing offline tests does not establish that the controller host is running.

The product had demonstrated supervised bounded movement:
- Lab-1 reviewed 96 ms W pulse delivered and released; later observation (7417.4199, 2926.6099) was 0.081 X/Z units from chosen point (7417.5, 2926.62), but the synchronous runner timed out before accepting feedback. Physical arrival evidence, NOT an accepted final result for that run.
- Earlier Lab-1 bounded movement trials did record accepted planar arrival under earlier epochs; they do not qualify the current session.
- Lab-2 accepted fixed-goal arrival with 0.057 planar error after a 44 ms W pulse, and a second independent arrival with 0.010 planar error after 52 ms W. These are narrow fixed-goal/planar successes, not general pathfinding, 3-D arrival or automatic navigation.
- Stalled-VNC cleanup at commit 3253ece was live confirmed on Lab-2, NOT on currently restored Lab-1.

Do not reuse old player coordinates, reader nonces, input calibration, game build assumptions or native addresses. Reacquire current exact game/process identity before testing.

## 9. Root-cause assessment

**Confirmed:** Old controller processes exited; current API unavailable; old plans stale; host credentials/config on main PC are not restored by VM snapshot; RIFT absent after snapshot; attempted new files unmaterialized.

**Plausible but not proven:** The primary obstacle now is missing/stale controller-host lifecycle and launch state rather than broken movement algorithms. ChatGPT-host approval/transport might have prevented file creation. VM restarts and expired session identity may have contributed to observed VNC/controller issues.

**Unresolved:** Why the last host process exited; whether an unknown host process still exists without the expected listener; exact ChatGPT write request interception; guest agent deployment/startup after the revert; whether controller can reconnect cleanly after a newly launched host.

## 10. Recommended next AI recovery runbook

1. Read AGENTS.md, docs/status.md (newest sections), docs/reference/native-vm-controls.md, docs/validation/control-fleet-live-2026-10-29.md and this report. Inspect git status and preserve user changes.
2. Recheck current Lab-1 VMX process/startTicks/logEpoch/VNC5905 owner. **The host-PC reboot makes PID 6824 obsolete.**
3. Independently check actual host Python/Pythonw processes, ports 49810/49811, authenticated HTTP status, Windows session, console mutex and queue ownership. Do not kill unidentified processes or start a duplicate.
4. Run read-only diagnostics: python scripts/lab_codex.py doctor --lab lab1; python scripts/lab_guest_probe.py --lab lab1; python scripts/control_fleet.py --manifest artifacts/control-fleet-live/fleet.json. Use the established control_client.py status with private config for authenticated checks.
5. If no valid controller host is running, reuse artifacts/control_fleet_host_entry_20261029.py and scripts/control_host.py. Generate new plan with fresh hashes/config/VM identity, unique unused receipt directory and absent shutdown marker. Launch one detached main-PC Session 1 pythonw.exe, not merely a child in a temporary Workbridge job. Keep inJob=false process receipt and exact identity guard.
6. Preserve existing queue artifacts/native-coordination-live/queue.sqlite3 and resource vm:rift-lab-1. Use --reconcile-existing, not reset/delete/recreate.
7. Verify process identity, bound ports, authenticated HTTP, no held keys, disarmed/idle state, queue lease and clean release.
8. RIFT was absent after revert: establish authorized RIFT build and guest agent, with fresh game/build/reader/nonce/position identity. A host waiting for an absent guest is not automatically a host failure.
9. Accept operational readiness only with live connected/ready/disarmed/idle, current identities, release and queue evidence. Only then run a small reviewed bounded movement test if safe and within existing authorization.
10. Inspect Lab-2 isolation read-only. Keep code fixes small and evidence-based. Run targeted tests and commit verified corrections plus updated handoff.

Never repeat the snapshot revert blindly, force-stop by PID alone, disable identity guards, re-arm silently, overwrite queue DB, expose private host.json/guest.json/log content, or bypass explicit approvals.

## 11. Post-reboot acceptance and preservation

A PC reboot will invalidate all running host/VM/process identities and live game/reader sessions. Both VMs were listed running during preboot audit. A new memory snapshot is not required for Lab-1 after baseline restore; Lab-2 has earlier snapshots pre-tools-20261026 and baseline-codex-connected-lab2-20261029. Lab-2's newest accepted movement evidence is recorded in the main-PC repository and does not require retaining game memory. Any additional Lab-2 memory snapshot is optional and not a disk-independent backup.

The Git repository had no remotes configured at audit time. After committing this report and companion handoff, create and verify a standalone Git bundle (recommended path C:\work\riftreader2-pre-reboot-20261030.bundle). This preserves committed Git history but does not include ignored artifacts/VMs or private .local state, and remains on the same disk. Do not claim off-machine backup.

**Final honest status:** VMware rollback succeeded and Codex guest is responsive. Lab-1 host controller is still not connected or verified ready. The immediate next action after reboot is to recover a fresh, guarded host controller lifecycle and guest connection, not to rewrite movement math.
