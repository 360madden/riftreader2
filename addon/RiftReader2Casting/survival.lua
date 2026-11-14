-- RR2SURV1 is an outbound, nonce-bound observation from the Casting dashboard.
-- Control commands bind/read the wire or configure its existing restricted
-- cast frame out of combat. Actual game actions require activating the frame.
local info, private = ...
local S = {}
private.Survival = S
local PREFIX, SUFFIX = "RR2SURV1|", "|ENDRR2SURV1"
local PAGE_SIZE, MAX_BYTES = 8, 8192
local nonce, epoch, sequence, lastClock, nextPublish, page = nil, 0, 0, nil, nil, 1
local api, model, selectAbility, controls, prepareSlot, canSetup, cache
local setupCleanupPending=false
local bytes = {}
local lastEvent, lastPositiveEvent, eventSequence = nil, nil, 0
local positives = {}
local lastIncoming, incomingSequence = nil, 0
local lastDeath, deathSequence = nil, 0
local EVENT_MAX_AGE = 2
local POSITIVE_MAX_AGE = 5
local DEATH_MAX_AGE = 5
RiftReader2SurvivalFrames = bytes

local function invoke(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, ...)
    if ok then return value end
end
local function finite(v) return type(v) == "number" and v == v and math.abs(v) < math.huge end
local function text(v, maximum)
    return type(v) == "string" and #v > 0 and #v <= maximum and not string.find(v, "[%z\1-\31]") and v or nil
end
local function project(raw, nums, strings, bools)
    local out = {}
    if type(raw) ~= "table" then return out end
    for key in string.gmatch(nums, "%S+") do if finite(raw[key]) then out[key] = raw[key] end end
    for key in string.gmatch(strings, "%S+") do out[key] = text(raw[key], 128) end
    for key in string.gmatch(bools, "%S+") do if type(raw[key]) == "boolean" then out[key] = raw[key] end end
    return out
end
local function clear()
    nonce, lastClock, nextPublish, cache, sequence, page = nil, nil, nil, nil, 0, 1
    lastEvent,lastPositiveEvent,eventSequence=nil,nil,0
    positives={}
    lastIncoming,incomingSequence=nil,0
    lastDeath,deathSequence=nil,0
    for i = 1, 8 do bytes[i] = nil end
    RiftReader2SurvivalWire = nil
end
local function catalog(clock, playerId)
    if cache and cache.playerId == playerId and clock >= cache.sampledAt and clock-cache.sampledAt < 2 then return cache end
    local source = api.Ability and api.Ability.New
    local list = source and invoke(source.List)
    cache = {playerId=playerId, sampledAt=clock, ids={}, names={}, status="unavailable"}
    if type(list) ~= "table" then return cache end
    local details = invoke(source.Detail, list)
    for id in pairs(list) do
        if not text(id, 128) or #cache.ids >= 1024 then
            cache.ids, cache.names, cache.status = {}, {}, "invalid"
            return cache
        end
        table.insert(cache.ids, id)
        local d = type(details) == "table" and details[id] or nil
        cache.names[id] = type(d) == "table" and text(d.name,128) or ""
    end
    table.sort(cache.ids)
    cache.status = "observed"
    return cache
end
local function catalogPage(c)
    if c.status ~= "observed" then return {status=c.status, sampledAt=c.sampledAt, entries={}} end
    local count, entries = #c.ids, {}
    local pages = math.max(1, math.ceil(count/PAGE_SIZE))
    page = math.min(page, pages)
    for i = (page-1)*PAGE_SIZE+1, math.min(page*PAGE_SIZE,count) do
        local id = c.ids[i]
        entries[id] = c.names[id]
    end
    return {status="observed", count=count, page=page, pages=pages, sampledAt=c.sampledAt, entries=entries}
end
local function trialState()
    local t = model.trial
    if type(t) ~= "table" then return {status="inactive"} end
    local v = project(t,"started deadline","status reason playerId targetId abilityId abilityNewId","hit healingConfirmed eventsTruncated")
    for _, name in ipairs({"lastHit","lastHeal"}) do
        if type(t[name]) == "table" then
            v[name] = project(t[name],"clock damage heal overheal","kind caster target ability abilityNew normalizedAbilityId","matchesTarget matchesAbility")
        end
    end
    return v
