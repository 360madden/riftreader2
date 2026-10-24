# V14 read-only preflight and V15 successor preparation — October 24, 2026

**Result: V14 remained the verified exclusive, ready native-console owner at the time of observation; V15 is prepared, not running. No VM or game intervention was performed.** This evidence is a point-in-time host-side observation, not a continuing health guarantee or a successful RIFT typed-capture run.

## Actual read-only evidence

- At **2026-10-24 19:30:35 UTC** the repository's `scripts.verify_guest_recovery` produced the ignored, retained observation `artifacts/update-recovery-20261023-01/v14-preflight-scout-copy-oct24-01.json` (SHA-256 `59DA4C579D0DE6B1DD0B6D494386B717603C1738BF67AE99EC5FF574CDCA9624`). It recorded `nativeReady=true`, `noGameplayInputSent=true`, guest RIFT PID **6940**, start ticks **639284177321390013**, executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- RIFT guest state had **`foreground=false`**. This is an important live-acceptance caveat: connectivity and native readiness do **not** prove that game UI input would go to RIFT. The host must re-observe game/window focus and restore it only under a legitimate exclusive maintenance window if a future operation needs it. No focus/input change was attempted here.
- The same observation identified VMware `vmware-vmx` PID **38044**, port **5905**, log epoch **2026-10-24T05:41:51.833Z**, matching the prior known VM epoch. Canonical queue `artifacts/native-coordination-live/queue.sqlite3`, resource `vm:rift-lab-1`, generation **1248**, held by nobody with **0** pending requests and `blocked=false`.
- At **19:31:32 UTC**, the existing `scripts.prepare_native_host_handover` generated a **same-VM-epoch V15 successor plan only**, stored in ignored `artifacts/update-recovery-20261023-01/coordinated-host-plan-v15.json` (SHA-256 `1863932E5785FD2ABA317ED3E71E13505D38D9B2C290EEC0320549580DC3F344`) and `run-coordinated-host-v15.py`. Its result was `handover-prepared-not-executed`. It pins the host config SHA-256 `90F2B8AB6F575C776941F0B160FF4CE1D8BC8575408975FE7645ADDED5325A2C`, VM identity and runtime script hashes.
- At this checkpoint, **V14 had not been stopped**, its STOP marker had **not** been created, V15 had **not** assumed ownership, and the new published executable had **not** been transferred into the guest.

## Gate to resume safely

1. Recheck exact V14 process/guest/VM identities, guest disarm, foreground status, queue and lease immediately before maintenance. A prepared plan is not evidence of current ownership.
2. Execute the tested normal **V14 STOP and release**, confirm receipt and free queue; never use the VM console while V14 owns it. Verify that the prepared V15 plan remains bound to the same VM and host runtime.
3. Under one verified exclusive maintenance lease, transfer the published `RiftReader2.Live.exe` (SHA-256 `484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716`) and exact epoch-bound `scout-copy-typed-native` request through a hash-checked, restricted path. Perform two bounded read-only observations and preserve original request/manifest/snapshot hashes; do not send gameplay input.
4. Validate both snapshots with strict `inspect-typed-wire` and report negative or partial results honestly; independently restore and recheck the pinned V15 supervisor even if the read-only trial fails.

**Remaining unproven:** in-guest deployment of the new CLI, current complete typed Lua frames, typed native XYZ, and patch/restart resilience. See [published host validation](typed-inline-capture-cli-host-2026-10-24.md).
