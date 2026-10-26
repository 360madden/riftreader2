# Rift Meter: combat outcome API reference

Inspected the installed guest `RiftMeter/RiftMeter.lua` on 2026-10-26 through
cached-login VMware Tools. TOC identifies Rift Meter 1.2, Environment 3.4. A second
`.disabled` source copy was also retrieved. No addon was changed and no game input
was sent. Source snapshots/hashes:
`artifacts/casting-20261025-01/riftmeter-review-01/source.json`.

## Reusable evidence patterns

- Lines 1516-1523 subscribe to `Event.Combat.Damage`, `Heal`, `Death`, `Dodge`,
  `Immune`, `Miss`, `Parry`, and `Resist` through `Command.Event.Attach`.
- `AbilityDetail:new`, around line 359, uses **info.abilityNew** as the modern
  ability ID and `Inspect.Ability.New.Detail` for its icon. This independently
  confirms the field used in the successful RiftReader2 dummy trial; generated
  API documentation did not list it.
- `CombatEventsHandler`, around line 1277, attributes results with `info.caster`,
  `info.target`, ability ID, amount, and event type. It retains damage/healing done
  and received, overkill and overhealing.
- `Ability:add`, around line 270, separates hits, crits, dodges, immunity, misses,
  parries and resists. It accumulates absorbed, blocked, deflected, intercepted
  and modified damage when those fields exist.
- `Inspect.Unit.Detail` supplies unit identity/name and, when fully available,
  calling, relation and alliance. `Inspect.Unit.Lookup(id .. '.owner')` links pets
  to owners. `Inspect.Time.Frame` supplies event/session timing.
- The addon derives totals, rates, min/max results and death histories from those
  observations. These are calculations over events, not separate game facts.

## What not to copy into qualification

The meter falls back to ability names for grouping when modern IDs are absent.
That is useful for display but does not prove our exact selected ability hit.
Keep unresolved IDs explicit. Pet/owner merging is a presentation choice; preserve
the original caster ID. Absorbs may be included in displayed totals by preference;
keep raw damage and absorb fields separate.

This implementation ignores events outside its own active combat session and can
drop events if caster unit details are unavailable. It ends ordinary sessions
after six seconds without qualifying damage. Those are meter policies, not proof
that a spell failed, no healing occurred, or a cooldown expired. In particular,
out-of-combat Light's Balm evidence should not depend on its visible totals.
An overheal event can help establish a healing result at full health; it does not
establish a health change or qualify a native health field. That test stays deferred.

## Combined workflow

Use [SpellDump's ability catalog](spelldump-api-reuse.md) to determine what the
character knows and its reported requirements. Use fresh ability/unit/castbar
inspection to assess readiness. Use Rift Meter's combat-event patterns to determine
what actually happened and to whom. Keep raw events before deriving summaries.
The existing casting addon already handles damage/outcome IDs; healing, mitigation
and pet attribution are useful later extensions, not claimed implemented here.
