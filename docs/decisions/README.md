# Decision register

This register separates accepted scope from proposed technical design.

## Agreed scope — 2026-10-18

Source: Joey's instructions in the RiftReader v2 conversation.

| Decision | Status |
|---|---|
| Create a separate `C:\work\riftreader2` folder and initialize Git. | Authorized repository preparation. |
| Prepare folder structure, documentation, and Codex/Workbridge guidance first. | Authorized repository preparation. |
| Discuss architecture before creating application code or a skeleton. | Initial boundary superseded by Joey's architecture/foundation implementation authorization on 2026-10-18. |
| Prioritize faster, reliable collection and durable, reusable findings. | Project direction. |
| Create an improved RiftReader2 guided by this repository; use V1 as reference rather than copying its application or inheriting its architecture by default. Evaluate selective reuse on its merits. | Explicitly reaffirmed by Joey on 2026-10-18; technical reuse choices remain open. |
| Use movement/turning to support reliable testing; keep dedicated automation/navigation/combat for a separate future program. | Scope direction. |

## Implementation decisions

- [0001: Modular offline foundation](0001-modular-offline-foundation.md):
  selected under Joey's explicit architecture and implementation authorization.
- [0002: Hybrid Lua addon and external reader](0002-hybrid-addon-and-reader.md):
  Joey's explicit hybrid requirement; the addon is a first-class product part.
- [0003: Addon observation contract](0003-addon-observation-contract.md):
  minimal Lua producer, strict .NET decoder, and shared cross-language fixtures.
- [0004: Nonce-bound addon transport](0004-nonce-bound-addon-transport.md):
  preserved RR2A1 payload, one-load reader nonce, and external freshness tracker.
- [0005: Durable field catalog](0005-durable-field-catalog.md):
  content-bound definitions, retained assessments, and scoped qualification.

## Future records

Use a short numbered Markdown record here when a material choice is made, for
example `0001-short-title.md`. The
[decision template](../templates/decision-record.md) is optional.

State the decision, its status, date, who or what authorized it, relevant
evidence, alternatives considered, and consequences. A later decision should
mark an old choice superseded instead of silently rewriting history.

Numbered records above own accepted runtime and protocol choices. Unrecorded
future storage, transport, native-access, and experiment details remain open
until implemented or explicitly decided.
