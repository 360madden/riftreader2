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
local evidence = {schemaVersion = 1, source = "RIFT Lua API", addonVersion = "0.1.0", trials = {}}
-- Ask the installed game for its own API documentation; saved only as research
-- evidence, never as live state or permission to invoke protected commands.
if type(Inspect.Documentation) == "function" then
    evidence.runtimeApi = {}
    for _, name in ipairs({"Inspect.Ability.New.Detail", "Inspect.Ability.New.List", "Inspect.Unit.Castbar",
        "Inspect.Unit.Detail", "Inspect.Tooltip", "Event.Combat.Damage", "Event.Ability.New.Cooldown.Begin",
        "Event.Ability.New.Cooldown.End", "Command.Event.Attach"}) do
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
    choices = model:Abilities()
    evidence.abilities = choices
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
        if item and model:Select(item.lookupId) then message = "Watching " .. item.name; picker:SetVisible(false) end
    end)
end
button("RR2CastingPrev", "Previous", picker, 5, 0, 110, function() page = math.max(1, page-1); showChoices() end)
button("RR2CastingNext", "Next", picker, 120, 0, 110, function() if page*48 < #choices then page=page+1 end; showChoices() end)
button("RR2CastingClose", "Close", picker, 580, 0, 110, function() picker:SetVisible(false) end)
button("RR2CastingAbilities", "Abilities", panel, 6, 187, 110, function() page=1; showChoices() end)
button("RR2CastingRecord", "Record 30s", panel, 120, 187, 125, function()
    local ok, reason = model:Begin()
    if ok then
        evidence.trials[#evidence.trials+1] = model.trial
        if #evidence.trials > 8 then table.remove(evidence.trials,1) end
        message = "Recording only; use the reviewed action-bar button."
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
    local result = t and (t.status .. ": " .. (t.reason or (t.hit and "intended hit confirmed" or "awaiting ability damage"))) or message
    text:SetText("RR2 Casting | seq " .. r.sequence .. " | " .. f(r.clock) .. "\n" ..
        "Target: " .. (r.target.name or "none") .. "  " .. (r.targetId or "") .. "\n" ..
        "Ability: " .. (r.ability.name or "choose below") .. "\n" ..
        string.upper(r.status) .. " - " .. r.reason .. "\n" ..
        "Effective cooldown (ability/GCD): " .. f(r.ability.currentCooldownRemaining or 0) .. "s\n" ..
        "Cast: " .. (r.cast.abilityName or "none") .. " " .. (r.cast.remaining and f(r.cast.remaining).."s" or "") .. "\n" ..
        "Power: " .. f(r.player.power) .. "  Cost: " .. f(r.ability.costPower) .. "\n" ..
        "Facing / line of sight: unverified\n" .. result .. "\n" ..
        (t and t.lastHit and ("HIT " .. (t.lastHit.abilityName or "?") .. " -> " .. (t.lastHit.targetName or "?") .. " : " .. f(t.lastHit.damage)) or ""))
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
for _, spec in ipairs({{"Damage","damage"},{"Miss","miss"},{"Immune","immune"},{"Resist","resist"},{"Dodge","dodge"},{"Parry","parry"}}) do
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
        if type(prior.last)=="table" and prior.last.abilityId then model:Select(prior.last.abilityId) end
    end
    evidence.loadedAt = Inspect.Time.Frame()
    evidence.abilities = model:Abilities()
    RiftReader2CastingEvidence = evidence
end, "RR2 casting saved evidence")
table.insert(Command.Slash.Register("rr2cast"), {function() panel:SetVisible(true) end, "RiftReader2Casting", "Show casting readout"})
