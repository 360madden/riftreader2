# Bidirectional hybrid validation — 2026-10-28

Status: **partial live validation; Phase 1 result display is not yet proved.**

This report separates source implementation and offline checks from what was
actually observed in RIFT. The saved [roadmap](../planning/bidirectional-hybrid-two-lab-roadmap.md)
and [feasibility record](../planning/bidirectional-feasibility-2026-10-28.md)
remain plans and constraints, not live evidence. Generated evidence is under
[`artifacts/bidirectional-20261028`](../../artifacts/bidirectional-20261028/).

## Implemented

- The external application can validate a current reader snapshot, calculate
  planar distance and signed X/Z/Y deltas, and emit one bounded
  `/rr2guide result ...` command. See
  [`AddonGuidanceCalculator.cs`](../../src/RiftReader2.Application/AddonGuidanceCalculator.cs),
  [`AddonGuidanceCommand.cs`](../../src/RiftReader2.Cli/AddonGuidanceCommand.cs),
  and the [operator contract](../reference/addon-guidance.md).
- The core addon implements immutable lab/nonce binding, exact-token and numeric
  bounds, player/epoch/sequence/clock checks, replay rejection, source expiry,
  displacement invalidation, and a passive status/result display. See
  [`guidance.lua`](../../addon/RiftReader2/guidance.lua) and
  [`main.lua`](../../addon/RiftReader2/main.lua).
- The narrow console helper allowlists only guidance bind/status/clear/result
  text plus separately reviewed Esc, Enter, and ordinary Hide controls. It pins
  VM and game identity, requires a fresh screenshot review and sole-controller
  state, and releases keys after use. It does not expose arbitrary Lua, macros,
  protected clicks, or general gameplay input. See
  [`addon_command_console.py`](../../scripts/addon_command_console.py).

## Offline validation

- Lua 5.1 tests exercise binding conflicts without poisoning state, ASCII and
  length limits, counter and finite-number bounds, player/epoch/clock checks,
  stale and rolled-back sources, duplicate/out-of-order results, latched movement
  invalidation, expiry, clear/replay behavior, UI text, and absence of action or
  macro creation. See [`test_guidance_addon.py`](../../tests/test_guidance_addon.py).
- C# tests cover calculation, snapshot gating, identity/freshness checks, and
  command generation. The cross-language contract corpus includes unavailable,
  malformed, escaping, zero/false, clock, player and finite-double cases under
  [`contract-01`](../../artifacts/bidirectional-20261028/contract-01/).
- These checks prove fail-closed parsing and calculation behavior. They do not
  prove current-client command entry, addon receipt, or visible live output.

## Live identity and installation evidence

- Fresh, read-only screenshots captured both running VMs at the same host time
  without input: Lab 1 used VMX PID `60472`, log epoch
  `2026-10-28T23:38:26.950Z`, port `5905`; Lab 2 used PID `42160`, log epoch
  `2026-10-28T01:23:53.486Z`, port `5906`. Each before/after identity was stable.
  See [`lab1-console-correct-runtime`](../../artifacts/bidirectional-20261028/lab1-console-correct-runtime/)
  and [`lab2-console-correct-runtime`](../../artifacts/bidirectional-20261028/lab2-console-correct-runtime/).
- Lab 2 contained one `rift_x64.exe`, PID `2700`, SHA-256
  `1935A05C...20A4BE8`. The native .NET `Process.StartTime.ToUniversalTime().Ticks`
  value is `639288075394270241`. The earlier CIM timestamp serialized only to
  microseconds (`...4270240Z`), which corresponds to a rounded/truncated final
  tick of `...240`; it must not replace the native `...241` identity.
- The core addon deployment was staged, backed up and postflight verified with
  stable VM/game identity and no input. Deployment alone did not reload Lua.
  The user then reloaded the UI; the live screenshot showed
  `RR2 GUIDANCE UNBOUND` and the core initialization messages. See
  [`lab2-deploy`](../../artifacts/bidirectional-20261028/lab2-deploy/) and
  [`runtime-load-review.json`](../../artifacts/bidirectional-20261028/lab2-after-install/runtime-load-review.json).
