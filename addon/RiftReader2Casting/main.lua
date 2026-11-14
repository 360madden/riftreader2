local addonInfo, private = ...
local FALLBACK_VERSION = "0.4.2"
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
local DEFAULT_PX, DEFAULT_PY, PW, PH = 286, 72, 584, 602
local PX, PY = DEFAULT_PX, DEFAULT_PY
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
        (role == "danger" and colors.dangerButton or
        (role == "ghost" and colors.raised or colors.section))
    local tint = role == "danger" and colors.red or
        (role == "ghost" and colors.muted or colors.accent)
    local frame = surface(name, parent, x, y, width, height, fill)
    if role == "ghost" then frame:SetLayer(3) end -- Clear of the header backdrop.
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
local header = block("RR2CastingHeader", panel, 4, 0, PW - 4, 66, colors.header)
local dragHandle = block("RR2CastingDragHandle", header, 0, 0, 450, 66, {0, 0, 0, 0})
dragHandle:SetLayer(1); dragHandle:SetMouseMasking("full")
label("RR2CastingTitle", panel, 24, 9, 408, 22, "RR2 CASTING  v" .. addonVersion, colors.text)
label("RR2CastingSubtitle", panel, 24, 43, 420, 13, "Drag header to move  /  /rr2cast help", colors.muted)

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
local sequenceText = label("RR2CastingSequence", panel, 414, 529, 150, 13, "SEQ --", colors.muted)

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
local pickerDragHandle = block("RR2CastingPickerDragHandle", picker, 0, 4, PW, 76, {0, 0, 0, 0})
pickerDragHandle:SetLayer(1); pickerDragHandle:SetMouseMasking("full")
local pageText = label("RR2CastingPage", picker, 273, 474, 162, 13, "PAGE 1 / 1", colors.muted)
local emptyText = label("RR2CastingPickerEmpty", picker, 32, 223, 516, 16,
    "No supported abilities reported by RIFT.", colors.muted)
emptyText:SetVisible(false)
local choices, page, rows = {}, 1, {}
local evidence = {schemaVersion = 1, source = "RIFT Lua API", addonVersion = addonVersion,
    trials = {}, hudPosition = {x = PX, y = PY}}
local savedLoaded = false -- Preserve saved evidence until its exact load-end event.

-- The actual macro targets are styled restricted Frames, not decorative click
-- proxies. Text and accents have no mouse handlers; only EventMacroSet casts.
local castContext = UI.CreateContext("RR2CastingSecure")
castContext:SetSecureMode("restricted")
local function secureButton(name, value, left, top, width, role, parent, height)
    height = height or 40
    local frame = UI.CreateFrame("Frame", name, parent or castContext)
    frame:SetSecureMode("restricted")
    frame:SetPoint("TOPLEFT", parent or UIParent, "TOPLEFT", left, top)
    frame:SetWidth(width); frame:SetHeight(height)
    frame:SetMouseMasking("full")
    background(frame, colors.border)
    local fill = block(name .. "Fill", frame, 1, 1, width - 2, height - 2,
        role == "danger" and colors.dangerButton or colors.primaryButton)
    fill:SetMouseMasking("limited")
    local accent = block(name .. "Accent", frame, 1, 1, 4, height - 2,
        role == "danger" and colors.red or colors.accent)
    accent:SetLayer(1); accent:SetMouseMasking("limited")
    if parent and role=="primary" then
        return frame, label(name.."Label",frame,12,0,width-16,20,value)
    end
    return frame, centeredLabel(name .. "Label", frame, width, height, value)
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

-- Keep all UIParent-anchored surfaces in one coordinate system. Restricted
-- frames must move first; a failed protected move never persists a new origin.
local function coordinate(v)
    return type(v) == "number" and v == v and math.abs(v) < math.huge
end
local function nonSecure()
    local system = type(Inspect) == "table" and Inspect.System
    local check = type(system) == "table" and system.Secure
    if type(check) ~= "function" then return false end
    local ok, value = pcall(check)
    return ok and value == false
