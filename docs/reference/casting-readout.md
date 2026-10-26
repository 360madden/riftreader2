# Casting readout and bounded dummy test

The optional `addon/RiftReader2Casting` addon is a read-only diagnostic panel.
It reuses RIFT's `Inspect.Ability.New.List/Detail`, `Inspect.Unit.Lookup/Detail`,
`Inspect.Unit.Castbar`, cooldown begin/end events, and combat outcome events.
It does not cast, select targets, change macros, or drive a rotation. The existing
screenshot-reviewed guarded helper supplies the single action-bar click.

## Use

Enable **RiftReader2 Casting Readout** in RIFT's Addons window (Refresh after a
new installation). Choose an ability with **Abilities**, select a training dummy
in the game, and inspect the readout. **Record 30s** starts observation only and
pins the player, target unit ID and ability ID. It refuses a known cooldown,
active cast/channel, range failure, unusable ability, insufficient/unknown
required resource, or mismatched effective target. A target/player change aborts
the recording. `/rr2cast` shows a hidden panel.

During the bounded recording, activate the reviewed action-bar ability once.
Only positive damage matching the recorded player, target and ability IDs counts
as a confirmed hit. Old/new ability identifiers may be reconciled through the
API; a matching name alone never establishes success. Miss, immunity, resist,
dodge and parry observations remain distinct outcomes. A timeout without matching
damage means no confirmed hit, not proof that input failed. Do not blindly retry.

The effective cooldown is labeled **ability/GCD**: the documented API describes
the cooldown currently influencing that ability, not a separately qualified GCD
clock. Timings use `Inspect.Time.Frame`. No fixed GCD sleep is used. Facing and
line of sight remain explicitly unverified; player XYZ alone cannot prove them.
This increment is a readout and supervised test, not a complete casting engine.

## Evidence

The panel samples at 10 Hz for up to 30 seconds, retaining at most 330 snapshots,
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
script discovers these tests too. Training-dummy live results are recorded in
`docs/status.md` when actually completed. Health-loss testing and patch recovery
remain deferred; networking and existing control-agent installation are unchanged.
