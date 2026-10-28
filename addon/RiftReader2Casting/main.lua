local _, private = ...
local model = private.Casting.New(Inspect)
private.Instance = model
local context = UI.CreateContext("RR2Casting")
local PX, PY, PW, PH = 300, 95, 540, 445
local colors = {
    background = {0.035, 0.055, 0.075, 0.97},
    header = {0.065, 0.11, 0.15, 0.98},
    section = {0.085, 0.12, 0.16, 0.96},
    button = {0.12, 0.19, 0.24, 0.98},
    accent = {0.24, 0.78, 0.86, 1},
    text = {0.93, 0.96, 0.98, 1},
    muted = {0.62, 0.74, 0.80, 1},
    green = {0.33, 0.89, 0.56, 1},
    amber = {1.00, 0.75, 0.34, 1},
    red = {1.00, 0.44, 0.45, 1}
}
local function background(frame, rgba)
    frame:SetBackgroundColor(rgba[1], rgba[2], rgba[3], rgba[4])
end
local function block(name, parent, x, y, width, height, rgba)
    local frame = UI.CreateFrame("Frame", name, parent)
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    frame:SetWidth(width); frame:SetHeight(height)
    background(frame, rgba)
    return frame
end
local function label(name, parent, x, y, width, size, value, rgba)
    local frame = UI.CreateFrame("Text", name, parent)
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    frame:SetWidth(width); frame:SetHeight(size + 8)
    frame:SetFontSize(size); frame:SetWordwrap(false)
    local c = rgba or colors.text
    frame:SetFontColor(c[1], c[2], c[3], c[4])
    frame:SetText(value or "")
    return frame
end
-- The normal controls are deliberately flat; the two protected macro controls
-- below must remain real, separately restricted RiftButtons.
local function button(name, value, parent, x, y, width, height, handler)
    local frame = block(name, parent, x, y, width, height, colors.button)
    block(name .. "Accent", frame, 0, 0, 3, height, colors.accent)
    local caption = UI.CreateFrame("Text", name .. "Label", frame)
    caption:SetPoint("CENTER", frame, "CENTER", 0, 0)
    caption:SetWidth(width - 12); caption:SetHeight(height)
    caption:SetFontSize(16); caption:SetWordwrap(false)
    caption:SetFontColor(0.94, 0.97, 0.99, 1)
    caption:SetText(value)
    frame:EventAttach(Event.UI.Input.Mouse.Left.Click, handler, name .. " click")
    return {
        SetText = function(_, v) caption:SetText(v) end,
        SetVisible = function(_, v) frame:SetVisible(v) end
    }
end
local function shortName(value, maxLength)
    if type(value) ~= "string" or value == "" then return "unknown" end
    if #value > maxLength then
        -- RIFT Lua 5.1 strings are bytes; never split a UTF-8 codepoint in a label.
        local last = maxLength - 3
        while last > 0 do
            local nextByte = string.byte(value, last + 1)
            if not nextByte or nextByte < 128 or nextByte >= 192 then break end
            last = last - 1
        end
        return string.sub(value, 1, last) .. "..."
    end
    return value
end

local panel = UI.CreateFrame("Frame", "RR2CastingPanel", context)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PX, PY)
panel:SetWidth(PW); panel:SetHeight(PH); background(panel, colors.background)
block("RR2CastingLeftAccent", panel, 0, 0, 4, PH, colors.accent)
block("RR2CastingHeader", panel, 4, 0, PW - 4, 60, colors.header)
label("RR2CastingTitle", panel, 16, 8, 315, 22, "RR2  /  CASTING", colors.text)
label("RR2CastingSubtitle", panel, 17, 39, 470, 13, "MANUAL CAST  /  FACING & LOS UNVERIFIED", colors.muted)
local sequenceText = label("RR2CastingSequence", panel, 355, 17, 170, 12, "SEQ --", colors.muted)
block("RR2CastingStatusBackground", panel, 14, 66, 512, 53, colors.section)
local statusAccent = block("RR2CastingStatusAccent", panel, 14, 66, 5, 53, colors.amber)
local statusText = label("RR2CastingStatus", panel, 27, 75, 155, 20, "BLOCKED", colors.amber)
local statusReason = label("RR2CastingReason", panel, 190, 83, 323, 14, "Choose ability and target", colors.text)
label("RR2CastingTargetLabel", panel, 17, 133, 86, 13, "TARGET", colors.muted)
local targetText = label("RR2CastingTarget", panel, 111, 129, 408, 18, "No target selected", colors.text)
label("RR2CastingAbilityLabel", panel, 17, 172, 86, 13, "ABILITY", colors.muted)
local abilityText = label("RR2CastingAbility", panel, 111, 168, 408, 18, "Choose an ability", colors.text)
block("RR2CastingDivider", panel, 14, 207, 512, 1, colors.header)
local function metric(name, x, y, caption)
    block(name .. "Card", panel, x, y, 248, 56, colors.section)
    label(name .. "Caption", panel, x + 10, y + 5, 228, 14, caption, colors.muted)
    return label(name .. "Value", panel, x + 10, y + 28, 228, 18, "unknown", colors.text)
