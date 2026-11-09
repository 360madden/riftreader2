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
| `lab1` | `AMD-DESKTOP` | Implemented managed capture; current controller recovery blocks live qualification |

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
Both VM targets default to capture only, not native-vitals sampling.
For Lab 1, use the same command with `--target lab1`; do not reuse Lab 2's output.
Lab 1 uses joined admission/capture/verification with its own exact task, VM, game,
queue resource and cleanup proof. Lab 1 split phases and native-vitals routing are
not enabled. The older Lab 2 commands and native confirmation behavior remain compatible.

For the already-implemented candidate native-vitals retrieval, explicitly add:

```powershell
& 'C:\work\riftreader2\.venv\Scripts\python.exe' scripts/observe_target.py --target lab2 --expected-host AMD-DESKTOP --native-vitals --preview
```

This retains existing candidate labels, source/build/session identity,
freshness checks, and cleanup. Physical native-vitals routing is not qualified.

## Native position and vitals without a screenshot

For an on-demand Lab 2 data read, run this from `C:\work\riftreader2` in PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' scripts/read_native_telemetry.py --lab lab2 --expected-host AMD-DESKTOP
```

This reuses or recovers the managed controller and existing native readers. It
needs neither a Lua reader/bind nor a screenshot, sends no game input, and returns
JSON containing XYZ, health, energy and an honest unavailable mana result when
applicable. Wrong-host requests stop before dependency startup. Both source
reports retain their own timestamps, hashes and exact game/VM/agent identities;
a mismatched unit key or changed postflight identity rejects the combined result.
Unit keys are decimal strings to avoid precision loss in JSON consumers.

These are **sequential candidate observations, not an atomic snapshot or qualified
movement feedback**. Successful acquisition does not establish field semantics,
passive freshness or restart durability. Do not replace an expired Lua movement
source with this output. A blocked read exits 2; no target or source fallback is
performed. On 2026-11-09, two actual Lab 2 reads completed in 5.53 and 6.22 seconds,
with advancing acquisition timestamps and the same unit identity. These are
sample timings, not a throughput guarantee.

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
VM pixels are `managed-controller/guest-agent`; physical pixels are
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
`controller-managed-owner-refused` means the existing controller failed ownership
admission, not that VM credentials are missing. Inspect the strict receipt resolver
for the underlying reason. Unknown exceptions remain redacted.

## Compact saved-image transport

When image delivery is text-only, `scripts/quick_review_capture.py --capture PATH
--sha256 ORIGINAL_SHA --compact` emits a WebP preview capped at 4,500 bytes,
with the original image hash and a separate preview hash. The default JPEG
contract is unchanged. An explicit `--crop LEFT TOP RIGHT BOTTOM` returns a
source-coordinate detail crop; its bounds are checked and reported. The command
only reads an existing capture: it does not focus the desktop, acquire a GUI
turn, approve an image, or change capture timestamps. A small or blurred preview
is not sufficient evidence merely because it arrived quickly.

The console's existing 60-second and movement capture's 45-second review limits
remain unchanged. A detail crop helped complete an exact Lab 2 reader rebind on
9 November, but full-frame movement review delivery still missed its deadline.
`control_client._arm` now also rejects missing, invalid, future or expired capture
timing locally before reserving an arm artifact or sending `/api/arm`; the guest
continues to perform its own checks. A shorter advertised window is honored;
metadata cannot widen the maximum 45-second movement review window.

The AMD host's `rr2-review-chatopen-c03` desktop capture remains quarantined under
the running Workbridge owner. Saved guest-image transport does not clear or
reconcile that host lock. Do not delete it or replay a quarantined operation.

## Live check: 2026-11-09

Lab 2 returned an original 1211×702 screenshot captured at 09:25:38 UTC:
workflow 4.197 s; total with preview 4.462 s. Cleanup was verified after a
graceful host-controller refresh, with the VM and game unchanged.
Physical AMD-DESKTOP correctly returned `not-running`; a positive image test remains pending.

Lab 1 remains on its existing controller: guest link disconnected; queue blocked/unheld without a cleanup receipt. Its runtime refresh and new-route qualification remain pending.
Focused validation: 146 tests passed; an actual wrong-host request was refused.

## Follow-up implementation and benchmark: 2026-11-09, 06:14 EST

Lab 1 identity, strict two-proof task admission and target-pinned capture routing
are now implemented and covered offline. A live Lab 1 request stopped at dependency
admission; the read-only resolver identified `managed-runtime-changed`. Its guest
remains disconnected, and its queue blocked/unheld without prior cleanup proof.
No lock was removed and no controller, guest or game was forcibly restarted.

Lab 2 completed 12/12 verified captures (3 warmups, 9 measured) using the same
VM/game/controller generation. Host-process wall-time medians: legacy capture-only
4.803 s, new capture-only 4.639 s, legacy native+UI 6.598 s. The small equal-work
difference is not established as a backend speedup. Omitting unrequested native
diagnostics saved about 1.96 s / 29.7% in this sample.
See [the benchmark](../validation/observation-workflow-benchmark-2026-11-09.md).

Physical AMD RIFT remained `not-running`; positive physical capture is still pending.
Final focused Python validation: 269 passed. Helper-manager PowerShell mocks passed.
