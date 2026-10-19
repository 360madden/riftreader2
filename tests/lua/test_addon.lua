local checkCount = 0

local function assertEqual(expected, actual, message)
    checkCount = checkCount + 1
    if expected ~= actual then
        error((message or "values differ") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
    end
end

local function assertTrue(value, message)
    checkCount = checkCount + 1
    if not value then
        error(message or "assertion failed")
    end
end

local function newApi(state)
    local lookupCount = 0
    return {
        Time = {
            Frame = function()
                if state.clockError then
                    error("clock failure")
                end
                return state.clock
            end
        },
        Unit = {
            Lookup = function(kind)
                assertEqual("player", kind, "lookup kind")
                lookupCount = lookupCount + 1
                if state.lookupError then
                    error("lookup failure")
                end
                if lookupCount % 2 == 1 then
                    return state.beforePlayer
                end
                return state.afterPlayer
            end,
            Detail = function(id)
                state.detailPlayer = id
                if state.detailError then
                    error("detail failure")
                end
                return state.detail
            end
        }
    }, function()
        return lookupCount
    end
end

local function validState()
    return {
        clock = 10,
        beforePlayer = "player-1",
        afterPlayer = "player-1",
        detail = {
            coordX = 0,
            coordY = -12.5,
            coordZ = 30.25,
            health = 0,
            healthMax = 100,
            combat = false
        }
    }
end

local function runTests(privateVars, mainSource)
    checkCount = 0
    assertTrue(type(privateVars.Wire) == "table", "wire module missing")
    assertTrue(type(privateVars.Producer) == "table", "producer module missing")

    local state = validState()
    local api, lookupCount = newApi(state)
    local producer, producerError = privateVars.Producer.New(api)
    assertTrue(producer ~= nil, producerError)

    local frame, observation = producer:Update()
    assertTrue(type(frame) == "string", "first observation was not published")
    assertEqual("RR2A1|", string.sub(frame, 1, 6), "frame prefix")
    assertEqual("|ENDRR2A1", string.sub(frame, -9), "frame suffix")
    assertEqual(1, observation.sequence, "initial sequence")
    assertEqual(1, observation.epoch, "initial epoch")
    assertEqual(false, observation.fields.combat.value, "false field")
    assertEqual(frame, producer.Frame, "published frame state")
    assertEqual(observation, producer.Observation, "published observation state")
    assertEqual("player-1", state.detailPlayer, "detail identity")

    observation.clock.value = -1
    assertEqual(nil, privateVars.Wire.Encode(observation), "negative successful clock encoded")
    observation.clock.value = 10

    state.clock = 10.1
    assertEqual(nil, producer:Update(), "interval throttle")
    assertEqual(2, lookupCount(), "throttled update acquired unit data")
    state.clock = 10.5
    frame, observation = producer:Update()
    assertTrue(frame ~= nil, "interval publication missing")
    assertEqual(2, observation.sequence, "interval sequence")
    assertEqual(nil, producer:Update(), "unchanged clock republished")

    state.clock = nil
    frame, observation = producer:Update()
    assertTrue(frame ~= nil, "clock clearing observation missing")
    assertEqual("unavailable", observation.clock.status, "clock loss status")
    assertEqual("unavailable", observation.player.status, "clock loss player")
    assertEqual(nil, producer:Update(), "repeated clock loss republished")
    state.clock = -1
    frame, observation = producer:Update()
    assertTrue(frame ~= nil, "changed clock failure did not publish")
    assertEqual("invalid", observation.clock.status, "invalid clock status")

    state.clock = 10.6
    frame, observation = producer:Update()
    assertTrue(frame ~= nil, "clock recovery did not publish")
    assertEqual(2, observation.epoch, "recovery epoch")
    state.clock = 1
    frame, observation = producer:Update()
    assertTrue(frame ~= nil, "clock regression did not publish")
    assertEqual(3, observation.epoch, "regression epoch")

    local escapedState = validState()
    escapedState.beforePlayer = "player-\"\\|ENDRR2A1"
    escapedState.afterPlayer = escapedState.beforePlayer
    local escapedProducer = assert(privateVars.Producer.New((newApi(escapedState))))
    local escapedFrame = escapedProducer:Update()
    assertTrue(string.find(escapedFrame, "player-\\\"\\\\|ENDRR2A1", 1, true) ~= nil, "player escaping missing")

    local changedState = validState()
    changedState.afterPlayer = "player-2"
    local changedProducer = assert(privateVars.Producer.New((newApi(changedState))))
    local _, changed = changedProducer:Update()
    assertEqual("invalid", changed.player.status, "identity race status")
    assertEqual("unavailable", changed.fields.coordX.status, "identity race fields")

    local badFrame = privateVars.Wire.Encode({})
    assertEqual(nil, badFrame, "malformed observation encoded")
    assertEqual(nil, privateVars.Producer.New(api, { intervalSeconds = 0.049 }), "small interval accepted")
    assertEqual(nil, privateVars.Producer.New(api, { intervalSeconds = 61 }), "large interval accepted")
    assertEqual(nil, privateVars.Producer.New(api, { unexpected = true }), "unknown option accepted")

    local exhaustedState = validState()
    local exhausted = assert(privateVars.Producer.New((newApi(exhaustedState))))
    exhausted.Sequence = 9007199254740991
    assertEqual(nil, exhausted:Update(), "exhausted sequence published")
    assertTrue(exhausted.Stopped, "exhausted producer did not stop")
    assertEqual(nil, exhausted.Frame, "exhaustion retained frame")

    local epochState = validState()
    local epochProducer = assert(privateVars.Producer.New((newApi(epochState))))
    epochProducer:Update()
    epochProducer.Epoch = 9007199254740991
    epochState.clock = 1
    assertEqual(nil, epochProducer:Update(), "exhausted epoch published")
    assertTrue(epochProducer.Stopped, "epoch exhaustion did not stop")

    local serializationState = validState()
    local serializationProducer = assert(privateVars.Producer.New((newApi(serializationState))))
    serializationProducer:Update()
    serializationState.clock = 10.5
    local originalEncode = privateVars.Wire.Encode
    privateVars.Wire.Encode = function()
        return nil, "injected serialization failure"
    end
    assertEqual(nil, serializationProducer:Update(), "serialization failure published")
    assertEqual(nil, serializationProducer.Frame, "serialization failure retained frame")
    privateVars.Wire.Encode = originalEncode
    frame, observation = serializationProducer:Update()
    assertTrue(frame ~= nil, "producer did not recover from serialization failure")
    assertEqual(2, observation.sequence, "serialization retry consumed a sequence")

    assertTrue(type(mainSource) == "string", "main source missing")
    local oldInspect = Inspect
    local oldEvent = Event
    local oldCommand = Command
    local oldFrame = RiftReader2_Frame
    local mainSucceeded, mainError = pcall(function()
        Inspect = nil
        Event = nil
        Command = nil
        RiftReader2_Frame = "stale"
        local missingApiMain = assert(loadstring(mainSource))
        missingApiMain({ identifier = "RiftReader2" }, privateVars)
        assertTrue(privateVars.Instance ~= nil, "main did not create missing-API producer")
        assertEqual(nil, RiftReader2_Frame, "main retained stale global on load")

        local mainState = validState()
        Inspect = (newApi(mainState))
        Event = {
            System = { Update = { Begin = {} } },
            Addon = { Startup = { End = {} } }
        }
        Command = {
            Event = {
                Attach = function(event, callback, identifier)
                    table.insert(event, { callback, identifier })
                end
            }
        }
        local mainChunk = assert(loadstring(mainSource))
        mainChunk({ identifier = "RiftReader2" }, privateVars)
        assertEqual(1, #Event.System.Update.Begin, "update hook count")
        assertEqual(1, #Event.Addon.Startup.End, "startup hook count")
        assertEqual("RiftReader2 update", Event.System.Update.Begin[1][2], "update hook identifier")
        assertEqual(0, select("#", Event.Addon.Startup.End[1][1]()), "startup callback returned values")
        assertTrue(type(RiftReader2_Frame) == "string", "startup callback did not publish")

        privateVars.Instance.Sequence = 9007199254740991
        mainState.clock = 10.5
        assertEqual(0, select("#", Event.System.Update.Begin[1][1]()), "update callback returned values")
        assertEqual(nil, RiftReader2_Frame, "counter exhaustion did not clear global")

        local reloadChunk = assert(loadstring(mainSource))
        reloadChunk({ identifier = "RiftReader2" }, privateVars)
        assertEqual(nil, RiftReader2_Frame, "reload retained prior global")
        assertEqual(2, #Event.Addon.Startup.End, "reload startup hook count")
        Event.Addon.Startup.End[2][1]()
        assertEqual(1, privateVars.Instance.Observation.sequence, "reload did not reset sequence")
    end)
    Inspect = oldInspect
    Event = oldEvent
    Command = oldCommand
    RiftReader2_Frame = oldFrame
    if not mainSucceeded then
        error(mainError)
    end

    return checkCount
end

return runTests
