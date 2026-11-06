# 0007: Read-only discovery compilation as a rebuildable view

Status: accepted implementation choice under Joey's October 24, 2026 authorization to plan and execute discovery filtering/sorting/export.

## Decision

Keep `field-catalog/1` as the authority for recorded field-definition qualification. Introduce a separate, immutable-input `discovery-sources/1` manifest with exact source lengths and SHA-256 pins, normalize several existing report contracts plus explicit curated observations to `discovery-compilation/1`, and query/export offline. Each row preserves original source kind, build/session identity, candidate/qualification status, source digest and limitations. No implicit cross-source fusion or qualification promotion.

Use the existing Domain/Application/Infrastructure/CLI project boundaries and file-based storage. The interactive explorer is a standalone HTML file that reads a user-selected compilation locally; no server or VM access. JSON retains full query/provenance metadata; CSV and JSONL expose selected rows to other programs. Outputs are deterministic for fixed inputs/options, bounded, atomically published and never overwritten.

## Alternatives reviewed

- Expanding the existing field-catalog schema: rejected because it would blur trusted definitions/assessments with unqualified captures and invalidate established fingerprints.
- Recursive scan of `artifacts/`: rejected because ignored/private/generated files may be stale, partial, or unrelated; explicit manifests are reviewable.
- Immediate SQLite or background indexing: deferred until measured workload requires it; it adds migration and state-recovery cost without current evidence.
- Web service or live VM dashboard: deferred; the first goal is offline compilation and export, not new console ownership.

## Consequences

Researchers can compile contradictory and candidate findings while downstream programs can filter deterministically. Evidence digests verify retained report bytes, **not** producer authenticity or game semantics. The existing field qualification evaluator still controls recorded claims. Future adapters require explicit schema review, bounds and test fixtures; future live/current-state views require a separate fresh-source contract.
