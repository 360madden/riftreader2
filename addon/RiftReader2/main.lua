local _, privateVars = ...

local inspectApi = type(Inspect) == "table" and Inspect or {}
local producer = privateVars.Producer.New(inspectApi, { intervalSeconds = 0.5 })
privateVars.Instance = producer
RiftReader2_Frame = nil

local function update()
    if not producer then
        RiftReader2_Frame = nil
        return
    end
    local succeeded = pcall(function()
        producer:Update()
    end)
    if not succeeded then
        producer:Clear("event callback failed", false)
    end
    RiftReader2_Frame = producer.Frame
end

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
