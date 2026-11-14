-- Optional, observation-only ability readiness wire.
--
-- This module owns a separate Casting model instance.  It never touches the
-- dashboard's selected ability, secure macro, frames, slash commands or trials.
-- The single pinned ability is a current research reference, not cast authority.
local addonInfo, private = ...
local Reference = {}
private.AbilityReference = Reference

local PRODUCER_VERSION = "0.1.0"
local MODEL_VERSION = "0.4.1"
local ABILITY_ID = "A0865F2DE73516486"
local ABILITY_NAME = "Lifebound Veil"
local PREFIX, SUFFIX = "RR2CASTREF1|", "|RR2CASTREFEND"
local MAX_JSON_BYTES = 8192
local PERIOD_SECONDS = 0.25
local RETRY_SECONDS = 2

local sequence, lastPublished, lastSelectAt = 0, nil, nil
local invalidClockSuppressed = false
local model, selected = nil, false

local function finite(value)
    return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function safeCall(fn, ...)
    if type(fn) ~= "function" then return nil, false end
    local ok, value = pcall(fn, ...)
    if not ok then return nil, false end
    return value, true
end

local function typed(value, kind, limit)
    if value == nil then return {status = "unavailable", reason = "missing", kind = kind} end
    if kind == "number" then
        if type(value) ~= "number" then return {status = "invalid", reason = "wrong-type", kind = kind} end
        if not finite(value) then return {status = "invalid", reason = "nonfinite", kind = kind} end
    elseif kind == "boolean" then
        if type(value) ~= "boolean" then return {status = "invalid", reason = "wrong-type", kind = kind} end
    elseif kind == "string" or kind == "unit-id" or kind == "ability-id" then
        if type(value) ~= "string" then return {status = "invalid", reason = "wrong-type", kind = kind} end
        if #value == 0 or #value > (limit or 256) or string.find(value, "[%z\1-\31]") then
            return {status = "invalid", reason = "invalid-string", kind = kind}
        end
    else
        return {status = "invalid", reason = "unsupported-kind", kind = tostring(kind)}
    end
    return {status = "ok", kind = kind, value = value}
end

local function jsonEscape(value)
    return '"' .. string.gsub(value, '[%z\1-\31\\"]', function(character)
        if character == '"' then return '\\"' end
        if character == '\\' then return '\\\\' end
        return string.format("\\u%04X", string.byte(character))
    end) .. '"'
end

