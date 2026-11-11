# Physical RIFT screenshot capture: failed WinApp, successful GDI fallback — 2026-11-11

**Host:** AMD-DESKTOP only. **Repo:** `C:\work\riftreader2` branch `codex/modular-foundation`. **Target:** physical RIFT, not VMware.

## Outcome

- **Failure:** Two Workbridge `desktop_capture_window` attempts using Microsoft WinApp CLI 0.7.1 returned `UI_TURN_BUSY` and produced no screenshot.
- **Success:** An independent PowerShell/.NET `System.Drawing.Graphics.CopyFromScreen` call saved a virtual-desktop PNG. The command exited 0, the file exists, and its SHA-256 was independently rechecked.
- **Not yet verified:** The PNG pixels were not visually inspected to establish RIFT is visible. No new A/D keys were sent during screenshot recovery. A/D **turning** is still visually unverified, although the earlier helper sent and released both keys successfully.

## Evidence and exact identifiers

| Stage | Result |
| --- | --- |
| Machine verification | `[Environment]::MachineName` = `AMD-DESKTOP` |
| Window discovery | PID `44888`, HWND `594412` (`0x911EC`), title `RIFT`, class `TWNClientFramework`, size `1936x1048`, `isForeground=false` |
| WinApp screenshot #1 | Request `rr2adbefore20261111a` → `UI_TURN_BUSY` |
| WinApp screenshot #2 | Request `rr2basicshot20261111b` → `UI_TURN_BUSY` |
| Independent GDI capture | Workbridge `terminal_run` PowerShell with `SystemInformation.VirtualScreen`, `Bitmap`, `Graphics.CopyFromScreen`; exit code 0 |
| File | `C:\work\riftreader2\artifacts\rr2-basic-gdi-20261111.png` |
| PNG size | 5,709,874 bytes |
| Virtual desktop | `(-1920, 0, 4480, 1440)` |
| Displays | DISPLAY5: (-1920,6), 1920x1080; DISPLAY1: (0,0), 2560x1440 |
| SHA-256 (rechecked) | `8E05CE7B703AAE6918C4880D6905A4D75CE6776C2038AD304074F7E0B5A46246` |

## Root cause: known versus unknown

The WinApp/Workbridge desktop operation reported busy. **The owner of the busy desktop turn and its root cause are unknown**; another session or stale coordination state are possibilities, not established facts. Successful window discovery does not establish that screenshot capture can acquire the desktop turn. The error does not prove RIFT rejects screenshots.

The PowerShell fallback **bypassed WinApp capture** and wrote visible virtual-screen pixels. This is not equivalent to a window-targeted capture: the RIFT window might be obscured or on another display. A saved PNG and matching hash are **not proof of useful game pixels**.

The earlier A/D testing mistake was checking XYZ displacement for keys that turn in place. No position change is expected for a pure turn. This is a **verification-design failure**, not evidence of failed key delivery.

## Repeatable independent capture — PowerShell on the owning PC

Check machine identity and game window first. **This captures the entire visible desktop**, potentially including private information; inspect/redact before sharing. Use a **new filename** rather than overwriting the retained artifact.

```powershell
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = [System.Drawing.Bitmap]::new($screen.Width, $screen.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
try {
    $g.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bmp.Size)
    $out = 'C:\work\riftreader2\artifacts\rr2-basic-gdi-NEW-UNIQUE-ID.png'
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    Get-Item -LiteralPath $out | Select-Object FullName,Length
    Get-FileHash -LiteralPath $out -Algorithm SHA256
} finally { $g.Dispose(); $bmp.Dispose() }
```

## Next A/D turning-only test

1. Verify current AMD-DESKTOP RIFT PID/start/SHA, exact window, A/D bindings, and exclusive control.
2. Obtain a **before** screenshot through a working backend; **open and inspect its pixels** to ensure RIFT and stable landmarks are visible. Do not send input without this baseline.
3. Send a bounded A pulse using the existing helper, confirm insertion/hold/release, capture and inspect **after**.
4. Repeat independently for D and confirm the opposite visible rotation; check a post-release stable frame.
5. Report separately: capture success, key delivery, visible viewpoint change, and actor yaw (still unqualified). Screenshots can establish visible turning without numerically proving actor yaw.

**Durable rule:** When `UI_TURN_BUSY` repeats, do not blindly retry or rewrite the working movement helper. Inspect desktop ownership, switch to an independent capture path, verify **both bytes and actual pixels**, then resume the experiment. Record failures and successful fallbacks separately.

Related: [move-key focus failure postmortem](move-key-focus-failure-postmortem-2026-11-11.md).