local addonInfo, private = ...
local FALLBACK_VERSION = "0.3.0"
local function versionFromMetadata(info)
    local toc = type(info) == "table" and info.toc
    local value = type(toc) == "table" and toc.Version
    if type(value) == "string" and #value > 0 and #value <= 24 and
        not string.find(value, "[^%w%.%-]") then return value end
    return FALLBACK_VERSION
end
local addonVersion = versionFromMetadata(addonInfo)
local model = private.Casting.New(Inspect)
private.Instance = model
local context = UI.CreateContext("RR2Casting")
local PX, PY, PW, PH = 286, 72, 584, 602
local colors = {
    background = {0.039, 0.067, 0.090, 0.98},
    header = {0.078, 0.125, 0.165, 0.98},
    section = {0.102, 0.165, 0.212, 0.98},
    raised = {0.135, 0.196, 0.247, 0.98},
    border = {0.176, 0.259, 0.314, 1},
    primaryButton = {0.086, 0.286, 0.341, 1},
    dangerButton = {0.286, 0.137, 0.188, 1},
    accent = {0.224, 0.737, 0.804, 1},
    text = {0.933, 0.965, 0.976, 1},
    muted = {0.655, 0.737, 0.780, 1},
    green = {0.314, 0.820, 0.545, 1},
    amber = {0.941, 0.745, 0.384, 1},
    red = {0.925, 0.416, 0.463, 1}
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
local function surface(name, parent, x, y, width, height, fill)
    local frame = block(name, parent, x, y, width, height, colors.border)
    local inset = block(name .. "Fill", frame, 1, 1, width - 2, height - 2, fill)
    inset:SetMouseMasking("limited")
    return frame
end
local function label(name, parent, x, y, width, size, value, rgba)
    local frame = UI.CreateFrame("Text", name, parent)
    frame:SetLayer(2) -- Explicit foreground above same-layer surface fills.
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    frame:SetWidth(width); frame:SetHeight(size + 8)
    frame:SetFontSize(size); frame:SetWordwrap(false)
    frame:SetMouseMasking("limited")
    local c = rgba or colors.text
    frame:SetFontColor(c[1], c[2], c[3], c[4])
    frame:SetText(value or "")
    return frame
end
local function centeredLabel(name, parent, width, height, value, rgba)
    local caption = UI.CreateFrame("Text", name, parent)
    caption:SetLayer(2)
    caption:SetPoint("CENTER", parent, "CENTER", 0, 0)
    caption:SetWidth(width - 16); caption:SetHeight(height)
    caption:SetFontSize(16); caption:SetWordwrap(false)
    caption:SetMouseMasking("limited") -- Decor only; clicks stay on the button frame.
    local c = rgba or colors.text
    caption:SetFontColor(c[1], c[2], c[3], c[4])
    caption:SetText(value)
    return caption
end
local function button(name, value, parent, x, y, width, height, handler, role)
    local fill = role == "primary" and colors.primaryButton or
        (role == "danger" and colors.dangerButton or colors.section)
    local tint = role == "danger" and colors.red or
        (role == "ghost" and colors.muted or colors.accent)
    local frame = surface(name, parent, x, y, width, height, fill)
    local accent = block(name .. "Accent", frame, 1, 1, 4, height - 2, tint)
    accent:SetLayer(1); accent:SetMouseMasking("limited")
    local caption = centeredLabel(name .. "Label", frame, width, height, value)
    frame:EventAttach(Event.UI.Input.Mouse.Left.Click, handler, name .. " click")
    return {
        SetText = function(_, v) caption:SetText(v) end,
        SetVisible = function(_, v) frame:SetVisible(v) end
    }
end
local function shortName(value, maxLength)
    if type(value) ~= "string" or value == "" then return "unknown" end
    if #value > maxLength then
        -- RIFT Lua 5.1 strings are bytes; do not split a UTF-8 codepoint.
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
block("RR2CastingHeader", panel, 4, 0, PW - 4, 66, colors.header)
label("RR2CastingTitle", panel, 24, 9, 408, 22, "RR2 CASTING  v" .. addonVersion, colors.text)
label("RR2CastingSubtitle", panel, 24, 43, 420, 13, "Observation console  /  Manual actions only", colors.muted)

surface("RR2CastingStatusBackground", panel, 16, 76, 552, 82, colors.header)
local statusAccent = block("RR2CastingStatusAccent", panel, 16, 76, 4, 82, colors.amber)
local statusText = label("RR2CastingStatus", panel, 28, 85, 178, 20, "BLOCKED", colors.amber)
local statusReason = label("RR2CastingReason", panel, 208, 91, 344, 14, "Choose an ability and target", colors.text)
surface("RR2CastingFacingChip", panel, 28, 122, 246, 28, colors.section)
surface("RR2CastingLosChip", panel, 284, 122, 272, 28, colors.section)
label("RR2CastingFacing", panel, 38, 125, 226, 13, "FACING   UNVERIFIED", colors.amber)
label("RR2CastingLineOfSight", panel, 294, 125, 254, 13, "LINE OF SIGHT   UNVERIFIED", colors.amber)

surface("RR2CastingSelectionCard", panel, 16, 168, 552, 82, colors.header)
label("RR2CastingTargetLabel", panel, 28, 175, 244, 13, "Target", colors.muted)
local targetText = label("RR2CastingTarget", panel, 28, 195, 244, 18, "No target selected", colors.text)
label("RR2CastingAbilityLabel", panel, 300, 175, 248, 13, "Ability", colors.muted)
local abilityText = label("RR2CastingAbility", panel, 300, 195, 248, 18, "Choose an ability", colors.text)

local function metric(name, x, y, caption)
    surface(name .. "Card", panel, x, y, 270, 64, colors.header)
    label(name .. "Caption", panel, x + 12, y + 6, 246, 13, caption, colors.muted)
    return label(name .. "Value", panel, x + 12, y + 29, 246, 18, "Unknown", colors.text)
end
local rangeText = metric("RR2CastingRange", 16, 260, "Range  /  Min - Max")
local castText = metric("RR2CastingCastTime", 298, 260, "Cast time  /  Channel")
local cooldownText = metric("RR2CastingCooldown", 16, 332, "Cooldown  /  Ability + GCD")
local powerText = metric("RR2CastingPower", 298, 332, "Power  /  Cost")

surface("RR2CastingTrialBackground", panel, 16, 404, 552, 58, colors.header)
local trialState = label("RR2CastingTrialState", panel, 28, 410, 526, 17, "NOT RECORDING", colors.accent)
local trialDetail = label("RR2CastingTrialDetail", panel, 28, 434, 526, 13,
    "Choose an ability and a target, then record.", colors.muted)

surface("RR2CastingManualTray", panel, 4, 521, PW - 4, 81, colors.header)
label("RR2CastingManualLabel", panel, 24, 529, 376, 13, "MANUAL ACTIONS  /  RIFT-PROTECTED", colors.muted)
local sequenceText = label("RR2CastingSequence", panel, 414, 530, 150, 11, "SEQ --", colors.muted)

local picker = UI.CreateFrame("Frame", "RR2CastingPicker", context)
picker:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PX, PY)
picker:SetWidth(PW); picker:SetHeight(519)
background(picker, colors.background)
picker:SetLayer(10); picker:SetVisible(false)
-- Empty-background clicks are absorbed; picker never overlays secure controls.
picker:EventAttach(Event.UI.Input.Mouse.Left.Click, function() end, "RR2 casting picker backdrop")
block("RR2CastingPickerAccent", picker, 0, 0, PW, 4, colors.accent)
label("RR2CastingPickerTitle", picker, 24, 17, 440, 22, "Choose an ability", colors.text)
label("RR2CastingPickerSubtitle", picker, 24, 49, 530, 13,
    "Supported manual-cast abilities from the current RIFT API catalog", colors.muted)