end
local function sameUnits(playerId, targetId)
    if type(api.Unit.Lookup) ~= "function" then return false end
    local okP, p = pcall(api.Unit.Lookup,"player")
    local okT, t = pcall(api.Unit.Lookup,"player.target")
    return okP and okT and p == playerId and t == targetId
end
local function oldestEventId(events)
    local oldest, count = nil,0
    for id,e in pairs(events) do
        count=count+1
        if not oldest or e.sequence < events[oldest].sequence then oldest=id end
    end
    return oldest,count
end
function S.ObserveCombat(kind, info)
    if not nonce or type(info) ~= "table" then return end
    local caster, recipient = text(info.caster,128), text(info.target,128)
    if not caster or not recipient then return end
    local p = invoke(api.Unit.Lookup,"player")
    local t = invoke(api.Unit.Lookup,"player.target")
    if not text(p,128) then return end
    local outgoing = caster == p and (recipient == p or recipient == t)
    local incoming = kind == "damage" and caster == t and caster ~= p and recipient == p
        and finite(info.damage) and info.damage > 0
    if not outgoing and not incoming then return end
    local clock = invoke(api.Time.Frame)
    if not finite(clock) then return end
    local id = text(info.abilityNew,128)
    local name
    if id and api.Ability and api.Ability.New then
        local d=invoke(api.Ability.New.Detail,id)
        if type(d) == "table" then name=text(d.name,128) end
    end
    if not id and info.abilityNew == nil and info.ability and api.Ability and api.Ability.New then
        local d = invoke(api.Ability.New.Detail,info.ability)
        if type(d) == "table" then id=text(d.idNew,128) or text(d.id,128) end
    end
    if not sameUnits(p,t) then return end
    local e=project(info,"damage heal overheal","caster target ability abilityNew","crit")
    e.kind,e.clock,e.normalizedAbilityId,e.selectedTargetId = kind,clock,id,t
    e.abilityName=name
    if incoming then
        incomingSequence=incomingSequence+1
        e.sequence,lastIncoming=incomingSequence,e
    else
        eventSequence=eventSequence+1
        e.sequence,lastEvent=eventSequence,e
        if (kind == "damage" and finite(e.damage) and e.damage > 0) or
                (kind == "heal" and finite(e.heal) and e.heal > 0) then
            lastPositiveEvent=e
            if id then
                positives[id]=e
                local oldest,count=oldestEventId(positives)
                if count > 8 then positives[oldest]=nil end
            end
        end
    end
end
function S.ObserveDeath(info)
    if not nonce or type(info) ~= "table" then return end
    local target = text(info.target,128)
    if not target then return end
    local clock = invoke(api.Time.Frame)
    if not finite(clock) or clock < 0 or (lastDeath and clock < lastDeath.clock) then return end
    local e = project(info,"","caster target casterName targetName","")
    -- The documented event requires target; caster is genuinely optional for
    -- environmental, pet, or otherwise unattributed deaths.
    e.target=target
    deathSequence=deathSequence+1
    e.sequence,e.clock=deathSequence,clock
    lastDeath=e
end
local function currentEvent(e, clock, selectedId, maxAge)
    return e and e.selectedTargetId == selectedId and clock >= e.clock and clock-e.clock <= maxAge
end
local function writeFrame(frame)
    local wire = PREFIX .. private.AbilityReference.EncodeJson(frame) .. SUFFIX
    if #wire > MAX_BYTES and frame.catalog.entries and next(frame.catalog.entries) then
        frame.catalog = {status="unavailable",reason="frame-size-budget",entries={}}
        wire = PREFIX .. private.AbilityReference.EncodeJson(frame) .. SUFFIX
    end
    while #wire > MAX_BYTES and frame.positiveEvents and next(frame.positiveEvents) do
        frame.positiveEvents[oldestEventId(frame.positiveEvents)]=nil
        wire=PREFIX .. private.AbilityReference.EncodeJson(frame) .. SUFFIX
    end
    if #wire > MAX_BYTES then
        frame.status, frame.reason = "unavailable", "frame-too-large"
        frame.player, frame.target, frame.ability, frame.cast = {}, {}, {}, {status="unavailable"}
        frame.catalog, frame.controls, frame.trial, frame.readiness = {status="unavailable",entries={}}, {}, {}, {status="blocked",reason=frame.reason}
        wire = PREFIX .. private.AbilityReference.EncodeJson(frame) .. SUFFIX
    end
    bytes[(sequence-1)%8+1] = wire
    RiftReader2SurvivalWire = wire