- The repository's current API-derived RR2 frame was later found by a bounded
  native scan and bound to a fresh nonce. The receipt records player
  `u035400012DFEB5BC`, epoch `1`, advancing source sequence, current frame clock,
  coordinates, health, completed scan, and `bindingStatus: bound` /
  `freshnessStatus: fresh`. See
  [`command-bind-02/bound-receipt.json`](../../artifacts/bidirectional-20261028/command-bind-02/bound-receipt.json).
- Native power remained explicitly unavailable with
  `unsupported-native-power-build`; addon coordinates/health do not qualify a
  native power field.

## Live command-entry findings

- Joey explicitly authorized autonomous bounded guidance entry while away. The
  grant covers reload, bind/status/clear and calculated-result delivery through
  the guarded repository helper; it does not authorize arbitrary commands or
  gameplay automation.
- The first `/rr2guide status` attempt typed a leading slash into RIFT's GUI
  shortcut path and did not establish command execution. Its execution receipt
  proves only that guarded input occurred and keys were released; it is retained
  as a failed transport/UI trial, not addon receipt. See
  [`command-status-01`](../../artifacts/bidirectional-20261028/command-status-01/).
- Recovery used separately reviewed, single-purpose steps: Esc closed ordinary
  panels, Enter opened an empty focused chat field, and exact command text was
  entered only after that chat state was visually proved. Ordinary Readiness and
  Casting **Hide** buttons were individually reviewed and clicked to remove UI
  obstruction; protected action controls were not used. Evidence is under the
  `ui-close-*`, `ui-open-chat-*`, `ui-hide-readiness-*`, and
  `ui-hide-casting-*` artifact directories.
- `command-bind-01` exercised the corrected chat-entry route. After its bounded
  reader expired, `command-bind-02` used a fresh reader nonce and produced the
  bound/fresh receipt above. This proves current API source discovery and live
  nonce binding, not yet calculated-result display.
- Reader processes were deliberately bounded rather than persistent. The first
  lifecycle used a 300-second automatic exit; later autonomous readers used
  900-second expirations. The final 900-second receipt reports
  `readerStatus: terminated`, guidance freshness `unavailable`, and
  `reader-terminated`; prior observations are not treated as live after expiry.
  See [`lab2-live-reader`](../../artifacts/bidirectional-20261028/lab2-live-reader/)
  and [`lab2-live-receiver/latest.json`](../../artifacts/bidirectional-20261028/lab2-live-receiver/latest.json).

## Blocked or not yet proved

- **Phase 1 value is still open:** no retained evidence yet proves one current
  coordinate snapshot was converted into a distance/direction command, accepted
  by the live addon, and displayed in RIFT. Until that receipt/screenshot exists,
  do not claim a practical external-to-addon result loop.
- Lab 1 is independently blocked at VMware Guest Operations. An encrypted,
  credential-protected `checkToolsState` returned `running`, while the single
  cached-login `listProcessesInGuest` validation timed out at 15 seconds. Host
  VM identity stayed stable; no inventory, console input, service restart, raw
  stderr, or secret persistence followed. See the sanitized
  [`encrypted-tools-and-guest-validation.json`](../../artifacts/bidirectional-20261028/lab1-recovery-research/encrypted-tools-and-guest-validation.json)
  and [research note](../../artifacts/bidirectional-20261028/lab1-recovery-research/findings.md).
- The live receipt demonstrates outbound reader delivery and external reading;
  it does not create a general inbound addon API. The supported return path in
  this phase remains reviewed manual-style slash-command entry.
- No arrival, facing, left/right steering, route progression, movement, combat
  action, protected macro, patch durability, or full-game-restart durability is
  established by this trial.

## Acceptance boundary

Promote Phase 1 only after one fresh reader/source identity is pinned, one result
is calculated inside all age windows, the exact result command is delivered by
the guarded chat route, and a post-entry screenshot or read-only addon receipt
shows the same lab, nonce, result sequence, source epoch/sequence/player and
displayed distance/deltas. Expired-reader data or a merely completed input
receipt is insufficient.
