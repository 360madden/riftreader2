# Discovery compilation and export — October 24, 2026

Scope: **offline** source selection, SHA verification, catalog/report normalization, query and file export. All work was performed through the Windows repository at `C:\work\riftreader2`; **no new RIFT/VMware interaction, V16 STOP, V17 launch, guest input or memory read** occurred. The latest authoritative live-control state remains in [current status](../status.md).

## Reviewed architecture and implementation

- Final roadmap checkpoint: `d62cbc3`; exact [roadmap](../planning/discovery-compilation-roadmap.md). Source-specific, bounded manifest; no implicit artifact scan or SQLite/service.
- Compiler milestone: `0f31cf6`; strict `discovery-sources/1` and `discovery-record-set/1` inputs; existing field-catalog evaluator reused unchanged; imported typed/native reviewers retain their own statuses, hashes and process epoch.
- CLI command: `export-discoveries`, supports multi-key sorts, source/category/status/text filters, deterministic JSON/CSV/JSONL, column-selected CSV, safe spreadsheet text, no-overwrite output.
- A synthetic tracked manifest at `samples/discovery-sources.json` contains one known [catalog sample](../../samples/catalog/README.md) and one recorded example file; no real RIFT data is committed.
- Standalone `scripts/discovery_explorer.html` loads exported JSON locally and offers filters, sorting, evidence inspection, pagination and selected-record downloads. It does not revalidate original files.

## Machine validation (compiler checkpoint)

Real Windows PowerShell 7.6.8 `-NoProfile -File scripts/validate.ps1` **exit 0** at **2026-10-25T01:30:07Z**, output evidence `artifacts/validation/20261025T012906Z-1dea9d50`:
- `439/439` .NET tests (300 core including 7 discovery tests; 139 Live).
- `660/660` Python tests.
- 108 Lua lifecycle/encoder tests, 22 Lua-to-C# cross-language cases.
- Locked restore, zero-warning Release build, format verification, native publish/self-process smoke, deterministic replay, 471 documentation links.
- Initial full gate failed solely on new C# whitespace formatting. The narrowly scoped `dotnet format whitespace` fixed this; the subsequent authoritative gate passed. No unrelated files were edited.

The first sample CLI run succeeded, exporting **six records from two sources** to ignored `artifacts/discovery-preview-20261024-01.json`, **9,225 bytes**, SHA-256 `FF03C470D16CD919F260199E9103D53F43E178DFD2CC5AFB8ACA209A0CAC3F9D`. It retained `supported-by-recorded-assessment`, `contradicted`, `unqualified` and `recorded-only` interpretations.

## Actual previously retained RIFT evidence imported — NO GAME ACCESS

A separate **ignored, no-overwrite** manifest `artifacts/update-recovery-20261023-01/rr2-discovery-v16-manifest-01.json` was authored with exact pins for two existing same-PID/build original review reports:

| Source ID | Original relative path below ignored update-recovery directory | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `lua-advancing-v15` | `rr2-inline-oct24-01-recovered/pair-a1-b2-typed-comparison.json` | 4,989 | `CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5` |
| `native-stationary-v16` | `rr2-v16-native-pointer-reviewed-live-oct24-01/position-review.json` | 2,640 | `1973D0C6A9CDCAE2D2B4B4826BB26C70BA36081EE090F0F7AC792BF96A6AAD53` |

Manifest SHA-256: `D5BED6438676AE0A15C1005851015F392CED5F16234E3A796429FE7013850006`.

`dotnet run --no-build --configuration Release --project src/RiftReader2.Cli -- export-discoveries` with exact game build `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`, session `pid:6940/ticks:639284177321390013`, and `--as-of 2026-10-25T00:25:38Z` exited **0**. Result `artifacts/update-recovery-20261023-01/rr2-discovery-v16-live-01.json` is **5,231 bytes**, SHA-256 `D2023A7A1FE3F6BE56470CB7F24481760087297786E76E92EB7A03A50EF7887A`. It contains **two separately source-attributed** rows for `player.position.xyz`:

1. `lua-advancing-v15:player.position.xyz`: `sourceKind=addon`, `status=advanced-in-covered-scope`, `qualification=source-advancement-only-not-native-qualified`; last typed frame XYZ **(7461.1997070312, 863.84997558594, 2977.0598144531)**, timestamp **2026-10-24T21:36:29.2356771Z**.
2. `native-stationary-v16:player.position.xyz`: `sourceKind=native`, `status=candidate-compatible`, `qualification=candidate-only-not-synchronized`; native XYZ **(7461.19921875, 863.8524169921875, 2977.061767578125)**, timestamp **2026-10-25T00:02:24.644708Z**, locator RVA 0x32E0200 with owner +0x320/+0x324/+0x328.

The report **does not** declare motion qualification, synchronization, locator survival after update, or reviewer authenticity. The standalone input reports predate this compilation; compiling them is not a new live experiment. Original artifacts remain ignored and unchanged.

## Actual Chromium local-interaction proof

After UI search expansion and precise UTC timestamp sorting, `node --check scripts/test_discovery_explorer_browser.mjs` and a direct Node check of the HTML script and fractional UTC ordering passed. No npm/browser driver package was installed. The standalone `scripts/test_discovery_explorer_browser.mjs` then launched an isolated **headless Google Chrome** with an ephemeral profile on the Windows host and used the actual HTML local file picker. Both full browser runs exited **0**:

- **Synthetic six-record output** (`rr2-disc-d4-browser-real-01`): 6 loaded, 1 selected by exact status, 3 selected by original evidence SHA search, ascending time-sort indicator, downloaded CSV with 3 filtered rows and JSON with the same 3 records and original SHA.
- **Retained actual RIFT two-record output** (`rr2-disc-d4-browser-live-evidence-01`): 2 loaded, 1 selected by status, 1 by SHA search, verified time sorting, downloaded and checked single-row CSV and JSON. Both original evidence hashes and status limitations remain unchanged; the local browser does not attest the source.

The harness uses only Node built-ins and locally installed Chrome/Edge, never connects to RIFT/VMware, and closes its separate browser after verification.

## Final authoritative D4 repository gate

Windows PowerShell 7.6.8 `pwsh -NoProfile -File scripts/validate.ps1` completed **exit 0 at 2026-10-25T01:51:18Z** (job `rr2-disc-d4-final-gate-01`). Retained evidence: `artifacts/validation/20261025T015017Z-106b7fd1`.

- Zero-warning, zero-error .NET 10 Release build; **302/302 core .NET + 139/139 Live = 441/441** tests.
- **660/660 Python** tests, **108 Lua 5.1** lifecycle/encoder tests and **22** real Lua-to-C# shared contract cases.
- Locked restore, formatter, Windows-host synthetic native publish/smoke, deterministic replay and **490** relative documentation links all passed.
- Expected negative-case logs such as `output already exists` and invalid reviewer mode occurred within passing tests; they are not gate failures.

The gate includes the refined CLI provenance search and static explorer contract checks. The two separately passing headless Chrome functional tests above cover the interactive file input, filters and actual downloads; they do not imply a manual graphical-layout review.

## Remaining confidence boundary

The compiler and its evidence-import adapters have actual offline execution proof. The HTML script passed Node syntax checking (job `rr2-disc-d3-node-syntax-01`); a dedicated static UI contract test checks local-only resources, safe DOM text rendering, pagination and download actions. Actual headless Chrome behavior and the final PowerShell repository gate have now passed. Manual visual and accessibility review across window sizes remains a separate human check; no new live RIFT movement, clock synchronization, or native field qualification is implied.