end
function S.Publish(r)
    if not nonce or type(r) ~= "table" or not finite(r.clock) or r.clock < 0 then return end
    if lastClock and r.clock < lastClock then clear(); return end
    if nextPublish and r.clock < nextPublish then return end
    lastClock, nextPublish, sequence = r.clock, r.clock+.2, sequence+1
    local p, t = text(r.playerId,128), text(r.targetId,128)
    local frame = {schemaVersion=1, addon="RiftReader2Casting", addonVersion=info.toc.Version, source="rift-api",
        sessionId=nonce, epoch=epoch, sequence=sequence, frameTime=r.clock,eventScope="selected-or-self/1",
        positiveEventScope="last-effective-damage-or-heal/1",positiveEventsScope="per-ability/1",
        deathScope="exact-unit-death/1",
        status="unavailable", reason="player-or-target-changed-or-unavailable",
        player={}, target={}, ability={}, cast={status="unavailable"}, catalog={status="unavailable",entries={}},
        controls={}, trial={}, readiness={status="blocked",reason="unavailable"}}
    -- Repeat both IDs around catalog/control collection. Player detail failure
    -- must not turn a cached catalog or previous target into current data.
    if p and r.reason ~= "player-unavailable" and r.reason ~= "identity-changed"
            and sameUnits(p,t) then
        local c = catalog(r.clock,p)
        local buttons = controls(p,t)
        if sameUnits(p,t) then
            frame.status, frame.reason, frame.playerId, frame.targetId = "observed", nil, p, t
            local nums = "level health healthMax power mana energy charge spirit planar combo coordX coordY coordZ"
            frame.player = project(r.player,nums,"id name calling relation","combat dead player")
            frame.target = project(r.target,nums,"id name calling relation","combat dead player")
            frame.ability = project(r.ability,"costPower costMana costEnergy costCharge costSpirit costPlanarCharge rangeMin rangeMax castingTime cooldown currentCooldownRemaining currentCooldownDuration currentCooldownBegin",
                "id idNew name target","channeled unusable outOfRange passive autoattack positioned currentCooldownPaused currentCooldownExpired")
            frame.ability.lookupId = text(r.abilityId,128)
            if type(r.ability) == "table" and finite(r.ability.channeled) then
                frame.ability.channeled = r.ability.channeled
            end
            frame.cast = project(r.cast,"begin duration remaining","ability abilityName","expired channeled")
            frame.cast.status = r.castStatus
            frame.readiness = {status=r.status, reason=r.reason, facingAndLineOfSight="unverified"}
            frame.catalog, frame.controls, frame.trial = catalogPage(c), buttons, trialState()
            if currentEvent(lastEvent,r.clock,t,EVENT_MAX_AGE) and lastEvent.caster == p and
                    (lastEvent.target == t or lastEvent.target == p) then frame.lastEvent=lastEvent end
            if currentEvent(lastPositiveEvent,r.clock,t,POSITIVE_MAX_AGE) and lastPositiveEvent.caster == p and
                    (lastPositiveEvent.target == t or lastPositiveEvent.target == p) then frame.lastPositiveEvent=lastPositiveEvent end
            frame.positiveEvents={}
            for id,e in pairs(positives) do
                if currentEvent(e,r.clock,t,POSITIVE_MAX_AGE) and e.caster == p and
                        (e.target == t or e.target == p) then frame.positiveEvents[id]=e end
            end
            if currentEvent(lastIncoming,r.clock,t,EVENT_MAX_AGE) and lastIncoming.caster == t and
                    lastIncoming.target == p then frame.lastIncoming=lastIncoming end
            if lastDeath and r.clock >= lastDeath.clock and r.clock-lastDeath.clock <= DEATH_MAX_AGE then
                frame.lastDeath=lastDeath
            end
            if c.status == "observed" then
                local names, complete = {}, true
                for _,id in ipairs(c.ids) do
                    local name = c.names[id]
                    if name == "" then complete = false end
                    names[name] = (names[name] or 0)+1
                end
                local function identify(button)
                    if button and button.mapped then
                        button.uniqueLearnedName = complete and names[button.abilityName] == 1 and
                            c.names[button.abilityId] == button.abilityName
                    end
                end
                identify(buttons.cast)
                for _, button in pairs(buttons.actions or {}) do identify(button) end
            end
        end
    end
    writeFrame(frame)
