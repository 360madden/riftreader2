# XYZ preparation, returned evidence and export commands

These three local Python commands replace repeated one-off preparation and
evidence-packaging work. They perform no game-memory scan, process execution,
VMware operation, credential lookup, listener startup or network transfer.
The [collection workflow](../workflows/xyz-collection.md) still owns the live
boundaries and the definition of a complete game restart.

## Prepare a pinned reader payload

```powershell
python scripts/prepare_xyz_deployment.py --manifest ABSOLUTE_DEPLOYMENT_MANIFEST --output NEW_ABSOLUTE_BUNDLE_DIRECTORY
```

Supply a small JSON manifest with two payload entries. Source paths must be
absolute, sizes positive and hashes explicit uppercase SHA-256. For example:

```json
{
  "executable": {
    "path": "C:\\work\\riftreader2\\artifacts\\validated-publish\\RiftReader2.Live.exe",
    "byteLength": 123456,
    "sha256": "REPLACE_WITH_VERIFIED_EXECUTABLE_SHA256"
  },
  "profile": {
    "path": "C:\\work\\riftreader2\\config\\position-candidate-profile.json",
    "byteLength": 395,
    "sha256": "REPLACE_WITH_VERIFIED_PROFILE_SHA256"
  }
}
```

The example is a template, not a current executable pin. Use the output of the
actual reviewed build; neither a filename nor this example qualifies a binary.
The tool checks sizes and hashes, validates the production profile contract and
stages only `RiftReader2.Live.exe`, `position-candidate-profile.json`, instructions
and `bundle-manifest.json`. It never runs the executable. Limits are 200 MiB for
the executable, 64 KiB for the input manifest, and the production 8 KiB limit
for the profile. Linked/reparse paths and existing outputs are rejected.

The derived manifest records the source manifest hash, game-build hash and every
payload hash. `guestInstalled`, `guestExecuted` and `liveValidated` remain false.
Optional historical manifest metadata is not accepted as proof of host tests.
An interrupted directory without a valid bundle manifest is not an accepted
payload. Exit **0** means prepared locally; exit **1** means rejected or failed.

This does not build an ISO, deploy the files or replace the old trial-specific
Courier. That Courier embeds a particular binary hash and installation path;
do not reuse it for a new binary without reviewing those pins. Use the existing
reviewed media/transfer and sole-controller procedure for an authorized live
deployment, verify guest hashes, and record that result separately.

## Verify a returned Courier archive

```powershell
python scripts/verify_xyz_evidence.py --archive ORIGINAL_GUEST_ZIP --sha256 EXPECTED_SHA256 --byte-length EXPECTED_BYTES --output NEW_VERIFIED_DIRECTORY
```

The expected SHA and byte length must come from the retained guest claim or
another independently recorded pin. Computing both from the same untrusted ZIP
only establishes self-consistency. This command does not authenticate a sender
or replay the one-use transfer-service receipts.

The verifier supports the existing `xyz-interface-full-game-restart-gui-evidence`
Courier manifest. It requires the exact declared member set, byte lengths and
hashes, plus `package-manifest.json` itself. Bounds are 16 MiB compressed and
expanded, 2,048 members, 8 MiB per member and 2 MiB for the manifest. It rejects
unsafe/nonportable Windows paths, case collisions and file/directory conflicts,
links, directory entries, encryption, unsupported compression and nonregular
members. It does not execute recovered files or use unrestricted ZIP extraction.

The result contains byte-identical `originals/` and `verification.json`. The
receipt pins the source ZIP and embedded manifest and records explicitly that
transport authentication, restart validation, panel behavior and field
qualification have not been established by this command. Exit **0** means
original-package integrity verified; exit **1** means rejected or failed.
Keep the source ZIP and its external pin with this derived result.
An accepted output requires a valid receipt and no `INCOMPLETE` marker. The
marker takes precedence even if a receipt exists: failed or interrupted output
must be rejected and the command rerun into a new directory.

## Export panel sessions with their audits

```powershell
python scripts/export_xyz_sessions.py --session-dir NEW_VERIFIED_DIRECTORY/originals/panel-01 --output NEW_EXPORT_DIRECTORY
```

Repeat `--session-dir` to compare up to eight completed sessions. The exporter
runs the [panel audit](../workflows/xyz-collection.md), snapshots only its original
session metadata, journal and referenced read reports, and checks the copied
bytes against the audit hashes. It refuses changed input sets and separate-output
violations. Total input is capped at 64 MiB, with 8,192 files per session.

The output includes:

- `session-NN/originals/` and `session-NN/review.json` for each input.
- `report.html`, `README.txt` and `summary.json`, preserving failed audits.
- `checksums.json` for the payload and `package.zip` containing that payload.
- `complete.json`, which pins the archive bytes after their contents are checked.

Exit **0** means exported with recorded checks passing; **2** means a completed
export retains behavioral findings; **1** means rejected or incomplete. A finished
export requires a valid `complete.json` and no `INCOMPLETE.txt`. Existing outputs
are never reused. Verify the recorded hashes when transferring or relying on a
copy. Originals are not redacted; unrelated source-directory files are excluded.

This is deliberately a **panel-session export**, not the complete restart
evidence package. Keep the original guest ZIP, transfer receipts, independent
process/pointer/Lua evidence and cleanup records separately. The earlier
[full restart report](../validation/position-panel-corrected-restart-2026-10-25.md)
and its portable package remain the authoritative record for that live trial.

## Evidence and remaining live work

The [offline integration record](../validation/xyz-workflow-tools-2026-10-25.md)
records replay of both retained trials and preparation of the pinned corrected
reader. No new guest installation or game restart is implied.

Authenticated VMware media control, the trial-specific Courier and one-use
transfer-service lifecycle remain on their existing guarded paths. They have
not been generalized by these local commands. Patch recovery and direct
ChatGPT Computer Use inside RIFT remain deferred.
