# RR2 Physical RIFT C# Move-Key Helper — Combined Engineering and Test Report

**Report date:** 2026-11-11 (America/New_York)
**Verified development machine:** AMD-DESKTOP
**Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`
**Scope:** Standalone RR2 .NET 10 helper, physical RIFT Live x64, Windows focus/input, native XYZ feedback, screenshot verification and failures. **No VMware or LEGION work.**

**Latest update (Nov 11, after report creation):** The November 9 Workbridge desktop lock was archived and WinApp screenshots resumed. Physical RR2 A/D 500 ms key pulses were then independently checked against three actual game screenshots: A visibly rotated the viewpoint; D visibly reversed it toward the initial view. **A/D visual turn response is now observed** (actor yaw/turn rate still unqualified). See [the A/D visual-turn verification and steering continuation](physical-ad-turn-visual-verification-2026-11-11.md). The original findings below describe the earlier incomplete state.

## Executive status

**Working:** The corrected RR2 helper acquired RIFT foreground focus, inserted bounded scan-code key presses, and reported successful release for W, S, Q, E, A and D. Same-owner native XYZ candidates changed in directionally consistent ways for W/S/Q/E. A and D were delivered but **not visually verified as turns**. A separate PowerShell/.NET virtual-desktop screenshot capture succeeded after the WinApp CLI capture backend repeatedly returned `UI_TURN_BUSY`.

**Not proven:** independent Lua/UI game-consumption confirmation for translation; actor yaw or actual A/D rotation; screenshot pixels containing RIFT; post-release visual stabilization; cross-restart and cross-machine reliability. The helper's output explicitly retains `gameResponseVerified=false`.

This is a combined reference, **not** a new live test. All process IDs and addresses below are historical pins; reacquire fresh identity for every future run.

## 1. What the helper does

The RR2-owned `src/RiftReader2.Live/Control/MoveKeyCommand.cs` runs under .NET 10. It targets an exact physical `rift_x64.exe` process/window, establishes foreground focus using Windows GUI input-thread attachment before `SetForegroundWindow`, inserts scan-code keyboard input via Windows `SendInput`, holds for a bounded interval, and releases the key. Optional before/after native XYZ readings report a **candidate** position delta.

Important distinctions: `windowsInputInserted=true` means Windows accepted the insertion, not that RIFT necessarily acted on it. `releaseSucceeded=true` records the helper's release action, not independent visual evidence that turning/movement stopped. The candidate native XYZ reader is not a second independent Lua/UI channel.

Key semantics for this RIFT binding: **W forward; S backward; A turn left; D turn right; Q strafe left; E strafe right.** A/D turning in place should not be evaluated by XYZ displacement.

## 2. Focus failure, known-good comparison, and successful repair

Earlier RR2 versions attempted `SetForegroundWindow` directly and then used `AttachThreadInput` only as a fallback. The real test reported: **"Windows denied RIFT foreground after direct and attached-thread activation; no input sent."** This was a foreground-activation failure **before game input**, not evidence of RIFT blocking software movement.

The assistant's engineering error was repeatedly changing RR2's focus implementation without first executing the known-good original RiftReader binary unchanged. Joey requested the decisive A/B test. The legacy helper successfully focused the same RIFT window from Edge and sent W for 750 ms. Its focus implementation attached GUI input threads **before** requesting foreground, waited while attached, then detached. RR2 was changed to the same essential synchronous ordering and added explicit focus diagnostics. **34/34 focused .NET 10 tests passed.**

An incidental launch failure followed when the assistant guessed a DLL output path without the `win-x64` segment. Correct path:
`src\RiftReader2.Live\bin\Debug\net10.0-windows\win-x64\RiftReader2.Live.dll`.
No input was sent during that path failure. The subsequent physical W test succeeded.

**Live W test:** requested 750 ms; observed 770.2 ms; foreground changed Edge PID 59072 to RIFT PID 44888, both input-thread attachments true; Windows insertion and key release succeeded. Native same-owner X/Z displacement candidate **4.651589 units** (delta X -4.576660, delta Z +0.831543). No independent game-response confirmation.

**Relevant commits:** `5cfb5b32` (direct-first attempt), `fc9aa86f` (unsuccessful fallback), `6643a34d` (corrected focus and W evidence), `790e39fa` (durable standalone focus postmortem). The full accountability and detailed A/B evidence are in [the focus postmortem](move-key-focus-failure-postmortem-2026-11-11.md).

## 3. Physical movement key test matrix — November 11

Machine AMD-DESKTOP; physical `rift_x64.exe` PID `44888`, HWND `594412` (`0x911EC`), process-start UTC ticks `639299470183328173`, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. These are **historical run identities only**.

| Key | Purpose | Requested hold | Observed hold | Native candidate delta X/Z | Planar candidate displacement | What passed |
| --- | --- | ---: | ---: | --- | ---: | --- |
| W | Forward | 750 ms | 770.2 ms | -4.576660 / +0.831543 | 4.651589 | Focus, insertion, release, candidate motion |
| S | Backward | 500 ms | 514.0 ms | +1.523926 / -0.276855 | 1.548870 | Insertion, release, candidate motion |
| Q | Strafe left | 500 ms | 519.9 ms | +0.558105 / +3.077881 | 3.128072 | Insertion, release, candidate motion |
| E | Strafe right | 500 ms | 511.1 ms | -0.548828 / -3.025879 | 3.075249 | Insertion, release, candidate motion |
| A | Turn left | 500 ms | 510.2 ms | 0 / 0 | 0 | Insertion and release only; turning unverified |
| D | Turn right | 500 ms | 510.1 ms | 0 / 0 | 0 | Insertion and release only; turning unverified |

All five later actions reported `windowsInputInserted=true`, `boundedActionCompleted=true`, `releaseSucceeded=true`, `targetLost=false`, and `cancelled=false`. The Q/E vectors were approximately opposite, supporting expected strafing semantics. **None** of these readings independently proves the game consumed the input; the output labels them `candidate-native-xyz-feedback` and `gameResponseVerified=false`.

**Test-design failure:** The assistant initially measured A/D with the same XYZ metric used for translation. Pure turning changes orientation without changing XYZ. A/D did **not** fail the helper's delivery check; **the test failed to verify the relevant behavior**. Screenshots were required for immediate qualitative visual verification, not an entirely new native yaw reader.

## 4. Screenshot backend failure and successful fallback

The first attempt to obtain an A-before-turn screenshot used Workbridge `desktop_capture_window`, backed by **Microsoft WinApp CLI 0.7.1**. Window enumeration identified the exact RIFT PID/HWND/title/class, but capture returned `UI_TURN_BUSY`. A second independent basic screenshot request through the same backend returned the same error. No new A/D pulses were sent after this capture blocker.

The precise owner/cause of the busy desktop turn is **unknown**. It may reflect competing or stale desktop-control coordination, but no such owner was identified. This is not evidence that RIFT or DirectX rejects screenshot capture.

After Joey requested an alternate method, PowerShell directly invoked `System.Drawing.Graphics.CopyFromScreen` on the **whole virtual screen**, without the WinApp capture backend. Command exit code was 0; the PNG was saved and its hash rechecked:

- File: `C:\work\riftreader2\artifacts\rr2-basic-gdi-20261111.png`
- Size: **5,709,874 bytes**
- Virtual screen: **4480 x 1440**, origin (-1920,0), two displays
- SHA-256: `8E05CE7B703AAE6918C4880D6905A4D75CE6776C2038AD304074F7E0B5A46246`
- **Limitation:** The actual PNG pixels were **not visually inspected** to confirm RIFT is visible. This was a successful screenshot **file acquisition**, not a completed A/D visual verification.

The reproducible PowerShell capture snippet and full error details are preserved in [the screenshot recovery report](physical-rift-screenshot-backend-failure-and-gdi-recovery-2026-11-11.md). Whole-desktop screenshots may include other applications and sensitive content; inspect before sharing.

## 5. Practical future workflow

1. **Verify host and live identity first:** AMD-DESKTOP only for this run; reacquire RIFT PID, process start, executable SHA, HWND, and binding state. Never reuse the recorded historical PID/HWND as defaults.
2. **Check screenshot capture before any turning pulse:** Acquire a baseline with a functioning backend, **inspect the image pixels**, and ensure RIFT and stationary landmarks are visible. If WinApp returns `UI_TURN_BUSY`, diagnose the desktop turn or use the independent PowerShell capture. Do not keep blindly retrying the same backend.
3. **Test A then D separately:** Use the existing corrected helper with bounded holds and explicit insertion/release results. Capture before and after each; compare opposite viewpoint rotation and a stable post-release frame. Do not treat unchanged XYZ as a turning failure.
4. **Keep evidence levels distinct:** (a) correct process/window, (b) foreground acquired, (c) input inserted and released, (d) native XYZ candidate changed, (e) visual game response, (f) independently qualified actor yaw. Do not collapse them into a single "verified" claim.
5. **Preserve the known-good mechanism:** If focus fails, run the unchanged legacy diagnostic comparator under the same verified conditions **before** changing RR2's focus code. Preserve attachment order, GUI thread identity, timing, and fail-closed release. The legacy executable remains reference-only; RR2 stays standalone.
6. **Keep it lean:** Reuse working .NET 10 helper and capture methods, do not introduce a new screenshot framework or heading reader merely to test A/D delivery. Record concise receipts; escalate only when evidence points to a new failure layer.

## 6. Outstanding work and confidence

| Capability | Current evidence | Status |
| --- | --- | --- |
| Correct host/target identification | Machine and process/window/build pinned in tested session | **Verified for that session** |
| Foreground focus from Edge | Same-window A/B comparison and corrected RR2 W run | **Verified in one live context** |
| Windows input insertion/release W/S/Q/E/A/D | Six physical helper receipts | **Verified as helper/Windows events** |
| W/S/Q/E positional response | Native candidate XYZ changes, Q/E opposite vectors | **Strong candidate, not independent game proof** |
| A/D visible turning | No successful before/after visual comparison | **Pending** |
| GDI screenshot file creation | File size, successful exit, SHA-256 recheck | **Verified file capture** |
| RIFT actually visible in saved screenshot | No pixel inspection | **Pending** |
| Actor yaw and turn rate | No current qualified heading reader | **Not established; unnecessary for immediate helper test** |
| Restart and machine parity | Not tested by this series | **Not established** |

## 7. Durable engineering lessons

**Do not confuse a failed layer with the next layer.** Focus failure means no input was sent; successful `SendInput` means only insertion; native XYZ is a candidate movement response; A/D requires orientation or visual evidence; saved PNG bytes do not prove useful RIFT pixels.

**Run the known-good thing before speculative rewrites.** The working legacy helper exposed the missing focus ordering. **Switch capture backends when the backend itself is blocked.** The GDI capture proved that one failed WinApp screenshot route was not the only option. **Match the test metric to the action.** Translation uses XYZ; turning uses visual rotation or actor yaw.

## Original durable source reports

- [Focus failure, A/B proof and corrective rule](move-key-focus-failure-postmortem-2026-11-11.md), committed `790e39fa`.
- [WinApp screenshot failure and GDI recovery](physical-rift-screenshot-backend-failure-and-gdi-recovery-2026-11-11.md), committed `11431b5`.
- [Movement helper operator quickstart](../move-key-quickstart.md).
- [Current RR2 status](../status.md).

**No additional gameplay input or screenshots were generated in creating this combined report.**