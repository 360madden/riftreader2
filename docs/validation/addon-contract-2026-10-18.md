# Minimal addon and decoder validation

Date: 2026-10-18 (America/New_York). Scope: offline RiftReader2 only.

Joey authorized a minimal Lua addon, C# decoder, and shared contract tests.
[ADR 0003](../decisions/0003-addon-observation-contract.md) records the selected
boundary; [the contract](../../contracts/addon/README.md) owns exact semantics.

## Observed checks

Command: `pwsh -NoProfile -File scripts/validate.ps1`.

- SDK 10.0.302 locked restore and Release build passed, zero warnings/errors.
- 138 C# tests passed, including 11 shared accepted scenarios, 36 rejected wire
  fixtures, framing boundaries, typed values, exact-frame hash, CLI rejection,
  cancellation, no-overwrite output, and the unchanged motion-analysis suite.
- 85 Lua assertions passed using actual Lua 5.1 through pinned `lupa==2.8`.
  Tests exercise throttling, zero/false, identity races, clock failure/recovery/
  regression, sequence/epoch exhaustion, serialization recovery, event callback
  behavior, missing APIs, global clearing, and a simulated addon reload.
- All 11 actual Lua-generated frames decoded through the built C# CLI and
  matched the same shared expectations, including nonfinite inputs, double
  extremes, escaped IDs, unavailable values, and zero/false preservation.
- The TOC executed as Lua in an isolated environment; metadata and startup
  module order passed. Every listed module executed in the Lua test runtime.
- Formatting, module boundaries, deterministic synthetic replay, documentation
  links, and tracked/untracked source whitespace checks passed.

Evidence directory: `artifacts/validation/20261019T010334Z-adba924a/`.
Its `addon/` directory preserves each exact `.wire` and decoded `.json`; the
parent contains matching deterministic `analysis.json` and `replay.json`.
This full gate checked 113 relative links. Documentation-only handoff edits
received a subsequent link and Git check. UTC directory date differs from the
local review date. Generated evidence is ignored by Git.

Test tooling was installed in `artifacts/tools/lua-python/` using the pinned
development requirement and an already cached wheel. The addon itself has no
Python or third-party runtime dependency. No global tool settings changed.

## Evidence and limits

API shape was informed by read-only primary local source:

- `C:\rift modding\RiftReader\addon\RiftReaderApiProbe\RiftAddon.toc`:
  RIFT metadata syntax and environment 4.4.
- `C:\rift modding\RiftReader\addon\RiftReaderApiProbe\validation.lua`:
  frame clock, player identity/detail APIs, and startup/update event names.
- `C:\rift modding\RiftReader\addon\ReaderBridge\ReaderBridge.lua`:
  `Command.Event.Attach(event, handler, id)` usage.

These sources inform compatibility assumptions; V1 was neither modified nor
tested. The V2 package is independently implemented. REA/Ghidra were not needed
for this source/contract increment.

Mocked APIs do not prove current RIFT support. No addon deployment, live API
capture, transport, native locator, process/build binding, restart/update
survival, or freshness qualification occurred. `epoch` and `sequence` can repeat
after reload; decoded reports always remain unbound and freshness unverified.
Frame SHA-256 identifies bytes and does not authenticate their source.
