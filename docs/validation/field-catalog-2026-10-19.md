# Durable field catalog validation

Date: 2026-10-19 (America/New_York).

This increment implements roadmap step 5's offline catalog and qualification
workflow. No game, VM, addon, V1 source, native memory, or remote service was
changed or exercised for this increment.

## Implementation

- Domain: field, assessment, context, claim, disposition, and fingerprint values.
- Application: deterministic qualification at explicit build/session/time.
- Infrastructure: strict versioned JSON, same-bytes assessment hash/parse,
  streamed artifact hashes, bounded flat-file references, and report DTO.
- CLI: `qualify-fields`, explicit context, implementation identity, and the
  existing atomic publication that preserves prior evidence.

See [ADR 0005](../decisions/0005-durable-field-catalog.md) and the
[contract](../reference/field-catalog.md) for bounds and semantics. No project,
production dependency, database, or runtime service was added.

## Checks

The 12 focused core tests and 6 CLI test cases passed before the full gate.
They cover scoped support, distinct restart/update contexts, cross-context
contradiction precedence, synthetic exclusion in both directions, expired and
future evidence, definition/locator/applicability changes, session-only address
rejection, strict JSON, artifact integrity, extreme length input, deterministic
reports, explicit UTC time, cancellation, and no overwrite.

Independent read-only review checked the policy, provenance, bounds, and CLI.
Review fixes made all four claim statuses visible, retained reviewer/rationale
and artifact references, excluded synthetic contradiction from real fields,
and clarified byte verification versus declared identity. Fingerprinting stays
in Domain without depending on JSON or Infrastructure.

The full gate passed with 214 C# tests (205 portable, 9 Windows), 108 Lua
assertions, 22 actual Lua-to-C# cases, 9 Python tests, locked restore,
zero-warning Release build, format/dependency checks, published native smoke,
deterministic motion/catalog replay, and 174 relative links before final
handoff edits. Command: `pwsh -NoProfile -File scripts/validate.ps1`.
Evidence: `artifacts/validation/20261019T050044Z-98856eec` and
`artifacts/catalog-validation.log`.
All 177 final documentation links passed in a separate post-handoff check.

## Retained demonstration

`samples/catalog/` contains three definitions, six content-pinned assessments,
and three synthetic observations. The required context is build `A` repeated
64 times, session `synthetic-session-a`, evaluated at `2026-10-19T00:00:00Z`.

| Field | Expected result |
|---|---|
| `demo.supported` | Four claims supported by recorded synthetic assessments; two sessions on build A and a separate build B. |
| `demo.disputed` | Contradicted meaning; supporting and expired history retained. |
| `demo.address-only` | Unqualified; no recorded assessment or durable locator. |

Two CLI runs with the same files, tool build, context, and time must produce
byte-identical reports. The full gate retains both reports. CLI tests also
alter one observation without changing its length and require SHA-256 failure
before publication; a second publication to the same destination preserves
the original report bytes.

The actual retained reports `catalog.json` and `catalog-replay.json` were both
21,738 bytes with SHA-256
`2357F31615E513155FBE6661E680BBE58CF9727E8425152F524BE0FDAB3E194A`.
Input `samples/catalog/catalog.json` SHA-256:
`0E4DFFFA309B476B9C06B40E467363166E3CEE8AC471F2E3BDC1A603E981DDD1`.
The report retained nine applicable declaration dispositions and one expired
disposition. Its three field statuses matched the table above.

## Limits

This validates the mechanical workflow, not any actual RIFT field meaning or
locator. Artifact bytes are verified; origin, reviewer, semantic interpretation,
and build/session attribution remain declarations. The report explicitly labels
these boundaries. Restart/update support means explicit recorded corroboration
within listed contexts, not automatic future compatibility or live attestation.

Assessments and observations are retained history, not authenticated records.
The report only reflects the evidence supplied by the catalog; removing a
reference changes the catalog hash but is not prevented. Invalidation conditions
are instructions for review, not continuously evaluated rules. Native acquisition
and addon runtime evidence retain their own exact executable and session scope.
