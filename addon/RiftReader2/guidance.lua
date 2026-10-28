local _, privateVars = ...

-- A bounded manual information channel. This module never executes game actions.
local Guidance = {}
privateVars.Guidance = Guidance
local MAX_INTEGER = 9007199254740991
local MAX_AGE = 10

local function finite(value)
    return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end

local function number(text, limit)
    if type(text) ~= "string" or #text > 32 or string.find(text, "[^0-9eE+%.%-]") then return nil end
    local value = tonumber(text)
    if not finite(value) or math.abs(value) > limit then return nil end
    return value
end

local function counter(text)
    if type(text) ~= "string" or not string.match(text, "^%d+$") then return nil end
    text = string.gsub(text, "^0+", "")
    if #text == 0 or #text > 16 or (#text == 16 and text > "9007199254740991") then return nil end
    local value = number(text, MAX_INTEGER)
    if not value or value < 1 or value ~= math.floor(value) then return nil end
    return value
end

local function validNonce(value)
    return type(value) == "string" and #value == 32 and not string.find(value, "[^0-9a-f]")
end

local function current(observation, now)
    if not finite(now) or type(observation) ~= "table" or type(observation.clock) ~= "table"
        or observation.clock.status ~= "ok" or not finite(observation.clock.value)
        or now < observation.clock.value or now - observation.clock.value > 1.5
        or type(observation.player) ~= "table" or observation.player.status ~= "ok"
        or type(observation.fields) ~= "table" then return nil end
    for _, value in ipairs({ observation.sequence or false, observation.epoch or false }) do
        if not finite(value) or value < 1 or value > MAX_INTEGER or value ~= math.floor(value) then return nil end
    end
    local values = {}
    for index, name in ipairs({ "coordX", "coordY", "coordZ" }) do
        local field = observation.fields[name]
        if type(field) ~= "table" or field.status ~= "ok" or not finite(field.value)
            or math.abs(field.value) > 10000000 then return nil end
        values[index] = field.value
    end
    return values
end

function Guidance.New()
    local instance = { LastSequence = 0, State = "unbound", Reason = "Bind this addon load to one lab and reader." }

    function instance:Bind(lab, nonce)
        if (lab ~= "lab1" and lab ~= "lab2") or not validNonce(nonce) then
            return false, "Expected bind lab1|lab2 and a 32-character reader nonce."
        end
        if self.Nonce and (self.Nonce ~= nonce or self.Lab ~= lab) then
            return false, "Already bound; reload the UI to change lab or reader."
        end
        if not self.Nonce then
            self.Lab, self.Nonce = lab, nonce
            self.State, self.Reason = "waiting", "No external result received."
        end
        return true, "Bound " .. lab .. "; manual feedback only."
    end

    function instance:Invalidate(reason)
        self.Result = nil
        self.State, self.Reason = "unavailable", reason
    end

    function instance:Status(observation, now)
        if not self.Result then return self.State, self.Reason end
        local result = self.Result
        local position = current(observation, now)
        if not position then
            self:Invalidate("Current addon coordinates or clock unavailable.")
        elseif observation.player.value ~= result.player or observation.epoch ~= result.epoch
            or observation.sequence < result.sourceSequence or observation.clock.value < result.clock then
            self:Invalidate("Player, epoch or sequence changed.")
        elseif now < result.clock or now - result.clock > MAX_AGE then
            self:Invalidate("Source expired; waiting for a new external result.")
        elseif math.abs(position[1] - result.x) > 0.5 or math.abs(position[2] - result.y) > 0.5
            or math.abs(position[3] - result.z) > 0.5 then
            self:Invalidate("Player moved; calculate a new result.")
        end
        return self.State, self.Reason
    end

    function instance:Receive(args, observation, now)
        if type(args) ~= "string" or #args > 512 or string.find(args, "[^ -~]") then
            return false, "Expected at most 512 printable ASCII characters."
        end
        local words = {}
        for word in string.gmatch(args, "%S+") do words[#words + 1] = word end
        if #words ~= 15 or words[1] ~= "result" then return false, "Malformed result." end
        if not self.Nonce or words[2] ~= self.Lab or words[3] ~= self.Nonce then
            return false, "Wrong lab or reader session."
        end
        local sequence, epoch, sourceSequence = counter(words[4]), counter(words[5]), counter(words[6])
        local clock = number(words[7], MAX_INTEGER)
        local player = words[8]
        local x, y, z = number(words[9], 10000000), number(words[10], 10000000), number(words[11], 10000000)
        local distance = number(words[12], 30000000)
        local dx, dz, dy = number(words[13], 20000000), number(words[14], 20000000), number(words[15], 20000000)
        if not sequence or not epoch or not sourceSequence or not clock or clock < 0
            or #player > 128 or not string.match(player, "^[A-Za-z0-9_]+$")
            or not x or not y or not z or not distance or distance < 0 or not dx or not dz or not dy then
            return false, "Invalid bounded result fields."
        end
        if sequence <= self.LastSequence then return false, "Duplicate or out-of-order result." end
        if self.LastSourceSequence and sourceSequence <= self.LastSourceSequence then
            return false, "Source observation did not advance."
        end
        if math.abs(math.sqrt(dx * dx + dz * dz) - distance) > math.max(0.01, distance * 0.000000001) then
            return false, "Distance and direction disagree."
        end
        local position = current(observation, now)
        if not position or player ~= observation.player.value or epoch ~= observation.epoch
            or sourceSequence > observation.sequence or clock > observation.clock.value
            or now < clock or now - clock > MAX_AGE then
            return false, "Source unavailable, expired or from another player/epoch."
        end
        if math.abs(position[1] - x) > 0.5 or math.abs(position[2] - y) > 0.5 or math.abs(position[3] - z) > 0.5 then
            return false, "Source position changed; calculate a new result."
        end
        self.LastSequence, self.LastSourceSequence = sequence, sourceSequence
        self.Result = { sequence = sequence, epoch = epoch, sourceSequence = sourceSequence, clock = clock,
            player = player, x = x, y = y, z = z, distance = distance, dx = dx, dz = dz, dy = dy,
            receivedClock = now, sourceToReceiptSeconds = now - clock }
        self.State, self.Reason = "received", "Calculated externally; manual delivery."
        return true, string.format("Received %s result %d; source age %.3fs.", self.Lab, sequence, now - clock)
    end

    function instance:Text(observation, now)
        self:Status(observation, now)
        if not self.Result then return "RR2 GUIDANCE  " .. string.upper(self.State) .. "\n" .. self.Reason end
        local r = self.Result
        return string.format("RR2 GUIDANCE  %s  RESULT %d\nPlanar distance %.2f   dX %+.2f   dZ %+.2f\nVertical dY %+.2f   source age %.1fs\nEXTERNAL CALCULATION / MANUAL DELIVERY", self.Lab, r.sequence,
            r.distance, r.dx, r.dz, r.dy, now - r.clock)
    end

    return instance
end