end
local function viewport()
    local okW, width = pcall(function() return UIParent:GetWidth() end)
    local okH, height = pcall(function() return UIParent:GetHeight() end)
    if not okW or not okH or not coordinate(width) or not coordinate(height) or
        width <= 0 or height <= 0 then return nil, nil end
    return width, height
end
local function safePoint(frame, x, y)
    local ok, result = pcall(frame.SetPoint, frame, "TOPLEFT", UIParent, "TOPLEFT", x, y)
    return ok and result ~= false
end
local function safeVisible(frame, visible)
    local ok, result = pcall(frame.SetVisible, frame, visible)
    return ok and result ~= false
end
local pendingPosition
local positionEditedBeforeLoad = false
local function setPosition(x, y, restoring)
    if not coordinate(x) or not coordinate(y) then return false, "invalid-coordinates" end
    if not nonSecure() then return false, "combat-lock" end
    local screenW, screenH = viewport()
    if not screenW then return false, "viewport-unavailable" end
    local newX = math.floor(math.max(0, math.min(x, math.max(0, screenW - PW))) + 0.5)
    local newY = math.floor(math.max(0, math.min(y, math.max(0, screenH - PH))) + 0.5)
    if newX == PX and newY == PY then
        pendingPosition = nil
        evidence.hudPosition = {x = PX, y = PY}
        if not savedLoaded and not restoring then positionEditedBeforeLoad = true end
        return true
    end
    local oldX, oldY = PX, PY
    local changes = {
        {castButton, oldX + 16, oldY + 552, newX + 16, newY + 552},
        {stopButton, oldX + 374, oldY + 552, newX + 374, newY + 552},
        {panel, oldX, oldY, newX, newY},
        {picker, oldX, oldY, newX, newY}
    }
    for i, entry in ipairs(changes) do
        if not safePoint(entry[1], entry[4], entry[5]) then
            local rollbackFailed = false
            for j = i, 1, -1 do
                local prior = changes[j]
                if not safePoint(prior[1], prior[2], prior[3]) then rollbackFailed = true end
            end
            evidence.layoutWarning = rollbackFailed and "layout-rollback-incomplete" or "layout-move-rejected"
            return false, evidence.layoutWarning
        end
    end
    PX, PY = newX, newY
    evidence.hudPosition = {x = PX, y = PY}
    evidence.layoutWarning = nil
    pendingPosition = nil
    if not savedLoaded and not restoring then positionEditedBeforeLoad = true end
    if savedLoaded then RiftReader2CastingEvidence = evidence end
    return true
end

local drag = {active = false, offsetX = 0, offsetY = 0}
local function mousePosition()
    local fn = type(Inspect) == "table" and Inspect.Mouse
    if type(fn) ~= "function" then return nil end
    local ok, pos = pcall(fn)
    if ok and type(pos) == "table" and coordinate(pos.x) and coordinate(pos.y) then return pos end
    return nil
end
local function beginDrag()
    drag.active = false
    if not nonSecure() then return end
    local pos = mousePosition()
    if not pos then return end
    drag.offsetX = pos.x - PX
    drag.offsetY = pos.y - PY
    drag.active = true
end
local function moveDrag()
    if not drag.active then return end
    if not nonSecure() then drag.active = false; return end
    -- Global Cursor.Move reports only a handle. Poll the actual screen mouse
    -- and held-button state so a missed Upoutside cannot cause hover-dragging.
    local pos = mousePosition()
    if not pos or pos.Left ~= true then drag.active = false; return end
    local ok = setPosition(pos.x - drag.offsetX, pos.y - drag.offsetY)
    if not ok then drag.active = false end
