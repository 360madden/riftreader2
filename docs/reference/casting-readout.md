# Casting readout and bounded dummy test

## Current interface — 0.5.0

The current addon uses a shared command service and a compact 344-by-226 HUD.
Use `/rr2cast list [page] [size]`, `/rr2cast select EXACT_ID`, `/rr2cast status`,
`/rr2cast record` and `/rr2cast trial` without opening the ability picker or
showing the HUD. Prefix service commands with `json` for structured results.
`/rr2cast abilities` remains the optional graphical picker; `show`, `hide`,
`toggle`, `move X Y` and `reset` control the compact view. Visibility and position
are saved per character. The GUI selects and records through the same service.

Other loaded addons use the versioned `RiftReader2CastingAPI.Execute(request)`
and `Snapshot()` interface. See the [command service documentation](../../addon/RiftReader2Casting/README.md)
for request fields, pagination, response semantics and survival configuration.
Selection uses the character's actual learned catalog; resource checks and
status support the observed resource types rather than assuming Warrior Power.
This does not qualify every class, build or ability mechanic.

Command acceptance is separate from game input and observed effect. The service
does not activate protected frames, cast or clear the external runtime's STOP
latch. The Cast/Stop attack frames and the survival toolbar's cancel control
retain their existing protected action path and measured control geometry.
External RR2 actions continue through the guarded native action backend. There
is no general physical OS-to-addon slash-command transport in this increment.
Detailed timing/resource/trial information is available through commands instead
of a large always-visible panel. Historical implementation and trial notes follow.

**November 14 physical check (AMD-DESKTOP):** the installed 0.5.0 addon reloaded
successfully, returned JSON from a 55-ability learned catalog, accepted exact
Shield of the Chosen selection while hidden, and started a 60-second observation
without showing the HUD or casting. Hidden visibility survived a subsequent UI
reload. Two advancing physical telemetry captures marked hidden Cast/Stop
rectangles unmapped and shown rectangles mapped. A later paint-only fix assigned
explicit context layers; live picker open/close then left both protected footer
buttons visible. The final HUD was placed using `/rr2cast reset` and left shown.
The verification did not execute casts, movement, a combat encounter or Resume.
The 160-test addon/telemetry slice and 78-test action/runtime/STOP slice passed.
Local captures, the previous installed files and screenshot are under
`artifacts/casting-compact-20261114/`. Full-game restart and all-class live
acceptance remain separate from this UI-reload check.

See [SpellDump API reuse](spelldump-api-reuse.md) for the inspected existing
batch ability catalog and the distinction between game facts and addon filters.

The optional `addon/RiftReader2Casting` addon provides a diagnostic panel and
separate secure Cast / Stop autoattack buttons.
It reuses RIFT's `Inspect.Ability.New.List/Detail`, `Inspect.Unit.Lookup/Detail`,
`Inspect.Unit.Castbar`, cooldown begin/end events, and combat outcome events.
It uses RIFT's restricted `EventMacroSet` facility for a named ability and the
standard `stopattack` command. Only a physical click activates those buttons;
there is no timer, automatic retry or rotation. Earlier supervised trials used
a screenshot-reviewed guarded helper. A Lab-2 game-input path is not yet
qualified for 0.4.0; the player can operate the controls manually. Target
selection remains explicit.

## Use

Enable **RiftReader2 Casting Readout** in RIFT's Addons window (Refresh after a
new installation). Choose an ability with **Choose ability**, select a training dummy
in the game, and inspect the readout. **Record 60s** starts observation only and
pins the player, target unit ID and ability ID. It refuses a known cooldown,
active cast/channel, range failure, unusable ability, insufficient/unknown
required resource, or mismatched effective target. A target/player change aborts
the recording. `/rr2cast` shows a hidden panel.

Version **0.2.2** enlarged typography and spacing in the structured HUD:
color-coded observed status, named target/ability, range/cast/channel/cooldown/
Power cards and a separate trial outcome. The supported-type picker displays
**up to 20 named entries per page**; the complete API catalog stays in evidence.
Absent or nonfinite values display as **unknown**, not zero. Exact-target dodge
remains a visible no-hit verdict. The flat **Abilities / Record / Hide** controls
sit inside the panel; the picker overlays them while open, intercepts background
clicks, and stays clear of the protected **Cast / Stop** row below. The native
Cast caption begins **Select ability**, then becomes **Cast: [name]** (shortened
for display when necessary); the secure macro retains the validated full name.

