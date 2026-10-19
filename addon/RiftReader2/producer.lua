local _, privateVars = ...

local Producer = {}
privateVars.Producer = Producer

local MAX_EXACT_INTEGER = 9007199254740991
local FIELD_NAMES = { "coordX", "coordY", "coordZ", "health", "healthMax", "combat" }

local function unavailable()
    return { status = "unavailable" }
end

local function invalid()
    return { status = "invalid" }
end

local function ok(value)
    return { status = "ok", value = value }
end

local function unavailableFields(status)
    local fields = {}
    for _, name in ipairs(FIELD_NAMES) do
        fields[name] = status == "invalid" and invalid() or unavailable()
    end
    return fields
end

local function isFinite(value)
    return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end

local function safeFunction(root, first, second)
    local succeeded, value = pcall(function()
        local parent = root[first]
        return type(parent) == "table" and parent[second] or nil
    end)
    if not succeeded or type(value) ~= "function" then
        return nil
    end
    return value
end

local function safeCall(callable, ...)
    if type(callable) ~= "function" then
        return false, nil
    end
    local succeeded, value = pcall(callable, ...)
    if not succeeded then
        return false, nil
    end
    return true, value
end

local function readClock(api)
    local callable = safeFunction(api, "Time", "Frame")
    local succeeded, value = safeCall(callable)
    if not succeeded or value == nil then
        return unavailable()
    end
    if not isFinite(value) or value < 0 then
        return invalid()
    end
    return ok(value)
end

local function validPlayerId(value)
    if type(value) ~= "string" or #value < 1 or #value > 128 then
        return false
    end
    for index = 1, #value do
        local byte = string.byte(value, index)
        if byte < 32 or byte > 126 then
            return false
        end
    end
    return true
end

local function readPlayer(api)
    local callable = safeFunction(api, "Unit", "Lookup")
    local succeeded, value = safeCall(callable, "player")
    if not succeeded or value == nil then
        return unavailable()
    end
    if not validPlayerId(value) then
        return invalid()
    end
    return ok(value)
end

local function readDetail(api, playerId)
    local callable = safeFunction(api, "Unit", "Detail")
    local succeeded, value = safeCall(callable, playerId)
    if not succeeded or value == nil then
        return "unavailable", nil
    end
    if type(value) ~= "table" then
        return "invalid", nil
    end
    return "ok", value
end

local function readField(detail, name, expectedType)
    local succeeded, value = pcall(function()
        return detail[name]
    end)
    if not succeeded or value == nil then
        return unavailable()
    end
    if expectedType == "number" then
        return isFinite(value) and ok(value) or invalid()
    end
    return type(value) == "boolean" and ok(value) or invalid()
end

local function acquire(api)
    local before = readPlayer(api)
    if before.status ~= "ok" then
        return before, unavailableFields()
    end

    local detailStatus, detail = readDetail(api, before.value)
    local after = readPlayer(api)
    if after.status ~= "ok" then
        return after, unavailableFields()
    end
    if before.value ~= after.value then
        return invalid(), unavailableFields()
    end
    if detailStatus ~= "ok" then
        return ok(before.value), unavailableFields(detailStatus)
    end

    return ok(before.value), {
        coordX = readField(detail, "coordX", "number"),
        coordY = readField(detail, "coordY", "number"),
        coordZ = readField(detail, "coordZ", "number"),
        health = readField(detail, "health", "number"),
        healthMax = readField(detail, "healthMax", "number"),
        combat = readField(detail, "combat", "boolean")
    }
end

local Instance = {}
Instance.__index = Instance

function Instance:Clear(errorMessage, stop)
    self.Frame = nil
    self.Observation = nil
    self.LastError = errorMessage
    if stop then
        self.Stopped = true
    end
end

function Instance:AdvanceEpoch()
    if self.Epoch >= MAX_EXACT_INTEGER then
        self:Clear("epoch counter exhausted", true)
        return false
    end
    self.Epoch = self.Epoch + 1
    return true
end

function Instance:Publish(clock, player, fields)
    if self.Sequence >= MAX_EXACT_INTEGER then
        self:Clear("sequence counter exhausted", true)
        return nil, nil
    end
    local observation = {
        schemaVersion = 1,
        addonVersion = "0.1.0",
        sequence = self.Sequence + 1,
        epoch = self.Epoch,
        clock = clock,
        player = player,
        fields = fields
    }
    local frame, errorMessage = privateVars.Wire.Encode(observation)
    if not frame then
        self:Clear("serialization failed: " .. tostring(errorMessage), false)
        self.NeedsPublication = true
        return nil, nil
    end
    self.Sequence = observation.sequence
    self.Frame = frame
    self.Observation = observation
    self.LastError = nil
    self.NeedsPublication = false
    return frame, observation
end

function Instance:UpdateCore()
    if self.Stopped then
        return nil, nil
    end

    local clock = readClock(self.Api)
    if clock.status ~= "ok" then
        self.LastClock = nil
        if self.ClockFailureStatus == clock.status and not self.NeedsPublication then
            return nil, nil
        end
        self.ClockFailureStatus = clock.status
        return self:Publish(clock, unavailable(), unavailableFields())
    end

    local value = clock.value
    local publishImmediately = false
    if self.ClockFailureStatus ~= nil then
        if not self:AdvanceEpoch() then
            return nil, nil
        end
        self.ClockFailureStatus = nil
        publishImmediately = true
    elseif self.LastClock ~= nil and value < self.LastClock then
        if not self:AdvanceEpoch() then
            return nil, nil
        end
        publishImmediately = true
    elseif self.NeedsPublication then
        publishImmediately = true
    elseif self.LastClock == value then
        return nil, nil
    elseif self.LastPublishedClock == nil then
        publishImmediately = true
    end

    self.LastClock = value
    if not publishImmediately and value - self.LastPublishedClock < self.IntervalSeconds then
        return nil, nil
    end

    local player, fields = acquire(self.Api)
    local frame, observation = self:Publish(clock, player, fields)
    if frame then
        self.LastPublishedClock = value
    end
    return frame, observation
end

function Instance:Update()
    local succeeded, frame, observation = pcall(self.UpdateCore, self)
    if not succeeded then
        self:Clear("producer update failed", false)
        return nil, nil
    end
    return frame, observation
end

function Producer.New(api, options)
    if type(api) ~= "table" then
        return nil, "Inspect API must be a table"
    end
    if options ~= nil and type(options) ~= "table" then
        return nil, "options must be a table"
    end
    options = options or {}
    for key in pairs(options) do
        if key ~= "intervalSeconds" then
            return nil, "unknown producer option: " .. tostring(key)
        end
    end
    local interval = rawget(options, "intervalSeconds")
    if interval == nil then
        interval = 0.5
    end
    if not isFinite(interval) or interval < 0.05 or interval > 60 then
        return nil, "intervalSeconds must be finite and between 0.05 and 60"
    end
    return setmetatable({
        Api = api,
        IntervalSeconds = interval,
        Sequence = 0,
        Epoch = 1,
        Frame = nil,
        Observation = nil,
        LastClock = nil,
        LastPublishedClock = nil,
        ClockFailureStatus = nil,
        NeedsPublication = false,
        LastError = nil,
        Stopped = false
    }, Instance)
end