end
local rangeText = metric("RR2CastingRange", 14, 216, "RANGE  /  MIN - MAX")
local castText = metric("RR2CastingCastTime", 278, 216, "CAST TIME  /  CHANNEL")
local cooldownText = metric("RR2CastingCooldown", 14, 281, "COOLDOWN  /  ABILITY + GCD")
local powerText = metric("RR2CastingPower", 278, 281, "POWER  /  COST")
block("RR2CastingTrialBackground", panel, 14, 347, 512, 52, colors.section)
local trialState = label("RR2CastingTrialState", panel, 24, 349, 480, 17, "NOT RECORDING", colors.accent)
local trialDetail = label("RR2CastingTrialDetail", panel, 24, 377, 480, 13, "Choose an ability and target, then record.", colors.muted)

local picker = UI.CreateFrame("Frame", "RR2CastingPicker", context)
picker:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PX - 10, PY - 10)
picker:SetWidth(590); picker:SetHeight(448); background(picker, colors.background)
picker:SetLayer(10); picker:SetVisible(false)
-- Absorb blank-background clicks so they cannot reach the HUD footer below.
picker:EventAttach(Event.UI.Input.Mouse.Left.Click, function() end, "RR2 casting picker backdrop")
block("RR2CastingPickerAccent", picker, 0, 0, 590, 4, colors.accent)
label("RR2CastingPickerTitle", picker, 16, 12, 470, 20, "CHOOSE AN ABILITY", colors.text)
label("RR2CastingPickerSubtitle", picker, 16, 43, 550, 13,
    "API catalog  /  supported click-to-cast types", colors.muted)
local pageText = label("RR2CastingPage", picker, 260, 417, 190, 13, "PAGE 1 / 1", colors.muted)
local choices, page, rows = {}, 1, {}
local evidence = {schemaVersion = 1, source = "RIFT Lua API", addonVersion = "0.2.2", trials = {}}
local savedLoaded = false -- Preserve the persisted table until the load-end event has consumed it.
-- Only a reviewed physical click may fire these secure macro buttons. Position
-- them as a single action row just beneath the HUD, never as floating full-width bars.
local castContext = UI.CreateContext("RR2CastingSecure")
castContext:SetSecureMode("restricted")
local castButton = UI.CreateFrame("RiftButton", "RR2CastingSecureButton", castContext)
castButton:SetSecureMode("restricted")
castButton:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PX + 14, PY + PH + 6)
castButton:SetWidth(350); castButton:SetHeight(36); castButton:SetText("Select ability")
local stopButton = UI.CreateFrame("RiftButton", "RR2CastingStopButton", castContext)
stopButton:SetSecureMode("restricted")
stopButton:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PX + 378, PY + PH + 6)
stopButton:SetWidth(148); stopButton:SetHeight(36); stopButton:SetText("Stop attack")
stopButton:EventMacroSet(Event.UI.Input.Mouse.Left.Click, "stopattack")
local function setPanelVisible(visible)
    local ok, secure = pcall(Inspect.System.Secure)
    if not ok or secure ~= false then return false end
    -- Do not hide the readout alone and leave orphaned secure action buttons.
    if not pcall(castButton.SetVisible, castButton, visible) then return false end
    if not pcall(stopButton.SetVisible, stopButton, visible) then
        pcall(castButton.SetVisible, castButton, not visible)
        return false
    end
    panel:SetVisible(visible)
    if not visible then picker:SetVisible(false) end
    return true