Version **0.2.3** added the version to the HUD title using validated TOC
metadata and a once-per-load teal-green General chat notification such as
**RiftReader2 Casting Readout v0.2.3 initialized.** A console failure has a
guarded colored-print fallback. Labels render on explicit foreground layers;
the fresh read-only Lab-2 capture
`artifacts/rr2-lab2-v023-readonly-capture-20261028-03/` confirms the versioned
title, readable metrics, and secure Cast/Stop row. Malformed ability costs
fail closed, and older trial data retains its original ability ID provenance.

Version **0.2.4** fixes a saved-ability restore path that previously evaluated
`Inspect.Ability.New.Detail` before `pcall`, plus related unguarded API table
access during live read updates. When the modern table/function disappears,
restoration fails safely and the readout shows blocked/unavailable status rather
than crashing. The title and once-per-load notice now contain **v0.2.4**.
The patch is installed and hash-verified **only in RIFT-Lab-2**, with a backup
and no game input: `artifacts/rr2-lab2-hud-deploy-20261028-05/`.
The 0.2.4 deployment required a manual `/reloadui`; the earlier 0.2.3
screenshot does not establish the live behavior of later versions.

## Unified Casting dashboard — 0.3.0

The panel uses a consistent **584 x 602** two-column diagnostic layout with
16-unit outer gutters, 12-unit column spacing, 8-unit row spacing and a clear
visual hierarchy: 22-unit title, 18-unit values, 13-unit metadata and
16-unit action captions. All controls share the same square, bordered,
flat-surface treatment, accessible light text and a 40-unit click target.
The header houses **Hide**; ability selection and **Record 60s** form one
ordinary-action row. A separate labeled **MANUAL ACTIONS / RIFT-PROTECTED**
tray holds the matching flat **Cast** and **Stop attack** controls. The 20-choice
picker uses two aligned columns and never overlays the protected tray.

The protected actions are restricted RIFT **Frame** instances with
`EventMacroSet` attached directly. Their visual fills and captions have
limited mouse masking so they do not consume or proxy clicks. There are no
ordinary input handlers on the protected frames; a human click remains
necessary and the macro continues to use the validated full ability name.
The actual in-game click behavior still needs manual verification.

**API READY** means only that the model's available RIFT target, resource,
range and cooldown checks passed. Separate amber **FACING UNVERIFIED** and
**LINE OF SIGHT UNVERIFIED** indicators deliberately do not assert generic
hostile-target LOS/facing: the saved client documentation exposes XYZ but no
general facing/yaw field; the `blocked` flag is scoped to group members in
that documented build. The next in-game evidence capture should recheck the
current client API before introducing a native or heuristic facing/LOS test.
The v0.3.0 title was visible after a player reload; its chat announcement
remains unverified in the available screenshot. That screenshot also revealed
a hard-to-read **Hide** label; v0.4.0
adds a higher-contrast foreground-layer control, pending a new live check.

## Draggable Casting HUD and slash CLI — 0.4.0

Drag the **Casting** header (away from **Hide**) to move the main dashboard, or
drag the **Abilities** picker header to move both panes together. The protected
**Cast** and **Stop attack** actions follow the dashboard but cannot be
activated through a drag gesture. The position is constrained to the client
viewport and saved per character as `RiftReader2CastingEvidence.hudPosition`
with finite `x`/`y` pixel coordinates. Corrupt saved coordinates are ignored.
If the game is in protected combat, the addon refuses repositioning and shows
an explanatory warning; it also defers restoration until the necessary
viewport and nonsecure state are available. Moving the HUD does not cast.

Enter `/rr2cast help` in game for the colored help guide. All commands are
case-insensitive; `/rr2cast` by itself opens the hidden dashboard:

| Command | Effect |
| --- | --- |
| `/rr2cast` or `/rr2cast show` | Reveal dashboard and manual action tray |
| `/rr2cast hide` or `/rr2cast toggle` | Hide the dashboard, or toggle it |
| `/rr2cast status` | Current API checks, selected target/ability, Power, cooldown, recording and panel position |
| `/rr2cast info` | Addon version, protections, documented limitations and readout details |
| `/rr2cast abilities` | Open the paginated 20-entry/page ability picker (when safe) |
| `/rr2cast record` | Start a supervised 60-second observation without casting |
| `/rr2cast position` | Show dashboard pixel position |
| `/rr2cast move 360 96` | Move dashboard to an example coordinate; actual result is viewport-clamped |
| `/rr2cast reset` | Return to a usable default dashboard location |
| `/rr2cast help` | Detailed colored command reference |

