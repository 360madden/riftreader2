# XYZ workflow, real catalog and numeric scout checkpoint

User-authorized scope: roadmap goals 1–4, including repeatable XYZ collection,
real XYZ qualification, health discovery and resource/power discovery with
changed-state and full-game restart evidence. Goals 1–2 are now demonstrated;
the health and resource/power goals remain open.

## Implemented

- `scripts/run_xyz_workflow.py` uses a local no-password configuration, current
  controller/VM/game identities, one in-memory guest login session, the installed
  reader, bounded before/after captures, fresh screenshot review and one guarded
  100 ms pulse. It verifies returned archives, runs the existing Lua/native
  reviewers, exports evidence and excludes private arm tokens. It has no imports
  from dated trial scripts. Configuration preview is offline.
- `scripts/vmware_guest_session.py` reuses the saved VM encryption credential
  and a guest login stored in Windows Credential Manager. Run 02 verified the
  prompted login and stored it; run 04 reused that cache without a prompt.
  Identity is checked before/after every operation, command failures do not
  expose secret argv, and file retrieval publishes without overwriting another
  writer's destination.
- `config/field-catalog/xyz/` retains seven byte-identical original evidence
  copies as `.json.raw`, plus normal editable catalog/assessment JSON. The
  evaluator reports supported meaning/locator/observed same-build restart for
  the recorded post-relaunch session; update survival stays unqualified. Earlier
  startup failures remain preserved. The `.raw` suffix keeps exact original
  bytes, including absent final newlines, distinct from editable source files.
- `scout-values-native` provides the missing bounded numeric scan using the
  existing read-only memory session. Exact request bytes, candidate contexts,
  partial reads, coverage, holes and forward resume cursors are retained. Private
  region filtering precedes the region cap; request bytes cannot change between
  hashing and retention; a permanent read hole cannot trap the resume cursor.

## Live acceptance

Reusable run 04 at `artifacts/validation/xyz-repeatable-20261025-04/` completed
`candidate-motion-consistent`. One guarded 100 ms W pulse produced **0.665936
native / 0.673551 Lua units** of displacement, maximum per-axis displacement
residual **0.0078125**, and **6/6** advancing cross-phase comparisons. The
baseline and after transfers verified **19 + 17 original files**. Final status
was foreground, disarmed, idle and no inputs held; the credential session closed.
The verified 63-file export is 1,712,950 bytes, SHA-256
`7C68EDED513C16981F49D54B0C6813F1AEE939CF5D35EBED778247AEC5F85FB6`.

Run 02 recorded `credentialSource: prompt`, `cacheWritten: true`, and recovered
19 already captured originals during packaging without resampling or movement.
Run 04 recorded `credentialSource: cache` and no project credential writes.
Run 03 retained its failed review: noninteractive execution supplied no review
input after stdin closed. The live review step therefore requires an interactive
terminal; agent execution must use `tty: true`.

The PowerShell 5 packaging fix explicitly sums hashtable file sizes. Archive
verification accepts normalized Windows separators while retaining traversal,
absolute-path and NUL guards. The 32 focused workflow/session tests passed. The
full repository gate including these fixes passed at
`artifacts/validation/20261025T185220Z-1da1dd52/`: 477 .NET tests, 811 Python
cases (809 passed, two skipped), 108 Lua checks and 22 shared Lua/C# cases,
native publish smoke and 595 relative links; zero build warnings or errors.

## Catalog and remaining work

The real catalog was rebuilt at
`artifacts/validation/xyz-field-catalog-20261025-02/`; post-relaunch support and
the earlier session's limited qualification were both inspected. The evaluator
labels semantic evidence `recorded-assertions-only` and identity `declared-only`;
retained-byte verification is not independent live attestation.

Goals 1–2 are demonstrated by the live reusable run and the mechanically rebuilt
catalog. Health/resource scout deployment and actual scans are pending. Retained
Lua frames show health/healthMax 18208 and raw power 100, but these were
unchanged during XYZ movement. They are reference observations, not native
field proof.
Next: a fresh Lua reference, one bounded health seed pass, small targeted reads
during real value changes, then locator derivation and normal full-game restart
verification. Resource type/behavior must be established independently; historical
power=100 matches do not satisfy it. Patch recovery remains deferred.
