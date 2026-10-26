local _, private = ...
local model = private.Casting.New(Inspect)
private.Instance = model
local context = UI.CreateContext("RR2Casting")
local panel = UI.CreateFrame("Frame", "RR2CastingPanel", context)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 375, 85)
panel:SetWidth(455); panel:SetHeight(220); panel:SetBackgroundColor(0, 0, 0, 0.86)
local text = UI.CreateFrame("Text", "RR2CastingText", panel)
text:SetPoint("TOPLEFT", panel, "TOPLEFT", 8, 6); text:SetFontSize(13)
local function button(name, label, parent, x, y, width, handler)
    local b = UI.CreateFrame("RiftButton", name, parent)
    b:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y); b:SetWidth(width); b:SetHeight(27); b:SetText(label)
    b:EventAttach(Event.UI.Input.Mouse.Left.Click, handler, name .. " click")
    return b
end
local picker = UI.CreateFrame("Frame", "RR2CastingPicker", context)
picker:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 365, 75)
picker:SetWidth(710); picker:SetHeight(500); picker:SetBackgroundColor(0.05, 0.05, 0.05, 0.98); picker:SetLayer(10); picker:SetVisible(false)
local choices, page, rows = {}, 1, {}
local evidence = {schemaVersion = 1, source = "RIFT Lua API", addonVersion = "0.2.0", trials = {}}
-- Use RIFT's existing secure macro facility. This button has no Lua casting
-- callback or automatic retry: only an actual reviewed click invokes its macro.
local castContext = UI.CreateContext("RR2CastingSecure")
castContext:SetSecureMode("restricted")
local castButton = UI.CreateFrame("RiftButton", "RR2CastingSecureButton", castContext)
castButton:SetSecureMode("restricted")
castButton:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 375, 315)
castButton:SetWidth(455); castButton:SetHeight(32); castButton:SetText("Cast: choose an ability above")
local stopButton = UI.CreateFrame("RiftButton", "RR2CastingStopButton", castContext)
stopButton:SetSecureMode("restricted")
stopButton:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 375, 350)
stopButton:SetWidth(455); stopButton:SetHeight(32); stopButton:SetText("Stop autoattack")
stopButton:EventMacroSet(Event.UI.Input.Mouse.Left.Click, "stopattack")
local function selectAbility(id)
    if model.trial and model.trial.status == "recording" then return false end
    local secureOk, secure = pcall(Inspect.System.Secure)
    if not secureOk or secure ~= false then return false end
    local ok, d = pcall(Inspect.Ability.New.Detail, id)
    if not ok or type(d)~="table" or type(d.name)~="string" or #d.name==0 or #d.name>120 or
        string.find(d.name, "[\r\n]") or d.passive or d.positioned or d.autoattack then return false end
    local macro = "cast " .. d.name
    local previous = model.selected
    if not model:Select(id) then return false end
    local attached = pcall(castButton.EventMacroSet, castButton, Event.UI.Input.Mouse.Left.Click, macro)
    if not attached then model.selected = previous; return false end
    castButton:SetText("Cast: " .. d.name)
    evidence.castButton = {abilityId = id, abilityName = d.name, macro = macro}
    return true
