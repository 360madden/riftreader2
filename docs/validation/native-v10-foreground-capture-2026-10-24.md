# RIFT-Lab-1 V10 — foreground recovery and leased native visual baseline

Date: October 24, 2026 (America/New_York). This continues the [guest receiver recovery](receiver-guest-recovery-2026-10-24.md). The target is still `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, VMware PID **38044**, log epoch **2026-10-24T05:41:51.833Z**.

## Rejected V9 attempt: foreground gate worked

- V9 was authenticated/ready with receiver and game PID **6940**, but `guest.target.isForeground=false` after the guest installer/PowerShell/Explorer checks. The first leased, read-only capture correctly failed `RIFT must already be foreground` at **2026-10-24T12:10:47Z**. It emitted **no image, ARM, action or movement**.
- The original request `rr2-v9-scout-20261024-01` was explicitly cancelled using the same canonical queue. Post-check: request **cancelled**, queue resource **blocked=0, holder=null, cleanup receipt present**, zero active/queued/cleanup requests, supervisor still running and guest disarmed.
- The coordinator's cooperative mutex prevented VNC while V9 was active. After independently confirming authenticated live identity, no held input, supervisor initial cleanup and no pending queue work, an ordinary V9 shutdown marker requested STOP/release. The supervisor-backed host exited **normally**: PID **50980** absent, exit receipt present, native ports 49712/49715 closed. Its shutdown intentionally left the canonical resource **blocked=1**, no holder, no cleanup receipt, zero pending. There was no hard kill, mutex bypass or manual queue modification.

## Controlled focus and independent V10 restoration

- Identity-checked VM-console screenshot showed File Explorer and diagnostic windows obscuring RIFT. A click at the visible RIFT title bar **did not** bring the game forward; subsequent screenshot proved it remained obscured. The running RIFT taskbar icon was positively identified from a crop, and a single click at guest desktop coordinates **(848,732)** made the actual in-world RIFT viewport the foremost window. No click was sent into the game's client area, and no gameplay key was pressed.
- A same-VM-epoch V10 plan/launcher was generated from V9 by **lossless textual substitution**, retaining the full `startTicks=134372941117887852` integer. The existing Python `render_launcher` contract, five runtime hashes, config hash, exact VMware identity, canonical queue quarantine, prior host exit, absent V10 shutdown marker, and unused native ports all passed before launch.
- V10 was created via WMI in the intended Windows session **2**, outside the Workbridge job, with process receipt PID **8168**. Authenticated status: host connected, coordinator `ready`, supervisor `running`, `initialCleanupVerified=true`, game PID **6940**, `isForeground=true`, guest disarmed, no held inputs; canonical SQLite **blocked=0**, holder null, fresh cleanup receipt, zero pending.
- V10 is the **current live coordinator** as of this record. Historical V7/V8/V9 process receipts must not be reused as active PIDs; re-detect the host and game before the next experiment.

## First successful identity-bound native frame

- A single-use script under ignored `artifacts/recovery-20261024-02/native-v10-scout-capture.py` reused `AccessQueue` and the existing authenticated `ControlClient._capture`. It verified host/VM process identity, readiness, `isForeground=true`, disarmed state, the prior cleanup receipt, and zero pending queue work **before** requesting a capture lease. The private grant token was retained **in process memory only**, not printed or saved.
- Request **`rr2-v10-scout-20261024-01`** (world/collision evidence track B) used one current-epoch lease. Capture succeeded at approximately **2026-10-24T12:21:16Z**. The existing client validated complete host metadata and the image digest:
  - BMP **1211 × 686**, **3,323,038 bytes**.
  - SHA-256 **`28297FAFD77F2D5E7433CBEABB5EA91B326F5CA382B6C51929AB9385032918E3`**.
  - Retained under ignored `artifacts/recovery-20261024-02/native-v10-scout-capture-01/` as `image.bmp`, `capture.json`, and an inspection-only `native-preview.jpg`.
- The image was visually inspected. It shows **live RIFT world geometry** (foreground mossy slope, adjacent rock and wall), character, minimap, chat panel and action/HUD bars without Explorer/PowerShell occlusion. RGB channel standard deviations were about **61.4/59.7/62.1**, so this is not a uniform black frame. Visual examination does not, by itself, prove how recent every rendered scene element is or establish any native field semantics.
- `AccessQueue.finish(...,'succeeded')` followed the image and target/hash checks. The supervisor completed normal STOP/release-backed cleanup. The retained request is **succeeded**, canonical resource free/unheld, zero pending, and the same authenticated guest remained ready/idle. No ARM, gameplay movement, camera motion or combat operation was sent.

## Boundaries and next discovery step

- This is a **visual baseline**, not movement/navigation calibration, automated logon or reboot testing, verified input-to-world response, or memory-field qualification. The foreground requirement is a real capture gate; do not weaken it.
- Preserve the original failed/cancelled V9 request, successful V10 request, retained queue/journal and ignored screenshot bytes. Do not stage captures or private logs into Git.
- Next: correlate the newly verified live visual/identity baseline with the existing addon/API/native read-only acquisition and REA evidence, prioritizing high-value movement/world-object fields. Use fresh process/build and data-provenance gates before promoting any candidate to the durable catalog. New game input still requires its separate reviewed bound-action protocol.
