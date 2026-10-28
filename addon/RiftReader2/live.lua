local _, privateVars = ...

-- The reader supplies a fresh challenge. No SavedVariables or inferred load IDs.
local Live = {}

function Live.New()
    local sessionId
    local instance = {}

    function instance:CanBind(value)
        if type(value) ~= "string" or #value ~= 32 or string.find(value, "[^0-9a-f]") then
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
        sessionId = value
        return true
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
