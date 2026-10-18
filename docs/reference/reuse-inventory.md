# Reuse inventory

Reviewed: 2026-10-18. These are concrete candidates for evaluation, not an accepted
V2 implementation plan. Source inspection establishes what code is present;
historical test reports and current runtime behavior are separate evidence.

## Existing capabilities

| Capability | What is already present | Limit to evaluate |
|---|---|---|
| Offline pointer resolution [R1] | A step-by-step resolver for saved qwords, floats, and exact-address bytes. It dereferences the root/intermediate offsets and adds the final offset without dereferencing it. | The memory adapter is an exact-address map, not a general range reader. Agree on semantics before reusing it elsewhere. |
| Numerical snapshot analysis [R2] | Raw/gzip segment loading, baseline/passive/displaced pose comparison, candidate float32 XYZ decoding, displacement comparison, noise penalties, and ranked JSON/JSONL/Markdown output. | Selected segments are fully loaded/decompressed in memory. Candidate limits can truncate analysis. Scores are heuristic; missing displacement remains a blocker. |
| Offline snapshot comparison [R3] | Saved register, disassembly, memory-map, and memory-read identity/hash comparison. A file-to-file entry point exists. | Changed hashes do not explain byte-level field meaning. The same module also contains live collection; name the offline entry point explicitly. |
| Motion observation and saved provenance [R4, R5] | A bounded native diagnostic plus a local recorder with phase, observer, time, target, build, and sample information. | The recorder's deduplication state is in memory; it suppresses certain read/parse errors. Recent-sample delivery can trim data. It is not a qualified lossless/restart-safe recorder. |
| Negative motion evidence [R6] | Saved free-travel and wall-slide observations with a rejected projected-velocity interpretation. | A saved wall-classification replay command was not identified in the bounded search. Do not claim an existing replay workflow has been verified. |
| Workbridge local computation and saved bytes [R7] | Recoverable file operations, command jobs, Git, manifest mapping, typed saved-byte reads, exact byte search, and prepared gzip access. Existing browser-chat evidence also shows an authored .NET 10 helper built and run. | Saved-byte search is exact-pattern inspection, not semantic discovery. Tool/output/job limits and script behavior still matter. |
| REA focused analysis and retained evidence [R8] | Installed REA documents function dossiers, selected evidence views, filtered lookup, and portable evidence export. | Provider/session capabilities must be checked in context. A session's retained evidence is not automatically a durable project archive. |

## Source entry points

- R1: `C:\rift modding\RiftReader\scripts\rift_live_test\x64dbg_static_chain_resolve.py`:
  `OfflineMemoryImage`, lines 215–265; `resolve_pointer_chain`, 268–323;
  coordinate reads, 334–358.
- R2: `C:\rift modding\RiftReader\scripts\family_snapshot_delta_analyzer.py`:
  segment loading, 67–82; numerical helpers, 144–224; `analyze_manifest`,
  631–730 and 809–924.
- R3: `C:\rift modding\RiftReader\scripts\rift_live_test\x64dbg_snapshot_diff.py`:
  `compare_scalar_maps`, 253–263; `diff_snapshots`, 273–341;
  `run_file_diff`, 721–739.
- R4: `C:\rift modding\RiftReader\.riftreader-local\motion-recovery\20261018\collect.py`,
  lines 15–50. This is ignored local research source, not a versioned V2 tool.
- R5: Native observer source and limits in the
  [motion evidence review](../research/motion-evidence-review-2026-10-18.md).
- R6: `C:\rift modding\RiftReader\.riftreader-local\motion-recovery\20261018\analysis-wall-motion.json`;
  evidence identity and review limits are recorded in the same motion review.
- R7: `C:\work\workbridge-mcp\docs\coding-workflow.md`,
  `C:\work\workbridge-mcp\docs\snapshots.md`, and
  `C:\work\workbridge-mcp\docs\local-pc-roadmap.md`.
  See the updated [Workbridge guide](../workflows/workbridge.md).
- R8: `C:\work\tools\rea\node_modules\rea-agents\skills\reverse-engineer-anything\references\native-and-artifacts.md`,
  lines 80–96, and installed `SKILL.md`, lines 251–271.
  See the [REA guide](../workflows/rea.md).

## Existing checks worth locating when reuse is chosen

V1 has focused tests for the snapshot delta analyzer, offline pointer resolver,
and snapshot diff, including missing displacement, missing module/read data,
implausible pointers, and synthetic changes. Their source is present; this audit
did not execute them or claim that the current checkout passes.

## Reuse questions

Before writing a replacement, identify the existing entry point, input/output
assumptions, supported cases, known failures, and smallest relevant validation.
Retain useful algorithms or evidence only after that review; importing a whole
module can also import unrelated behavior.

The [first-objective comparison](../planning/first-objective-options.md) uses
this inventory to make the next discussion concrete.