end

local function resetSetup()
    clear()
    local clean=true
    for i=1,8 do if not invoke(prepareSlot,i,"clear") then clean=false end end
    setupCleanupPending=not clean
    return clean
end
local function setup(arg)
    local requested,list=arg:match("^%s*setup%s+([0-9a-f]+)%s+(%S+)%s*$")
    local ids,seen={},{}
    local a=api.Ability and api.Ability.New
    local learned=a and invoke(a.List)
    local valid=requested and #requested==32 and type(learned)=="table"
    if valid then
        for id in (list..","):gmatch("([^,]*),") do
            if not text(id,128) or not id:match("^A[%da-fA-F]+$") or seen[id] or not learned[id] or #ids==8 then
                valid=false; break
            end
            ids[#ids+1]=id; seen[id]=true
        end
    end
    if not invoke(canSetup) then
        clear(); setupCleanupPending=true
        return false,"out-of-combat setup unavailable; unbound, repeat setup when available"
    end
    local clean=resetSetup()
    if not valid or #ids==0 or not clean then return false,"setup refused; unbound" end
    for i,id in ipairs(ids) do
        if not invoke(prepareSlot,i,id) then
            resetSetup()
            return false,"slot "..i.." setup failed; unbound"
        end
    end
    nonce=requested; epoch=epoch+1
    return true,"bound "..nonce.." epoch="..epoch.." slots="..#ids
end
function S.Command(arg)
    if type(arg) ~= "string" or #arg > 1120 then return false,"invalid command" end
    if arg:match("^%s*setup%f[%W]") or arg:match("^%s*setup%s*$") then return setup(arg) end
    if #arg > 180 then return false,"invalid command" end
    local slot, ability = string.match(arg, "^%s*slot%s+([1-8])%s+(%S+)%s*$")
    if slot and nonce and text(ability,128) then
        if invoke(prepareSlot,tonumber(slot),ability) then
            nextPublish,cache=nil,nil
            return true,"configured slot "..slot
        end
        return false,"slot configuration unavailable"
    end
    local verb, value = string.match(arg or "", "^%s*(%w+)%s*(%S*)%s*$")
    if verb == "bind" and #value == 32 and not string.find(value,"[^0-9a-f]") then
        if setupCleanupPending then return false,"repeat setup out of combat to clear previous slots" end
        if nonce ~= value then clear(); epoch=epoch+1; nonce=value end
        return true,"bound "..nonce.." epoch="..epoch
    elseif verb == "clear" and value == "" then clear(); return true,"cleared"
    elseif verb == "status" and value == "" then
        return true,"session="..(nonce or "unbound").." epoch="..epoch.." sequence="..sequence
    elseif verb == "page" and nonce and string.match(value,"^%d+$") and cache and cache.status == "observed" then
        local n = tonumber(value)
        if n >= 1 and n <= math.max(1,math.ceil(#cache.ids/PAGE_SIZE)) then
            page=n; nextPublish=nil; return true,"catalog page "..n
        end
    elseif verb == "select" and nonce and text(value,128) then
        local a = api.Ability and api.Ability.New
        local list = a and invoke(a.List)
        if type(list) == "table" and list[value] and selectAbility(value) then
            nextPublish=nil; return true,"selected "..value
        end
        return false,"ability selection unavailable"
    end
    return false,"use /rr2surv setup NONCE ID1[,ID2...], bind NONCE, status, page N, select ID, slot 1..8 ID|clear, or clear"
end
function S.Start(inspect, casting, select, rects, slots, setupAllowed)
    api, model, selectAbility, controls, prepareSlot, canSetup = inspect, casting, select, rects, slots, setupAllowed
    local list = Command.Slash.Register("rr2surv")
    table.insert(list, {function(a,b)
        local arg = type(b) == "string" and b or type(a) == "string" and a or ""
        local _, message = S.Command(arg)
        Command.Console.Display("general",false,"RR2 survival: "..message,false)
    end,"RiftReader2Casting","Survival telemetry and ability selection"})
end