The `/rr2cast` interface never invokes the restricted Cast/Stop actions:
those still require a **physical click** under the game's protection rules.
It refuses unsafe action during secure combat and never promotes uncertain
facing/LOS into **API READY**. Malformed command input fails with a
human-readable usage hint instead of writing corrupted state.

**Live qualification still required after `/reloadui`:** verify that both
header drag handles receive mouse events, the HUD and protected controls stay
aligned, the saved position survives a subsequent reload, Hide is legible,
`/rr2cast help` is readable, and clicking the protected actions behaves
normally. Lua 5.1 mock tests prove policy and error handling, not live hit
regions, focus or RIFT secure-click dispatch. The v0.4.0 title and colored
one-time initialization notification still derive their version from the TOC.

During the bounded recording, click the selected **Cast: [name]** button once
after reviewing current readiness and the remaining recording time. Then use **Stop attack**
to end any follow-on melee. Ability selection/macro configuration is refused in
secure combat or during a trial. The secure Cast button does not itself enforce
the diagnostic readiness checks; supervise the click and let RIFT enforce its
own ability restrictions.
Only positive damage matching the recorded player, target and ability IDs counts
as a confirmed hit. Combat `abilityNew` is authoritative when present; legacy
identifiers may be reconciled through the API. A matching name alone never
establishes success. Miss, immunity, resist,
dodge and parry observations remain distinct outcomes. A timeout without matching
damage means no confirmed hit, not proof that input failed. Do not blindly retry.

Version 0.2.0 also records healing and overhealing. Positive effective healing
produces `intended-heal-confirmed`; overhealing alone produces
`intended-overheal-observed`. Neither is a damage hit or proof of a health change.
The player, ability and intended target must still match exactly; select a friendly
target or self for an appropriately targeted heal. No matching result produces
`no-matching-outcome-observed`. Damage mitigation and overkill remain separate raw
fields. These additions have offline tests and historical damage replay coverage;
live healing/overhealing qualification is pending.

The panel also displays the selected ability's API-provided `rangeMin` / `rangeMax`,
`castingTime` and `channeled` metadata. Each missing or nonfinite range endpoint
shows **unknown**; missing or nonfinite cast time stays **unknown** (only explicit
zero is **instant**). Missing channel state is **unknown**, not `no`. These are
ability properties, not measured player-to-target distance or proof of facing,
line of sight or readiness. API `outOfRange`, cooldown/readiness checks and the
secure Cast/Stop guards are unchanged; picker filtering semantics are unchanged.

The effective cooldown is labeled **ability/GCD**: the documented API describes
the cooldown currently influencing that ability, not a separately qualified GCD
clock. Timings use `Inspect.Time.Frame`. No fixed GCD sleep is used. Facing and
line of sight remain explicitly unverified; player XYZ alone cannot prove them.
This increment is a readout and supervised test, not a complete casting engine.

## Evidence

The [2026-10-26 ranged-reach trial](../validation/casting-ranged-2026-10-26.md)
deployed 0.2.0 and verified the updated layout. Light's Decree dealt 402 Life
damage to the exact selected dummy after an earlier dodged attempt; Power and
12-second cooldown recovery were recorded. Other-target area damage was excluded.
This does not qualify healing, independent GCD, all casting types or game restart.

The panel samples at 10 Hz for up to 60 seconds, retaining at most 630 snapshots,
64 combat events and 64 selected-ability cooldown events per trial. Recent trials
persist as historical saved evidence. The addon consumes prior data on the exact
`SavedVariables.Load.End` event before publishing its new evidence table; early
frame updates do not overwrite persisted data, and duplicate load-end events
are ignored. The last selected ability is restored only after current-API and
nonsecure-state revalidation. No trial resumes from saved state. The addon also
captures selected documentation and related function names through the installed
client's `Inspect.Documentation`.

`RiftReader2CastingEvidence` is a character SavedVariable, written by RIFT when
it saves addon state. Retrieve the resulting `RiftReader2Casting.lua` file through
the existing cached-login VMware Tools route after a normal UI reload. This file
is **offline evidence**, never a live feed. Preserve the original file plus the
external exact process/build identity, reviewed screenshots, and click receipt.
UI reload does not establish full-game restart durability.

## Checks and scope

Run `artifacts/tools/lua-python/Scripts/python.exe -m unittest discover -s tests
-p test_casting_addon.py` for the focused Lua 5.1 checks. The normal validation
script discovers these tests too. See the [live validation and handoff](../workflows/casting-handoff-2026-10-26.md)
for the actual dummy result and earlier failed trials. Health-loss testing and patch recovery
remain deferred; networking and existing control-agent installation are unchanged.