end
local function endDrag() drag.active = false end
local function attachDrag(handle, suffix, begin, move, finish)
    local mouse = Event.UI and Event.UI.Input and Event.UI.Input.Mouse
    local left = mouse and mouse.Left
    local cursor = mouse and mouse.Cursor
    if not left or not left.Down or not left.Up or not cursor or not cursor.Move then
        evidence.dragWarning = "rift-mouse-events-unavailable"
        return
    end
    handle:EventAttach(left.Down, begin or beginDrag, "RR2 casting drag start" .. suffix)
    handle:EventAttach(cursor.Move, move or moveDrag, "RR2 casting drag move" .. suffix)
    handle:EventAttach(left.Up, finish or endDrag, "RR2 casting drag end" .. suffix)
    if left.Upoutside then
        handle:EventAttach(left.Upoutside, finish or endDrag, "RR2 casting drag cancel" .. suffix)
    end
end
attachDrag(dragHandle, "")
attachDrag(pickerDragHandle, " picker")

local panelVisible = true
local function setPanelVisible(visible)
    if type(visible) ~= "boolean" then return false, "invalid-visibility" end
    if not nonSecure() then return false, "combat-lock" end
    local before = panelVisible
    if not safeVisible(castButton, visible) then return false, "cast-visibility-rejected" end
    if not safeVisible(stopButton, visible) then
        safeVisible(castButton, before)
        return false, "stop-visibility-rejected"
    end
    if not safeVisible(panel, visible) or
        (not visible and not safeVisible(picker, false)) then
        safeVisible(panel, before)
        safeVisible(castButton, before)
        safeVisible(stopButton, before)
        return false, "panel-visibility-rejected"
    end
    panelVisible = visible
    if not visible then drag.active = false end
    return true
end
local function selectAbility(id)
    if model.trial and model.trial.status == "recording" then return false end
    if not nonSecure() then return false end
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

-- Export the actual restricted frames in UIParent coordinates. The external
-- reader owns process/window binding and the conversion to client pixels.
local function actionRect(frame, mapped)
    local rect = {mapped = mapped}
    local ok, x, y, w, h = pcall(function()
        return frame:GetLeft()-UIParent:GetLeft(), frame:GetTop()-UIParent:GetTop(),
            frame:GetWidth(), frame:GetHeight()
    end)
    if ok and coordinate(x) and coordinate(y) and coordinate(w) and coordinate(h) and w > 0 and h > 0 then
        rect.left, rect.top, rect.width, rect.height = x, y, w, h
    end
    return rect
end
local profileSlots, profileCancel = {}, nil
local toolbar = {x=72,y=270,width=248,height=44,visible=false}
local function toolbarUnlocked()
    if not nonSecure() then return false end
    local ok,p=pcall(Inspect.Unit.Lookup,"player")
    if not ok or not p then return false end
    local valid,detail=pcall(Inspect.Unit.Detail,p)
    return valid and type(detail)=="table" and detail.combat~=true
end
local function placeToolbar(x,y)
    local w,h=viewport()
    if not toolbarUnlocked() or not w or w<toolbar.width or h<toolbar.height then return false end
    x=math.max(0,math.min(math.floor(x+.5),math.floor(w-toolbar.width)))
    y=math.max(0,math.min(math.floor(y+.5),math.floor(h-toolbar.height)))
    if not safePoint(toolbar.frame,x,y) then return false end
    toolbar.x,toolbar.y=x,y
    return true
