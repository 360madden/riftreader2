# Bidirectional hybrid validation — 2026-10-28

Status: **Phase 1 static Lab 2 loop passed once; broader durability remains open.**

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
- The final helper gate passed: **539 .NET tests**, **962 Python tests with two
  skips**, **110 Lua lifecycle/encoder checks plus 22 existing shared cases**,
  **two round trips**, and **685 link checks**. Evidence is in
  [`20261029T014842Z-76addab5`](../../artifacts/validation/20261029T014842Z-76addab5/)
  and [`bidirectional-helper-final-gate-20261028.log`](../../artifacts/bidirectional-helper-final-gate-20261028.log).
- Deferred-result intent mode is implemented, independently reviewed, and
  covered by that gate. It freezes and reviews destination/sequence intent,
  then calculates from a fresh source at execution time. This is offline/helper
  validation by itself; the first separate live use is recorded below.

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
- Reader lifetimes were bounded: initial 300-second and 900-second launches,
  followed by an 1800-second launch. Their startup receipts remain under
  [`lab2-live-reader`](../../artifacts/bidirectional-20261028/lab2-live-reader/).
  The receiver's `latest.json` is a rolling file; use the frozen receipt in the
  accepted result attempt below for historical source claims.
- The earlier 1800-second Lab 2 reader, PID `3524`, expired at `2026-10-29T01:24:36Z`.
  At that point there was no fresh-reader or current-bound claim; its earlier
  receipt remains historical evidence only. The later acceptance used a new
  reader and nonce as recorded next.

## First live static result loop

- **PASS, one Lab 2 case.** A new bounded reader, PID `9384`, native start ticks
  `639288371649316705`, nonce `ba60619b5e9549e8994db9e9bb571700`, was launched
  by `auto-8359dbbb18bc4e3d8267acbeae68f84c` with expiry
  `2026-10-29T03:19:24.9316705Z`.
- Deferred-result intent `7fca06f4d8b04574ba4fc5c5334cfc41` used current
  source epoch `1`, sequence `2568`, clock `30891.716796875`, player
  `u035400012DFEB5BC`, and a reviewed destination offset of X `+3`, Z `+4`, Y
  `0`. The frozen calculator produced planar distance `5` and result sequence
  `1`; the receipt, report and exact command matched under independent review.
- The guarded manual-style agent delivery completed with stable VM/game identity
  and released keys. The reviewed after-screen visibly shows `RESULT 1`,
  distance `5`, `dX 3`, `dZ 4`, `dY 0`, and chat acceptance with source age
  `1.797s`; the captured guidance panel showed source age about `2.1s`. See
  [`deferred-result-7fca06f4d8b04574ba4fc5c5334cfc41`](../../artifacts/bidirectional-20261028/deferred-result-7fca06f4d8b04574ba4fc5c5334cfc41/), including the
  [independent review](../../artifacts/bidirectional-20261028/deferred-result-7fca06f4d8b04574ba4fc5c5334cfc41/independent-live-review.json).
- A later read-only screenshot shows `UNAVAILABLE` / `Source expired` with no old
  result numbers, demonstrating fail-closed removal after expiry. The capture was
  taken after the limit, not exactly at the TTL boundary, so it does not measure
  expiry timing precision. See
  [`lab2-result-expiry-01`](../../artifacts/bidirectional-20261028/lab2-result-expiry-01/).
- Scope is narrow: this proves one static coordinate-to-distance/display loop in
  Lab 2 through operator-mediated slash-command entry. It does not prove manual
  movement invalidation, a second lab, repeated operation, full-game restart
  durability, facing/cardinal direction, or autonomous gameplay control.

## Recovery and remaining limits

- Lab 1 was blocked specifically at VMware Guest Operations. A root-reviewed,
  UAC-approved `Restart-Service VMTools -Force` reinitialized toolbox/channel at
  `2026-10-29T01:49:40Z`; the next bounded cached-login GuestOps call still timed
  out after 15 seconds. A separately reviewed `Restart-Service VGAuthService
  -Force` changed its native PID from `3176` to `2084`, but the following single
  GuestOps proof also timed out. See
  [`lab1-vgauth-post-audit`](../../artifacts/bidirectional-20261028/lab1-vgauth-post-audit/).
- An elevated installed-MSI Repair using `C:\Windows\Installer\e27ba.msi`,
  `/norestart`, and `REBOOT=ReallySuppress` completed through the installer UI at
  `02:04:26Z`. The one post-Repair cached GuestOps proof again timed out at 15
  seconds. At that checkpoint no VM, Windows, or game restart had been sent. See
  [`lab1-tools-repair-progress-04`](../../artifacts/bidirectional-20261028/lab1-tools-repair-progress-04/)
  and [`lab1-tools-full-repaired-proof`](../../artifacts/bidirectional-20261028/lab1-tools-full-repaired-proof/).
