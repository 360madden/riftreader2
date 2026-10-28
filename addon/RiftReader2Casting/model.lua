local _, private = ...
local M = {}
private.Casting = M

local function call(f, ...)
    if type(f) ~= "function" then return nil end
    local ok, result = pcall(f, ...)
    if ok then return result end
end
local function number(v)
    return type(v) == "number" and v == v and math.abs(v) < math.huge
end
local function copy(t, keys)
    local r = {}
    if type(t) == "table" then
        for _, k in ipairs(keys) do
            local v = t[k]
            if type(v) == "boolean" or (type(v) == "string" and #v <= 2048) or number(v) then r[k] = v end
        end
    end
    return r
end
local abilityKeys = {"id", "idNew", "name", "description", "target", "castingTime", "channeled",
    "cooldown", "currentCooldownBegin", "currentCooldownDuration", "currentCooldownRemaining",
    "currentCooldownExpired", "currentCooldownPaused", "unusable", "outOfRange", "rangeMin", "rangeMax",
    "costPower", "costMana", "costEnergy", "costCharge", "costSpirit", "costPlanarCharge", "positioned", "passive",
    "continuous", "autoattack", "weapon", "stealthRequired", "icon", "focusMin", "focusMax"}
local unitKeys = {"id", "name", "health", "healthMax", "power", "mana", "energy", "charge", "spirit", "planar", "combo",
    "combat", "relation", "player", "coordX", "coordY", "coordZ"}
local function outcome(t)
    if t.hit then return "intended-hit-confirmed" end
    if t.healingConfirmed then return "intended-heal-confirmed" end
    if t.overhealObserved then return "intended-overheal-observed" end
    return "no-matching-outcome-observed"
end

function M.New(api)
    local self = {api = api, sequence = 0, selected = nil, trial = nil, last = nil}
    local empty = {}
    local function section(name, nested)
        if type(api) ~= "table" then return empty end
        local value = api[name]
        if type(value) ~= "table" then return empty end
        if nested ~= nil then value = value[nested] end
        return type(value) == "table" and value or empty
    end
    function self:Abilities()
        local list = call(section("Ability", "New").List)
        local result = {}
        if type(list) ~= "table" then return result end
        local details = call(section("Ability", "New").Detail, list)
        if type(details) ~= "table" then return result end
        for id in pairs(list) do
            local d = details[id]
            if type(d) == "table" then
                local item = copy(d, abilityKeys); item.lookupId = id
                result[#result + 1] = item
            end
        end
        table.sort(result, function(a,b) return (a.name or a.lookupId) < (b.name or b.lookupId) end)
        return result
    end
    function self:Select(id)
        if self.trial and self.trial.status == "recording" then return false end
        local d = call(section("Ability", "New").Detail, id)
        if type(d) ~= "table" then return false end
        self.selected = id
        return true
    end
    function self:Read()
        self.sequence = self.sequence + 1
        local now = call(section("Time").Frame)
        local player = call(section("Unit").Lookup, "player")
        local target = call(section("Unit").Lookup, "player.target")
        local pd = player and call(section("Unit").Detail, player)
        local td = target and call(section("Unit").Detail, target)
        local ad = self.selected and call(section("Ability", "New").Detail, self.selected)
        local castOk, cast = false, nil
        if player and type(section("Unit").Castbar) == "function" then castOk, cast = pcall(section("Unit").Castbar, player) end
        local r = {sequence = self.sequence, clock = now, playerId = player, targetId = target,
            player = copy(pd, unitKeys), target = copy(td, unitKeys), abilityId = self.selected,
            ability = copy(ad, abilityKeys), cast = copy(cast, {"ability", "abilityName", "begin", "duration", "remaining", "expired", "channeled"}),
            status = "blocked", reason = "unavailable", facingAndLineOfSight = "unverified"}
        -- Keep long tooltip descriptions once in the inventory, not every 100 ms.
        r.ability.description = nil
        if not number(now) or type(pd) ~= "table" then r.reason = "player-unavailable"
        elseif not target or type(td) ~= "table" then r.reason = "no-target"
        elseif type(ad) ~= "table" then r.reason = "select-ability"
        elseif call(section("Unit").Lookup, "player") ~= player or call(section("Unit").Lookup, "player.target") ~= target then r.reason = "identity-changed"
        elseif not number(pd.health) or pd.health <= 0 then r.reason = "player-not-alive"
        elseif not number(td.health) or td.health <= 0 then r.reason = "target-not-alive"
        elseif ad.passive or ad.positioned or ad.autoattack then r.reason = "unsupported-ability-type"
        elseif ad.target ~= target then r.reason = "ability-target-mismatch"
        elseif ad.outOfRange then r.reason = "out-of-range"
        elseif not castOk then r.reason = "cast-state-unavailable"
        elseif ad.currentCooldownRemaining ~= nil and (not number(ad.currentCooldownRemaining) or ad.currentCooldownRemaining < 0) then r.reason = "invalid-cooldown"
        elseif ad.currentCooldownPaused then r.reason = "cooldown-paused"
        elseif number(ad.currentCooldownRemaining) and ad.currentCooldownRemaining > 0 then r.status = "waiting"; r.reason = "cooldown-ability-or-gcd"
        elseif type(cast) == "table" and (cast.ability or cast.abilityName) then r.status = "waiting"; r.reason = "cast-or-channel-active"
        elseif ad.unusable then r.reason = "ability-unusable"
        else
            r.status = "ready"; r.reason = "observed-ready"
            for _, pair in ipairs({{"costPower","power"},{"costMana","mana"},{"costEnergy","energy"},{"costCharge","charge"},{"costSpirit","spirit"},{"costPlanarCharge","planar"}}) do
                local cost = ad[pair[1]]
                if cost ~= nil and (not number(cost) or cost < 0) then
                    r.status = "blocked"; r.reason = "invalid-ability-cost"; break
                elseif number(cost) and cost > 0 and (not number(pd[pair[2]]) or pd[pair[2]] < cost) then
                    r.status = "blocked"; r.reason = "insufficient-or-unknown-" .. pair[2]; break
                end
            end
        end
        self.last = r
        local t = self.trial
        if t and t.status == "recording" then
            if not number(now) or now < t.started then t.status = "aborted"; t.reason = "clock-invalid"
            elseif player ~= t.playerId or target ~= t.targetId then t.status = "aborted"; t.reason = "target-or-player-changed"
            elseif now > t.deadline then t.status = "finished"; t.reason = outcome(t)
            elseif #t.samples < 630 then t.samples[#t.samples + 1] = r end
        end
        return r
    end
    function self:Begin()
        if self.trial and self.trial.status == "recording" then return false, "already-recording" end
        local r = self:Read()
        if r.status ~= "ready" then return false, r.reason end
        -- Observation only: this does not arm a controller or trigger a spell.
        self.trial = {status = "recording", started = r.clock, deadline = r.clock + 60,
            playerId = r.playerId, targetId = r.targetId, targetName = r.target.name,
            abilityId = self.selected, abilityNewId = r.ability.idNew or r.ability.id,
            abilityName = r.ability.name, samples = {r}, events = {}, cooldowns = {}, hit = false,
            healingConfirmed = false, overhealObserved = false}
        return true
    end
    function self:Combat(kind, info)
        local t = self.trial
        if not t or t.status ~= "recording" or type(info) ~= "table" then return end
        local now = call(section("Time").Frame)
        if not number(now) or now < t.started or now > t.deadline then return end
        if call(section("Unit").Lookup, "player") ~= t.playerId or call(section("Unit").Lookup, "player.target") ~= t.targetId then
            t.status = "aborted"; t.reason = "target-or-player-changed"; return
        end
        if info.caster ~= t.playerId then return end
        local event = copy(info, {"caster", "casterName", "target", "targetName", "ability", "abilityNew", "abilityName",
            "damage", "damageAbsorbed", "damageBlocked", "damageDeflected", "damageIntercepted", "damageModified",
            "overkill", "heal", "overheal", "crit", "type"})
        event.clock = now; event.kind = kind
        local detail, normalized
        if info.abilityNew ~= nil then
            normalized = type(info.abilityNew) == "string" and info.abilityNew or nil
            event.abilityMappingSource = "Event.Combat.abilityNew"
        else
            detail = info.ability and call(section("Ability", "New").Detail, info.ability)
            normalized = type(detail) == "table" and (detail.idNew or detail.id) or nil
            event.abilityMappingSource = normalized and "Inspect.Ability.New.Detail" or nil
        end
        if info.abilityNew == nil and not normalized and info.ability and type(section("Ability").Detail) == "function" then
            detail = call(section("Ability").Detail, info.ability)
            normalized = type(detail) == "table" and detail.idNew or nil
            event.abilityMappingSource = normalized and "Inspect.Ability.Detail" or nil
        end
        if type(normalized) ~= "string" or #normalized == 0 or #normalized > 128 then normalized = nil end
        event.normalizedAbilityId = normalized
        if info.abilityNew ~= nil then
            event.matchesAbility = normalized ~= nil and normalized == t.abilityNewId
        else
            event.matchesAbility = info.ability ~= nil and (info.ability == t.abilityId or
                (t.abilityNewId ~= nil and (info.ability == t.abilityNewId or normalized == t.abilityNewId)))
        end
        event.matchesTarget = info.target == t.targetId
        if #t.events < 64 then t.events[#t.events + 1] = event else t.eventsTruncated = true end
        if kind == "damage" and event.matchesAbility and event.matchesTarget and number(info.damage) and info.damage > 0 then
            t.hit = true; t.lastHit = event
        end
        if kind == "heal" and event.matchesAbility and event.matchesTarget then
            if number(info.heal) and info.heal > 0 then t.healingConfirmed = true; t.lastHeal = event end
            if number(info.overheal) and info.overheal > 0 then t.overhealObserved = true; t.lastHeal = event end
        end
    end
    function self:Cooldown(kind, cooldowns)
        local t, now = self.trial, call(section("Time").Frame)
        if not t or t.status ~= "recording" or type(cooldowns) ~= "table" or
            not number(now) or now < t.started or now > t.deadline then return end
        if call(section("Unit").Lookup, "player") ~= t.playerId or call(section("Unit").Lookup, "player.target") ~= t.targetId then return end
        local value = cooldowns[t.abilityId] or (t.abilityNewId and cooldowns[t.abilityNewId])
        if number(value) and #t.cooldowns < 64 then
            t.cooldowns[#t.cooldowns+1] = {kind = kind, clock = now, remaining = value, abilityId = t.abilityId}
        end
    end
    return self
end
