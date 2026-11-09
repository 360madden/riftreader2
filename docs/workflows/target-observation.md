# Target observation

Run `scripts/observe_target.py` from the owning Windows checkout
(`C:\work\riftreader2` on AMD-DESKTOP), using the verified repository virtual environment.
The endpoint's friendly name is not identity proof: the entry point checks the
actual host against both the selected target and required `--expected-host`.

## Choose the explicit target

| Target | Expected host | Capture backend / availability |
| --- | --- | --- |
| `lab2` | `AMD-DESKTOP` | Managed controller / guest-agent capture |
| `physical-amd-desktop` | `AMD-DESKTOP` | Microsoft.WinAppCli host-window capture |
| `physical-legion` | `LEGION` | Physical adapter; not live tested on LEGION |
| `lab1` | `AMD-DESKTOP` | Refused: managed capture not yet qualified |

There is no cross-target or cross-machine fallback. A Lab 2 failure does not
authorize a physical capture. Physical routing does not import VMware or guest
authentication code. Existing VM-specific cached credentials remain owned and
reused by the established guest helpers when needed; supply no new secrets.

## Screenshot-only default

Enter in PowerShell on AMD-DESKTOP, with the repository as the working directory:

```powershell
& 'C:\work\riftreader2\.venv\Scripts\python.exe' scripts/observe_target.py --target lab2 --expected-host AMD-DESKTOP --preview
```

Omitting `--output` selects a unique directory under the existing artifacts
location. To select it yourself, add `--output <fresh absolute directory>`.
The directory must be new; do not reuse a failed run or another target's output.
Default Lab 2 observation requests capture only, not native-vitals sampling.

For the already-implemented candidate native-vitals retrieval, explicitly add:

```powershell
& 'C:\work\riftreader2\.venv\Scripts\python.exe' scripts/observe_target.py --target lab2 --expected-host AMD-DESKTOP --native-vitals --preview
```

This retains existing candidate labels, source/build/session identity,
freshness checks, and cleanup. Physical native-vitals routing is not qualified.

## Physical screenshot

Physical capture may focus RIFT. Use the foreground flag only with applicable
shared-desktop ownership and authority; omit it while Joey is using the PC
unless that foreground change has been authorized.

```powershell
& 'C:\work\riftreader2\.venv\Scripts\python.exe' scripts/observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --allow-foreground-change --preview
```

The default without `--allow-foreground-change` is a blocked result. The
registered Workbridge backend retains its shared desktop turn and quarantine
checks; the flag does not override those checks or authorize game input.
Fresh PID/start/build/HWND checks bracket the capture; absent RIFT reports
`not-running`, not another target's image.

## Delivery and failures

Success is `verified-awaiting-visual-review`, not visual approval. The result
identifies the target, workflow, backend, capture time, original image and hash.
Lab 2 pixels are `managed-controller/guest-agent`; physical pixels are
`Microsoft.WinAppCli-host-window`. Neither proves native VMware screenshot
capture. Capture success does not qualify field semantics or gameplay actions.

`--preview` adds a bounded, non-authoritative JPEG (at most 40,000 bytes).
`--preview-width` defaults to 840 and accepts 500–1600. Preserve the original
image/hash, provenance and review age. In ChatGPT, combine predictable command
completion and delivery, parse the JSON, and emit the preview as an image
(`image("data:image/jpeg;base64," + result.preview.base64)` in `functions.exec`);
do not print the base64. Review the returned pixels before a visual decision.

Blocked results exit 2 and retain a specific safe reason. Do not display an
earlier image or automatically retry denied/busy/quarantined operations.
`managed-runtime-changed` requires a proper controller refresh through its
existing managed lifecycle, followed by fresh admission. Do not rewrite its
receipt, remove its lock, or bypass runtime identity checks. Preserve cleanup
and shared desktop ownership while resolving the actual blocker.

## Live check: 2026-11-09

Lab 2 returned an original 1211×702 screenshot captured at 09:25:38 UTC:
workflow 4.197 s; total with preview 4.462 s. Cleanup was verified after a
graceful host-controller refresh, with the VM and game unchanged.
Physical AMD-DESKTOP correctly returned `not-running`; a positive image test remains pending.

Lab 1 remains on its existing controller: guest link disconnected; queue blocked/unheld without a cleanup receipt. Its runtime refresh and new-route qualification remain pending.
Focused validation: 146 tests passed; an actual wrong-host request was refused.
