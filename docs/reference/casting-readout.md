# Casting readout and bounded dummy test

See [SpellDump API reuse](spelldump-api-reuse.md) for the inspected existing
batch ability catalog and the distinction between game facts and addon filters.

The optional `addon/RiftReader2Casting` addon provides a diagnostic panel and
separate secure Cast / Stop autoattack buttons.
It reuses RIFT's `Inspect.Ability.New.List/Detail`, `Inspect.Unit.Lookup/Detail`,
`Inspect.Unit.Castbar`, cooldown begin/end events, and combat outcome events.
It uses RIFT's restricted `EventMacroSet` facility for a named ability and the
standard `stopattack` command. Only a physical click activates those buttons;
there is no timer, automatic retry or rotation. The existing screenshot-reviewed
guarded helper supplies each bounded click. Target selection remains explicit.

## Use

Enable **RiftReader2 Casting Readout** in RIFT's Addons window (Refresh after a
new installation). Choose an ability with **Abilities**, select a training dummy
in the game, and inspect the readout. **Record 60s** starts observation only and
pins the player, target unit ID and ability ID. It refuses a known cooldown,
active cast/channel, range failure, unusable ability, insufficient/unknown
required resource, or mismatched effective target. A target/player change aborts
the recording. `/rr2cast` shows a hidden panel.

Version **0.2.1** replaces the crowded multiline readout with a structured HUD:
color-coded observed status, named target/ability, range/cast/channel/cooldown/
Power cards and a separate trial outcome. The supported-type ability picker shows
24 named entries per page; the complete API catalog remains in saved evidence.
Nonfinite and absent values display as unknown, not zero. An exact-target dodge
is described in the visible trial detail without changing its no-hit verdict.
The flat **Abilities / Record / Hide** controls sit inside the panel, while the
restricted manual **Cast / Stop** buttons form one aligned row below. Hiding and
reopening these secure buttons requires the game to be outside secure combat.
This layout has offline tests but still needs fresh in-game visual verification.

During the bounded recording, click the named **Cast** button once after reviewing
current readiness and the remaining recording time. Then use **Stop autoattack**
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
secure Cast/Stop guards are unchanged; ability picking behaves as before.

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
and the selected ability survive UI reload as historical saved evidence. A trial
is never resumed from saved state. The addon also captures selected documentation
and related function names through the installed client's `Inspect.Documentation`.

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
