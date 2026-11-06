# Offline two-snapshot follow-up from the first live typed-prefix scout — October 24, 2026

**Outcome:** A reusable, **host-only** planner was tested and applied to the **original** 2,902-byte RIFT-Lab-1 scout report. It produced **two no-overwrite, SHA-identified `snapshot-native` request files** and a provenance manifest, targeting three small neighborhoods around the observed marker addresses. **No guest snapshot was executed by this milestone.** V13 retains the live exclusive VM console until a separately guarded normal handover.

## Exact source and production

- Current game process at **source scan time**: `rift_x64.exe` PID **6940**, start ticks **639284177321390013**, on-disk executable SHA-256 **`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`**. These values are *not* proof the process remains unchanged later.
- Original source report: `artifacts/update-recovery-20261023-01/rr2-scout-oct24-01-host.json`, **2,902 bytes**, SHA-256 **`87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6`**. Exact source [live scout record](typed-prefix-scout-live-2026-10-24.md).
- New reusable implementation: `scripts/plan_typed_scout_snapshots.py`, Python standard library only, entirely offline. It requires a caller-provided source SHA-256, validates schema/marker/scope/status, exact request-versus-observed game identity, canonical addresses, coverage and intersecting holes; it rejects duplicate JSON fields and unsupported windows. It merges adjacent/overlapping windows; checks the **256-range, 64 MiB, 16,384-chunk and 64 KiB request** limits from the existing C# snapshot command; and refuses existing output directories.
- Published (ignored, recoverable) plan folder: `artifacts/update-recovery-20261023-01/rr2-typed-snapshot-plan-oct24-01/`, containing **`plan.json`**, **`sample-01.request.json`**, and **`sample-02.request.json`**. This folder was absent before first publication; reruns against the same path fail rather than overwrite.
- Manifest SHA-256: **`C8D508350162FBF5D245F65BBE5E140DD6A5A8BECD3DF67E3810CC2ADDDDE3A7`**. Both independently read request-file bytes are equal and have SHA-256 **`0BF11FCFB280BF4042DC97CA68DE98AA8099B4194F9DD2D241F34C82E7DFF92F`**. The manifest declares this request hash twice for **separate future acquisitions**, not duplicate already-captured evidence.

## Window selection

Each marker's containing 4 KiB page is captured with **two pages before** and **four pages after**. This leaves at least 16 KiB after any marker start, enough for the inspector's maximum 8,192-byte JSON payload plus wire delimiters, without widening to a whole-heap scan.

| Live scout prefix | Planned absolute snapshot range start | Byte length |
| --- | --- | ---: |
| `0xD3DB230` | `0xD3D9000` | 28,672 |
| `0xD6C0550` | `0xD6BE000` | 28,672 |
| `0xD763500` | `0xD761000` | 28,672 |

Each sample is **86,016 bytes / 84 KiB**, **3 nonoverlapping ranges** and **21 × 4,096-byte read chunks**, with a **10,000 ms** acquisition budget. This is only **0.016%** of the earlier 512 MiB scan's 536,870,912-byte cap per sample, or about **0.00091%** of reported eligible private virtual bytes. Source scout had zero holes within all selected windows, but **a later snapshot may legitimately contain inaccessible or changed bytes**.

## Verification actually run

- Focused `tests/test_plan_typed_scout_snapshots.py`: **13/13 passing**. Includes real ignored source evidence integration, exact 64-bit identity, reproducibility, merge rules, SHA mismatch, duplicate JSON fields, stale identity, invalidated source, noncanonical/duplicate prefix, insufficient coverage, intersecting hole, no-overwrite, pre-write rejection and dry-run.
- Independently decoded and SHA-checked each of the three published files; verified exact request identities, two byte-identical request digests, 86,016 selected bytes, the precise expected three windows, and the source scout SHA. **All gates passed**.
- Added the focused suite to the `scripts/validate.ps1` Python test list. The separate full `python -m unittest discover -s tests -p test_*.py -q` regression **passed 537/537 tests in 50.687 seconds**. The independently run unchanged .NET 10 Release solution suite passed **410/410 tests** (117 Live + 293 core). The PowerShell 7 composite runner was not invoked in this host-only milestone.

To preview the plan on Joey's Windows host **from `C:\work\riftreader2`** without writing files:

```powershell
C:\Python314\python.exe scripts\plan_typed_scout_snapshots.py --scout-report artifacts\update-recovery-20261023-01\rr2-scout-oct24-01-host.json --expected-scout-sha256 87A67D74E2EC8E54530944B4C24893F605719D437F74A3F03FD81D367B9771F6 --output-directory artifacts\update-recovery-20261023-01\rr2-typed-snapshot-plan-oct24-01 --dry-run
```

Remove `--dry-run` **only with a new, nonexistent output directory**. The actual artifact above already exists and is deliberately protected from overwrite.

## Pending distinct live gate

1. Verify current VMware PID/start/log epoch, the RIFT game PID/start/executable SHA, coordinator authenticated health and canonical SQLite queue **again**. If the game epoch changed, **discard these session-address requests** and rescout.
2. Prepare an exactly pinned V14 successor while V13 is healthy; request the **normal V13 STOP**, verify release and no competing authority, then use existing exclusive guarded guest-console operations. Do not bypass V13, open concurrent VNC, or manually unblock the queue.
3. Verify the existing published V2 guest binary and **each request's original digest** in guest before running read-only `snapshot-native` twice, with **different unused report paths** and independent later UTC capture windows. The same request bytes do not make two outputs independent; actual timestamps/content and fresh identity checks do.
4. Return both entire reports to host with one-use content-hash-pinned transfer and separate byte/hash checks, close shell, restore V14 via the normal queue-cleanup path and verify healthy console ownership.
5. Run the already-validated strict [two-snapshot typed-wire inspector](../reference/typed-wire-snapshot.md); preserve `blocked`/`unavailable` results. `advanced-in-covered-scope` needs independently advancing complete producer content, not only a prefix hit. Only then pursue a same-epoch native/Lua XYZ field comparison.

**No current advancing typed frame, native XYZ equivalence, or whole-process coverage is claimed by this host-only plan.**
