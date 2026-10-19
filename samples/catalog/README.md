# Synthetic catalog example

This flat bundle contains fabricated observations, field definitions, and
reviewer assessments. It tests the qualification workflow; it is not RIFT
evidence. Build hashes made of `A` and `B` and all session IDs are synthetic.

Evaluate at `2026-10-19T00:00:00Z`, build `A` repeated 64 times, session
`synthetic-session-a`, using the command in the
[catalog guide](../../docs/reference/field-catalog.md).

Expected fields:

- `demo.supported`: all four claims supported by recorded synthetic assessments;
  restart uses two sessions of build A, update uses build A and build B.
- `demo.disputed`: current conflicting meaning assessments; an older expired
  record remains visible.
- `demo.address-only`: a demonstration of an insufficient native locator,
  with no assessment or real game applicability.

All referenced files have exact byte-length and SHA-256 pins. Preserve LF line
endings. Changing an observation requires updating its assessment reference and
then the assessment hash in the catalog. Changing a field definition requires a
new definition fingerprint and new assessments. Deliberately keep contradictory
and expired history; do not regenerate it into unanimous support.
