# Discovery compilation, query and export roadmap

Status: **D0–D4 implemented and validated October 24, 2026 (America/New_York)**; next-stage features explicitly deferred.
Owner: RiftReader2. Scope: offline evidence presentation for other programs and human review. No guest input, live memory reads, VMware access, new service or new database.

## Outcome

Compile *explicitly selected, retained* RIFT evidence into a deterministic, read-only, versioned view. Search, filter and sort across source kinds; export JSON, CSV or JSON Lines without erasing originals. Provide a standalone local browser explorer that loads the exported JSON and offers the same practical filters and local downloads. A compilation is a view, **not** new evidence or qualification.

## Design review and decisions

1. **Reuse rather than replace** `field-catalog/1`, `FieldCatalogFile.LoadAsync`, `FieldQualificationEvaluator`, `JsonFormat`, `JsonReportWriter`, and `RiftReader2.Cli`. Do not alter existing catalog fingerprints, assessment semantics, or contracts.
2. **Explicit manifest, not recursive artifact mining.** A bounded `discovery-sources/1` file lists each input source with source ID, kind, relative path, exact byte length and SHA-256. Every file must validate before output. No ambient file discovery, untracked surprise inputs, network access or writes to original sources. The manifest is itself hashed.
3. **Preserve provenance per record.** Every row records its source/report kind, hash and path, field ID, source kind, build/session identity, status, qualification caveat, locator, observation time and value where justified. Never fuse identical coordinates/names/pointers across source reports implicitly. Historical and contradictory rows remain addressable.
4. **Source-specific importers:** existing assessed field catalogs; `typed-wire-snapshot-inspection/1` advancing-Lua reports; `native-pointer-versus-typed-wire-review/1` stationary comparisons; `native-motion-pair-review/1` moving comparisons; and explicit `discovery-record-set/1` rows for other bounded research findings. Importers validate report version/identity/status shape; an offline JSON report is not automatically semantically attested.
5. **Honest status semantics.** Catalog rows carry exact evaluator statuses (`supported-by-recorded-assessment`, `contradicted`, `unqualified`). Native reviewers retain candidate-only status and qualification. Typed producer advancement is not native field qualification. Curated research is `recorded-only`. No universal “verified” badge that erases these distinctions.
6. **Storage choice:** keep files as authoritative. A compiled JSON view is disposable/rebuildable. Do not add SQLite until repeated measured workloads demonstrate a concrete shortcoming (roadmap step 7).
7. **No overwrite.** Publish files atomically with create-new behavior; reject invalid manifest, stale hash, duplicate IDs, output conflict, unknown options, oversized sources and canceled operations before a successful report. Default deterministic ordering and stable tie-breakers.

## Implemented stages and acceptance gates

### D0. Finalized contract and roadmap (checkpoint commit)
- Document data identity, bounded manifest and normalized row shape.
- Verify no change to V17 live ownership or existing field-catalog semantics.
- Check that the proposed CLI can be added without changing a production dependency boundary.

### D1. Offline compiler and importers
- Add Domain record/view types, Application filtering/sorting, Infrastructure input loader and adapters, CLI composition. Keep CLI configuration and file I/O out of Domain.
- Version `discovery-sources/1`, `discovery-record-set/1`, and `discovery-compilation/1`.
- Use declared context (`--build-sha256`, `--session-id`, `--as-of`) for catalog evaluation; include other source reports as their own exact epochs, not falsely contextualized.
- Bound manifest size, source count/bytes, record count and JSON depth. Reject duplicate JSON properties, nonfinite values, path traversal/reparse links and hash mismatches.
- Tests: synthetic catalog still shows support/contradiction/unqualification; source reports retain candidate statuses and full identity; tampered/unsupported inputs fail closed.

### D2. Query and file export
- `export-discoveries --manifest ... --build-sha256 ... --session-id ... --as-of ... [--source ...] [--category ...] [--status ...] [--search ...] [--sort ...] [--columns ...] --format json|csv|jsonl --output PATH`.
- Stable multi-key ascending/descending sort, case-insensitive text matching, exact filter semantics and deterministic ID tiebreaker. Missing dates last.
- JSON includes manifest digest, selected filter/sort parameters, source identity/metadata, counts and full row provenance; CSV/JSONL preserve chosen row order, with correct quoting and no-overwrite publication. Row IDs remain distinct even when fields agree.
- Tests: filter combinations, tie/missing-date order, Unicode/CSV formula safety, deterministic reruns and existing-file preservation.

### D3. Offline local explorer
- One self-contained HTML file under `scripts/`, loaded directly on Windows (no server) with a user-selected compiled JSON file. Search, source/category/status filters, header sorting, counts and filtered CSV/JSON downloads. It must display candidate/conflict/qualification honestly.
- Keep file inputs local; no network requests or live agent access. Guard HTML rendering against content injection; do not claim to validate evidence in the browser.
- Test static contract and browser-side logic where practical.

### D4. Integration and handoff
- Tracked synthetic compilation fixture; examples and exact CLI instructions. Real ignored live evidence can be imported only when individually declared/pinned; do not commit bulky/private artifacts.
- Focused tests, then `pwsh -NoProfile -File scripts/validate.ps1` with actual exit-code/output review. Test deterministic two-run output, bad SHA, invalid paths, categories/status separation and filtered file contents.
- Update documentation index, CLI help and `docs/status.md`; commit coherent verified milestones locally. No push or deployment.

## Completion evidence

D0 design was committed as `d62cbc3`; D1/D2 as `0f31cf6`. D3 local browser functionality passed on six synthetic and two retained real RIFT discovery records, including filtered CSV/JSON downloads. D4 passed the full PowerShell 7.6.8 validation gate on 2026-10-25 UTC with 441 .NET, 660 Python, 108 Lua, 22 Lua-to-C# and 490 documentation links. All selected retained game evidence remained read-only; [precise evidence and handoff](../validation/discovery-compilation-2026-10-24.md). The console owner remains the latest independently recorded V16.

## Deferred by design

Interactive editing/reclassification, automatic filesystem watches, SQLite persistence, live VM control, automatic field promotion, and cross-build semantic merge/diff are outside D0-D4. A later comparison mode may align stable IDs across retained exact-build reports while still displaying missing/contradicting evidence; that needs its own tests and acceptance.

## Operational handoff

The latest recorded owner remains V16 with exclusive VMware-console reservation; V17 successor was staged only. **This work is wholly offline and does not use or change that authority.** Review the current `docs/status.md` separately before any future live trial.