local pageText = label("RR2CastingPage", picker, 273, 474, 162, 13, "PAGE 1 / 1", colors.muted)
local emptyText = label("RR2CastingPickerEmpty", picker, 32, 223, 516, 16,
    "No supported abilities reported by RIFT.", colors.muted)
emptyText:SetVisible(false)
local choices, page, rows = {}, 1, {}
local evidence = {schemaVersion = 1, source = "RIFT Lua API", addonVersion = addonVersion, trials = {}}
local savedLoaded = false -- Preserve saved evidence until its exact load-end event.

-- The actual macro targets are styled restricted Frames, not decorative click
-- proxies. Text and accents have no mouse handlers; only EventMacroSet casts.
local castContext = UI.CreateContext("RR2CastingSecure")
castContext:SetSecureMode("restricted")
local function secureButton(name, value, left, top, width, role)
    local frame = UI.CreateFrame("Frame", name, castContext)
    frame:SetSecureMode("restricted")
    frame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", left, top)
    frame:SetWidth(width); frame:SetHeight(40)
    frame:SetMouseMasking("full")
    background(frame, colors.border)
    local fill = block(name .. "Fill", frame, 1, 1, width - 2, 38,
        role == "danger" and colors.dangerButton or colors.primaryButton)
    fill:SetMouseMasking("limited")
    local accent = block(name .. "Accent", frame, 1, 1, 4, 38,
        role == "danger" and colors.red or colors.accent)
    accent:SetLayer(1); accent:SetMouseMasking("limited")
    return frame, centeredLabel(name .. "Label", frame, width, 40, value)