end
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
    castButton:SetText("Cast: " .. shortName(d.name, 17))
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
local message = "Choose an ability and select a target."
local lastUpdate = -1
local perPage = 20
local function showChoices()
    evidence.abilities = model:Abilities()
    choices = {}
    for _, item in ipairs(evidence.abilities) do
        if type(item.name) == "string" and #item.name > 0 and #item.name <= 120 and
            not string.find(item.name, "[\r\n]") and not item.passive and
            not item.positioned and not item.autoattack then
            choices[#choices + 1] = item
        end
    end
    local pages = math.max(1, math.ceil(#choices / perPage))
    page = math.min(page, pages)
    pageText:SetText("PAGE " .. page .. " / " .. pages)
    for i = 1, perPage do
        local item = choices[(page - 1) * perPage + i]
        rows[i]:SetText(item and shortName(item.name or item.lookupId, 26) or "-")
        rows[i]:SetVisible(item ~= nil)
    end
    picker:SetVisible(true)
end
for i = 1, perPage do
    local index = i
    rows[i] = button("RR2CastingChoice" .. i, "-", picker,
        12 + ((i - 1) % 2) * 287, 70 + math.floor((i - 1) / 2) * 33, 279, 29, function()
        local item = choices[(page - 1) * perPage + index]
        if item and selectAbility(item.lookupId) then
            message = "Selected " .. shortName(item.name, 42)
            picker:SetVisible(false)
        end
    end)
end
button("RR2CastingPrev", "PREVIOUS", picker, 12, 408, 110, 30, function()
    page = math.max(1, page - 1); showChoices()
end)
button("RR2CastingNext", "NEXT", picker, 132, 408, 110, 30, function()
    if page * perPage < #choices then page = page + 1 end
    showChoices()
end)
button("RR2CastingClose", "CLOSE", picker, 464, 408, 114, 30, function() picker:SetVisible(false) end)
button("RR2CastingAbilities", "ABILITIES", panel, 14, 408, 160, 30, function()
    page = 1; showChoices()
end)
button("RR2CastingRecord", "RECORD 60s", panel, 188, 408, 160, 30, function()
    local ok, reason = model:Begin()
    if ok then
        evidence.trials[#evidence.trials + 1] = model.trial
        if #evidence.trials > 8 then table.remove(evidence.trials, 1) end
        message = "Recording only. Review readiness before clicking Cast."
    else
        message = "Not recording: " .. (reason or "unavailable")
    end
end)
button("RR2CastingHide", "HIDE", panel, 366, 408, 160, 30, function() setPanelVisible(false) end)

local function finite(v) return type(v) == "number" and v == v and math.abs(v) < math.huge end
local function f(v) return finite(v) and string.format("%.2f", v) or "unknown" end
local function castTime(v)
    if not finite(v) then return "unknown" end
    return v == 0 and "instant (0s)" or string.format("%.2fs", v)
end
local function channel(v)
    if type(v) ~= "boolean" then return "unknown" end
    return v and "yes" or "no"
end
local reasonLabels = {
    ["observed-ready"] = "Observed checks pass; facing/LOS unknown",
    ["no-target"] = "Select a target in RIFT",
    ["select-ability"] = "Choose an ability",
    ["player-unavailable"] = "Player data unavailable",
    ["target-not-alive"] = "Selected target is not alive",
    ["player-not-alive"] = "Player is not alive",
    ["identity-changed"] = "Player/target identity changed",
    ["unsupported-ability-type"] = "Unsupported ability type",
    ["ability-target-mismatch"] = "Ability target does not match selection",
    ["out-of-range"] = "Target is out of API range",
    ["cooldown-ability-or-gcd"] = "Waiting for ability/GCD cooldown",
    ["cast-or-channel-active"] = "A cast/channel is active",
    ["insufficient-or-unknown-power"] = "Insufficient/unknown Power",
    ["cast-state-unavailable"] = "Cast state unavailable",
    ["ability-unusable"] = "Ability is unavailable"
}
local function humanReason(reason)
    return reasonLabels[reason] or string.gsub(reason or "unavailable", "-", " ")
end
local function trialOutcome(t)
    if t.lastHit then
        return "HIT  " .. f(t.lastHit.damage) .. " damage on " .. shortName(t.lastHit.targetName, 24)
    end
    if t.lastHeal then
        return "HEAL  " .. f(t.lastHeal.heal) .. " / OVERHEAL  " .. f(t.lastHeal.overheal)
    end
    -- A matched dodge/miss is meaningful evidence even though it cannot become a
    -- positive damage/heal verdict. Preserve the recorder's strict verdict.
    for i = #(t.events or {}), 1, -1 do
        local event = t.events[i]
        if event.matchesAbility and event.matchesTarget and
            (event.kind == "dodge" or event.kind == "miss" or event.kind == "parry" or
             event.kind == "resist" or event.kind == "immune") then
            return string.upper(event.kind) .. " on selected target (no confirmed hit)"
        end
    end
    return "No exact-target damage or healing confirmed"
end
local function update()
    local now = Inspect.Time.Frame()
    if not finite(now) then error("frame-clock-unavailable") end
    if now < lastUpdate then lastUpdate = -1 end
    if now - lastUpdate < .1 then return end
    lastUpdate = now
    local r = model:Read()
    evidence.last = r; evidence.trial = model.trial
    if savedLoaded then RiftReader2CastingEvidence = evidence end

    sequenceText:SetText("SEQ " .. r.sequence .. "  /  " .. f(r.clock))
    statusText:SetText(string.upper(r.status))
    local tint = r.status == "ready" and colors.green or
        (r.status == "waiting" and colors.amber or colors.red)
    statusText:SetFontColor(tint[1], tint[2], tint[3], tint[4])
    background(statusAccent, tint)
    statusReason:SetText(shortName(humanReason(r.reason), 43))
    targetText:SetText(shortName(r.target.name, 38) ~= "unknown" and shortName(r.target.name, 38) or "No target selected")
    abilityText:SetText(shortName(r.ability.name, 38) ~= "unknown" and shortName(r.ability.name, 38) or "Choose an ability")
    rangeText:SetText(f(r.ability.rangeMin) .. "  /  " .. f(r.ability.rangeMax))
    castText:SetText(castTime(r.ability.castingTime) .. "  /  " .. channel(r.ability.channeled))
    cooldownText:SetText(f(r.ability.currentCooldownRemaining) ..
        (finite(r.ability.currentCooldownRemaining) and "s" or ""))
    powerText:SetText(f(r.player.power) .. "  /  " .. f(r.ability.costPower))

    local t = model.trial
    if not t then
        trialState:SetText("NOT RECORDING")
        trialDetail:SetText(shortName(message, 67))
    else
        if t.status == "recording" then
            trialState:SetText("RECORDING  /  " .. math.max(0, math.ceil(t.deadline - now)) .. "s left")
        else
            trialState:SetText(string.upper(t.status) .. "  /  " .. shortName(humanReason(t.reason), 38))
        end
        trialDetail:SetText(shortName(trialOutcome(t), 67))
    end
end
Command.Event.Attach(Event.System.Update.Begin, function()
    local ok, reason = pcall(update)
    if not ok then
        evidence.last = {status = "unavailable", reason = "readout-update-failed"}
        evidence.error = string.sub(tostring(reason), 1, 240)
        if model.trial and model.trial.status == "recording" then
            model.trial.status = "aborted"; model.trial.reason = "readout-update-failed"
        end
        statusText:SetText("UNAVAILABLE")
        statusText:SetFontColor(colors.red[1], colors.red[2], colors.red[3], colors.red[4])
        background(statusAccent, colors.red)
        statusReason:SetText("Readout update failed")
        trialState:SetText("ABORTED / READOUT ERROR")
        trialDetail:SetText("No readiness claim; see saved evidence error.")
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
    if id ~= "RiftReader2Casting" or savedLoaded then return end
    local prior = RiftReader2CastingEvidence
    if type(prior)=="table" then
        evidence.previousTrials = {}
        for _, list in ipairs({
            type(prior.previousTrials) == "table" and prior.previousTrials or {},
            type(prior.trials) == "table" and prior.trials or {}
        }) do
            for _, trial in ipairs(list) do
                if type(trial) == "table" then
                    evidence.previousTrials[#evidence.previousTrials+1] = trial
                    if #evidence.previousTrials > 8 then table.remove(evidence.previousTrials, 1) end
                end
            end
        end
        if type(prior.last)=="table" and prior.last.abilityId then selectAbility(prior.last.abilityId) end
        -- Read-only API reconciliation of retained raw combat IDs. Historical
        -- trial verdicts remain untouched; this records what the current API says.
        evidence.abilityMappings = {}
        for _, trial in ipairs(evidence.previousTrials) do
            for _, event in ipairs(type(trial.events) == "table" and trial.events or {}) do
                if type(event) == "table" and type(event.ability)=="string" and not evidence.abilityMappings[event.ability] then
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
    savedLoaded = true
    RiftReader2CastingEvidence = evidence
end, "RR2 casting saved evidence")
table.insert(Command.Slash.Register("rr2cast"), {function() setPanelVisible(true) end, "RiftReader2Casting", "Show casting readout"})
