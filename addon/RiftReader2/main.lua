local _, privateVars = ...

local inspectApi = type(Inspect) == "table" and Inspect or {}
local producer = privateVars.Producer.New(inspectApi, { intervalSeconds = 0.5 })
local live = privateVars.Live.New()
privateVars.Instance = producer
RiftReader2_Frame = nil
RiftReader2_LiveFrame = nil

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