end
private.SelectAbility = selectAbility
-- Ask the installed game for its own API documentation; saved only as research
-- evidence, never as live state or permission to invoke protected commands.
if type(Inspect.Documentation) == "function" then
    evidence.runtimeApi = {}
    for _, name in ipairs({"Inspect.Ability.New.Detail", "Inspect.Ability.Detail", "Inspect.Ability.New.List", "Inspect.Unit.Castbar",
        "Inspect.Unit.Detail", "Inspect.Tooltip", "Event.Combat.Damage", "Event.Combat.Heal", "Event.Ability.New.Cooldown.Begin",
        "Event.Ability.New.Cooldown.End", "Command.Event.Attach", "Layout:EventMacroSet", "Inspect.System.Secure"}) do
        local ok, doc = pcall(Inspect.Documentation, name)
        if ok and type(doc)=="string" then evidence.runtimeApi[name] = string.sub(doc, 1, 16000) end
    end
    local ok, index = pcall(Inspect.Documentation)
    if ok and type(index)=="table" then
        evidence.relevantApiNames = {}
        for name in pairs(index) do
            if type(name)=="string" and (string.find(string.lower(name), "cooldown", 1, true) or
                string.find(string.lower(name), "cast", 1, true) or string.find(name, "Ability", 1, true)) then
                evidence.relevantApiNames[#evidence.relevantApiNames+1] = name
            end
        end
        table.sort(evidence.relevantApiNames)
    end
end
local message = "Select an ability; select one training dummy."
local lastUpdate = -1
local function showChoices()
    evidence.abilities = model:Abilities()
    choices = {}
    for _, item in ipairs(evidence.abilities) do
        if not item.passive and not item.positioned and not item.autoattack then choices[#choices+1] = item end
    end
    for i = 1, 48 do
        local item = choices[(page - 1) * 48 + i]
        rows[i]:SetText(item and item.name or "-"); rows[i]:SetVisible(item ~= nil)
    end
    picker:SetVisible(true)
end
for i = 1, 48 do
    local index = i
    rows[i] = button("RR2CastingChoice" .. i, "-", picker, 5 + ((i-1)%3)*235, 30 + math.floor((i-1)/3)*28, 230, function()
        local item = choices[(page - 1)*48 + index]
        if item and selectAbility(item.lookupId) then message = "Watching " .. item.name; picker:SetVisible(false) end
    end)
end
button("RR2CastingPrev", "Previous", picker, 5, 0, 110, function() page = math.max(1, page-1); showChoices() end)
button("RR2CastingNext", "Next", picker, 120, 0, 110, function() if page*48 < #choices then page=page+1 end; showChoices() end)
button("RR2CastingClose", "Close", picker, 580, 0, 110, function() picker:SetVisible(false) end)
button("RR2CastingAbilities", "Abilities", panel, 6, 187, 110, function() page=1; showChoices() end)
button("RR2CastingRecord", "Record 60s", panel, 120, 187, 125, function()
    local ok, reason = model:Begin()
    if ok then
        evidence.trials[#evidence.trials+1] = model.trial
        if #evidence.trials > 8 then table.remove(evidence.trials,1) end
        message = "Recording only; click the named Cast button once."
    else message = "Not recording: " .. reason end
end)
button("RR2CastingHide", "Hide", panel, 340, 187, 100, function() panel:SetVisible(false) end)
local function f(v) return type(v)=="number" and string.format("%.2f",v) or "?" end
local function update()
    local now = Inspect.Time.Frame()
    if type(now) ~= "number" or now ~= now or math.abs(now) == math.huge then error("frame-clock-unavailable") end
    if now < lastUpdate then lastUpdate = -1 end
    if now-lastUpdate < .1 then return end
    lastUpdate = now
    local r = model:Read()
    evidence.last = r; evidence.trial = model.trial
    RiftReader2CastingEvidence = evidence
    local t = model.trial
    local pending = t and (t.hit and "intended hit confirmed" or t.healingConfirmed and "intended heal confirmed" or
        t.overhealObserved and "intended overheal observed" or "awaiting ability outcome")
    local result = t and (t.status .. ": " .. (t.reason or pending)) or message
    if t and t.status == "recording" then result = result .. " (" .. math.ceil(t.deadline-now) .. "s left)" end
    local detail = ""
    if t and t.lastHit then
        detail = "HIT " .. (t.lastHit.abilityName or "?") .. " -> " .. (t.lastHit.targetName or "?") .. " : " .. f(t.lastHit.damage)
    elseif t and t.lastHeal then
        detail = "HEAL " .. f(t.lastHeal.heal) .. " / OVERHEAL " .. f(t.lastHeal.overheal) .. " -> " .. (t.lastHeal.targetName or "?")
    end
    text:SetText("RR2 Casting | seq " .. r.sequence .. " | " .. f(r.clock) .. "\n" ..
        "Target: " .. (r.target.name or "none") .. "  " .. (r.targetId or "") .. "\n" ..
        "Ability: " .. (r.ability.name or "choose below") .. "\n" ..
        string.upper(r.status) .. " - " .. r.reason .. "\n" ..
        "Effective cooldown (ability/GCD): " .. f(r.ability.currentCooldownRemaining or 0) .. "s\n" ..
        "Cast: " .. (r.cast.abilityName or "none") .. " " .. (r.cast.remaining and f(r.cast.remaining).."s" or "") .. "\n" ..
        "Power: " .. f(r.player.power) .. "  Cost: " .. f(r.ability.costPower) .. "\n" ..
        "Facing / line of sight: unverified\n" .. result .. "\n" ..
        detail)
end
Command.Event.Attach(Event.System.Update.Begin, function()
    local ok, reason = pcall(update)
    if not ok then
        evidence.last = {status = "unavailable", reason = "readout-update-failed"}
        evidence.error = string.sub(tostring(reason), 1, 240)
        if model.trial and model.trial.status == "recording" then
            model.trial.status = "aborted"; model.trial.reason = "readout-update-failed"
        end
        text:SetText("RR2 Casting: unavailable\nReadout update failed; no readiness claim.")
        lastUpdate = -1
    end
end, "RR2 casting readout")
for _, spec in ipairs({{"Damage","damage"},{"Heal","heal"},{"Miss","miss"},{"Immune","immune"},{"Resist","resist"},{"Dodge","dodge"},{"Parry","parry"}}) do
    local kind = spec[2]
    if Event.Combat[spec[1]] then
        Command.Event.Attach(Event.Combat[spec[1]], function(_, info) model:Combat(kind, info) end, "RR2 casting " .. kind)
    end
end
if Event.Ability and Event.Ability.New and Event.Ability.New.Cooldown then
    for _, name in ipairs({"Begin", "End"}) do
        local kind = name
        Command.Event.Attach(Event.Ability.New.Cooldown[name], function(_, values) model:Cooldown(kind, values) end,
            "RR2 casting cooldown " .. name)
    end
end
Command.Event.Attach(Event.Addon.SavedVariables.Load.End, function(_, id)
    if id ~= "RiftReader2Casting" then return end
    local prior = RiftReader2CastingEvidence
    if type(prior)=="table" then
        evidence.previousTrials = {}
        for _, list in ipairs({prior.previousTrials or {}, prior.trials or {}}) do
            for _, trial in ipairs(list) do
                evidence.previousTrials[#evidence.previousTrials+1] = trial
                if #evidence.previousTrials > 8 then table.remove(evidence.previousTrials, 1) end
            end
        end
        if type(prior.last)=="table" and prior.last.abilityId then selectAbility(prior.last.abilityId) end
        -- Read-only API reconciliation of retained raw combat IDs. Historical
        -- trial verdicts remain untouched; this records what the current API says.
        evidence.abilityMappings = {}
        for _, trial in ipairs(evidence.previousTrials) do
            for _, event in ipairs(trial.events or {}) do
                if type(event.ability)=="string" and not evidence.abilityMappings[event.ability] then
                    local item = {}
                    for _, name in ipairs({"New", "Legacy"}) do
                        local fn = name == "New" and Inspect.Ability.New.Detail or Inspect.Ability.Detail
                        if type(fn)=="function" then
                            local ok, detail = pcall(fn, event.ability)
                            if ok and type(detail)=="table" then
                                item[name] = {id=detail.id, idNew=detail.idNew, name=detail.name}
                            else item[name] = {unavailable=true} end
                        end
                    end
                    evidence.abilityMappings[event.ability] = item
                end
            end
        end
    end
    evidence.loadedAt = Inspect.Time.Frame()
    evidence.abilities = model:Abilities()
    RiftReader2CastingEvidence = evidence
end, "RR2 casting saved evidence")
table.insert(Command.Slash.Register("rr2cast"), {function() panel:SetVisible(true) end, "RiftReader2Casting", "Show casting readout"})
