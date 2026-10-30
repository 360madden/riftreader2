local _, privateVars = ...

local inspectApi = type(Inspect) == "table" and Inspect or {}
local producer = privateVars.Producer.New(inspectApi, { intervalSeconds = 0.5 })
local live = privateVars.Live.New()
local guidance = privateVars.Guidance.New()
privateVars.Instance = producer
privateVars.GuidanceInstance = guidance
RiftReader2_Frame = nil
RiftReader2_LiveFrame = nil
RiftReader2_Guidance = nil

local panel
local lastText
local rebindAfterSequence
local rebindFailedClosed = false
local function clock()
    local ok, value = pcall(function() return Inspect.Time.Frame() end)
    return ok and value or nil
end

local function displayGuidance()
    local text = guidance:Text(producer and producer.Observation, clock())
    RiftReader2_Guidance = { protocol = "RR2G1", state = guidance.State, lab = guidance.Lab,
        session = guidance.Nonce, result = guidance.Result, reason = guidance.Reason }
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
        RiftReader2_LiveFrame = nil
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
        RiftReader2_LiveFrame = nil
    else
        RiftReader2_LiveFrame = live:Wrap(producer.Frame)
        if rebindAfterSequence and RiftReader2_LiveFrame then rebindAfterSequence = nil end
    end
    displayGuidance()
end

-- Legacy slash events pass only the argument string (unlike modern event handles).
pcall(function()
    table.insert(Command.Slash.Register("rr2bind"), {
        function(args)
            local accepted, reason = live:Bind(args)
            if accepted then
                print("RiftReader2 reader bound; waiting for advancing observations.")
            else
                print("RiftReader2: " .. reason)
            end
        end,
        "RiftReader2",
        "Bind a live reader for this addon load"
    })
end)

pcall(function()
    table.insert(Command.Slash.Register("rr2guide"), {
        function(args)
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
                        RiftReader2_LiveFrame = nil
                        rebindAfterSequence = producer.Sequence
                    else
                        rebindFailedClosed = true
                        RiftReader2_LiveFrame = nil
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
        end,
        "RiftReader2",
        "Bounded manual external guidance; no game actions"
    })
end)

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