end
local castButton, castCaption = secureButton("RR2CastingSecureButton",
    "SELECT AN ABILITY", PX + 16, PY + 552, 350, "primary")
local stopButton, stopCaption = secureButton("RR2CastingStopButton",
    "Stop attack", PX + 374, PY + 552, 194, "danger")
local stopOk, stopResult = pcall(stopButton.EventMacroSet,
    stopButton, Event.UI.Input.Mouse.Left.Click, "stopattack")
if not stopOk or stopResult == false then
    stopCaption:SetText("STOP UNAVAILABLE")
    evidence.secureActionWarnings = {"stop-macro-unavailable"}
end

local function setPanelVisible(visible)
    local ok, secure = pcall(Inspect.System.Secure)
    if not ok or secure ~= false then return false end
    -- Never leave an orphaned protected action row when hiding the dashboard.
    local castOk, castResult = pcall(castButton.SetVisible, castButton, visible)
    if not castOk or castResult == false then return false end
    local stopShowOk, stopShowResult = pcall(stopButton.SetVisible, stopButton, visible)
    if not stopShowOk or stopShowResult == false then
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
    local abilityApi = type(Inspect) == "table" and type(Inspect.Ability) == "table" and Inspect.Ability or nil
    local newApi = abilityApi and type(abilityApi.New) == "table" and abilityApi.New or nil
    local detail = newApi and newApi.Detail
    if type(detail) ~= "function" then return false end
    local ok, d = pcall(detail, id)
    if not ok or type(d)~="table" or type(d.name)~="string" or #d.name==0 or #d.name>120 or
        string.find(d.name, "[\r\n]") or d.passive or d.positioned or d.autoattack then return false end
    local macro = "cast " .. d.name
    local previous = model.selected
    if not model:Select(id) then return false end
    local attached, accepted = pcall(castButton.EventMacroSet,
        castButton, Event.UI.Input.Mouse.Left.Click, macro)
    if not attached or accepted == false then model.selected = previous; return false end
    castCaption:SetText("CAST  " .. shortName(d.name, 25))
    evidence.castButton = {abilityId = id, abilityName = d.name, macro = macro}
    return true
end
private.SelectAbility = selectAbility

