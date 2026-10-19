# 0005: Content-bound field catalog and recorded qualification

Status: accepted implementation choice under Joey's step-5 authorization.
Date: 2026-10-19.

## Decision

Use small versioned JSON files for field definitions, assessments, and references
to retained artifacts. Keep qualification rules in Application, values in
Domain, file verification in Infrastructure, and offline composition in CLI.
No database, background service, new project, or live-game dependency is needed.

A field definition records meaning, units, source, locating method, exact
applicability, and invalidation conditions. Its content fingerprint binds every
assessment to that definition; changing meaning or locator cannot silently
reuse an earlier assessment. An absolute session address is insufficient for a
durable locator claim.

Evaluate at an explicit time and exact build/session context. Keep separate
claims for meaning, locator, restart, and update. Restart requires recorded
evidence from distinct sessions on the same build; update requires distinct
builds. These claims do not grant unbounded future applicability. Contradictory,
expired, future, and out-of-scope evidence stays visible in the report.

Artifact hashes verify retained bytes. Reviewer assertions describe their
interpretation of those bytes. Neither hashes nor successful raw-memory reads
independently prove a game-field meaning. Report this distinction explicitly;
do not label synthetic examples as live RIFT evidence or treat a positive
assessment as independent certification.

## Consequences

Reports can be rebuilt from retained files without AI interpretation. Assessment
history is append-oriented; disagreement is retained rather than resolved by
silently replacing an earlier result. Definition changes require new bound
assessments. Human review and live experiment quality remain separate obligations
from mechanical integrity and qualification-rule checks.

The implementation remains file based until step 7 has a measured need for an
index. Step 6's experiment controls and live field discovery remain separate.
See the [catalog contract and workflow](../reference/field-catalog.md).
