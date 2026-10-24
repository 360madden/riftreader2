# Receiver recovery after VMware epoch change — host media preparation

Date: October 24, 2026 (America/New_York). Status: **host-side ISO verified; guest installation and reconnection unverified**.

## Live diagnosis (read-only)

- Exact VM: C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx. Current vmware-vmx.exe PID **38044**, log epoch **2026-10-24T05:41:51.833Z**, VNC listener 5905. VMware UI remains PID 9476/HWND 2230572 in the sampled Windows session.
- Coordinated native host: Python PID **34352**, started October 23 at 23:48:28Z from run-coordinated-host-v7.py. It listens on 192.168.56.1:49712 and 127.0.0.1:49715. Authenticated, read-only status: **connected=false**, coordination waiting, no supervisor, but exclusive console reservation still held.
- The V7 launch plan pins older VMX PID **31884**, epoch **2026-10-22T20:41:22.372Z**. All five runtime source hashes and the private config hash still match the plan; the VM epoch does **not**. The running VmEpochGuard intentionally rejects identity drift while reserving the console. Never silently repurpose that host for a replacement VM process.
- Read-only canonical SQLite queue query: resource vm:rift-lab-1, blocked=1, holder absent, cleanup receipt absent, zero queued/active/cleanup requests, one historical succeeded request. The existing readiness gate refused resource-not-cleaned as designed. Do not reset this queue, bypass the reservation, kill the host, or create its shutdown marker just for status.
- Workbridge GUI-005a captured the actual Rift display through the VMware host window. It did not verify the guest receiver or a Windows Startup shortcut. October 22 historical records explicitly state that receiver Startup installation was not completed.

## Verified one-click installation medium

- Preserved the previously tested six-file ZIP unchanged:
  artifacts/receiver-milestones-20261022-01/host-only-download/RR2-Guest-Startup-v2.zip;
  8,243 bytes, SHA-256 ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f.
- New tracked scripts/Prepare-GuestReceiverISO.ps1 uses Windows' installed IMAPI2 file-system COM component and strictly pins the ZIP hash/entry list. The resulting ISO9660/Joliet disc has exactly two root files: the unchanged ZIP and START-HERE.cmd. It bounds output, refuses overwrites and reports SHA-256.
- START-HERE.cmd is meant for **one double-click inside signed-in guest Windows**. It rechecks the ZIP hash, refuses an existing extraction directory, expands to a local-user directory, then runs the unchanged INSTALL-ONCE.cmd. That installer independently verifies the expected launcher, game/receiver files and guest identity before registering the current-user Startup shortcut. Executing the wrapper is not by itself a connection/Startup proof.
- Created host-only ISO:
  artifacts/receiver-milestones-20261022-01/RR2-Guest-Startup-v2.iso;
  **63,488 bytes**, SHA-256 **507002784F251628E05DA12AEAD4F70391C6F88CFC3D6D3180D8A1C5174F25A1**.
  The receipt is alongside it. Independent read-only Joliet parsing confirmed both file records; embedded ZIP bytes were identical to the original. New focused test suite passed **4/4**, including repeat-run overwrite refusal.
- **Not done:** VM power/config change, CD-media swap, guest installer run, host restart, guest input, game input, queue write, firewall modification or credential change. VMware SATA0:1 still names the original artifacts/field-discovery/rr2-fields.iso.

## Versioned native-host handover prepared (October 24)

- New tracked `scripts/prepare_native_host_handover.py` verifies the prior V7 launcher/process epoch, unchanged runtime/config hashes, canonical queue quarantine with no outstanding work, and read-only current VMware process/log/listener identity. It intentionally uses the console-free identity collector: `VmEpochGuard.collect()` initially failed `controller-busy` because the live V7 host still legitimately owns the console mutex.
- Prepared **V8**, with the exact new VM process PID 38044/log epoch `2026-10-24T05:41:51.833Z`, a distinct absent shutdown marker and the identical existing queue/config/source pins. Local ignored artifacts are `artifacts/update-recovery-20261023-01/coordinated-host-plan-v8.json` and `run-coordinated-host-v8.py`. The previous V7 PID 34352 was revalidated by its process-creation identity; it has **not** been stopped.
- The preparation did **not** create either shutdown marker, take the mutex, modify the SQLite queue, launch V8, mount media or send guest input. The generated V8 launcher still independently revalidates its epoch/config and must obtain the lock normally. Handover-script tests passed 3/3.

## Safe completion roadmap

1. **Ownership handover:** recheck actual VM epoch, host PID/ports/status, blocked queue, and current V7 stop marker. Review/test the existing orderly shutdown path; release console reservation only by that path and verify it has actually released. Prepare a new one-use host wrapper with a fresh VM-epoch identity, unchanged checked runtime/config hashes, fresh shutdown marker and the **same canonical queue**. Do not wipe the blocked authority.
2. **Guest delivery:** after the proper console handover, attach the prepared ISO through normal VMware removable-media UI, preserving the original rr2-fields.iso device state. Visually confirm guest disc content, double-click START-HERE.cmd once, record its installer result, and verify the actual guest Startup shortcut and manifest. Do not retry previous blind Windows Run command batches: they lost the cmd.exe prefix and failed to execute.
3. **Coordinator return:** restore the original optical image and start the newly pinned coordinated host. Require authenticated guest reconnection, correct VM/game identity, no held guest input, ready supervisor, queue unblocked and a fresh cleanup receipt before declaring receiver service restored.
4. **Autostart qualification:** separately test receiver-only restart, guest sign-out/sign-in, and controlled VM reboot; prove an unattended new receiver instance and native connection each time. Do not infer guest login or autostart from a screenshot or a host process alone.

The vmrun captureScreen password prompt concerned encrypted VMware authorization, **not** guest Windows autologin. The proven WinApp screenshot fallback needs neither VM encryption credentials nor guest input.
