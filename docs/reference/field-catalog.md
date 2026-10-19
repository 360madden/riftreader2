# Durable field catalog

The offline catalog preserves a field definition and the evidence used to
assess it. Application evaluates recorded claims; Infrastructure verifies
retained files; CLI writes deterministic reports. No game access or database
is required. See [ADR 0005](../decisions/0005-durable-field-catalog.md).

## Evaluate

```powershell
dotnet run --project src/RiftReader2.Cli -- qualify-fields --catalog samples/catalog/catalog.json --build-sha256 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA --session-id synthetic-session-a --as-of 2026-10-19T00:00:00Z --output artifacts/catalog-report.json
```

The explicit UTC instant uses `Z`, optionally with fractional seconds. An
existing output is never overwritten. Exit `0` means evaluation completed,
including reports with unsupported or contradicted claims. Exit `2` means
invalid input or failed artifact verification; `130` means canceled. Consumers
must inspect field and claim statuses, exact context, and limitations.

The sample is synthetic. Its fabricated build IDs and observations exercise
the workflow and do not qualify any real RIFT field.

## Author and retain knowledge

1. Define one field's meaning, units, source, locator method, exact applicability,
   required claims, and invalidation conditions. Start with no assessments.
2. Run evaluation and retain the emitted definition fingerprint. This hash
   binds interpretation and locator changes as well as field identity.
3. Retain the observation or analysis artifact. Record its exact byte length
   and SHA-256, declared evidence kind, build, and session. A process session
   should include enough identity to distinguish restarts, such as PID and
   process creation ticks; addon load/reader identity may also be necessary.
4. Write an assessment identifying its reviewer, method, dates, exact context,
   definition fingerprint, explicit claim/outcome/rationale, and artifact refs.
   A successful native capture alone is acquisition evidence. Semantic support
   needs a review that explains the measured relationship to the proposed field.
5. Hash that assessment and reference it from the catalog. Keep prior contrary
   or expired assessments alongside new ones. Evaluate again at the intended
   build/session/time and retain the report with the catalog and artifacts.

Use `Get-Item -LiteralPath PATH` for length and `Get-FileHash -LiteralPath PATH
-Algorithm SHA256` for file identity. Do not edit retained evidence in place to
make a check pass. Publish a new artifact/assessment and update its reference.
Editing a definition changes its fingerprint; older assessments remain visible
but cannot support the new definition. Invalidation conditions are retained
review instructions, not executable monitoring rules.

## What confidence means

`supported-by-recorded-assessment` means that the retained declarations satisfy
the mechanical policy for this exact context and evaluation time. It does not
mean the program independently proved the reviewer's game interpretation.
`contradicted` and `unqualified` must remain distinguishable from support.
Every report emits all four claim statuses. The field's aggregate status uses
only its explicit `requiredClaims`; it never implies that an omitted restart
or update requirement was satisfied. Consumers must check the particular
claims their use requires.

Byte hashes are verified. Artifact evidence kind, reviewer identity, origin,
build/session attribution, and semantic judgments remain recorded declarations;
there is no signature, reviewer authentication, or live attestation. The report
labels semantic verification as `recorded-assertions-only` and build/session
identity verification as `declared-only`. Evidence is not made trustworthy
merely by hashing it.

Meaning, locator, restart survival, and update survival are separate claims.
An address tied to one process cannot become a durable locator. A restart claim
requires explicit corroboration from distinct sessions of the selected build;
an update claim requires distinct builds. Neither expands applicability to an
unlisted future process or build. Expired and out-of-context records remain
visible, and contradiction cannot be resolved simply by adding more support.
Active restart contradictions anywhere in the field's declared contexts for
the selected build block restart support. Active update contradictions anywhere
in its declared contexts block update support. Meaning and locator claims use
the exact selected context.

## Version-1 files

`field-catalog/1` requires `schemaVersion: 1`, `contractVersion`, `fields`, and
`assessments`. Each assessment reference contains a sibling `path`, exact
`byteLength`, and `sha256`. Paths are relative to the catalog's folder; nested
paths, absolute paths, traversal, and reparse-point links are rejected. Hard-link
aliases are not detected; exact content hashes still bind their bytes.

| Field definition member | Meaning |
|---|---|
| `fieldId`, `meaning`, `units` | Stable label and explicit interpretation. |
| `sourceKind` | `addon`, `native`, `derived`, or `synthetic`. |
| `locator.kind`, `locator.method` | Source-compatible locator type and written locating procedure. |
| `applicability` | Exact `{buildSha256, sessionId}` contexts; no wildcard. |
| `invalidationConditions` | Explicit conditions requiring review; no executable expressions. |
| `requiredClaims` | Two to four claims: `meaning` and `locator` are mandatory; optionally `restart-survival` and `update-survival`. |

Locator kinds are `addon-api`, `module-relative-rva`, `signature-scan`,
`derivation`, `absolute-session-address`, and `synthetic-fixture`, restricted
to their matching source kinds. A method describes how to locate the value;
the catalog does not execute scans or derivations.

`field-assessment/1` requires version/contract, `assessmentId`, `fieldId`,
`fieldDefinitionSha256`, `reviewer`, `method`, `evidenceOrigin`, `assessedAtUtc`,
nullable `expiresAtUtc`, exact `applicability`, `declarations`, and `artifacts`.
Each declaration records `claim`, `outcome` (`supports` or `contradicts`), and
`rationale`. Origin is `synthetic` or `rift-recording`. Each observation artifact
reference contains `evidenceRole: observation`, sibling `path`, exact byte length
and SHA-256, `evidenceKind`, `buildSha256`, and `sessionId`.

Retain unknown-field and old-definition assessments for history. Unsupported
schema versions, unknown/duplicate/missing members, null entries, invalid bounds,
incoherent identity, missing files, and hash mismatches fail validation rather
than being silently discarded. Synthetic evidence cannot affect non-synthetic
field confidence. Assessment expiration is inclusive: at its expiration instant
it no longer supplies active support or contradiction.

Bounds are 64 KiB per catalog/assessment JSON, 128 fields, 256 assessments,
64 applicability contexts per field, 32 invalidation conditions, and four
claims/declarations. Each assessment references at most 16 artifacts; each is
at most 16 MiB, with 64 MiB aggregate artifact verification across all references
(including repeated references). Artifact hashes are streamed. JSON depth is
limited to 16. Artifact contents remain opaque; declared build/session metadata
must agree with the assessment but is not inferred from arbitrary file bytes.

The definition fingerprint uses `RiftReader2.FieldDefinitionFingerprint/1`
binary framing: each UTF-8 string is prefixed by its unsigned 32-bit little-endian
byte length; lists are prefixed by their unsigned 32-bit element count. It
includes the version tag, field ID, meaning, units, source, locator kind/method,
ordered applicability pairs, ordered invalidation conditions, and ordered
required claims. The reader normalizes build hashes to uppercase first. SHA-256
of these bytes is the fingerprint. List reordering also changes the fingerprint;
it is distinct from the exact catalog/assessment file hashes.

The tracked [synthetic bundle](../../samples/catalog/README.md) demonstrates the
complete files and expected results. The validation record documents tested
boundaries and limitations.