end
local function initToolbar()
    local frame=UI.CreateFrame("Frame","RR2SurvivalToolbar",castContext)
    frame:SetSecureMode("restricted")
    frame:SetWidth(toolbar.width); background(frame,colors.background)
    frame:SetMouseMasking("limited")
    toolbar.frame=frame
    safeVisible(frame,false)
    local handle=block("RR2SurvivalHandle",frame,2,2,155,40,colors.header)
    handle:SetMouseMasking("full")
    label("RR2SurvivalTitle",handle,12,4,138,22,"Survival",colors.text)
    attachDrag(handle," survival",function()
        toolbar.drag=nil
        local pos=mousePosition()
        if toolbarUnlocked() and pos then toolbar.drag={x=pos.x-toolbar.x,y=pos.y-toolbar.y} end
    end,function()
        if not toolbar.drag then return end
        local pos=mousePosition()
        if not pos or pos.Left~=true or not placeToolbar(pos.x-toolbar.drag.x,pos.y-toolbar.drag.y) then
            toolbar.drag=nil; return
        end
        evidence.survivalToolbarPosition={x=toolbar.x,y=toolbar.y}
    end,function() toolbar.drag=nil end)
    local caption
    profileCancel,caption=secureButton("RR2SurvivalCancel","STOP",160,2,86,"danger",frame)
    caption:SetFontSize(20)
end
local function layoutToolbar()
    if not nonSecure() then return false end
    if not toolbar.frame then return true end
    local n=0
    for i=1,8 do
        local slot=profileSlots[i]
        if slot and slot.id then
            local ok,accepted=pcall(slot.frame.SetPoint,slot.frame,"TOPLEFT",toolbar.frame,"TOPLEFT",4,44+n*50)
            if not ok or accepted==false then return false end
            n=n+1
        end
    end
    toolbar.height=44+n*50
    toolbar.frame:SetHeight(toolbar.height)
    local show=n>0
    if show and not placeToolbar(toolbar.x,toolbar.y) then return false end
    if not safeVisible(toolbar.frame,show) then return false end
    toolbar.visible=show
    return true
end
local function refreshToolbarSize()
    if not toolbar.frame or not toolbar.visible then return end
    local w,h=viewport()
    if w and (toolbar.x+toolbar.width>w or toolbar.y+toolbar.height>h) then
        placeToolbar(toolbar.x,toolbar.y)
    end
end
local function prepareSlot(index, id)
    if not toolbarUnlocked() then return false end
    local entry = profileSlots[index]
    if id == "clear" then
        if not entry then return true end
        if not safeVisible(entry.frame,false) then return false end
        entry.id, entry.name, entry.monitor = nil,nil,nil
        return layoutToolbar()
    end
    local learned = Inspect.Ability.New.List()
    if type(learned) ~= "table" or not learned[id] then return false end
    local d = Inspect.Ability.New.Detail(id)
    if type(d) ~= "table" or type(d.name) ~= "string" or #d.name == 0 or #d.name > 120
            or d.name:find("[%z\1-\31]") or d.positioned or d.autoattack or d.passive then return false end
    for i, existing in pairs(profileSlots) do if i ~= index and existing.id == id then return false end end
    local monitor = private.Casting.New(Inspect)
    if not monitor:Select(id) then return false end
    if not profileCancel then
        initToolbar()
    end
    local cancelOk,cancelResult = pcall(profileCancel.EventMacroSet,profileCancel,
        Event.UI.Input.Mouse.Left.Click,"stopcasting\nstopattack")
    if not cancelOk or cancelResult == false or not safeVisible(profileCancel,true) then return false end
    if not entry then
        local name="RR2SurvivalSlot"..index
        local f, caption = secureButton(name,"",4,44,240,"primary",toolbar.frame,48)
        local status=label(name.."Status",f,12,25,224,15,"Checking",colors.muted)
        entry={frame=f,caption=caption,status=status}; profileSlots[index]=entry
        if not safeVisible(f,false) then return false end
    end
    local macro = "cast "..d.name.."\nstopattack"
    local ok,accepted = pcall(entry.frame.EventMacroSet,entry.frame,Event.UI.Input.Mouse.Left.Click,macro)
    if not ok or accepted == false then return false end
    entry.id,entry.name,entry.macro,entry.monitor = id,d.name,macro,monitor
    entry.caption:SetText(shortName(d.name,23))
    entry.lastStatus=nil; entry.status:SetText("Checking")
    if not layoutToolbar() or not safeVisible(entry.frame,true) then
        entry.id,entry.name,entry.monitor=nil,nil,nil
        safeVisible(entry.frame,false); layoutToolbar()
        return false
    end
    return true
