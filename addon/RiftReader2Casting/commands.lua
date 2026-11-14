-- Shared, versioned command service for RR2 Casting.
-- This module configures/readies existing diagnostics only. It never activates
-- a restricted frame, sends a cast, or creates a second STOP mechanism.
local _, private = ...
local Commands = {}
private.CastingCommands = Commands

local SCHEMA_VERSION, SERVICE_VERSION = 1, "1.0.0"
local MAX_TEXT, MAX_ID, MAX_ARGS, MAX_PAGE_SIZE, MAX_ABILITIES = 512, 128, 10, 25, 1024
local SURVIVAL_ACTIONS = {setup=true, slot=true, status=true, clear=true}

local function text(value, maximum, allowSpace)
    if type(value) ~= "string" or #value == 0 or #value > maximum or
            string.find(value, "[%z\1-\31\127]") then return nil end
    if not allowSpace and string.find(value, "%s") then return nil end
    return value
end

local function integer(value, minimum, maximum)
    return type(value) == "number" and value == math.floor(value) and
        value >= minimum and value <= maximum and value or nil
end

local function safeCopy(value, depth, budget, seen)
    local kind = type(value)
    if kind == "nil" or kind == "boolean" then return value, true end
    if kind == "number" then
        if value == value and math.abs(value) < math.huge then return value, true end
        return nil, false
    end
    if kind == "string" then
        local result = text(value, 2048, true)
        return result, result ~= nil
    end
    if kind ~= "table" or depth <= 0 or seen[value] then return nil, false end
    seen[value] = true
    local result, count = {}, 0
    for key, item in pairs(value) do
        count = count + 1; budget.remaining = budget.remaining - 1
        if count > 128 or budget.remaining < 0 then seen[value] = nil; return nil, false end
        local keyType = type(key)
        if (keyType == "string" and text(key, 128, true)) or
                (keyType == "number" and integer(key, 1, 4096)) then
            local copied, ok = safeCopy(item, depth - 1, budget, seen)
            if not ok then seen[value] = nil; return nil, false end
            result[key] = copied
        else
            seen[value] = nil; return nil, false
        end
    end
    seen[value] = nil
    return result, true
end

local function bounded(value)
    local result, ok = safeCopy(value, 6, {remaining=512}, {})
    return ok and result or nil
end

local function invoke(callbacks, name, ...)
    local callback = callbacks[name]
    if type(callback) ~= "function" then return false, nil, name .. "-unavailable" end
    local ok, first, second = pcall(callback, ...)
    if not ok then return false, nil, name .. "-failed" end
    return true, first, second
end

local function envelope(command, accepted, status, reason, result)
    return {
        schemaVersion=SCHEMA_VERSION, serviceVersion=SERVICE_VERSION, command=command,
        accepted=accepted == true, status=status, reason=reason, result=result,
        gameActionSent=false, effectStatus="not-performed",
        effectQualification="Command acceptance never establishes a cast or gameplay effect.",
    }
end

local function capabilities(callbacks)
    return {
        schemaVersion=SCHEMA_VERSION, serviceVersion=SERVICE_VERSION,
        commands={"capabilities", "status", "list", "select", "record", "trial-status", "survival"},
        survivalActions={"setup", "slot", "status", "clear"},
        limits={maxText=MAX_TEXT, maxAbilityId=MAX_ID, maxArgs=MAX_ARGS,
            maxPageSize=MAX_PAGE_SIZE, maxLearnedAbilities=MAX_ABILITIES},
        callbacks={snapshot=type(callbacks.snapshot)=="function",
            listLearned=type(callbacks.listLearned)=="function",
            selectAbility=type(callbacks.selectAbility)=="function",
            record=type(callbacks.record)=="function",
            trialStatus=type(callbacks.trialStatus)=="function",
            survival=type(callbacks.survival)=="function",
            stopStatus=type(callbacks.stopStatus)=="function"},
        programmaticCast=false, restrictedActivation="protected-frame-activation-required",
        stopControl="existing-callback-status-only",
    }
end

local function callbackView(callbacks, name)
    local called, value, reason = invoke(callbacks, name)
    if not called then return {status="unavailable", reason=reason} end
    if value == nil then return {status="unavailable", reason=reason or name .. "-unavailable"} end
    local copy = bounded(value)
    if copy == nil then return {status="unavailable", reason=name .. "-result-invalid"} end
    return {status="observed", value=copy}
end

