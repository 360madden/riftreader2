local _, privateVars = ...

local inspectApi = type(Inspect) == "table" and Inspect or {}
local producer = privateVars.Producer.New(inspectApi, { intervalSeconds = 0.5 })
local live = privateVars.Live.New()
local reference = privateVars.Reference and privateVars.Reference.New(inspectApi, { intervalSeconds = 0.5 })
local guidance = privateVars.Guidance.New()
privateVars.Instance = producer
privateVars.GuidanceInstance = guidance
RiftReader2_Frame = nil
RiftReader2_LiveFrame = nil
RiftReader2_LiveFrames = {}
RiftReader2_Guidance = nil
RiftReader2_ReferenceFrame = nil
RiftReader2_ReferenceFrames = {}

-- A complete native scan can take longer than one 0.5 second publication.
-- Keep a few sequence-distinct envelopes reachable so the scanner can finish one
-- pass, while the reader still selects the highest valid producer sequence.
local LIVE_FRAME_RETENTION = 8
local lastRetainedSequence
local function clearLiveFrames()
    RiftReader2_LiveFrame = nil
    for index = #RiftReader2_LiveFrames, 1, -1 do
        RiftReader2_LiveFrames[index] = nil
    end
    lastRetainedSequence = nil
end

local function publishLiveFrame(frame)
    if type(frame) ~= "string" then
        clearLiveFrames()
        return
    end
    RiftReader2_LiveFrame = frame
    if producer.Sequence == lastRetainedSequence then return end
    RiftReader2_LiveFrames[#RiftReader2_LiveFrames + 1] = frame
    if #RiftReader2_LiveFrames > LIVE_FRAME_RETENTION then
        table.remove(RiftReader2_LiveFrames, 1)
    end
    lastRetainedSequence = producer.Sequence
end

local referenceEpoch, referencePlayerStatus, referencePlayerId
local function clearReferenceFrames()
    RiftReader2_ReferenceFrame = nil
    referenceEpoch, referencePlayerStatus, referencePlayerId = nil, nil, nil
    for index = #RiftReader2_ReferenceFrames, 1, -1 do
        RiftReader2_ReferenceFrames[index] = nil
    end
end

local rebindFailedClosed = false
local function updateReference()
    if not reference or rebindFailedClosed then return end
    local nonce = live:SessionId()
    if not nonce then return end
    reference:Bind(nonce)
    local frame, observation = reference:Update()
    if frame then
        local player = observation.player
        if referenceEpoch ~= observation.epoch or referencePlayerStatus ~= player.status or referencePlayerId ~= player.value then
            clearReferenceFrames()
        end
        referenceEpoch, referencePlayerStatus, referencePlayerId = observation.epoch, player.status, player.value
        RiftReader2_ReferenceFrame = frame
        RiftReader2_ReferenceFrames[#RiftReader2_ReferenceFrames + 1] = frame
        if #RiftReader2_ReferenceFrames > 8 then table.remove(RiftReader2_ReferenceFrames, 1) end
    elseif not reference.Frame then
        clearReferenceFrames()
    end
end

local panel
local lastText
local rebindAfterSequence
local function clock()
    local ok, value = pcall(function() return Inspect.Time.Frame() end)
    return ok and value or nil
end

local slashRegistration = { rr2bind = "pending", rr2guide = "pending" }

local function displayGuidance()
    local text = guidance:Text(producer and producer.Observation, clock())
    RiftReader2_Guidance = { protocol = "RR2G1", state = guidance.State, lab = guidance.Lab,
        session = guidance.Nonce, result = guidance.Result, reason = guidance.Reason,
        slashCommands = slashRegistration }
    -- Create lazily: a baseline-only addon load need not add a visible panel.
    if guidance.Nonce and not panel then
        local ok, frame = pcall(function()
            local context = UI.CreateContext("RiftReader2Guidance")
            local label = UI.CreateFrame("Text", "RiftReader2GuidanceText", context)
            label:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -30, 80)
            label:SetWidth(620)
            label:SetHeight(100)
            label:SetFontSize(14)
            label:SetBackgroundColor(0.03, 0.05, 0.08, 0.94)
            return label
        end)
        if ok then panel = frame end
    end
    if panel and text ~= lastText then
        local ok = pcall(function() panel:SetText(text) end)
        if ok then lastText = text end
    end
end

local function update()
    if not producer then
        RiftReader2_Frame = nil
        clearLiveFrames()
        return
    end
    local succeeded = pcall(function()
        producer:Update()
    end)
    if not succeeded then
        producer:Clear("event callback failed", false)
    end
    RiftReader2_Frame = producer.Frame
    if rebindFailedClosed or (rebindAfterSequence and producer.Sequence <= rebindAfterSequence) then
        clearLiveFrames()
    else
        publishLiveFrame(live:Wrap(producer.Frame))
        if rebindAfterSequence and RiftReader2_LiveFrame then rebindAfterSequence = nil end
    end
    updateReference()
    displayGuidance()
end

-- Legacy slash events pass only the argument string (unlike modern event handles).
-- Report registration failures rather than swallowing them in a bare pcall.
-- A successful registration alone does not prove that typed input reached this handler.
local function registerSlash(name, handler, description)
    local ok, commands = pcall(function()
        return Command.Slash.Register(name)
    end)
    if not ok or type(commands) ~= "table" then
        slashRegistration[name] = not ok and "register-error" or ("invalid-list-" .. type(commands))
        print("RiftReader2: slash registration failed for /" .. name .. " (" .. slashRegistration[name] .. ").")
        return false
    end
    local inserted = pcall(table.insert, commands, { handler, "RiftReader2", description })
    if not inserted then
        slashRegistration[name] = "insert-error"
        print("RiftReader2: slash registration failed for /" .. name .. " (insert-error).")
        return false
    end
    slashRegistration[name] = "registered"
    print("RiftReader2: slash command ready /" .. name)
    return true
end

registerSlash("rr2bind", function(args)
    local accepted, reason = live:Bind(args)
    if accepted then
        print("RiftReader2 reader bound; waiting for advancing observations.")
    else
        print("RiftReader2: " .. reason)
    end
end, "Bind a live reader for this addon load")

registerSlash("rr2guide", function(args)
    if type(args) ~= "string" or #args > 512 then print("RiftReader2: malformed guidance command."); return end
    if rebindFailedClosed and args ~= "status" then
        print("RiftReader2: Reader rebind failed closed; reload the UI before using guidance commands.")
        displayGuidance()
        return
    end
    local lab, nonce = string.match(args, "^bind (lab[12]) ([0-9a-f]+)$")
    local rebindLab, rebindNonce = string.match(args, "^rebind (lab[12]) ([0-9a-f]+)$")
    local accepted, reason
    if lab then
        -- Validate both bindings before changing the guidance identity.
        accepted, reason = live:CanBind(nonce)
        if accepted then accepted, reason = guidance:Bind(lab, nonce) end
        if accepted then
            local liveAccepted, liveReason = live:Bind(nonce)
            accepted = liveAccepted
            if not accepted then
                reason = liveReason
                guidance:Invalidate(reason)
            end
        end
    elseif rebindLab then
        -- Prevalidate both sides. An unexpected split mutation below
        -- latches publication off until the next UI reload.
        accepted, reason = live:CanRebind(rebindNonce)
        if accepted then accepted, reason = guidance:CanRebind(rebindLab, rebindNonce) end
        if accepted then
            local priorSequence = producer and producer.Sequence
            if type(priorSequence) ~= "number" then
                accepted, reason = false, "Observation producer unavailable; reload the UI before rebinding."
            end
        end
        if accepted then
            local mutationSucceeded, liveAccepted, liveReason, guidanceAccepted, guidanceReason = pcall(function()
                local changedLive, changedLiveReason = live:Rebind(rebindNonce)
                if not changedLive then
                    return changedLive, changedLiveReason, false, nil
                end
                local changedGuidance, changedGuidanceReason = guidance:Rebind(rebindLab, rebindNonce)
                return changedLive, changedLiveReason, changedGuidance, changedGuidanceReason
            end)
            accepted = mutationSucceeded and liveAccepted and guidanceAccepted
            reason = accepted and guidanceReason or liveReason or guidanceReason
            if accepted then
                -- Do not leave the old nonce globally visible until the
                -- next producer update.
                clearLiveFrames()
                clearReferenceFrames()
                rebindAfterSequence = producer.Sequence
            else
                rebindFailedClosed = true
                clearLiveFrames()
                clearReferenceFrames()
                pcall(function()
                    guidance:Invalidate("Reader rebind failed closed; reload the UI before attaching another reader.")
                end)
                reason = "Reader rebind failed closed; reload the UI before attaching another reader."
            end
        end
    elseif args == "status" then
        reason = guidance:Text(producer and producer.Observation, clock())
    elseif args == "clear" then
        guidance:Invalidate("Cancelled by operator; waiting for a new result.")
        reason = guidance.Reason
    elseif string.match(args, "^result ") then
        accepted, reason = guidance:Receive(args, producer and producer.Observation, clock())
    else
        reason = "Use /rr2guide bind lab1|lab2 NONCE, rebind lab1|lab2 NEW_NONCE, result ..., status, or clear. Results expire after 10s from source; movement invalidates them."
    end
    print("RiftReader2: " .. tostring(reason))
    displayGuidance()
end, "Bounded manual external guidance; no game actions")

local function attach(event, label)
    if event == nil then
        return
    end
    pcall(function()
        if type(Command) == "table" and type(Command.Event) == "table" and type(Command.Event.Attach) == "function" then
            Command.Event.Attach(event, update, label)
        end
    end)
end

local updateEvent
local startupEvent
pcall(function()
    updateEvent = Event.System.Update.Begin
end)
pcall(function()
    startupEvent = Event.Addon.Startup.End
end)
attach(updateEvent, "RiftReader2 update")
attach(startupEvent, "RiftReader2 startup")