end
local function toolbarRect(frame,w,h)
    local rect=actionRect(frame,true)
    rect.mapped=toolbar.visible and w~=nil and rect.left~=nil and rect.left>=0 and rect.top>=0
        and rect.left+rect.width<=w and rect.top+rect.height<=h
    return rect
end
local function toolbarStatus(slot,state)
    if slot.lastStatus==state then return end
    local tint=state=="ready" and colors.green or (state=="waiting" and colors.amber or colors.muted)
    local text=state=="ready" and "Ready" or (state=="waiting" and "Waiting" or (state=="blocked" and "Blocked" or "Unknown"))
    -- A client that restricts text decoration in combat must still publish the exact action observation.
    local ok=pcall(function()
        slot.status:SetText(text)
        slot.status:SetFontColor(tint[1],tint[2],tint[3],tint[4])
    end)
    if ok then slot.lastStatus=state end
end
local function survivalControls(playerId,targetId)
    local bound = evidence.castButton
    local mapped = type(bound) == "table" and type(model.selected) == "string" and
        bound.abilityId == model.selected
    local cast = actionRect(castButton, mapped)
    if mapped then cast.abilityId, cast.abilityName, cast.macro = bound.abilityId, bound.abilityName, bound.macro end
    local width, height = viewport()
    local actions = {}
    for i, slot in pairs(profileSlots) do
        if slot.id then
            local v = toolbarRect(slot.frame,width,height)
            if toolbar.drag or not width or toolbar.x+toolbar.width>width or toolbar.y+toolbar.height>height then
                v.mapped=false
            end
            v.slot,v.abilityId,v.abilityName,v.macro,v.visible = i,slot.id,slot.name,slot.macro,v.mapped
            local r = slot.monitor:Read(true)
            if r.playerId == playerId and r.targetId == targetId and r.abilityId == slot.id then
                v.readiness = {status=r.status,reason=r.reason}
                v.ability = {target=r.ability.target,idNew=r.ability.idNew,currentCooldownRemaining=r.ability.currentCooldownRemaining,
                    outOfRange=r.ability.outOfRange,unusable=r.ability.unusable,costPower=r.ability.costPower}
            else v.readiness={status="blocked",reason="profile-identity-changed"}; v.ability={} end
            slot.lastRead=r.clock
            toolbarStatus(slot,v.readiness.status)
            actions[slot.id]=v
        end
    end
    local cancel
    if profileCancel and next(actions) then
        cancel = toolbarRect(profileCancel,width,height); cancel.visible=cancel.mapped
        cancel.macro="stopcasting\nstopattack"; cancel.effectQualification="unverified"
    end
    return {visible = panelVisible, space = "UIParent", viewportWidth = width, viewportHeight = height,
        actions=actions,cancel=cancel,cast = cast, stop = actionRect(stopButton, stopOk and stopResult ~= false)}
end
if private.Survival then
    private.Survival.Start(Inspect, model, selectAbility, survivalControls, prepareSlot,toolbarUnlocked)
end

-- Retain the installed game's API descriptions as offline evidence.
if type(Inspect.Documentation) == "function" then
    evidence.runtimeApi = {}
    for _, name in ipairs({"Inspect.Ability.New.Detail", "Inspect.Ability.Detail", "Inspect.Ability.New.List", "Inspect.Unit.Castbar",
        "Inspect.Unit.Detail", "Inspect.Tooltip", "Event.Combat.Damage", "Event.Combat.Heal", "Event.Ability.New.Cooldown.Begin",
        "Event.Ability.New.Cooldown.End", "Command.Event.Attach", "Layout:EventMacroSet", "Inspect.System.Secure",
        "Frame:EventMacroSet", "Frame:SetMouseMasking", "Inspect.Mouse",
        "Event.UI.Input.Mouse.Cursor.Move", "Event.UI.Input.Mouse.Left.Down", "Frame:SetPoint"}) do
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
local function openPicker()
    if not nonSecure() then return false, "combat-lock" end
    if not panelVisible then
        local visible, reason = setPanelVisible(true)
        if not visible then return false, reason end
    end
    page = 1
    local ok = pcall(showChoices)
    if not ok then return false, "ability-catalog-unavailable" end
    return true
