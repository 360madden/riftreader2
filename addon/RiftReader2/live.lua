local _, privateVars = ...

-- The reader supplies a fresh challenge. No SavedVariables or inferred load IDs.
local Live = {}

local function validSessionId(value)
    return type(value) == "string" and #value == 32 and not string.find(value, "[^0-9a-f]")
end

function Live.New()
    local sessionId
    local usedSessionIds = {}
    local instance = {}

    function instance:CanBind(value)
        if not validSessionId(value) then
            return false, "Expected the reader's 32 lowercase hexadecimal characters."
        end
        if sessionId and sessionId ~= value then
            return false, "Already bound. Reload the UI before attaching a new reader."
        end
        return true
    end

    function instance:Bind(value)
        local accepted, reason = self:CanBind(value)
        if not accepted then return false, reason end
        if not sessionId then
            sessionId = value
            usedSessionIds[value] = true
        end
        return true
    end

    function instance:CanRebind(value)
        if not validSessionId(value) then
            return false, "Expected the reader's 32 lowercase hexadecimal characters."
        end
        if not sessionId then
            return false, "Bind a reader before rebinding."
        end
        if sessionId == value then
            return false, "Rebind requires a new reader nonce."
        end
        if usedSessionIds[value] then
            return false, "That reader nonce was already used during this addon load."
        end
        return true
    end

    function instance:Rebind(value)
        local accepted, reason = self:CanRebind(value)
        if not accepted then return false, reason end
        sessionId = value
        usedSessionIds[value] = true
        return true
    end

    function instance:SessionId()
        return sessionId
    end

    function instance:Wrap(frame)
        if not sessionId or type(frame) ~= "string" or #frame > 4096 then
            return nil
        end
        return "RR2L1|" .. sessionId .. "|" .. frame .. "|ENDRR2L1"
    end

    return instance
end

privateVars.Live = Live
