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
    RiftReader2_LiveFrame = live:Wrap(producer.Frame)
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
            local lab, nonce = string.match(args, "^bind (lab[12]) ([0-9a-f]+)$")
            local accepted, reason
            if lab then
                -- Validate both bindings before changing the guidance identity.
                accepted, reason = live:CanBind(nonce)
                if accepted then accepted, reason = guidance:Bind(lab, nonce) end
                if accepted then
                    accepted, reason = live:Bind(nonce)
                    if not accepted then guidance:Invalidate(reason) end
                end
            elseif args == "status" then
                reason = guidance:Text(producer and producer.Observation, clock())
            elseif args == "clear" then
                guidance:Invalidate("Cancelled by operator; waiting for a new result.")
                reason = guidance.Reason
            elseif string.match(args, "^result ") then
                accepted, reason = guidance:Receive(args, producer and producer.Observation, clock())
            else
                reason = "Use /rr2guide bind lab1|lab2 NONCE, result ..., status, or clear. Results expire after 10s from source; movement invalidates them."
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
