# RiftReader2 Casting command service

Version 0.5.0 loads `commands.lua` before `main.lua`. It is the CLI-first service
shared by the addon's slash command, compact GUI and other loaded addons. It does not click a restricted
frame, cast an ability, send game input or create/clear an independent STOP
latch. Existing guarded native activation of protected frames remains a
separate action backend; the service does not bypass or replace it.

The module exports `private.CastingCommands`. `main.lua` creates the service after
its model and survival callbacks exist, installs the global API, and routes the
GUI's exact ability selection and Record button through the same operations:

```lua
local service = private.CastingCommands.Create({
    snapshot = function() return currentSummary end,
    listLearned = function() return model:Abilities() end,
    selectAbility = function(id) return selectAbility(id) end,
    record = function() return model:Begin() end,
    trialStatus = function() return projectedTrialStatus end,
    survival = function(action, args) return delegateSurvival(action, args) end,
    stopStatus = function() return existingStopStatus end,
})
private.CastingCommands.InstallGlobal(service)
```

Callbacks use the existing Lua convention: mutations return `true, value` or
`false, reason`; summary callbacks return a bounded table or `nil, reason`.
`record` should call the observation model directly and must not depend on the
dashboard being visible. `survival(action, args)` is invoked only for `setup`,
`slot`, `status` and `clear`. `stopStatus` is read-only.

## Structured API

Other loaded addons can use the versioned global:

```lua
local result = RiftReader2CastingAPI.Execute({
    schemaVersion = 1,
    requestId = "caller-17",
    command = "select",
    abilityId = "A0123456789ABCDEF",
})
local status = RiftReader2CastingAPI.Snapshot()
```

Every result includes `schemaVersion`, `serviceVersion`, `command`, optional
`requestId`, `accepted`, `status`, `reason`, `result`, `gameActionSent=false`
and `effectStatus="not-performed"`. Acceptance means the requested query or
configuration was accepted. It never claims that an ability was activated or
that a gameplay effect occurred.

Commands are:

- `capabilities`
- `status`
- `list` with optional `page` and `pageSize` (maximum 25)
- `select` with one exact, case-sensitive `abilityId`
- `record`
- `trial-status`
- `survival` with `action` and bounded `args`

Learned-ability output is capped at 1,024 entries. IDs and arguments are literal,
bounded strings; pages, input length, nesting and returned table size are also
bounded. Status callbacks should return summaries rather than raw trial sample
arrays. Resource summaries are class-neutral and may contain Power, Mana, Energy
or other actually observed model fields.

## Text command

`private.CastingCommands.DispatchText(service, text)` uses the same dispatcher:

```text
status
list 1 8
select A0123456789ABCDEF
record
trial
survival status
survival slot 1 A0123456789ABCDEF
json status
```

Aliases are `help`/`commands` for capabilities and `abilities` for list. A
leading `json` marks the structured result with `outputFormat="json"`.
`private.CastingCommands.EncodeResponse(result)` supplies the bounded encoder
used by the slash handler and preserves command arrays, including empty arrays.

Actual in-game examples are:

```text
/rr2cast status
/rr2cast list 1 8
/rr2cast select A0123456789ABCDEF
/rr2cast record
/rr2cast trial
/rr2cast capabilities
/rr2cast survival status
/rr2cast json status
```

There is currently no external OS-to-RIFT slash-command transport. External
game actions continue to use the existing guarded action backend rather than
injecting shell text or inventing a new command channel.
