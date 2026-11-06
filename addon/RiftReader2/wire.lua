local _, privateVars = ...

local Wire = {}
privateVars.Wire = Wire

local MAX_EXACT_INTEGER = 9007199254740991
local ROOT_KEYS = {
    schemaVersion = true,
    addonVersion = true,
    sequence = true,
    epoch = true,
    clock = true,
    player = true,
    fields = true
}
local FIELD_KEYS = {
    coordX = true,
    coordY = true,
    coordZ = true,
    health = true,
    healthMax = true,
    combat = true
}

local function isFinite(value)
    return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end

local function isExactInteger(value)
    return isFinite(value) and value >= 1 and value <= MAX_EXACT_INTEGER and value == math.floor(value)
end

local function hasExactKeys(value, expected)
    if type(value) ~= "table" then
        return false
    end
    for key in pairs(value) do
        if expected[key] ~= true then
            return false
        end
    end
    for key in pairs(expected) do
        if rawget(value, key) == nil then
            return false
        end
    end
    return true
end

local function encodeString(value)
    local parts = { "\"" }
    for index = 1, #value do
        local byte = string.byte(value, index)
        if byte == 34 then
            parts[#parts + 1] = "\\\""
        elseif byte == 92 then
            parts[#parts + 1] = "\\\\"
        elseif byte < 32 or byte > 126 then
            return nil, "strings must contain printable ASCII only"
        else
            parts[#parts + 1] = string.char(byte)
        end
    end
    parts[#parts + 1] = "\""
    return table.concat(parts)
end

local function encodeNumber(value)
    if not isFinite(value) then
        return nil, "numbers must be finite"
    end
    if value == 0 then
        return "0"
    end
    -- Seventeen significant digits preserve a binary64 value across JSON replay.
    -- Normalize the decimal separator in case the client inherits a non-C locale.
    return (string.gsub(string.format("%.17g", value), ",", "."))
end

local function encodeInteger(value)
    if not isExactInteger(value) then
        return nil, "counter must be an exact positive integer"
    end
    return string.format("%.0f", value)
end

local function encodeStatus(field, expectedType)
    if type(field) ~= "table" then
        return nil, "field must be an object"
    end
    local status = rawget(field, "status")
    if status == "unavailable" or status == "invalid" then
        if not hasExactKeys(field, { status = true }) then
            return nil, "non-ok field must contain only status"
        end
        return "{\"status\":\"" .. status .. "\"}"
    end
    if status ~= "ok" or not hasExactKeys(field, { status = true, value = true }) then
        return nil, "ok field must contain status and value"
    end
    local value = rawget(field, "value")
    local encoded
    local errorMessage
    if expectedType == "number" then
        encoded, errorMessage = encodeNumber(value)
    elseif expectedType == "boolean" then
        if type(value) ~= "boolean" then
            return nil, "boolean field has the wrong value type"
        end
        encoded = value and "true" or "false"
    elseif expectedType == "player" then
        if type(value) ~= "string" or #value < 1 or #value > 128 then
            return nil, "player identifier is invalid"
        end
        encoded, errorMessage = encodeString(value)
    end
    if not encoded then
        return nil, errorMessage or "field value is invalid"
    end
    return "{\"status\":\"ok\",\"value\":" .. encoded .. "}"
end

function Wire.Encode(observation)
    if not hasExactKeys(observation, ROOT_KEYS) then
        return nil, "observation root does not match schema 1"
    end
    if rawget(observation, "schemaVersion") ~= 1 or rawget(observation, "addonVersion") ~= "0.1.0" then
        return nil, "unsupported observation schema or addon version"
    end

    local sequence, sequenceError = encodeInteger(rawget(observation, "sequence"))
    if not sequence then
        return nil, sequenceError
    end
    local epoch, epochError = encodeInteger(rawget(observation, "epoch"))
    if not epoch then
        return nil, epochError
    end
    local clock, clockError = encodeStatus(rawget(observation, "clock"), "number")
    if not clock then
        return nil, clockError
    end
    local clockField = rawget(observation, "clock")
    if rawget(clockField, "status") == "ok" and rawget(clockField, "value") < 0 then
        return nil, "successful clock must be nonnegative"
    end
    local player, playerError = encodeStatus(rawget(observation, "player"), "player")
    if not player then
        return nil, playerError
    end

    local fields = rawget(observation, "fields")
    if not hasExactKeys(fields, FIELD_KEYS) then
        return nil, "fields do not match schema 1"
    end
    local clockStatus = rawget(rawget(observation, "clock"), "status")
    local playerStatus = rawget(rawget(observation, "player"), "status")
    if clockStatus ~= "ok" and playerStatus ~= "unavailable" then
        return nil, "unsuccessful clock requires unavailable player"
    end
    if clockStatus ~= "ok" or playerStatus ~= "ok" then
        for name in pairs(FIELD_KEYS) do
            local field = rawget(fields, name)
            if type(field) ~= "table" or rawget(field, "status") ~= "unavailable" then
                return nil, "unsuccessful clock or player requires unavailable fields"
            end
        end
    end
    local encodedFields = {}
    local orderedFields = { "coordX", "coordY", "coordZ", "health", "healthMax", "combat" }
    for index, name in ipairs(orderedFields) do
        local expectedType = name == "combat" and "boolean" or "number"
        local encoded, errorMessage = encodeStatus(rawget(fields, name), expectedType)
        if not encoded then
            return nil, name .. ": " .. (errorMessage or "invalid")
        end
        encodedFields[index] = "\"" .. name .. "\":" .. encoded
    end

    local json = "{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":" .. sequence ..
        ",\"epoch\":" .. epoch .. ",\"clock\":" .. clock .. ",\"player\":" .. player ..
        ",\"fields\":{" .. table.concat(encodedFields, ",") .. "}}"
    local frame = "RR2A1|" .. json .. "|ENDRR2A1"
    if #frame > 4096 then
        return nil, "encoded frame exceeds 4096 bytes"
    end
    return frame
end
