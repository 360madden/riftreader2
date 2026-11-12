# RR2 physical GPU window capture probe — AMD-DESKTOP

**Status:** Verified on physical RIFT on AMD-DESKTOP, November 11, 2026. WGC captured the game world and HUD during the Atank turn trials.

A standalone C#/.NET 10 one-shot window capture candidate using [WgcSharp 1.1.1](https://www.nuget.org/packages/WgcSharp/1.1.1). This project is isolated from RR2's working input helper. It adds no service, UI automation tree, keyboard/mouse hook, focus request, game addon, or process-memory reader.

## Why these backends for RIFT

- **`wgc` (preferred):** Windows Graphics Capture targets a verified game HWND and can capture GPU-rendered frames, including the borderless DirectX 9 RIFT client on Windows 11 if the window is capturable.
- **`dxgi` (fallback):** desktop-duplication capture of the visible output and window crop. Output may include occluding windows and can fail if RIFT is hidden, minimized, cloaked, or on another desktop.
- **Existing GDI `CaptureBmp`:** retain as diagnostic only. A direct window-DC `BitBlt` cannot be assumed to include Direct3D game pixels.
- No automatic fallback: the requested mode is always recorded in the JSON receipt. A single capture attempt is allowed per command.

## Commands

From **PowerShell on AMD-DESKTOP**:

```powershell
cd C:\work\riftreader2
dotnet restore tools\physical-wgc-probe\PhysicalWgcProbe.csproj --locked-mode
dotnet build tools\physical-wgc-probe\PhysicalWgcProbe.csproj -c Debug --no-restore
dotnet run --project tools\physical-wgc-probe\PhysicalWgcProbe.csproj -c Debug --no-build -- --self-test
```

For a single local WGC capture, run the following from the repository root with Python and Pillow installed. Choose the current PID from the process listing. The observer writes a new artifact directory and returns the image and receipt paths.

```powershell
Get-Process rift_x64 | Select-Object Id, MainWindowTitle
python scripts/observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --physical-pid <CURRENT_PID> --physical-capture-backend wgc
```

For *read-only identity inspection*, supply current values for a visible, non-cloaked target from the same machine:

```powershell
dotnet run --project tools\physical-wgc-probe\PhysicalWgcProbe.csproj -c Debug --no-build -- `
  --inspect --host AMD-DESKTOP --process rift_x64 `
  --pid <CURRENT_PID> --start-ticks <CURRENT_START_UTC_TICKS> `
  --sha256 <CURRENT_EXE_SHA256> --hwnd 0x<CURRENT_HWND> --backend wgc
```

This prints target metadata only; **no pixels or input**. Values in this file are placeholders, not reusable process pins.

Direct invocation requires `--capture`, all the same exact target identity fields, an explicit `--allow-one-capture` flag, `--backend wgc|dxgi`, and `--out C:\work\riftreader2\artifacts\NEW_UNIQUE.png`. The output must be a new file under RR2 `artifacts` (no overwrite). The command writes a PNG and JSON receipt with image hash, frame dimensions, capture duration, before/after pinned identity, and sampled pixel diversity. **Do not run until reviewed Workbridge GUI ownership is available.**

## Verified on AMD-DESKTOP

- SDK **10.0.302**, Win-x64 target, WgcSharp 1.1.1 restore and Debug build: **0 errors / 0 warnings**.
- `--self-test`: **9/9 checks passed**, including argument rejection, simulated occupied/quarantined desktop, and synthetic BMP color diversity.
- A deliberate no-frame `--capture` test while the existing quarantine was active returned exit 2, `desktop-turn-recovery-required`. Neither PNG nor JSON receipt was created, no game input was sent, and the old shared Workbridge lock remained untouched.
- Current physical RIFT process at the read-only check: **PID 18092**, start ticks **639300391441133615**, HWND **0xE0842**, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. **These are historical session values; reacquire them before reuse.**
- Read-only `--inspect` validated target process and window, but returned **`window-cloaked`**, so the game window was not currently suitable for WGC capture. Workbridge's separate read-only `desktop_windows` reported that HWND as not foreground. No focus/window movement was requested.
- Three preserved pre-quarantine physical RIFT screenshots (`artifacts/physical-turn-visual-20261111/{before-a,after-a,after-d}.png`) were independently SHA-256-verified, each **1920×1032**, 91 distinct sampled colors, just 1% dark samples. They are valid non-black reference game images; this **does not** validate WGC/DXGI output.

## Desktop gate and limitations

The probe tests the presence of the Workbridge `desktop-input-turn.lock`, `desktop-turn-admission.lock`, and any `desktop-turn-quarantine-*.json` **before any capture** and again **before publishing**. It never creates, rewrites, clears, archives, or bypasses Workbridge's locks. This is an observational fail-closed check, **not an exclusive shared lease** and not a substitute for Workbridge's owner reconciliation. A present lock or quarantine blocks the capture attempt.

On November 11, the local observer captured a 1920 x 1032 physical RIFT frame with the same process and window identity before and after capture. The frame showed Atank and the practice dummies. The receipt recorded no input or focus change. Later trials paired screenshots with native actor-pose samples. Camera and body yaw still need independent measurements. DXGI remains unverified on this client.

The first observer frame and receipt were retained locally under `artifacts/observe-wgc-4ff136b278354b97a5fe21c872e04b41/`. The rebased turn trial is under `artifacts/rebased-ad-20261111-203431/`.
