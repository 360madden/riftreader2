# XYZ movement and restart results export, October 25

The user requested an export and documentation of the completed live results. A
portable offline evidence package now combines the [guest deployment and movement
trial](native-xyz-sampler-live-2026-10-25.md) with the [normal RIFT restart
validation](native-xyz-restart-2026-10-25.md). This export performs no new live
acquisition or VM input and does not change the source qualifications.

## Outputs and source selection

Export folder: `artifacts/exports/xyz-live-and-restart-20261025-01/`.
The sibling `xyz-live-and-restart-20261025-01.zip` contains that complete folder;
its `.zip.sha256` sidecar pins the outer archive. Open `report.html` after
extraction for a readable summary and local evidence links. `README.txt` explains
the contents, verification and replay.

The existing [discovery compiler](../reference/discovery-compilation.md) exported
canonical `discoveries.json` (`discovery-compilation/1`), row-only
`discoveries.csv` and `discoveries.jsonl`, with **four records** in each. The
unchanged offline `discovery_explorer.html` is included; select the JSON using its
file picker. `discovery-sources.json` pins these four byte-exact reports:

| Source ID | Original input relative to `artifacts/update-recovery-20261023-01/` | Preserved status |
| --- | --- | --- |
| `movement-lua` | `xyz-live-oct25-02/motion-typed-comparison.json` | `advanced-in-covered-scope` |
| `movement-native` | `xyz-live-oct25-02/motion-review.json` | `candidate-motion-consistent` |
| `restart-lua` | `xyz-restart-oct25-01/comparisons/a2-b4.json` | `advanced-in-covered-scope` |
| `restart-native` | `xyz-restart-oct25-01/position-review.json` | `candidate-compatible` |

The compilation's explicit catalog context is game SHA
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`,
session `pid:9704/ticks:639285237698112372`, as-of
`2026-10-25T11:38:10Z`. **Both original source epochs remain distinct**: movement
retains `pid:6940/ticks:639284177321390013`; restart retains the new epoch. The
catalog context does not relabel the movement evidence or create field-catalog
qualification. `export-provenance.json` records the source repository revision
`993f6b4` and actual export creation time. `export-receipts.json` retains the CLI
arguments, successful exit results and summaries.

## Evidence included

- Untouched before/after movement guest ZIPs and the restart ZIP, plus the partial
  `recovery.zip` and empty-frame `prestate.zip` negative acquisition archives.
- All recovered restart originals, all nine strict Lua diagnostics, the native
  review, exact replay outputs/proof, receiver claims and upload receipts.
- Movement native feed, insertion/release action receipt, typed/native comparison,
  source recovery proofs, and original deployment/movement summary.
- Original final-state observations and successful full-gate logs/results for each
  milestone. Earlier controller identities are dated observations, not a current
  liveness claim.
- Byte-exact snapshots of the two detailed validation documents and this export
  record, plus the unchanged profile and offline explorer.

The package uses an explicit allowlist. Private arming/grant/lease/configuration
files, credentials, executable binaries, operational helper scripts and desktop
screenshots are excluded. Raw snapshot bytes are retained inside the selected
original guest archives; these are local research evidence, not a public upload.

`checksums.json` pins every payload file by length and SHA-256, excluding itself.
The outer ZIP hash pins that manifest too. Archive member names were checked for
traversal/absolute paths and forbidden private/executable files; original guest
ZIP CRCs were checked. Every extracted restart member matched its original ZIP
bytes. The original movement/restart summary manifests' declared hashes and
lengths were checked against the retained source files.

## Results and limits

The report records **30/30 native samples** spanning the bounded movement trial,
**0.6473471 game units** of observed motion, sub-**0.0025** per-axis endpoint
agreement, and unchanged-profile reacquisition after one normal same-build game
restart with **5/5 + 3/3** successful reads. Absent-game and old-PID requests were
rejected. Both selected restart reviews replayed byte for byte.

Native movement remains `candidate-only-no-stimulus-or-clock-skew-proof`; the
insertion/release receipt is separate evidence. Restart remains
`candidate-only-not-synchronized`, with **71.106/80.122-second** source/native
lags. The source scouts' partial coverage remains explicit. Patch survival,
arbitrary future restart reliability, loading/menu semantics, synchronized clocks
and semantic field-catalog promotion are not established by this export.

## Export verification

All three CLI formats completed successfully with four records. JSON source pins,
record counts, statuses and both original epochs were asserted; CSV and JSONL row
counts were checked. JSON and JSONL records matched exactly; CSV retained the same
record IDs and evidence hashes. The unchanged real-browser smoke loaded the exported JSON,
filtered by status and exact SHA, sorted timestamps, and verified filtered CSV
and JSON downloads. Its result is retained as `browser-smoke.json`. Every payload
file was rehashed, and the completed outer ZIP was reopened, CRC-checked and all
manifest-pinned member bytes verified. Repository documentation links and the
required full gate passed with **exit 0 at 2026-10-25T12:09:11Z**, including
**450 .NET, 669 Python, 108 Lua and 22 actual Lua-to-C# cases**, plus build,
published native synthetic smoke, replay, formatting and **523 relative links**.
Evidence: `artifacts/validation/20261025T120811Z-9edb1ef3`; export-time gate log and
result are included as `export-full-gate.log` and `export-full-gate-result.json`.
The source live-run gate evidence remains unchanged inside the package.
