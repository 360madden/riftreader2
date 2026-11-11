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

## November 11 follow-up: root of repeated `UI_TURN_BUSY` refusals identified

**New finding (read-only AMD-DESKTOP Workbridge inspection):** The repeated November 11 `desktop_capture_window` refusals were caused by a **retained exact-path Workbridge GUI lock left by a different November 9 operation**, not by proven failure of the WinApp CLI screenshot engine. This supersedes the earlier *unknown owner* assessment for the repeated refusals, but not for the original November 9 child's termination subcause.

- Lock: `C:\work\workbridge-mcp\.tools\desktop-evidence\desktop-input-turn.lock`; SHA-256 `7E26BB336B3232DC204137CA92ED4E304439CBBEBC8B6352203F9CD63D37747B`.
- Owner stamp: `leaseId=1052beed-a941-410f-a5bf-3bc94d67f420`, `requestId=rr2-review-chatopen-c03`, Workbridge owner PID `33712`, target `python.exe` PID `57952`/HWND `1578652`, acquired `2026-11-09T15:40:10.007Z` (10:40:10 EST).
- Matching quarantine: `desktop-turn-quarantine-1052beed-a941-410f-a5bf-3bc94d67f420.json`; SHA-256 `2CF72B2F564D6396B1AB01750617E1D946E8395A960C7AFD7FC026FE3C2844BF`; created `2026-11-09T15:40:10.617Z` (610 ms later); `reasonCode=DESKTOP_TREE_UNSETTLED`, `automaticRetryAllowed=false`.
- Inspection on November 11: owner PID `33712` and target PID `57952` were absent, the admission lock was absent, the matching lock and sidecar remained. Windows last boot was November 9 at 4:05 PM EST, after the original lock was created.
- Workbridge source `src/desktop-registration.ts`: exclusive `open(lockPath, 'wx')` fails with `EEXIST`, mapped directly to `UI_TURN_BUSY` **before** calling the image-capture action. The sidecar deliberately prevents automatic retry. `src/desktop-cli-runner.ts` treats timeout, abnormal wrapper exit, invalid wrapper response and several other paths as `DESKTOP_TREE_UNSETTLED`, so the original short November 9 cause is **not recoverable from these records alone**.
- Existing `gui-turn-reconcile-readonly.ps1` with exact lock/lease/request pins returned `reasonCode=OWNER_PID_NOT_PRESENT`, `releaseEligible=false`, `manualArchiveDecisionRequired=true`. This does not prove historical child-tree settlement.
- Existing `Archive-DesktopQuarantine.ps1`, run **without** `-Execute` and exact lock+sidecar pins, exited 0 with `readyForManualReview=true`, `releaseEligible=false`, `archiveCreated=false`. This is **not approval or execution** of recovery.
- Workbridge had archived an *older, distinct November 2* screenshot quarantine on November 5 with its reviewed maintenance script and then successfully captured RIFT screenshots. The November 9 quarantine is a new incident, not the unreleased November 2 guard.
- Searching existing Workbridge autostart logs did not find the original request ID; a deeper cause such as specific WinApp timeout or wrapper exception remains **unproven**.

**Next safe action, only with explicit approval:** Re-run pinned evidence, quiescence and owner checks immediately before and inside the existing **operator-reviewed** one-shot archival procedure, with a fresh unique operation ID. The script protects and preserves byte-exact originals and does not replay the historical capture. Do **not** delete a guard manually, rerun the quarantined request ID, bypass a live maintenance gate, or claim cleanup without archive and subsequent capture verification. **No lock, sidecar, Workbridge runtime, RIFT process, or screenshot was changed during this follow-up investigation.**

## November 11 approved archival and live screenshot recovery — verified

Joey explicitly authorized **archiving the exact November 9 lock and matching quarantine record**, preserving both as evidence rather than deleting them. This section supersedes the preceding investigation's still-pending **next action**; it does not change the unresolved historical original screenshot outcome.

- Executed existing `C:\work\workbridge-mcp\scripts\Archive-DesktopQuarantine.ps1` with `-Execute` and exact lock SHA-256 `7E26BB336B3232DC204137CA92ED4E304439CBBEBC8B6352203F9CD63D37747B`, sidecar SHA-256 `2CF72B2F564D6396B1AB01750617E1D946E8395A960C7AFD7FC026FE3C2844BF`, lease ID `1052beed-a941-410f-a5bf-3bc94d67f420`, request ID `rr2-review-chatopen-c03`.
- Command receipt `rr2-gui-archive-approved-nov09-20261111a`: `passed`, exit code 0, `ok=true`, `mode=archived`, `newActionPerformed=false`, `priorActionOutcome=unknown_outcome`. Archive: `C:\work\workbridge-mcp\.tools\desktop-evidence\recovery-archives\rr2_gui_archive_20261111_approved_01`. Workbridge maintenance handles admission, quiescence and file identity checks, makes byte-exact durable backups and relocates sidecar **before** guard.
- Independent short postcheck `rr2-gui-archive-short-postcheck-20261111c` on AMD-DESKTOP: zero active `desktop-input-turn.lock` / `desktop-turn-admission.lock` / quarantine sidecars; **four of four** backup+relocated lock/sidecar files exist with original SHA-256 values; `manifest.json`, `journal.jsonl` and `completed.json` exist.
- Fresh, separate `desktop_capture_window` request `rr2postarchivephysical20261111a` on physical RIFT PID44888/HWND594412 **succeeded** (not replayed) through WinApp CLI: PNG `1920x1032`, `3,902,880` bytes, SHA-256 `93BC65FAB819E0BD13D1FD214E6279CDD1099E57365CD96FD1F3C3288D4A9BBF`, `inputInjected=false`, timestamp `2026-11-11T14:36:55.243Z`. Return receipt independently verified the image dimensions, digest and bytes.
- Post-capture health `rr2-gui-postcapture-health-20261111a`: **zero active desktop locks**; capture PNG exists and its SHA-256 was rechecked; archive `completed.json` records `newActionPerformed=false`.
- **No game input was sent** and no RIFT process was restarted; any screenshot foreground effect is a separate window-capture behavior. This proves the **capture backend works again after archival** for this test, not that it will never quarantine again. The original November 9 child's exact failure subcause and its screenshot outcome remain unknown. A/D visually observed turning still requires an actual before/after comparison.

**Prevent recurrence:** Workbridge currently retains a GUI lock on `DESKTOP_TREE_UNSETTLED` without automatic expiry. Future failures should report the exact lock+sidecar owner metadata, inspect the process tree, preserve both original SHA-pinned artifacts, and use approved reviewed archival if necessary—not manually delete or automatically override the guard.
