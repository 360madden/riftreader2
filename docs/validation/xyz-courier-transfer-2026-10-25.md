# Reusable XYZ Courier and transfer lifecycle — October 25, 2026

Added the [reusable Courier and guarded transfer commands](../reference/xyz-courier-transfer.md).
The new source comes from the project's own retained trial Courier, with
reviewed configuration, packaging and process-continuity changes. Historical
Courier artifacts and historically pinned HTTP receiver sources are unchanged.

## Concrete host results

- Built the accepted Courier from tracked source SHA
  `8A34AA9A1DF6B0F3CCD81E28B6CC774D1ADABAE87A7A9223B474D638539AD974`
  using the installed Windows .NET Framework compiler. The accepted artifact
  is **52,224 bytes**, SHA
  `6EFD6000A464438A5F28969EB53672DCC76BB238A859B23E8AA67A6413499863`.
- Bundle:
  `artifacts/validation/xyz-courier-transfer-20261025-01/accepted-courier/`;
  run ID **xyz-reusable-oct25-03**. Its manifest pins the compiler, source,
  configuration, original corrected reader and profile. The independently
  retained `courier-manifest.json` SHA is
  `7638351CA2A5BC1F62E8DBBC8EA8ACCD26808032ED2854754027B31FE11549F1`.
  Verify that pin and every listed payload before any guest use. Earlier scratch builds
  in this validation directory are superseded, not guest deployments.
- Executed only the newly compiled Courier's `--preflight`. It reported
  `preflight-passed-no-install-performed`, `installationPerformed:false`,
  `readerExecuted:false`, `networkUsed:false`. No Courier window was opened.
- Replayed the static transfer preview using retained V20/V21 maintenance
  records. Plan SHA:
  `7F196B2A7FF4A2257B0955F3FE5AE1009BFEE82537A33A09E594D481F0EC28A9`;
  source `artifacts/validation/xyz-transfer-preview-20261025-01.json`.
  Result: `verified-not-serving`, `liveNotChecked:true`, `listenerStarted:false`.
  The captured result is
  `artifacts/validation/xyz-courier-transfer-20261025-01/transfer-preview.json`.
  Historical identities were used only to test file/contract validation, never
  as proof of current guest or controller state.

## Checks and fixes

The Courier's compiled preflight tests cover configuration grammar, unsafe run
IDs, source/profile pin drift, duplicate profile keys, the production 8 KiB
profile limit, and mismatch with the explicitly supported pointer recipe.
Publication uses exclusive writes and rejects output inside the input bundle.
The configuration supplies data, not arbitrary commands, paths or endpoints.

The retained Courier had two relevant gaps now corrected: source bytes could
change between manifest hashing and ZIP creation, and the launched panel was
not required to remain alive at absent/after capture boundaries. The reusable
version checks manifest/source consistency, snapshots verified bytes, reopens
the ZIP for exact member/hash verification, and publishes only afterward.
It also checks the launched panel's exact process/start identity around those
captures, then requires clean panel exit for packaging. A compiled offline test
harness exercises archive mutation and process-continuity rejection without
constructing the GUI or interacting with a game.

The host wrapper tests cover strict plan/receipt provenance, phase order,
exclusive output reservation, unknown process-state rejection, final VM-check
failure, file drift, and mutex-release/port-closure conditions. Loopback-only
HTTP tests exercise the reused claim handler and an absolute deadline for
partial headers, including expiration before a socket is registered. They do
not use the lab's network addresses or establish actual guest connectivity.

Focused suites: **18 Courier tests and 21 transfer-lifecycle tests passed**.
The final process-exit regression ensures that an image-path change alone cannot
count as process exit: the old PID/start epoch must actually be gone or replaced.

The full repository gate passed **469 .NET tests, 778 Python cases (776 passed,
two directory-symlink permission skips), 108 Lua checks and 22 Lua/C# cases**,
plus build, format, published-native smoke, replay and **584 relative links**.
Evidence: `artifacts/validation/20261025T155921Z-6bcfb709/`; log:
`artifacts/validation/xyz-courier-transfer-20261025-01/full-gate.log`.
The final process-epoch tightening was followed by a complete Python-suite rerun
with **779 cases: 777 passed and the same two skipped**. Its log is
`artifacts/validation/xyz-courier-transfer-20261025-01/final-python.log`.

## Limits and next live gate

No new reader installation, real guest transfer, VMware command, credential
lookup, game-memory scan, game exit/relaunch or direct in-game Computer Use was
performed. The new GUI buttons and the real lab network/maintenance lifecycle
remain **unverified live**. The [earlier corrected trial](position-panel-corrected-restart-2026-10-25.md)
is still the live evidence for the deployed reader, not for this new Courier.

Next is a separately bounded guest trial with a fresh maintenance handover,
independently pinned final bundle, operator-controlled game exit/relaunch,
guarded transfer, original-evidence verification, and successor restoration.
The service holds the console mutex while listening, so console automation
cannot be used concurrently; the operator uses the guest buttons manually.
Patch recovery and direct in-game Computer Use remain deferred.
