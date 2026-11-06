# NAV-SCHED-02I — Coordinated host activated

Date: October 22, 2026 (America/New_York). **Production composition is implemented and the recovered RIFT-Lab-1 host is now running coordinated mode.** This is live ownership/observation acceptance, not a claim of navigation or combat automation.

## Runtime and activation

The old native host PID 49956 was identified by image, creation time, Windows session, command-line wrapper and both listening ports. Fresh host-side VM detection preceded guest access. A native STOP was acknowledged and followed by idle/disarmed, recovery-free status with no sampled held inputs. Only that pinned host process was then terminated; the old version had no shutdown endpoint. The VM, RIFT and guest receiver were not restarted.

The replacement uses the reviewed main-checkout code and original configuration, with unchanged ports and credentials. It is a normal user process launched through WMI in Windows session 1, outside the tool job. A disposable probe first demonstrated that launch method surviving its tool command. The wrapper verifies runtime hashes, configuration hash, exact VM identity and Windows session before listening. Successful live readiness was recorded at **2026-10-22T05:39:31.854007+00:00**, native host **PID 54952**.

Runtime receipt: `artifacts/navsched02i-20261022-01/evidence/coordinated-process.json`.
Original host configuration: `artifacts/native-usability-20261020/host.json`.
Durable authority: `artifacts/native-coordination-live/queue.sqlite3`.
Resource: `vm:rift-lab-1`.
Single-use launch wrapper: `artifacts/navsched02i-20261022-01/run_live_host.py`.

No Windows service, automatic startup task, firewall change, new dependency, credential rotation, VM restart or guest binary deployment was introduced. A future PC or VM restart requires fresh detection and an explicit host launch, not today's PIDs or blindly repeating a single-use wrapper. The database must be preserved, never deleted to fix a blocked state.

## Production composition contract

`control_host.py` now accepts explicit `--coordination-db`, `--coordination-resource`, `--reconcile-existing` and `--shutdown-file` options. Legacy defaults remain unchanged. Coordinated mode requires the existing absolute-path database and exact VM configuration. It owns the established console mutex for its lifetime, publishes every authenticated session blocked, and runs one existing OwnedSupervisor after fresh target qualification and verified cleanup. No caller receives a grant automatically.

`HostCoordinator` runs on the console-owning host thread. Reconnect waits for the former supervisor thread to finish before probing or preparing the new session. It then journals a proposed transition and performs an exact-row compare-and-swap update. Same-target reconnect still invalidates old tokens and queued requests. Old request/history rows are retained. Unrelated resources are not reset; other resources in a multi-resource grant remain quarantined until their own cleanup completes.

A process restart does not silently claim an existing authority: `--reconcile-existing` explicitly permits revocation and new release verification. Concurrent or stale reconciliation is rejected instead of overwriting newer state. A missing/corrupt database is not recreated. Failed preparation on a given connection is not retried on every poll.

Supervisor readiness, console reservation and connection sequence are exposed through ordinary authenticated native status. Status never treats a terminated or disconnected supervisor as ready. Queue status still has the standalone store's static `live_enforcement: false` field: that store does not send commands. Actual runtime enforcement is established by the host coordination state and the live reject/accept checks below, not by relabelling the store.

## Verified live behavior

A capture without a lease was rejected as `navigation dispatch refused: navigation lease required`. A single issued lease then captured the native RIFT frame through the ordinary command-line client. Capture ID: `9afffb13b78e4415b01b48dfd6f3339d`. The retained 3,323,038-byte BMP matches SHA-256 `6d6584569fb09890f3568eb7abbe11da657fe0cfd49401237c4401210ebdb50d` and the expected game/window identity. Image bytes and metadata were validated; no visual screenshot review or text-entry-state qualification is claimed.