-- Retain the installed game's API descriptions as offline evidence.
if type(Inspect.Documentation) == "function" then
    evidence.runtimeApi = {}
    for _, name in ipairs({"Inspect.Ability.New.Detail", "Inspect.Ability.Detail", "Inspect.Ability.New.List", "Inspect.Unit.Castbar",
        "Inspect.Unit.Detail", "Inspect.Tooltip", "Event.Combat.Damage", "Event.Combat.Heal", "Event.Ability.New.Cooldown.Begin",
        "Event.Ability.New.Cooldown.End", "Command.Event.Attach", "Layout:EventMacroSet", "Inspect.System.Secure",
        "Frame:EventMacroSet", "Frame:SetMouseMasking"}) do
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
    emptyText:SetVisible(#choices == 0)
    for i = 1, perPage do
        local item = choices[(page - 1) * perPage + i]
        rows[i]:SetText(item and shortName(item.name or item.lookupId, 27) or "-")
        rows[i]:SetVisible(item ~= nil)
    end
    picker:SetVisible(true)
end
for i = 1, perPage do
    local index = i
    rows[i] = button("RR2CastingChoice" .. i, "-", picker,
        16 + ((i - 1) % 2) * 282, 84 + math.floor((i - 1) / 2) * 36, 270, 34, function()
        local item = choices[(page - 1) * perPage + index]
        if item and selectAbility(item.lookupId) then
            message = "Selected " .. shortName(item.name, 42)
            picker:SetVisible(false)
        end
    end)
end
button("RR2CastingPrev", "Previous", picker, 16, 461, 112, 40, function()
    page = math.max(1, page - 1); showChoices()
end)
button("RR2CastingNext", "Next", picker, 136, 461, 112, 40, function()
    if page * perPage < #choices then page = page + 1 end
    showChoices()
end)
button("RR2CastingClose", "Close", picker, 450, 461, 118, 40,
    function() picker:SetVisible(false) end)
button("RR2CastingAbilities", "Choose ability", panel, 16, 473, 270, 40, function()
    page = 1; showChoices()
end)
button("RR2CastingRecord", "Record 60s", panel, 298, 473, 270, 40, function()
    local ok, reason = model:Begin()
    if ok then
        evidence.trials[#evidence.trials + 1] = model.trial
        if #evidence.trials > 8 then table.remove(evidence.trials, 1) end
        message = "Recording only. Review readiness before clicking Cast."
    else
        message = "Not recording: " .. (reason or "unavailable")
    end
end, "primary")
button("RR2CastingHide", "Hide", panel, 484, 16, 84, 38,
    function() setPanelVisible(false) end, "ghost")

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
    ["observed-ready"] = "Target, power and cooldown checks passed",
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
    ["invalid-ability-cost"] = "Ability cost data invalid",
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
    statusText:SetText(r.status == "ready" and "API READY" or string.upper(r.status))
    local tint = r.status == "ready" and colors.green or
        (r.status == "waiting" and colors.amber or colors.red)
    statusText:SetFontColor(tint[1], tint[2], tint[3], tint[4])
    background(statusAccent, tint)
    statusReason:SetText(shortName(humanReason(r.reason), 43))
    targetText:SetText(shortName(r.target.name, 25) ~= "unknown" and shortName(r.target.name, 25) or "No target selected")
    abilityText:SetText(shortName(r.ability.name, 25) ~= "unknown" and shortName(r.ability.name, 25) or "Choose an ability")
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
local initializedNoticeSent = false
local function announceInitialized()
    if initializedNoticeSent then return end
    initializedNoticeSent = true
    local plain = "RiftReader2 Casting Readout v" .. addonVersion .. " initialized."
    local colored = '<font color="#52E3BB">' .. plain .. '</font>'
    local console = type(Command) == "table" and Command.Console
    if type(console) == "table" and type(console.Display) == "function" then
        local ok, accepted = pcall(console.Display, "general", true, colored, true)
        if ok and accepted ~= false then return end
    end
    -- If the console API fails, retain a colored, best-effort chat fallback.
    if type(print) == "function" then pcall(print, "|cff52E3BB" .. plain .. "|r") end
end
local addonLoadEnd = Event.Addon and Event.Addon.Load and Event.Addon.Load.End
if addonLoadEnd then
    pcall(Command.Event.Attach, addonLoadEnd, function(_, info)
        local loadedId = type(info) == "table" and info.identifier or info
        if loadedId == "RiftReader2Casting" then announceInitialized() end
    end, "RR2 casting initialized")
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
        local abilityApi = type(Inspect) == "table" and type(Inspect.Ability) == "table"
            and Inspect.Ability or {}
        local newApi = type(abilityApi.New) == "table" and abilityApi.New or {}
        for _, trial in ipairs(evidence.previousTrials) do
            for _, event in ipairs(type(trial.events) == "table" and trial.events or {}) do
                if type(event) == "table" and type(event.ability)=="string" and not evidence.abilityMappings[event.ability] then
                    local item = {}
                    for _, name in ipairs({"New", "Legacy"}) do
                        local fn
                        if name == "New" then
                            fn = newApi.Detail
                        else
                            fn = abilityApi.Detail
                        end
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
    local loadWarnings = {}
    local clockOk, loadedAt = pcall(function()
        return Inspect.Time.Frame()
    end)
    if clockOk and finite(loadedAt) then
        evidence.loadedAt = loadedAt
    else
        loadWarnings[#loadWarnings + 1] = "frame-clock-unavailable"
    end
    local listOk, list = pcall(model.Abilities, model)
    if listOk and type(list) == "table" then
        evidence.abilities = list
    else
        evidence.abilities = {}
        loadWarnings[#loadWarnings + 1] = "ability-catalog-unavailable"
    end
    if #loadWarnings > 0 then evidence.loadWarnings = loadWarnings end
    savedLoaded = true
    RiftReader2CastingEvidence = evidence
    announceInitialized()
end, "RR2 casting saved evidence")
table.insert(Command.Slash.Register("rr2cast"), {function() setPanelVisible(true) end, "RiftReader2Casting", "Show casting readout"})