local function jsonEncode(value, stack)
    local valueType = type(value)
    if valueType == "nil" then return "null" end
    if valueType == "boolean" then return value and "true" or "false" end
    if valueType == "number" then
        if not finite(value) then error("non-finite JSON number") end
        return tostring(value)
    end
    if valueType == "string" then return jsonEscape(value) end
    if valueType ~= "table" then error("unsupported JSON value") end
    stack = stack or {}
    if stack[value] then error("cyclic JSON table") end
    stack[value] = true
    local keys = {}
    for key in pairs(value) do
        if type(key) ~= "string" then error("JSON object keys must be strings") end
        keys[#keys + 1] = key
    end
    table.sort(keys)
    local parts = {}
    for _, key in ipairs(keys) do
        parts[#parts + 1] = jsonEscape(key) .. ":" .. jsonEncode(value[key], stack)
    end
    stack[value] = nil
    return "{" .. table.concat(parts, ",") .. "}"
end
Reference.EncodeJson = jsonEncode

local function addonVersion()
    local toc = type(addonInfo) == "table" and addonInfo.toc
    local value = type(toc) == "table" and toc.Version
    if type(value) == "string" and #value > 0 and #value <= 24 and
            not string.find(value, "[^%w%.%-]") then return value end
    return MODEL_VERSION
end

local initialClock = safeCall(type(Inspect) == "table" and
    type(Inspect.Time) == "table" and Inspect.Time.Frame or nil)
local loadToken = finite(initialClock) and string.format("frame-%.6f", initialClock) or "unavailable"

local function ensureModel(clock)
    if model == nil and type(private.Casting) == "table" and
            type(private.Casting.New) == "function" and type(Inspect) == "table" then
        local ok, value = pcall(private.Casting.New, Inspect)
        if ok and type(value) == "table" then model = value end
    end
    if model == nil then return false end
    if not selected and (lastSelectAt == nil or not finite(clock) or clock - lastSelectAt >= RETRY_SECONDS) then
        lastSelectAt = clock
        local ok, value = pcall(model.Select, model, ABILITY_ID)
        selected = ok and value == true
    end
    return selected
end

local function publish(snapshot)
    RiftReader2CastingAbilityReference = snapshot
    local ok, value = pcall(jsonEncode, snapshot)
    if not ok or #value > MAX_JSON_BYTES then
        RiftReader2CastingAbilityReferenceJson = nil
        RiftReader2CastingAbilityReferenceWire = nil
        return false
    end
    RiftReader2CastingAbilityReferenceJson = value
    RiftReader2CastingAbilityReferenceWire = PREFIX .. value .. SUFFIX
    return true
end

-- model:Read() owns the readiness decision.  A second detail is used only to
-- retain strict typed fields in the wire, so every readiness-relevant value
-- must still equal the model observation.  Otherwise neither sample is
-- represented as a coherent ability state.
local coherentAbilityKeys = {
    "id", "idNew", "name", "target", "currentCooldownRemaining",
    "currentCooldownPaused", "unusable", "outOfRange", "passive",
    "positioned", "autoattack", "costPower", "costMana", "costEnergy",
    "costCharge", "costSpirit", "costPlanarCharge",
}
local function abilityDetailsCoherent(observed, current)
    if type(observed) ~= "table" or type(current) ~= "table" then return false end
    for _, key in ipairs(coherentAbilityKeys) do
        if observed[key] ~= current[key] then return false end
    end
    return true
end

local function unavailable(clock, reason)
    return {
        schemaVersion = 1,
        producer = "RiftReader2CastingAbilityReference",
        producerVersion = PRODUCER_VERSION,
        addonVersion = addonVersion(),
        loadToken = loadToken,
        loadedAtFrame = typed(initialClock, "number"),
        sequence = sequence,
        frameClock = typed(clock, "number"),
        source = "rift-api",
        lineage = {
            model = "RiftReader2Casting/private.Casting",
            calls = "Inspect.Ability.New.Detail;Inspect.Unit.Lookup;Inspect.Unit.Detail;Inspect.Unit.Castbar",
            installedSourceSha256 = "external-deployment-receipt-required",
            sampling = "sequential-non-atomic",
        },
        referenceAbility = {lookupId = ABILITY_ID, expectedName = ABILITY_NAME},
        playerId = typed(nil, "unit-id"), targetId = typed(nil, "unit-id"),
        player = {health = typed(nil, "number"), mana = typed(nil, "number"),
                  combat = typed(nil, "boolean")},
        ability = {lookupId = ABILITY_ID, id = typed(nil, "ability-id"),
                   idNew = typed(nil, "ability-id"), name = typed(nil, "string"),
                   costMana = typed(nil, "number"), target = typed(nil, "unit-id")},
        castbar = {ability = typed(nil, "ability-id"), abilityName = typed(nil, "string")},
        readiness = {status = "blocked", reason = reason},
        facingAndLineOfSight = "unverified",
        actionAllowed = false,
    }
end

function Reference.Refresh(force, suppliedClock)
    local clock = suppliedClock
    if clock == nil then
        clock = safeCall(type(Inspect) == "table" and
            type(Inspect.Time) == "table" and Inspect.Time.Frame or nil)
    end
    if not finite(clock) then
        if invalidClockSuppressed and not force then
            return RiftReader2CastingAbilityReference
        end
        invalidClockSuppressed = true
        sequence = sequence + 1
        local snapshot = unavailable(clock, "frame-clock-invalid")
        publish(snapshot)
        return snapshot
    end
    local recoveredFromInvalidClock = invalidClockSuppressed
    invalidClockSuppressed = false
    if not force and not recoveredFromInvalidClock and finite(clock) and finite(lastPublished) and
            clock >= lastPublished and clock - lastPublished < PERIOD_SECONDS then
        return RiftReader2CastingAbilityReference
    end
    sequence = sequence + 1
    if finite(clock) then lastPublished = clock end
    if not ensureModel(clock) then
        local snapshot = unavailable(clock, "reference-ability-unavailable")
        publish(snapshot)
        return snapshot
    end

    local readOk, observation = pcall(model.Read, model)
    if not readOk or type(observation) ~= "table" then
        local snapshot = unavailable(clock, "model-read-unavailable")
        publish(snapshot)
        return snapshot
    end
    local abilityApi = type(Inspect.Ability) == "table" and
        type(Inspect.Ability.New) == "table" and Inspect.Ability.New.Detail or nil
    local rawAbility, rawOk = safeCall(abilityApi, ABILITY_ID)
    if not rawOk or type(rawAbility) ~= "table" then rawAbility = {} end
    local lookup = type(Inspect.Unit) == "table" and Inspect.Unit.Lookup or nil
    local afterPlayer = safeCall(lookup, "player")
    local afterTarget = safeCall(lookup, "player.target")

    local ability = observation.ability or {}
    local player = observation.player or {}
    local cast = observation.cast or {}
    local status = type(observation.status) == "string" and observation.status or "blocked"
    local reason = type(observation.reason) == "string" and observation.reason or "model-status-invalid"
    local canonicalId = rawAbility.idNew or rawAbility.id
    if not rawOk then status, reason = "blocked", "ability-detail-unavailable"
    elseif not abilityDetailsCoherent(ability, rawAbility) then
        status, reason = "blocked", "ability-detail-inconsistent"
    elseif canonicalId ~= ABILITY_ID then status, reason = "blocked", "ability-id-mismatch"
    elseif rawAbility.name ~= ABILITY_NAME then status, reason = "blocked", "ability-name-mismatch"
    elseif afterPlayer ~= observation.playerId or afterTarget ~= observation.targetId then
        status, reason = "blocked", "identity-changed-after-detail"
    end

    local snapshot = {
        schemaVersion = 1,
        producer = "RiftReader2CastingAbilityReference",
        producerVersion = PRODUCER_VERSION,
        addonVersion = addonVersion(),
        loadToken = loadToken,
        loadedAtFrame = typed(initialClock, "number"),
        sequence = sequence,
        frameClock = typed(observation.clock, "number"),
        source = "rift-api",
        lineage = {
            model = "RiftReader2Casting/private.Casting",
            calls = "Inspect.Ability.New.Detail;Inspect.Unit.Lookup;Inspect.Unit.Detail;Inspect.Unit.Castbar",
            installedSourceSha256 = "external-deployment-receipt-required",
            sampling = "sequential-non-atomic",
        },
        referenceAbility = {lookupId = ABILITY_ID, expectedName = ABILITY_NAME},
        playerId = typed(observation.playerId, "unit-id", 128),
        targetId = typed(observation.targetId, "unit-id", 128),
        player = {
            health = typed(player.health, "number"),
            mana = typed(player.mana, "number"),
            combat = typed(player.combat, "boolean"),
        },
        ability = {
            lookupId = ABILITY_ID,
            id = typed(rawAbility.id, "ability-id", 128),
            idNew = typed(rawAbility.idNew, "ability-id", 128),
            name = typed(rawAbility.name, "string", 120),
            costMana = typed(rawAbility.costMana, "number"),
            target = typed(rawAbility.target, "unit-id", 128),
            currentCooldownRemaining = typed(rawAbility.currentCooldownRemaining, "number"),
            currentCooldownPaused = typed(rawAbility.currentCooldownPaused, "boolean"),
            unusable = typed(rawAbility.unusable, "boolean"),
            outOfRange = typed(rawAbility.outOfRange, "boolean"),
            passive = typed(rawAbility.passive, "boolean"),
            positioned = typed(rawAbility.positioned, "boolean"),
            autoattack = typed(rawAbility.autoattack, "boolean"),
        },
        castbar = {
            ability = typed(cast.ability, "ability-id", 128),
            abilityName = typed(cast.abilityName, "string", 120),
            remaining = typed(cast.remaining, "number"),
            channeled = typed(cast.channeled, "boolean"),
        },
        readiness = {status = status, reason = reason,
                     modelStatus = observation.status, modelReason = observation.reason},
        facingAndLineOfSight = "unverified",
        actionAllowed = false,
    }
    publish(snapshot)
    return snapshot
end

function Reference.OnUpdate()
    local clock = safeCall(type(Inspect) == "table" and
        type(Inspect.Time) == "table" and Inspect.Time.Frame or nil)
    Reference.Refresh(false, clock)
end

Reference._test = {
    abilityId = ABILITY_ID, abilityName = ABILITY_NAME,
    jsonEncode = jsonEncode, maxJsonBytes = MAX_JSON_BYTES,
    prefix = PREFIX, suffix = SUFFIX,
    abilityDetailsCoherent = abilityDetailsCoherent,
}

local update = type(Event) == "table" and type(Event.System) == "table" and
    type(Event.System.Update) == "table" and Event.System.Update.Begin or nil
if update ~= nil and type(Command) == "table" and type(Command.Event) == "table" and
        type(Command.Event.Attach) == "function" then
    pcall(Command.Event.Attach, update, function() Reference.OnUpdate() end,
        "RR2 casting ability reference")
end

-- Initial publication is best effort.  Any API failure remains a typed blocked
-- frame and cannot prevent main.lua from constructing the existing dashboard.
pcall(Reference.Refresh, true)