The request `navsched02i-capture-20261022-01` finished as **succeeded** only after watchdog STOP/status cleanup and durable receipt publication. Its completed token was rejected on another capture request. A cooperating console mutex contender was refused with `controller-busy` before any VNC connection or input. The VM remained foreground, idle and disarmed. **No ARM, movement, camera or game-action command was sent.** STOP was sent for host handover and normal verified cleanup; this is not represented as zero commands of any kind.

After 135 seconds without caller activity, live acceptance observed **1 automatic reconnect(s)** within the same host instance. The host returned to ready with a fresh supervisor, the same recovered VM/game/receiver, no active/queued/cleanup requests, and a free resource with fresh cleanup evidence. Completion timestamp: **2026-10-22T05:43:41.769040+00:00**. The test did not restart the guest or force a transport disconnect.

## Validation and retained unsuccessful evidence

Both final isolated and main-checkout full gates passed **364 C# tests and 441 Python tests**, **108 Lua checks and 22 shared Lua/C# cases**, zero-warning Release, locked restore, formatting, native synthetic smoke and deterministic replay. The 34 new Python tests are included in the 441 total. Process tests exercise the real host main/HTTP/queue/supervisor/shutdown in disposable processes; only their fake VM identity and loopback binding are substituted after real configuration validation.

The first process harness used a loopback guest address that the production configuration correctly refused. The fixture was corrected without weakening that restriction, and the unsuccessful run remains retained. Review also exposed a real new-code defect: failure to write a shutdown diagnostic could let a blocked host exit and abandon its mutex. A dedicated process regression failed before correction and passed afterward. Diagnostics now cannot release ownership merely by failing to write. Earlier passing results are retained separately rather than substituted for the final gate.

Final candidate gate: `navsched02i-full-gate-v2-20261022-01`.
Main gate: `navsched02i-main-full-gate-20261022-01`.
Main full-gate artifacts: `artifacts/validation/20261022T053513Z-2df12ca7`.
Reviewed code patch: `navsched02i-source-promotion-20261022-01`.
Code review: full initial diff plus the complete final correction delta, by the implementing assistant, not an independent reviewer.

## Operation and maintenance

Protected native capture/ARM/action/recovery now require a valid issued private lease; the existing screenshot-review/ARM protocol is still separate. The CLI/panel can transport the credential, but do not automatically issue, renew or recover grants. STOP/release/status remain available without a lease. Known cooperating V1/V2 console and bootstrap entrypoints are locked out while this host owns the console; use the native leased capture path instead.

For an intentional shutdown, the configured absent marker is `C:\work\riftreader2\artifacts\native-coordination-live\stop-20261022-01.request`. Creating that file requests shutdown; it is not an instruction to delete state or force-kill the host. Do not create it merely to inspect status. The host stops admission, verifies STOP/release and joins the supervisor before closing the connection and releasing the console mutex. If cleanup is pending or unverified, the host reports blocked shutdown and keeps ownership rather than falsely reporting success. A forced external exit is not a verified release. Remove/replace a stale shutdown request only as part of an explicit, identity-checked new launch; do not replay this single-use launch blindly.

A new VM process requires fresh host-side detection and startup, not silent migration to a new target. Manual VMware UI input, arbitrary socket clients, direct SQL modifications, independent databases and other Windows sessions remain outside the cooperative exclusion contract. A failed status/identity/cleanup condition blocks controls; this is not a guarantee against all hardware/OS failures.

## Resume

The connection outage and coordinated native-host integration are resolved and live-validated. Continue the actual field-discovery/navigation research roadmap using issued leases and fresh observation; do not rebuild the completed ownership layers or repeat activation. The visual/keybinding and bounded movement evidence gates remain separate—no new gameplay response was qualified by this no-movement trial.

Read [current status](../status.md), [coordination roadmap](../planning/navigation-access-queue.md), [native controls](../reference/native-vm-controls.md), and [prior console-exclusion qualification](navigation-console-exclusion-2026-10-22.md). Completion and preservation evidence: `artifacts/navsched02i-20261022-01/evidence/milestone-complete.json`.

Model: GPT-6 Astra Pro. Reasoning level:
