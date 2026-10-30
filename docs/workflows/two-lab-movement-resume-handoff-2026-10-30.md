# RiftReader2 — Post-reboot two-lab movement handoff
Date: October 30, 2026; observations around 13:42–13:53 UTC (09:42–09:53 EDT).
Repository: C:\work\riftreader2, branch codex/modular-foundation.
Starting source commit: e1b9f1e; recheck Git HEAD, status and VM identities on resumption.

## Outcome: guest access recovered, game controllers still offline

| Item | Lab 1 | Lab 2 |
| --- | --- | --- |
| Actual VMX | C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx | C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx |
| VM process when checked | 11164 | 35784 |
| VNC port | 5905 | 5962 |
| Guest doctor | READY, exit 0, Codex CLI 0.165.0, login available | READY, exit 0, Codex CLI 0.165.0, login available |
| Guest process inventory | 161 processes, RIFT absent | 191 processes, RIFT absent |
| Operator HTTP API | 127.0.0.1:49811 refused connection | 127.0.0.1:49921 refused connection |
| Agent host endpoint | 192.168.56.1:49810 | 192.168.56.1:49920 |
| Game/agent/controller readiness | NOT verified | NOT verified |

This is a time-stamped diagnostic snapshot, NOT a valid current identity for later input. Reacquire actual VM PID/start ticks/log epoch, current guest process/executable hash, nonce, console owner, queue lease and game foreground on every run. Never reuse old movement coordinates, calibration or screenshot approvals.

### Exactly what was repaired and saved

- Lab 1 VMX relocated from the deleted RIFT-Lab folder to RIFT-Lab-1; the .local/lab-codex.json active config and tracked config/lab-codex.example.json point to the new location.
- Guest Windows cached credentials are keyed partly by the VMX path. scripts/vmware_guest_session.py checks the current guest cache on EVERY session and, only when missing, explicitly checks the old-path cached credential for THAT SAME LAB. scripts/lab_codex.py accepts an optional per-lab legacyGuestVmx and prevents aliasing another active lab. Existing credentials were reused, not copied, disclosed, overwritten or recreated.
- AGENTS.md lines 164–171 record Joey's durable EVERY-VM-LOGIN cached-credential check, including failures, reboot, snapshot restore and relocation. Always check cached credentials afresh for EVERY VM login; no exceptions. Never substitute credentials from the other lab.
- Focused tests passed: 21 guest session tests and 19 lab Codex tests; diff whitespace checks passed. Commit e1b9f1e includes the source fix, tests, policy and workflow documentation.
- Lab 1 ignored/private host controller config, artifacts/control-fleet-live/lab1/host.json, had a stale VMX path. Corrected ONLY its /vmx property to C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx. Lab 2 private host config unchanged. Do not commit private configs or print their tokens.
- Static fleet validation then passed, exit 0: two separate host configs, VMX files, ports, addresses and output locations. Static valid does NOT mean a host is running.
- Both post-fix authenticated controller client status calls failed with WinError 10061 (connection refused). No successful live host-controller verification, agent handshake or movement trial occurred.
- A host process/port inventory produced no matching output; this alone does not prove why controllers are absent or grant authority to kill or start any process.

### Evidence commands and durable Workbridge job IDs

- Lab 1 doctor: rr2-lab1-doctor-legacy-fallback-20261030-01 (ready/exit 0).
- Lab 1 guest inventory: rr2-lab1-guest-probe-fixed-20261030-01 (161/RIFT absent/exit 0).
- Lab 2 doctor: rr2-handoff-lab2-doctor-20261030-01 (ready/exit 0).
- Lab 2 guest inventory: rr2-handoff-lab2-guestprobe-20261030-01 (191/RIFT absent/exit 0).
- Two-lab static fleet: rr2-fleet-after-lab1-vmx-fix-20261030-01 (configuration-valid/exit 0).
- Both API checks: rr2-handoff-lab1-api-status-20261030-01 and rr2-handoff-lab2-api-status-20261030-01 (WinError 10061/exit 1).
- Focused tests: rr2-legacy-cred-tests-final-session-20261030-01 (21 passed) and rr2-legacy-cred-tests-final-labcodex-20261030-01 (19 passed).

### Historical movement results, not a fresh trial

- Lab 2: two accepted independent reviewed fixed-X/Z-goal arrivals on October 29, ending 0.057 and 0.010 planar units from the fixed goals. The latest docs/status.md contains source receipts and their limits. Turn/calibrate/forward workflow has successful narrow examples; not general routing or current-runtime success.
- Lab 1: a reviewed 96 ms W pulse was delivered and released; later evidence showed 0.081 planar units from its chosen goal, but the synchronous runner timed out before accepting feedback. Do not call this an accepted repeated arrival.
- The October 29 movement-resume-prompt-2026-10-29.md describes an older stage, including an outdated Lab-2 S-only prerequisite; supersede its priorities using the newest docs/status.md and the October 30 companion prompt. Preserve the underlying raw evidence.

