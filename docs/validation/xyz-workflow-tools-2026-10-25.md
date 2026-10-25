# XYZ workflow tools — offline integration, October 25, 2026

Implemented three reusable commands for pinned payload preparation, recovery of
returned evidence and audited panel-session export. See the
[command reference](../reference/xyz-workflow-tools.md). No VMware operation,
credential lookup, network transfer, game-memory scan, guest deployment or new
live restart was performed.

## Actual retained-evidence replay

The CLI sequence used a new directory:
`artifacts/validation/xyz-workflow-20261025-01/`.

1. `prepare_xyz_deployment.py` consumed the retained corrected trial's
   `deployment.json`. The input manifest SHA was
   `0B81816CD5FBA5126D744739DC79FDFF7606822C39D3E3A7AFA9D35E1815C73E`.
   It prepared the exact 116,924,768-byte reader, SHA
   `E01EA1DF88BD70E760F91D4DDB33757D647290A293166EC272DA2BAF2A617E95`,
   and 395-byte profile, SHA
   `FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8`.
   The derived bundle manifest explicitly reports no guest execution/deployment
   or live validation. Historical caller test metadata was not treated as proof.
2. `verify_xyz_evidence.py` accepted the independently recorded archive pins:
   initial trial **385,136 bytes**, SHA
   `C3B3A1B95160D3B92DB6EF1B33B1B27CBEF8EAB5C71DB26BB979062970F2E82C`,
   and corrected trial **537,644 bytes**, SHA
   `8456D319242DA19A3982B4F66155626E61C35856C3463AB68CDDF9E256496899`.
   Recovered **260** and **357** files including each package manifest, verified
   against their declared sets/hashes. Both integrity receipts explicitly leave
   transport authentication, restart and semantic qualification unestablished.
3. `export_xyz_sessions.py` consumed each newly recovered `originals/panel-01`
   directory, reran the panel audits and exported **559 payload files**. The
   initial trial retained **226 reports / 48 findings**; the corrected trial
   retained **323 reports / zero findings**. Exit **2** was expected because the
   combined export intentionally preserves the original startup-value failure.

The panel-only portable result is
`artifacts/exports/xyz-panel-workflow-20261025-01/package.zip`, **916,815 bytes**,
SHA `770C0C51E6F68EFD7A83E1614D84EF194C068C50EA301797B7B772AF49E4CC7A`.
The same directory contains `report.html`, payload checksums and the completion
receipt. This new package supplements rather than replaces the
[complete corrected restart evidence](position-panel-corrected-restart-2026-10-25.md).

## Verification boundaries

Focused tests exercise pinned-content failures, strict profiles, no-overwrite
races, partial writes, unsafe ZIP paths/metadata, source mutation, exact archive
bytes, withheld versus live startup values and preservation of failed audits.
Synthetic executable fixtures establish that preparation does not execute the
payload. Directory-symlink cases can be skipped where Windows denies creating
test symlinks; explicit reparse checks remain in production code.

The final focused suite ran **51 cases: 49 passed, two directory-symlink creation
tests skipped** because the Windows account lacks that permission. The complete
repository gate then passed **469 .NET tests; 740 Python cases (738 passed,
the same two skipped); 108 Lua checks; 22 Lua/C# cases**, plus locked restore,
zero-warning build, format, published-native smoke, replay and **575 relative
links**. Gate evidence: `artifacts/validation/20261025T153826Z-6b54eea3/`;
log: `artifacts/validation/xyz-workflow-20261025-01/full-gate.log`.
The final deployment implementation was also replayed into the new
`prepared-final/` subdirectory after final payload and manifest readback checks
were added. Source pins and the not-deployed result were unchanged.

The new tools generalize local preparation and post-transfer evidence work.
They do not generalize authenticated media control, the trial-specific Courier,
or the live transfer-service lifecycle. Those remain on existing guarded paths.
Actual deployed behavior continues to rely on the earlier retained live trials,
not on this offline replay. Patch recovery and direct in-guest Computer Use
remain deferred.
