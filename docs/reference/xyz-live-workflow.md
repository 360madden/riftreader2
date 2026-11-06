# Repeatable live XYZ workflow

Use `scripts/run_xyz_workflow.py` to repeat the proven guest CLI collection and
one supervised guarded W pulse. It reuses the installed reader, the current
sole controller and the existing native/Lua comparison. It does not deploy a
new reader, open another VM console or recover changed game builds.

## Local setup

Store a small configuration under ignored `artifacts/`, for example
`artifacts/xyz-workflow.json`. It contains no passwords:

```json
{
  "schemaVersion": 1,
  "hostPlan": "C:\\work\\riftreader2\\artifacts\\...\\current-host-plan.json",
  "hostProcess": "C:\\work\\riftreader2\\artifacts\\...\\current-host-process.json",
  "vmrun": "C:\\Program Files\\VMware\\VMware Workstation\\vmrun.exe",
  "guestDirectory": "C:\\RIFT_TRANSFER\\installed-reader",
  "readerSha256": "REPLACE_WITH_VERIFIED_INSTALLED_READER_SHA256",
  "profile": "C:\\work\\riftreader2\\config\\position-candidate-profile.json"
}
```

Use the actual reviewed plan/process receipts and installed reader hash. Host
recovery may require updating those two paths; normal RIFT restart does not
require inserting a new game PID. The runner obtains the current game identity
from authenticated controller status and pins it for the whole run. It checks
the VM/controller identity, runtime/config hashes, game build, reader and
profile before relying on them. The independent comparison currently supports
the proven `0x32E0200` / `0x320,0x324,0x328` recipe only.

Build the existing offline CLI normally before use. Validate configuration
without credentials, live process queries or input:

```powershell
python scripts/run_xyz_workflow.py --config artifacts/xyz-workflow.json
```

## Run one trial

Keep RIFT stationary and foreground in a clear area. Select a new output
directory each time:

```powershell
python -u scripts/run_xyz_workflow.py --config artifacts/xyz-workflow.json --output artifacts/validation/xyz-run-01 --run
```

The screenshot review reads from the interactive terminal. Keep that terminal
attached through the review; agent-launched runs must request `tty: true`.
Piped or closed stdin cannot approve movement and fails safely without a pulse.

1. A previously cached guest login is reused automatically. On the first run,
   enter the guest Windows account in the local Windows dialog. Add
   `--cache-login` to store it in Windows Credential Manager after VMware verifies
   it; Joey authorized this on October 25 to avoid repeated entry. Run 02 stored
   a verified prompted login and run 04 reused it without prompting. The VM
   encryption credential remains a separate existing Windows entry. Neither
   password belongs in configuration, chat, receipts or exported evidence.
   VMware's own CLI requires secret arguments in its short-lived process; the
   helper never prints or retains those arguments. Failed cached authentication
   stops with a diagnostic rather than guessing or repeatedly prompting.
2. The runner takes three stable native samples, an independent pointer read and
   a bounded Lua scout. It transfers and verifies the original files through
   VMware Tools.
3. It acquires the existing access queue and saves a fresh game screenshot.
   Inspect the printed image path. Within 22 seconds, enter
   `approve CAPTURE_ID clear ground; no text entry or dialog`, using the actual
   printed capture ID and an accurate review note. An agent can inspect that
   image and submit the review under existing user authorization. Timeout or
   rejection sends no pulse and performs cleanup.
4. Exactly one requested 100 ms W pulse is issued. STOP/release and queue cleanup
   run even on failure. The runner then takes the after-capture, checks every
   cross-phase Lua pair, selects the newest advancing pair, and runs the existing
   independent native/Lua motion reviewer.
5. The credential session closes. `summary.json`, `motion-review.json`, final
   controller status and a verified `evidence.zip` remain in the output directory.
   The ZIP excludes private arm tokens. It retains original diagnostics and
   explicit partial-scan limits.

PowerShell 5 phase packaging sums hashtable file sizes explicitly. Archive
verification normalizes Windows separators for comparison while retaining the
existing traversal, absolute-path and NUL protections.

## October 25 live acceptance

`artifacts/validation/xyz-repeatable-20261025-04/` completed with cached guest
credentials and no prompt. Baseline and after transfers verified 19 and 17
original files. One guarded 100 ms W pulse completed with successful release;
native/Lua displacement was **0.665936 / 0.673551 units**, maximum per-axis
displacement residual **0.0078125**, and **6/6** cross-phase comparisons advanced.
Final status was foreground, disarmed, idle and no inputs held. The verified
63-file export is 1,712,950 bytes, SHA-256
`7C68EDED513C16981F49D54B0C6813F1AEE939CF5D35EBED778247AEC5F85FB6`.

Run 02 also retained a packaging-only recovery of 19 originals without
resampling or movement. Run 03 demonstrated the noninteractive boundary: stdin
closed before a review could be entered, so the review failed and no pulse was
authorized. Thirty-two focused workflow/session tests cover the final fixes;
the earlier full repository gate predates them.

Exit 0 means this run returned `candidate-motion-consistent`; exit 2 means a
blocked/failed/nonmatching run. Inspect `failure.json` and retained phase
diagnostics rather than silently retrying input. Existing files are never
overwritten. A failed or insufficient-motion comparison is evidence, not success.

This is endpoint displacement with recorded input insertion/release, not speed,
continuous tracking, measured RIFT input-consumption timing or patch survival.
The [real XYZ catalog](xyz-field-catalog.md) records the separately observed
full-game restart evidence. Patch recovery remains deferred.