## Exact next recovery sequence

1. Read AGENTS.md, the top of docs/status.md, docs/workflows/lab1-controller-handoff-2026-10-30.md, docs/reference/native-vm-controls.md, and this handoff. Inspect HEAD and working tree; preserve unrelated changes. Reacquire current VM identity and verify VM-specific cached credentials on EACH guest login attempt.
2. Recheck read-only doctor/probe, static fleet preflight and controller status for each lab. Inspect current Python/Pythonw processes, listening port owners, Windows Session 1, console mutex and shared SQLite queue. Do not assume a host is dead solely from an API refusal. Do not kill unknown processes or replay stale PID/stop-marker files.
3. Restore the persistent main-PC control host separately for each VM if absent, using reviewed artifacts/control_fleet_host_entry_20261029.py and scripts/control_host.py with NEW identity/hashes, unique unused stop/output receipts and a detached Session-1 pythonw.exe with inJob=false. Never mistake a temporary Workbridge terminal child for a persistent controller. Reuse artifacts/native-coordination-live/queue.sqlite3 and --reconcile-existing; never reset/delete it. Queue resources: vm:rift-lab-1 and vm:rift-lab-2. Revalidate independent lab isolation.
4. Require authenticated API connected/ready/disarmed/idle, no held inputs, correct VM/game identities and exclusive input ownership before any gameplay. If unready, continue independent read-only diagnostics only.
5. Both RIFT clients were absent in the latest guest inventories. Use already authorized guarded game/guest-agent startup only after fresh verification; do not reboot/revert snapshots as setup. Verify executable SHA/PID/start ticks, current addon/reader nonce, telemetry endpoints, foreground/client capture and guest agent. Restore per-lab receivers/readers and source pins without reusing stale files. Keep credentials private.
6. First qualify sustained reader freshness in fixed no-input windows, preferably the proposed eight-minute per-lab window. Preserve fresh/warming/missing/failed counts; latency p50/p95/max, longest gap, scan times and exact identities. Meet the current controller 4.5 s feedback bound. Stagger CPU-intensive scans/builds and do not compare unmatched windows as a formal A/B benchmark.
7. Split movement roles: **Lab 1 = controller recovery plus a bounded, fresh-calibration repeatability test**; **Lab 2 = independent reproduction and variation of the previously accepted fixed-goal turn/calibrate/forward flow**. Measure key responses afresh (never assume Q/E/A/D/inverse meanings); visually review clear terrain; use current X/Z goals only. Coordinator owns input for both labs, with ONE exclusive controller per lab and non-conflicting workers.
8. Existing motion gates remain: 15-second finite arm, 12-second movement phase, at most 150 ms per pulse, 900 ms total key hold, six actions, six-unit displacement radius, cross-track <=0.50, vertical drift <=1.5 and planar arrival tolerance <=0.30. Require feedback after actions, fresh capture/lease/epoch, verified STOP/disarm/key release and independent advancing stationary no-input arrival confirmation. Never silently rearm, extend blind input, use stale samples, or bypass the safety stop when nearby threats or contention are visible.
9. Proposed acceptance milestone: two independently accepted, reviewed nearby fixed-goal trials **per lab**, including at least one multi-action feedback trial on each lab. This is a future goal, not proven. Retain every failed/aborted run and explain why it failed. If acquisition blocks movement, fix the smallest demonstrated bottleneck, remeasure, and report partial completion honestly.
10. Run focused tests and the repository validation gate when code changes. Commit verified progress. Preserve working hosts/agents and only terminate exact-owned temporary processes. Record current identities, build hashes, received/issued actions, feedback timeliness, errors, releases, attempt outcomes, and next milestone. Update this handoff and docs/status.md.

## Parallel-agent partition (as available)

Use up to six useful disjoint subagent lanes if actually supported; coordinator integrates shared changes and alone authorizes physical game input: (1) Lab-1 host lifecycle and queue ownership; (2) Lab-1 game/agent restoration; (3) Lab-2 baseline/independent validation; (4) native feedback reliability and scan profiling; (5) bounded movement/controller regression checks; (6) independent source/evidence/acceptance review. No duplicate writers to one file, no concurrent input controllers on one lab, no heavy scans during timing measurements and no secret-bearing logs.

Keep direct ChatGPT Computer Use against RIFT, patch/update recovery, uncontrolled gameplay automation, debugger/process writes, and edits to reference-only V1 deferred as specified in AGENTS.md.

**Related docs:** docs/workflows/lab1-controller-handoff-2026-10-30.md, docs/validation/lab1-controller-recovery-incident-2026-10-30.md, docs/workflows/movement-handoff-2026-10-29.md, docs/workflows/movement-resume-prompt-2026-10-29.md, docs/planning/bidirectional-hybrid-two-lab-roadmap.md.