- A root-reviewed visible PowerShell audit independently showed both
  VMware services `Running` and exactly one current game: PID `12136`, UTC start
  ticks `639288278518174834`, executable
  `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, and SHA-256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
  These values were manually transcribed from the screenshot/visible OS console;
  they are **not** successful GuestOps evidence. See
  [`lab1-visible-game-audit-current`](../../artifacts/bidirectional-20261028/lab1-visible-game-audit-current/).
- The final game view showed `43 FPS`, Atank45 in Sanguine Shores, health
  `18208/18208`, power `100/100`, and ReaderBridge `0.3.2` sequence `8406`
  advancing. This establishes visible current health and addon activity, not the
  external GuestOps transport or a guidance result. PowerShell and Programs were
  closed and the preserved Notepad buffer was minimized before recovery continued.
- The user then explicitly approved restarting Lab 1 and rechecking it. An
  orderly Windows `shutdown /r /t 0` began at `02:26:33Z`; the fresh Windows boot
  still produced one 15-second GuestOps timeout. See
  [`lab1-post-reboot-proof`](../../artifacts/bidirectional-20261028/lab1-post-reboot-proof/).
- Recovery required a complete VM stop/start cycle. An orderly Windows
  `shutdown /s /t 0` ended old VMX PID `60472`; a scoped headless start returned
  exit code `0` and created VMX PID `68572`, start ticks
  `134377147707331937`, log epoch `2026-10-29T02:32:50.782Z`, still on port
  `5905`. See
  [`lab1-complete-cycle-start/result.json`](../../artifacts/bidirectional-20261028/lab1-complete-cycle-start/result.json).
- GuestOps is currently recovered in that new VM epoch: the VM-specific cached
  session process-list validation, PowerShell system collector, copy-back and
  guest cleanup all succeeded. The guest reported boot UTC
  `2026-10-29T02:33:00.5000000Z`, both `VMTools` and `VGAuthService` running,
  `5942 MB` free of `8191 MB` RAM, `53.1 GB` free disk, and `games: []`.
  See [`lab1-post-full-cycle-proof`](../../artifacts/bidirectional-20261028/lab1-post-full-cycle-proof/).
- The before/after boundary supports only this statement: the complete VM power
  cycle was the observed recovery step after service restarts, MSI Repair and a
  Windows-only restart had failed. It does **not** establish the underlying cause
  of the GuestOps wedge. RIFT was absent immediately after boot and the recovered
  desktop was captured.
- Lab 1 RIFT was subsequently relaunched through the normal Glyph shortcut with
  the saved login preserved. After the ordinary Play action, authenticated
  GuestOps collected PID `8160`, native UTC start ticks `639288387782122269`,
  executable `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, and SHA-256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
  See [`lab1-game-after-cycle-proof`](../../artifacts/bidirectional-20261028/lab1-game-after-cycle-proof/).
- A broad inventory attempt timed out inside its guest PowerShell script phase;
  that is not a renewed GuestOps transport failure. Later minimal launch
  inventory completed in `8.8s`, and the final exact identity collection
  completed in `14.8s`, demonstrating repeated valid access. This evidence does
  not prove a complete hash inventory of all installed addons.
- Atank45 was selected and ordinary Play was clicked under fresh VM/game guards.
  The client first showed Sanguine Shores while loading at `02:49:45Z`; the final
  in-world screenshot instead shows Atank45 at Thedeor's Circle in Sanctum after
  the full-game exit also exited the prior dimension. It shows `50 FPS`,
  ReaderBridge `0.3.2` sequence `76`, Casting `0.2.3`, and Readiness loaded. See
  [`lab1-after-restart-in-game-01`](../../artifacts/bidirectional-20261028/lab1-after-restart-in-game-01/).
- One guarded Esc closed the ordinary Daily Rewards calendar; remaining addon
  panels were deliberately left visible and no gameplay input was sent. The
  later screen shows `46 FPS`, ReaderBridge sequence `304` and Casting sequence
  `2843` advancing, with no visible Lua error. See
  [`lab1-after-restart-close-calendar`](../../artifacts/bidirectional-20261028/lab1-after-restart-close-calendar/).
- The final authenticated post-load GuestOps proof retained the new VM epoch and
  exact RIFT PID `8160`, native start ticks `639288387782122269`, executable SHA,
  and both VMware services `Running`. See
  [`lab1-final-game-identity`](../../artifacts/bidirectional-20261028/lab1-final-game-identity/).
- This accepts Lab 1 recovery through in-game health and repeated authenticated
  identity reads. It does not qualify any game field, reproduce the Lab 2
  guidance loop in Lab 1, prove all addon hashes, or make the known external
  control-host endpoint ready; that endpoint still refused connection. All VM
  input ended and the console mutex was released after every guarded step.
- Earlier timeout evidence and the sanitized credential boundary remain in
  [`encrypted-tools-and-guest-validation.json`](../../artifacts/bidirectional-20261028/lab1-recovery-research/encrypted-tools-and-guest-validation.json)
  and [research note](../../artifacts/bidirectional-20261028/lab1-recovery-research/findings.md).
- During the Lab 1 service-repair workflow, a focused typo in an existing
  unsaved Notepad buffer (`pIdentifier`) was fully restored with ordinary Undo.
  The reviewed screenshot shows all 280 characters and no unsaved marker; this
  is recovery evidence, not GuestOps or addon evidence. See
  [`lab1-notepad-undo-click`](../../artifacts/bidirectional-20261028/lab1-notepad-undo-click/).
- The live receipt demonstrates outbound reader delivery and external reading;
  it does not create a general inbound addon API. The supported return path in
  this phase remains reviewed manual-style slash-command entry.
- No arrival, facing, left/right steering, route progression, movement, combat
  action, protected macro, or patch durability is established. Lab 1 proves one
  post-cycle full-game relaunch with fresh process identity and visible addon
  activity; it does not prove guidance-result durability across that restart.

## Acceptance boundary

The Phase 1 static acceptance boundary was met for the single Lab 2 case above:
fresh reader/source identity, calculation inside the age windows, exact guarded
delivery, matching source identity, visible result, and later unavailable state.
Any claim of repeatability, movement invalidation, second-lab operation or
restart durability still requires its own fresh evidence. Expired-reader data or
a merely completed input receipt remains insufficient.
