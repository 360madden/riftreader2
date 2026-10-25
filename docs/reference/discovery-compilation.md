# Discovery compilation and offline exports

The `export-discoveries` command compiles **explicitly selected saved evidence**, not live RIFT memory. It imports the existing `field-catalog/1` evaluator, strict typed Lua snapshot inspections, native position/motion reviews, and recorded research rows. Nothing is promoted by being included in a report. See the [final implementation roadmap](../planning/discovery-compilation-roadmap.md) and [ADR 0007](../decisions/0007-discovery-compilation-views.md).

## Quick start (PowerShell 7, on the Windows host)

```powershell
cd C:\work\riftreader2

dotnet run --project src/RiftReader2.Cli -- export-discoveries `
  --manifest samples/discovery-sources.json `
  --build-sha256 ('A' * 64) `
  --session-id synthetic-session-a `
  --as-of 2026-10-21T00:00:00Z `
  --format json `
  --output artifacts/discoveries-example.json
```

Open `scripts/discovery_explorer.html` directly in Edge or Chrome, then select `artifacts/discoveries-example.json` in its file picker. The HTML interface needs no local server or external connection. It searches and filters by source, category and status; supports header sorting and evidence inspection; renders 100 rows per page while exporting **all** filtered rows. Its local CSV/JSON download buttons do not alter saved originals. The browser does **not** revalidate the source evidence.

For repeatable real-browser smoke validation, Node.js 26 or another recent Node with built-in `WebSocket` plus installed Chrome or Edge is sufficient (no npm packages). With the JSON already exported, run `node scripts/test_discovery_explorer_browser.mjs artifacts/discoveries-example.json` from the repository root. It starts a separate temporary headless browser, opens the HTML as a `file:` page, selects the output using the native file picker, checks filtering, search and sorting, downloads filtered CSV/JSON, verifies contents, and closes the browser. Original reports remain untouched.

The sample compilation is entirely **synthetic**: it combines the repository's three-field assessment fixture and three explicitly recorded research examples. Its supported/contradicted/unqualified statuses test the catalog evaluator; none qualifies a real game field.

## Formats and filters

```powershell
dotnet run --project src/RiftReader2.Cli -- export-discoveries `
  --manifest samples/discovery-sources.json `
  --build-sha256 ('A' * 64) --session-id synthetic-session-a `
  --as-of 2026-10-21T00:00:00Z `
  --source addon,native --category combat,movement `
  --search ability --sort observedAtUtc:desc,fieldId:asc `
  --format csv --columns fieldId,category,status,value,evidenceSha256 `
  --output artifacts/selected-discoveries.csv
```

- `--manifest`, `--build-sha256`, `--session-id`, `--as-of`, `--format` and `--output` are required. Time must end with `Z`; catalog evaluation uses that exact build/session/time. Other report sources preserve **their own** process epoch and are not relabeled as applicable to the selected catalog context.
- Optional `--source`, `--category` and `--status` accept comma-separated exact names, case-insensitive. `--search` finds substrings in IDs, meaning, provenance, locator and values.
- `--sort` accepts up to five unique keys with `:asc`/`:desc`: `id`, `fieldId`, `category`, `sourceKind`, `status`, `qualification`, `buildSha256`, `sessionId`, `observedAtUtc`, `evidenceKind`. Missing observation timestamps always sort last; ties resolve by stable record ID.
- `--columns` is CSV-only, using names from the default header. All CSV fields are quoted and formula-like cells are prefixed as inert text for spreadsheet applications.
- `json` is the canonical compilation file: `discovery-compilation/1` includes input source pins, query metadata, exact catalog context, total/selected counts, complete normalized records, and the manifest SHA-256. `csv` and `jsonl` are row-only subsets with per-record source/byte identity; preserve the JSON compilation when the query and input manifest are important.
- Existing outputs are never overwritten. On success the CLI prints a small `exported` summary. Exit 2 means invalid options, input/verification error or output conflict; 130 means cancellation. Neither a failed nor canceled export publishes a completed file.

## Input manifest (`discovery-sources/1`)

A manifest is a strict versioned JSON object with `schemaVersion: 1`, `contractVersion: "discovery-sources/1"`, and 1–128 `sources` entries. Each entry has **exactly** `sourceId`, `kind`, `path`, `byteLength`, `sha256`. See the executable [sample manifest](../../samples/discovery-sources.json). Paths are relative to the manifest folder, may use forward-slash subfolders, and cannot traverse `..` or links. Author a manifest at a common parent directory when importing several retained artifacts. No automatic file discovery occurs.

For each source, record exact file length and SHA-256 after evidence is finalized:

```powershell
(Get-Item -LiteralPath 'C:\work\riftreader2\artifacts\some-report.json').Length
(Get-FileHash -LiteralPath 'C:\work\riftreader2\artifacts\some-report.json' -Algorithm SHA256).Hash
```

| Manifest `kind` | Accepted input and resulting row |
| --- | --- |
| `field-catalog` | Existing `field-catalog/1`, retaining qualification results and claim-status reasons; no invented observed value. |
| `typed-wire` | `typed-wire-snapshot-inspection/1`; advancing producer XYZ or explicit blocked/unavailable status, never a qualified native field. |
| `native-position-review` | `native-pointer-versus-typed-wire-review/1`; retains stationary candidate status and synchronization caveat. |
| `native-motion-review` | `native-motion-pair-review/1`; retains moving candidate status and missing stimulus/clock-skew qualification. |
| `record-set` | Explicit `discovery-record-set/1` with bounded research rows for other categories. These remain `recorded-only`. |

All source files must match their declared byte length and SHA-256; referenced catalog assessments/artifacts undergo their original verification too. Bounds: 64 KiB manifest, 8 MiB per direct source, 64 MiB combined direct sources, 8,192 normalized output records, JSON depth 16. The existing field-catalog loader has its additional limits. Unknown source kinds/schema versions, duplicate IDs/properties, traversal/reparse links, malformed values and nonfinite numbers are rejected.

Normalized rows contain stable `id`, `fieldId`, `category`, `sourceKind`, `status`, `qualification`, `meaning`, `units`, `locatorKind`/`locator`, `buildSha256`, `sessionId`, optional `observedAtUtc` and typed `value`, `evidenceKind`, `evidenceSha256`, `sourceId`, `sourcePath` and `limitations`. Report IDs are prefixed by the manifest's source ID; two disagreeing reports are never silently deduplicated. The research row-set requires a distinct `recordId`, category, exact declared context, explicit status and limitations. Supported recorded statuses are `hypothesis`, `observed`, `rejected`, `unqualified` — all with qualification `recorded-only`.

## Qualification and limitations

Content hashes verify bytes, not the author's interpretation or the evidence producer's identity. Field-catalog statuses are *recorded assessment* outcomes; native reports remain candidate-only; typed sequence advancement proves only advancement **in inspected snapshot scope**. A view does not resolve conflicting source reports, prove an update-surviving locator, synchronize host/guest clocks, or certify gameplay control. A separately justified field qualification must still follow [the catalog rules](field-catalog.md). Synthetic or manually curated rows must never be mistaken for fresh RIFT observations.

The browser has a 32 MiB selected-JSON preview limit and paginates the table at 100 rows; CLI exports remain available for larger files. All generation is offline; the current V16/V17 VM-control handoff remains entirely separate.