local function learnedPage(callbacks, request)
    local page = request.page == nil and 1 or integer(request.page, 1, 128)
    local pageSize = request.pageSize == nil and 8 or integer(request.pageSize, 1, MAX_PAGE_SIZE)
    if not page or not pageSize then return nil, "invalid-page" end
    local called, raw, reason = invoke(callbacks, "listLearned")
    if not called or type(raw) ~= "table" then return nil, reason or "learned-catalog-unavailable" end
    local catalog = {}
    for index, item in ipairs(raw) do
        if index > MAX_ABILITIES or type(item) ~= "table" then return nil, "learned-catalog-invalid" end
        local id = text(item.lookupId or item.id, MAX_ID, false)
        if not id then return nil, "learned-catalog-invalid" end
        local projected = {id=id}
        for _, field in ipairs({"idNew", "name", "target"}) do
            if item[field] ~= nil then
                projected[field] = text(item[field], field == "name" and 256 or MAX_ID, true)
                if not projected[field] then return nil, "learned-catalog-invalid" end
            end
        end
        catalog[#catalog+1] = projected
    end
    local count = #catalog
    local pages = math.max(1, math.ceil(count / pageSize))
    if page > pages then return nil, "page-out-of-range" end
    local entries = {}
    for index=(page-1)*pageSize+1, math.min(page*pageSize, count) do entries[#entries+1] = catalog[index] end
    return {status="observed", count=count, page=page, pages=pages,
        pageSize=pageSize, entries=entries}
end

function Commands.Create(callbacks)
    if type(callbacks) ~= "table" then error("callbacks must be a table") end
    local service = {}
    function service.Execute(request)
        if type(request) ~= "table" or request.schemaVersion ~= SCHEMA_VERSION then
            return envelope("invalid", false, "rejected", "unsupported-request-schema")
        end
        local command = text(request.command, 32, false)
        local requestId = request.requestId == nil and nil or text(request.requestId, 64, false)
        if not command or (request.requestId ~= nil and not requestId) then
            return envelope(command or "invalid", false, "rejected", "invalid-request")
        end
        local response
        if command == "capabilities" then
            response = envelope(command, true, "observed", nil, capabilities(callbacks))
        elseif command == "status" then
            response = envelope(command, true, "observed", nil, {
                state=callbackView(callbacks, "snapshot"), trial=callbackView(callbacks, "trialStatus"),
                stop=callbackView(callbacks, "stopStatus")})
        elseif command == "list" then
            local result, reason = learnedPage(callbacks, request)
            response = result and envelope(command, true, "observed", nil, result) or
                envelope(command, false, "rejected", reason)
        elseif command == "select" then
            local id = text(request.abilityId, MAX_ID, false)
            if not id then response = envelope(command, false, "rejected", "invalid-ability-id")
            else
                local called, accepted, reason = invoke(callbacks, "selectAbility", id)
                if not called then response = envelope(command, false, "rejected", reason)
                elseif accepted == true then response = envelope(command, true, "accepted", nil,
                    {abilityId=id, selectionConfigured=true, castPerformed=false})
                else response = envelope(command, false, "rejected", reason or "ability-selection-refused") end
            end
        elseif command == "record" then
            local called, accepted, reason = invoke(callbacks, "record")
            if not called then response = envelope(command, false, "rejected", reason)
            elseif accepted == true then response = envelope(command, true, "accepted", nil,
                {recordingStarted=true, castPerformed=false})
            else response = envelope(command, false, "rejected", reason or "recording-refused") end
        elseif command == "trial-status" then
            local result = callbackView(callbacks, "trialStatus")
            response = envelope(command, result.status == "observed",
                result.status == "observed" and "observed" or "rejected", result.reason, result)
        elseif command == "survival" then
            local action = text(request.action, 16, false)
            local args = request.args == nil and {} or request.args
            local argCount, argsValid = 0, type(args) == "table"
            if argsValid then
                for key in pairs(args) do
                    if not integer(key, 1, MAX_ARGS) then argsValid=false; break end
                    argCount=argCount+1
                end
                for index=1,argCount do if args[index] == nil then argsValid=false; break end end
            end
            if not action or not SURVIVAL_ACTIONS[action] or not argsValid then
                response = envelope(command, false, "rejected", "invalid-survival-command")
            else
                local safeArgs, valid = {}, true
                for index=1,argCount do
                    local maximum = action == "setup" and index == 2 and MAX_TEXT or MAX_ID
                    safeArgs[index] = text(args[index], maximum, false)
                    if not safeArgs[index] then valid=false; break end
                end
                if not valid then response = envelope(command, false, "rejected", "invalid-survival-arguments")
                else
                    local called, accepted, value = invoke(callbacks, "survival", action, safeArgs)
                    if not called then response = envelope(command, false, "rejected", value)
                    elseif accepted == true then response = envelope(command, true, "accepted", nil,
                        {action=action, message=text(value, 512, true), configurationOnly=true, castPerformed=false})
                    else response = envelope(command, false, "rejected", value or "survival-command-refused") end
                end
            end
        else response = envelope(command, false, "rejected", "unknown-command") end
        response.requestId = requestId
        return response
    end
    function service.Snapshot() return service.Execute({schemaVersion=SCHEMA_VERSION, command="status"}) end
    return service
end

function Commands.DispatchText(service, raw)
    local jsonOutput = type(raw) == "string" and
        string.lower(string.match(raw, "^%s*(%S+)") or "") == "json"
    local function finish(response)
        if jsonOutput then response.outputFormat = "json" end
        return response
    end
    if type(service) ~= "table" or type(service.Execute) ~= "function" or
            type(raw) ~= "string" or #raw > MAX_TEXT or string.find(raw, "[%z\1-\31\127]") then
        return finish(envelope("invalid", false, "rejected", "invalid-command-text"))
    end
    local tokens = {}
    for token in string.gmatch(raw, "%S+") do
        if #tokens >= MAX_ARGS + 2 or #token > MAX_TEXT then
            return finish(envelope("invalid", false, "rejected", "invalid-command-text"))
        end
        tokens[#tokens+1] = token
    end
    if jsonOutput then table.remove(tokens, 1) end
    local command = string.lower(tokens[1] or "status")
    if command == "help" or command == "commands" then command = "capabilities" end
    if command == "abilities" then command = "list" end
    if command == "trial" then command = "trial-status" end
    local request = {schemaVersion=SCHEMA_VERSION, command=command}
    if command == "list" then
        if (tokens[2] and not tonumber(tokens[2])) or (tokens[3] and not tonumber(tokens[3])) then
            return finish(envelope(command, false, "rejected", "invalid-page"))
        end
        request.page, request.pageSize = tonumber(tokens[2]), tonumber(tokens[3])
        if #tokens > 3 then return finish(envelope(command, false, "rejected", "unexpected-arguments")) end
    elseif command == "select" then
        request.abilityId = tokens[2]
        if #tokens ~= 2 then return finish(envelope(command, false, "rejected", "invalid-ability-id")) end
    elseif command == "survival" then
        request.action, request.args = string.lower(tokens[2] or ""), {}
        for index=3,#tokens do request.args[#request.args+1] = tokens[index] end
    elseif #tokens > 1 then return finish(envelope(command, false, "rejected", "unexpected-arguments")) end
    return finish(service.Execute(request))
end

local JSON_ARRAY_FIELDS = {commands=true, survivalActions=true, entries=true}
local function jsonEscape(value)
    local replacements = {['"']='\\"', ['\\']='\\\\', ['\b']='\\b', ['\f']='\\f',
        ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
    return '"' .. string.gsub(value, '[%z\1-\31\\"]', function(character)
        return replacements[character] or string.format('\\u%04x', string.byte(character))
    end) .. '"'
end
local function encodeJson(value, field, depth, budget, seen)
    local kind = type(value)
    if kind == "nil" then return "null" end
    if kind == "boolean" then return value and "true" or "false" end
    if kind == "number" then
        if value ~= value or math.abs(value) == math.huge then return nil, "non-finite-number" end
        return tostring(value)
    end
    if kind == "string" then
        if not text(value, 2048, true) then return nil, "invalid-string" end
        return jsonEscape(value)
    end
    if kind ~= "table" or depth <= 0 or seen[value] then return nil, "invalid-json-value" end
    seen[value] = true
    local numeric, stringKeys, maximum, count = true, {}, 0, 0
    for key in pairs(value) do
        count=count+1; budget.remaining=budget.remaining-1
        if count > 128 or budget.remaining < 0 then seen[value]=nil; return nil,"json-budget" end
        if type(key) == "number" and integer(key,1,4096) then maximum=math.max(maximum,key)
        elseif type(key) == "string" and text(key,128,true) then numeric=false; stringKeys[#stringKeys+1]=key
        else seen[value]=nil; return nil,"invalid-json-key" end
    end
    if numeric and (maximum > 0 or JSON_ARRAY_FIELDS[field]) then
        if maximum ~= count then seen[value]=nil; return nil,"sparse-json-array" end
        local values={}
        for index=1,maximum do
            local encoded,reason=encodeJson(value[index],nil,depth-1,budget,seen)
            if not encoded then seen[value]=nil; return nil,reason end
            values[#values+1]=encoded
        end
        seen[value]=nil; return "["..table.concat(values,",").."]"
    end
    if maximum > 0 then seen[value]=nil; return nil,"mixed-json-table" end
    table.sort(stringKeys)
    local values={}
    for _,key in ipairs(stringKeys) do
        local encoded,reason=encodeJson(value[key],key,depth-1,budget,seen)
        if not encoded then seen[value]=nil; return nil,reason end
        values[#values+1]=jsonEscape(key)..":"..encoded
    end
    seen[value]=nil; return "{"..table.concat(values,",").."}"
end
function Commands.EncodeResponse(response)
    if type(response) ~= "table" then return nil,"response-must-be-table" end
    return encodeJson(response,nil,8,{remaining=1024},{})
end

function Commands.InstallGlobal(service, namespace)
    namespace = namespace or _G
    if type(namespace) ~= "table" or type(service) ~= "table" or
            type(service.Execute) ~= "function" or type(service.Snapshot) ~= "function" then
        return false, "invalid-service"
    end
    local api = {schemaVersion=SCHEMA_VERSION, serviceVersion=SERVICE_VERSION,
        Execute=function(request) return service.Execute(request) end,
        Snapshot=function() return service.Snapshot() end}
    namespace.RiftReader2CastingAPI = api
    return true, api
end

