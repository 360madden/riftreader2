# RR2 handoff — physical movement, native turning, and optimal RIFT screenshots

**Recorded:** 2026-11-11, 17:00 EST
**Machine:** AMD-DESKTOP only (verified by machine-local PowerShell, not connector label)
**Repository:** `C:\work\riftreader2`
**Branch:** `codex/modular-foundation`
**HEAD at preflight:** `f9c06fb25607bb9f0bd5eb7e879403b4422544e5`
**Last movement-lane commit:** `1fedc13` (pushed successfully)
**Other developers' later commits:** `7cd38bc`, `f5bf355`, `82c2a32`, `73d0842`, `3f6a7b9`, `f9c06fb` relate to native RR2R1/RRE intake; preserve.

## Operational constraints

- Follow repository `AGENTS.md`. Work on **AMD-DESKTOP only** unless Joey explicitly switches hosts. **Never touch LEGION or use retired VMware RIFT labs in this session.**
- Verify the computer identity and rebind the real `rift_x64.exe` PID, process start, executable path/SHA and window before every live operation. At this handoff, historical physical client PID **44888**, HWND **594412**, start UTC ticks **639299470183328173**, RIFT SHA **1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8**. Do not treat these historical values as future proof.
- Do not stage, reset, stash, overwrite or commit concurrent files. The preflight dirty files belong to other work: `scripts/fresh_native_actor_pose.py`, `tests/test_fresh_native_actor_pose.py`, three `src/RiftReader2.{Application,Domain,Infrastructure}/packages.lock.json`; untracked `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `tests/test_rank_native_anchor_candidates.py`.
- Read-only process-memory sampling and offline analysis are available. New physical game input/screenshots **must not** bypass a known shared desktop operation quarantine or an input-owner gate.

## Movement/turning achievements (verified)

1. **C# `move-key` input works with legacy RiftReader focus technique.** In the existing helper, attach both GUI input threads *before* `SetForegroundWindow`, then verify exact target and bounded key release. W/S/Q/E real physical movement receipts were captured; A/D 500-ms bounded inputs produced visually changed viewpoint in earlier screenshots. Do not label screenshot movement alone as qualified actor heading or game consumption. See `docs/validation/move-key-focus-failure-postmortem-2026-11-11.md` and `docs/validation/physical-ad-turn-visual-verification-2026-11-11.md`.
2. **Last milestone `1fedc13` adds tighter timing evidence:** `src/RiftReader2.Live/Control/MoveKeyCommand.cs` emits `inputCallTiming` (UTC envelope around bounded executor), `keySendEvents` (per Windows SendInput key-down/up call start/end and insertion status, including watchdog-thread key-up), and `keyHoldWindows` (minimum/maximum/midpoint monotonic hold candidate). An OS injection may occur inside each SendInput call; exact injection and game-consumption timestamps remain unknown. A/D candidate angle-rate math now uses bounded hold midpoint only when clocks, delivery and release are consistent. No new gameplay input was sent in the timing milestone.
3. `scripts/physical_move_key_calibration.py` reads three receipt generations: legacy executor-only, executor+UTC-envelope, and new per-key send-window. It labels the hold measurement source, uses the bounded midpoint when valid, rejects incomplete or contradictory evidence, and keeps all outputs `movementEligible=false` and `gameResponseVerified=false`.
4. **Tests for `1fedc13`: 49/49 focused .NET, 1,196/1,196 full Live .NET tests, 28/28 targeted Python tests.** Current physical RIFT `move-key` preview-only command with `--measure-actor-pose` returned `inputSent=false`. Historical W400 receipt still replays as legacy evidence; exact key timing cannot be reconstructed retrospectively.
5. Historical empirical W/S/Q/E candidate vectors are almost cardinal (W/S 179.996° opposite, W/Q 89.977° perpendicular, Q/E 179.998° opposite). Backward is about half forward speed in those samples. `scripts/physical_move_basis.py`, `physical_move_basis_waypoint.py`, and `physical_move_step_feedback.py` reuse these receipts for **offline** one-pulse planning, predicted/observed XYZ comparison, and STOP/review on divergent evidence. A rotation-based later-facing strafe projection is mathematical only; no same-facing live Q/E test qualified it.
6. **Fast read-only actor-pose/orientation samplers** defer costly full executable/module revalidation until the end of each bounded burst, keeping per-read player ownership checks. Physical actor-pose acquisition improved 25.5 Hz → ~3,691 Hz in 30/0 burst (~145×), full capture ~52.8 ms; orientation acquisition ~4,384 Hz, full capture ~43.3 ms. Python consumers were fixed to preserve .NET 100-ns timestamp order.
7. Position secondary matrix `+0x94` and actor matrix `+0x398` matched all 9 float32 bits at two separated stationary states, ~111.882° and ~10.228°; they are copies/related state, not independent heading validators. Smoothed scalar fields stayed `0,0,0,15` through a ~101.65° actor-matrix candidate change, so **do not assume the scalar is absolute yaw**. Genuine A/D angle calibration and body/camera differentiation remain outstanding.

## Live screenshot blocker (do not circumvent)

A WinApp `desktop_capture_window` request `rr2navposebeforeA20261111b` produced `DESKTOP_TREE_UNSETTLED` and quarantined shared GUI ownership; exact lease ID `d85dd9f0-93e8-4e09-a8ca-ab996efb8586`, `automaticRetryAllowed=false`. On this handoff preflight:

- `C:\work\workbridge-mcp\.tools\desktop-evidence\desktop-input-turn.lock` exists, SHA-256 `E2453FB24A5D970A65289A9D7B4D34581EEB84C2DD30546BFC5538D2C0B142B2`.
- `desktop-turn-quarantine-d85dd9f0-93e8-4e09-a8ca-ab996efb8586.json` exists, SHA-256 `5A1A1370B560082A845817E2F294D2146C47144D330061BAE50BB56960C54E05`.

Earlier read-only reconciliation found the original Workbridge owner PID still present and unattributed descendants, so `releaseEligible=false`. **No lock unlink, archive, process termination, unauthorized alternative GUI action or screenshot retry was performed.** The October/November 9 quarantine recovery is a different episode and does not constitute approval for this one.

## New research: which screenshot technique is optimal for physical RIFT?

**Recommendation: Windows Graphics Capture (WGC) per-HWND first, DXGI Desktop Duplication second, existing RR2 GDI/BitBlt diagnostic third.** Do not depend on WinApp CLI for routine game screenshots.

Why specifically RIFT:
- RIFT's published minimum requirements specify **DirectX 9.0c**, and the current physical client is **64-bit in borderless-windowed mode on Windows 11**. Prefer a GPU-native capture of its rendered frame rather than UI Automation or a GDI surface that may not contain all Direct3D pixels. Official support: https://support.gamigo.com/en/support/solutions/articles/201000105482-minimum-system-requirements-for-rift
- **WGC** has Win32 `IGraphicsCaptureItemInterop::CreateForWindow(HWND)` (Windows 10 1903+), so target the exact current RIFT window without the WinApp GUI tree. Microsoft's Win32 sample notes minimized windows are not captured: https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow and https://github.com/microsoft/Windows.UI.Composition-Win32-Samples/blob/master/cpp/ScreenCaptureforHWND/README.md. Runtime success on this RIFT build **is not yet measured**.
- **DXGI Desktop Duplication** is independent of the game's original DirectX version and provides GPU desktop frames. It captures the **visible monitor** (not an unobstructed named window), so select the correct physical output/monitor and crop to a revalidated game-client rectangle. Reject occlusion/hidden window, desktop-switch, device-lost or output changes: https://learn.microsoft.com/en-us/windows-hardware/drivers/display/desktop-duplication-api
- **Existing C# GDI** in `src/RiftReader2.Live/Control/WindowsControlDesktop.cs::CaptureBmp` uses `GetDC(window)` / `BitBlt` / bitmap encoding and is invoked by `ControlAgent` operation `capture` (requires game already foreground, no focus change; retains target identity). Reuse for baseline/diagnostics, but do **not assume** this captures Direct3D 9 GPU-rendered scenes correctly. No recent GDI-versus-GPU live comparison was run.
- **OBS Game Capture** is efficient for game video, according to https://obsproject.com/kb/game-capture-source, but it involves a separate OBS pipeline/hooking. Not the preferred dependency for RR2's tiny one-shot C# observer.
- Avoid screenshot methods that rely on a UIA window tree, `PrintWindow` assumptions, artificial keyboard shortcuts or game focus changes.

**Safety and acceptance:** Switching APIs is not permission to ignore shared GUI/input ownership. First clarify whether a proposed **passive and focus-neutral** backend is independent of the quarantined GUI turn; if its operation is covered by that lock, defer live execution until reviewed reconciliation. Work offline or in a disposable, non-RIFT target to validate WGC/DXGI implementation. When eligible, compare one bounded still-frame per backend under the same pinned PID/HWND and frame: real non-black game world pixels and HUD, correct dimensions/client crop, latency, timestamp and SHA, no focus or input changes, and no replacement of an uncertain screenshot action. Even a valid image does not independently prove body yaw.

## Smallest practical next steps

1. **Verify AMD-DESKTOP**, Git status, current physical RIFT PID/start/hash/HWND, and quarantine metadata. Read this handoff, `docs/move-key-quickstart.md`, and the current `AGENTS.md`; preserve peer changes.
2. Develop a **single-purpose, capture-only C#/.NET 10 WGC prototype** bound to an exact HWND, with a one-frame timeout, no picker/input/focus operations, exact process/window identity, immutable image receipt and no-overwrite output. Exercise it first against an independent disposable non-RIFT test window. Do not rebuild the whole control framework.
3. If WGC fails or yields an invalid/blank frame, develop the **DXGI monitor-crop fallback** and compare quality/performance when capture ownership is eligible. Keep GDI `CaptureBmp` as a tested baseline only.
4. After reviewed screenshot-owner recovery, obtain one before-angle/before-frame → **single** bounded A or D key pulse (new key-send windows) → after-angle/after-frame, same PID/start/build/player. Verify release and review screenshots. **Do not replay blocked/uncertain input.** Calculate provisional signed actor-matrix delta and candidate degrees/sec with actual held-window bounds. Distinguish camera rotation from body facing.
5. Until then continue useful **read-only** native discovery and pure offline tests, not a blind navigation controller loop.

**Handoff status:** Source code is saved and `1fedc13` plus newer concurrent commits were already pushed. This handoff is a documentation-only addition. No new gameplay input, screenshot, service restart, WinApp recovery or cross-host operation was performed during its creation.
