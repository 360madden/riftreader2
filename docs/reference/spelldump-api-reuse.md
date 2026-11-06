# SpellDump: reuse the game's ability catalog

Pair this catalog with [Rift Meter's combat-event patterns](riftmeter-api-reuse.md)
for observed outcomes, exact targets, healing and damage breakdowns.

Source inspected from the RIFT guest on 2026-10-26 through cached-login VMware
Tools. Original addons were not modified, enabled, or renamed. Both source folders
have `.disabled` suffixes; their names alone do not establish current load state.
Source snapshots and SHA256 hashes are preserved in
`artifacts/casting-20261025-01/spelldump-review-02/source.json`.

## What the existing addons actually do

SpellDump 2.1.0 (`SpellDump.lua`, collectAbilities, lines 793 onward) uses just:

```lua
local ids = Inspect.Ability.New.List()
local details = Inspect.Ability.New.Detail(ids)
```

The second call accepts the whole ID table. Its display keeps name, ID, and base
cooldown, sorts by name, and offers copyable output. Most of the addon code is UI,
selection, logging, and persistence; ability discovery itself is small. It does
not read native memory or discover pointers. Its SavedVariables retain settings
and logs, not a complete durable spell catalog.

SpellDump2 (`SpellDump2.lua`, buildAbility around line 211 and collectAbilities
around line 245) uses the same two calls. It displays description, castingTime,
cooldown, rangeMax, weapon requirement, resource cost, channeled, positioned, and
stealthRequired. Costs include Mana, Power, Energy, Charge, Spirit and Planar.
Its raw export is name/cast/cooldown/range/weapon/cost; it omits IDs and several
flags, so preserve the original API detail records for machine use.

Its categories and role labels are addon-derived. The offensive filter excludes
passive/continuous abilities, requires a positive resource cost, then tests range
or weapon-related properties. That can exclude free attacks and include abilities
that do not damage the target. It is not an authoritative offensive-spell list.
Likewise, its melee/ranged categories can overlap because a melee weapon
requirement does not imply melee reach. Keep range and weapon requirement distinct.

## Apply this to RiftReader2

Use the game's complete current-character ability catalog first. Reuse the batch
List/Detail pattern instead of asking the user to identify familiar abilities or
rebuilding spell metadata through memory scans or individual tooltip clicks.
Keep raw IDs/details; add display categories separately. A missing field remains
unknown, rather than automatically meaning no cost, no cooldown, or instant.

Separate catalog facts (description, base cooldown, range, cast/channel flags,
cost and requirements) from fresh readiness (effective cooldown remaining,
outOfRange, unusable, effective target, current resources and castbar). Refresh
readiness immediately before a supervised action and verify the outcome through
combat events. The existing casting addon already uses these APIs; its catalog
inventory now uses SpellDump's batch-call pattern in addon 0.2.0. It retains
passive and free abilities in the catalog while keeping unsupported ability types
out of the supervised Cast picker. Spirit cost, stealth requirements, continuous
flags, icons and focus limits are retained when available.
The API supports more fields than either SpellDump display chooses to retain.

Actual prior dummy evidence established `Event.Combat.abilityNew` as the exact
modern ability ID, even though generated API docs omitted that member. Inspect
working addon code, installed-client documentation, and actual returned records
together. Do not replace exact IDs with name matching or copy derived labels as
game facts. SavedVariables remain offline evidence, not live readiness.

The API inventory now feeds the existing picker/readout. Additional categorized
views remain optional; no heuristic offensive classification is required. Patch
recovery and player-health-loss testing remain deferred.