end
local function beginRecording()
    local called, ok, reason = pcall(model.Begin, model)
    if not called then ok, reason = false, "observation-unavailable" end
    if ok then
        evidence.trials[#evidence.trials + 1] = model.trial
        if #evidence.trials > 8 then table.remove(evidence.trials, 1) end
        message = "Recording only. Review readiness before clicking Cast."
    else
        message = "Not recording: " .. (reason or "unavailable")
    end
    return ok, reason
end
button("RR2CastingAbilities", "Choose ability", panel, 16, 473, 270, 40, function()
    local ok, reason = openPicker()
    if not ok then message = "Picker unavailable: " .. (reason or "unknown") end
end)
button("RR2CastingRecord", "Record 60s", panel, 298, 473, 270, 40, function()
    beginRecording()
end, "primary")
button("RR2CastingHide", "Hide", header, 480, 16, 84, 38,
    function()
        local ok, reason = setPanelVisible(false)
        if not ok then message = "Cannot hide: " .. (reason or "unavailable") end
    end, "ghost")

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
    refreshToolbarSize()
    local r = model:Read()
    if private.Survival and private.Survival.Publish then private.Survival.Publish(r) end
    for _,slot in pairs(profileSlots) do
        if slot.id and slot.lastRead and (now<slot.lastRead or now-slot.lastRead>1) then toolbarStatus(slot,"unknown") end
    end
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
    if pendingPosition and nonSecure() then
        local pending = pendingPosition
        local moved, failure = setPosition(pending.x, pending.y, true)
        if not moved and failure ~= "combat-lock" and failure ~= "viewport-unavailable" then
            evidence.layoutWarning = failure
            pendingPosition = nil
        end
    end
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
        Command.Event.Attach(Event.Combat[spec[1]], function(_, info)
            model:Combat(kind, info)
            if private.Survival then private.Survival.ObserveCombat(kind, info) end
        end, "RR2 casting " .. kind)
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
    if not positionEditedBeforeLoad and type(prior) == "table" and
        type(prior.hudPosition) == "table" then
        local priorX, priorY = prior.hudPosition.x, prior.hudPosition.y
        if coordinate(priorX) and coordinate(priorY) then
            local moved, failure = setPosition(priorX, priorY, true)
            if not moved then
                evidence.hudPosition = {x = priorX, y = priorY}
                if failure == "combat-lock" or failure == "viewport-unavailable" then
                    pendingPosition = {x = priorX, y = priorY}
                else
                    loadWarnings[#loadWarnings + 1] = "hud-position-restore-failed"
                end
            end
        else
            loadWarnings[#loadWarnings + 1] = "invalid-saved-hud-position"
        end
    end
    local savedBar=type(prior)=="table" and prior.survivalToolbarPosition
    if not evidence.survivalToolbarPosition and type(savedBar)=="table" and coordinate(savedBar.x) and coordinate(savedBar.y) then
        evidence.survivalToolbarPosition={x=savedBar.x,y=savedBar.y}
        if not toolbar.frame then toolbar.x,toolbar.y=savedBar.x,savedBar.y
        elseif nonSecure() then placeToolbar(savedBar.x,savedBar.y) end
    end
    if #loadWarnings > 0 then evidence.loadWarnings = loadWarnings end
    savedLoaded = true
    RiftReader2CastingEvidence = evidence
    announceInitialized()
end, "RR2 casting saved evidence")
-- The legacy RIFT slash callback receives one raw argument string (not an
-- event handle). Keep the CLI diagnostic-only; it must never click a macro.
local function cliOutput(value, level)
    local palette = {info = "99DDE8", success = "52E3BB", caution = "F0BE62", error = "EC6A76"}
    local hex = palette[level] or palette.info
    local line = type(value) == "string" and value or "RR2 Casting: unavailable"
    local console = type(Command) == "table" and Command.Console
    if type(console) == "table" and type(console.Display) == "function" then
        local ok, accepted = pcall(console.Display, "general", true,
            '<font color="#' .. hex .. '">' .. line .. '</font>', true)
        if ok and accepted ~= false then return end
    end
    if type(print) == "function" then pcall(print, "|cff" .. hex .. line .. "|r") end
end
local function safeCli(value, maxLength)
    if type(value) ~= "string" then return "unknown" end
    local clean = string.gsub(value, "[%c<&>|]", " ")
    return shortName(clean, maxLength)
end
local function commandHelp()
    cliOutput("RR2 CASTING v" .. addonVersion .. "  /  COMMAND GUIDE", "success")
    cliOutput("/rr2cast (or show) - show dashboard; hide/toggle also available", "info")
    cliOutput("/rr2cast abilities | record - picker / 60s observation", "info")
    cliOutput("/rr2cast status | info - API checks / feature limits", "info")
    cliOutput("/rr2cast position - coordinates and drag instructions", "info")
    cliOutput("/rr2cast move X Y | reset - place HUD / restore default", "info")
    cliOutput("Drag the header or picker title. Cast and Stop require manual clicks.", "caution")
    cliOutput("Facing and hostile LOS are UNVERIFIED; API READY is not a clear-shot claim.", "caution")
end
local function commandStatus()
    local r = evidence.last
    if type(r) ~= "table" then
        cliOutput("RR2 Casting v" .. addonVersion .. " | No readout sample yet.", "caution")
    else
        local state = type(r.status) == "string" and string.upper(r.status) or "UNKNOWN"
        if state == "READY" then state = "API READY" end
        local reason = safeCli(humanReason(r.reason), 68)
        local severity = r.status == "ready" and "success" or
            (r.status == "waiting" and "caution" or "error")
        cliOutput("RR2 Casting v" .. addonVersion .. " | " .. safeCli(state, 20) ..
            " | " .. reason, severity)
        local target = type(r.target) == "table" and r.target.name or nil
        local ability = type(r.ability) == "table" and r.ability or {}
        local player = type(r.player) == "table" and r.player or {}
        cliOutput("Target: " .. safeCli(target, 42) ..
            "  |  Ability: " .. safeCli(ability.name, 42), "info")
        cliOutput("Range: " .. f(ability.rangeMin) .. " - " .. f(ability.rangeMax) ..
            "  |  Cast: " .. castTime(ability.castingTime) ..
            "  |  Channel: " .. channel(ability.channeled), "info")
        cliOutput("Ability/GCD cooldown: " .. f(ability.currentCooldownRemaining) ..
            "s  |  Power: " .. f(player.power) .. " / " .. f(ability.costPower), "info")
    end
    local trial = model.trial
    local trialStatus = type(trial) == "table" and trial.status or "not recording"
    cliOutput("Trial: " .. safeCli(trialStatus, 30) ..
        "  |  HUD: " .. (panelVisible and "shown" or "hidden") ..
        "  |  X " .. PX .. "  Y " .. PY, "info")
    cliOutput("Facing: UNVERIFIED  |  Line of sight: UNVERIFIED", "caution")
    if evidence.layoutWarning then
        cliOutput("Layout warning: " .. safeCli(evidence.layoutWarning, 60), "error")
    end
end
local function parseCommand(raw)
    if raw == nil then raw = "" end
    if type(raw) ~= "string" or #raw > 96 then return nil end
    local tokens = {}
    for word in string.gmatch(raw, "%S+") do
        if #tokens >= 3 or #word > 32 then return nil end
        tokens[#tokens + 1] = string.lower(word)
    end
    return tokens
end
local function slashCommand(raw)
    local tokens = parseCommand(raw)
    if not tokens then
        cliOutput("Invalid command arguments. Use /rr2cast help.", "error")
        return
    end
    local verb = tokens[1] or "show"
    if verb == "?" or verb == "commands" then verb = "help" end
    if verb == "version" then verb = "info" end
    if verb == "open" then verb = "show" end
    if verb == "close" then verb = "hide" end
    if verb ~= "move" and #tokens > 1 then
        cliOutput("Unexpected extra arguments. Use /rr2cast help.", "error")
        return
    end
    if verb == "help" then
        commandHelp()
    elseif verb == "status" then
        commandStatus()
    elseif verb == "info" then
        cliOutput("RR2 Casting v" .. addonVersion .. " | RIFT Lua diagnostics and bounded trials.", "success")
        cliOutput("API READY means available target/resource/range/cooldown checks passed.", "info")
        cliOutput("Facing/LOS not verified; no automated casting, retries or movement.", "caution")
        cliOutput("Position saved with character data; use /rr2cast help for controls.", "info")
    elseif verb == "position" then
        cliOutput("HUD top-left: X " .. PX .. ", Y " .. PY ..
            ". Drag header/title or use /rr2cast move X Y; reset for default.", "info")
        if pendingPosition then cliOutput("Saved position awaits the end of combat.", "caution") end
        if evidence.dragWarning then cliOutput("Drag warning: " .. safeCli(evidence.dragWarning, 48), "caution") end
    elseif verb == "move" then
        if #tokens ~= 3 or not coordinate(tonumber(tokens[2])) or
            not coordinate(tonumber(tokens[3])) then
            cliOutput("Usage: /rr2cast move X Y  (finite screen coordinates)", "error")
            return
        end
        local ok, reason = setPosition(tonumber(tokens[2]), tonumber(tokens[3]))
        cliOutput(ok and ("HUD moved to X " .. PX .. ", Y " .. PY) or
            ("Cannot move HUD: " .. safeCli(reason, 48)), ok and "success" or "error")
    elseif verb == "reset" then
        local ok, reason = setPosition(DEFAULT_PX, DEFAULT_PY)
        cliOutput(ok and ("HUD reset to X " .. PX .. ", Y " .. PY) or
            ("Cannot reset HUD: " .. safeCli(reason, 48)), ok and "success" or "error")
    elseif verb == "show" or verb == "hide" or verb == "toggle" then
        local desired = verb == "show" or (verb == "toggle" and not panelVisible)
        local ok, reason = setPanelVisible(desired)
        cliOutput(ok and ("Dashboard " .. (desired and "shown" or "hidden")) or
            ("Visibility unchanged: " .. safeCli(reason, 48)), ok and "success" or "caution")
    elseif verb == "abilities" then
        local ok, reason = openPicker()
        cliOutput(ok and "Ability picker opened; select only while out of combat." or
            ("Cannot open picker: " .. safeCli(reason, 48)), ok and "success" or "caution")
    elseif verb == "record" then
        if not panelVisible then
            local shown, failure = setPanelVisible(true)
            if not shown then
                cliOutput("Cannot record while hidden: " .. safeCli(failure, 48), "error")
                return
            end
        end
        local ok, reason = beginRecording()
        cliOutput(ok and "Recording 60s. Casting still requires a manual click." or
            ("Not recording: " .. safeCli(reason, 48)), ok and "success" or "caution")
    else
        cliOutput("Unknown RR2 Casting command. Use /rr2cast help.", "error")
    end
end
local registerOk, registerList = pcall(function() return Command.Slash.Register("rr2cast") end)
if registerOk and type(registerList) == "table" then
    table.insert(registerList, {slashCommand, "RiftReader2Casting", "Casting v" ..
        addonVersion .. ": help, status, show/hide, position, manual recording"})
else
    evidence.slashWarning = "rr2cast-registration-unavailable"
end
