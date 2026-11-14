local addonInfo, private = ...
local owner = addonInfo.identifier or addonInfo.Identifier or (addonInfo.toc and addonInfo.toc.Identifier)
assert(type(owner)=="string" and owner~="", "NPC survey requires the loading addon's identifier")
local nonce, epoch, sequence, ids, lastTime, selfId
local visibleMode,page
epoch=0
local ring={}
RiftReader2NpcSurveyFrames=ring

local function unit(value)
    if type(value)=="string" and #value==17 and value:match("^u%x+$") then
        return "u"..value:sub(2):upper()
    end
end
local function finite(value)
    return type(value)=="number" and value==value and math.abs(value)<math.huge
end
local function quote(value)
    local s=value:gsub('[%z\1-\31\\"]', function(c)
        if c=='"' or c=='\\' then return "\\"..c end
        return string.format("\\u%04X",c:byte())
    end)
    return '"'..s..'"'
end
local function jsonObject(values)
    local parts={}
    for key,v in pairs(values) do
        local raw
        if type(v)=="string" then raw=quote(v)
        elseif type(v)=="boolean" or finite(v) then raw=tostring(v)
        elseif type(v)=="table" then raw=jsonObject(v) end
        if raw then parts[#parts+1]=quote(key)..":"..raw end
    end
    table.sort(parts)
    return "{"..table.concat(parts,",").."}"
end
local function clear()
    nonce,ids,selfId,lastTime,visibleMode,page=nil,nil,nil,nil,false,1
    for i=1,8 do ring[i]=nil end
    RiftReader2NpcSurveyWire=nil
end
local function command(arg)
    if arg=="clear" then clear(); return true,"cleared" end
    if arg=="status" then return true,nonce and ("bound; sequence "..sequence) or "unbound" end
    if type(arg)~="string" or #arg>270 then return false,"invalid survey command" end
    local requestedPage=arg:match("^%s*page%s+(%d+)%s*$")
    if requestedPage and nonce and visibleMode then
        local number=tonumber(requestedPage)
        if number<1 or number>342 then return false,"invalid survey page" end
        page=number; return true,"requested page "..page
    end
    local n,list=arg:match("^%s*bind%s+([0-9a-f]+)%s+(%S+)%s*$")
    if not n or #n~=32 then return false,"use bind NONCE UNIT[,UNIT...], status or clear" end
    local selected,seen={},{}
    for token in (list~="visible" and list.."," or ""):gmatch("([^,]*),") do
        local id=unit(token)
        if not id or seen[id] or #selected>=12 then return false,"expected 1 to 12 distinct unit IDs" end
        selected[#selected+1]=id; seen[id]=true
    end
    if n==nonce then return false,"use a new nonce for each survey" end
    clear()
    nonce,ids,epoch,sequence=n,selected,epoch+1,0
    visibleMode=list=="visible"
    return true,visibleMode and "bound visible units; page 1" or "bound "..#ids.." units"
end
local function visibleUnits()
    local ok,list=pcall(Inspect.Unit.List)
    if not ok or type(list)~="table" then return nil end
    local keys,byId={},{}
    for key in pairs(list) do
        local id=unit(key)
        if not id or byId[id] or #keys>=4096 then return nil end
        keys[#keys+1]=id; byId[id]=true
    end
    table.sort(keys)
    return keys,byId
end
local function sample(id)
    local ok,detail=pcall(Inspect.Unit.Detail,id)
    if not ok or type(detail)~="table" then return {status="unavailable"} end
    if unit(detail.id)~=id then return {status="identity-mismatch"} end
    local row={status="observed",id=id}
    for _,key in ipairs({"name","relation","alliance","zone","type"}) do
        local v=detail[key]
        if type(v)=="string" and #v>0 and #v<=128 and not v:find("[%z\1-\31]") then row[key]=v end
    end
    for _,key in ipairs({"level","coordX","coordY","coordZ","health","healthMax"}) do
        if finite(detail[key]) then row[key]=detail[key] end
    end
    for _,key in ipairs({"player","combat"}) do
        if type(detail[key])=="boolean" then row[key]=detail[key] end
    end
    local availability=detail.availability
    if finite(availability) or type(availability)=="boolean" or
            (type(availability)=="string" and #availability>0 and #availability<=128
             and not availability:find("[%z\1-\31]")) then row.availability=availability end
    if type(detail.attackable)=="boolean" then row.rawAttackable=detail.attackable end
    return row
end
local function update()
    if not nonce then return end
    local ok,t=pcall(Inspect.Time.Frame)
    if not ok or not finite(t) or t<0 or (lastTime and t<lastTime) then clear(); return end
    if lastTime and t-lastTime<.25 then return end
    local pok,p=pcall(Inspect.Unit.Lookup,"player")
    p=unit(p)
    if not pok or not p or (selfId and selfId~=p) then clear(); return end
    local before,seenBefore=visibleUnits()
    local selected=ids
    if visibleMode then
        selected={}
        if before then
            for i=(page-1)*12+1,math.min(page*12,#before) do selected[#selected+1]=before[i] end
        end
    end
    local rows={}
    for _,id in ipairs(selected) do
        if not visibleMode or (seenBefore and seenBefore[id]) then rows[id]=sample(id)
        else rows[id]={status=before and "not-visible" or "visibility-unavailable"} end
    end
    local after,seenAfter=visibleUnits()
    local stable=before and after and #before==#after
    if stable then
        for i,id in ipairs(before) do if id~=after[i] then stable=false; break end end
    end
    for _,id in ipairs(selected) do
        if visibleMode then
            if not seenAfter then rows[id]={status="visibility-unavailable"}
            elseif seenBefore and seenBefore[id] and not seenAfter[id] then rows[id]={status="visibility-changed"} end
        end
        if before then rows[id].visibleBefore=seenBefore[id]==true end
        if after then rows[id].visibleAfter=seenAfter[id]==true end
    end
    local stillOk,stillP=pcall(Inspect.Unit.Lookup,"player")
    if not stillOk or unit(stillP)~=p then clear(); return end
    sequence=sequence+1; selfId=p; lastTime=t
    local frame={schemaVersion=1,addon="RiftReader2NpcSurvey",addonVersion="0.1.0",
        source="Inspect.Unit.Detail",sessionId=nonce,epoch=epoch,sequence=sequence,
        frameTime=t,playerId=p,units=rows,status=(not visibleMode or (before and after)) and "observed" or "visibility-unavailable",
        selectionScope=visibleMode and "specifier-tree-page" or "explicit-native-id-detail",
        mode=visibleMode and "visible" or "explicit",page=visibleMode and page or nil,
        beforeCount=before and #before,afterCount=after and #after,keysetStable=stable}
    local wire="RR2NPC1|"..jsonObject(frame).."|ENDRR2NPC1"
    if #wire>8192 then
        frame.status="oversized"
        for _,id in ipairs(ids) do rows[id]={status="unavailable"} end
        wire="RR2NPC1|"..jsonObject(frame).."|ENDRR2NPC1"
    end
    ring[(sequence-1)%8+1]=wire
    RiftReader2NpcSurveyWire=wire
end
private.Command=command
local slash=Command.Slash.Register("rr2survey")
table.insert(slash,{function(a,b)
    local _,message=command(type(b)=="string" and b or a)
    Command.Console.Display("general",false,"RR2 NPC survey: "..message,false)
end,owner,"Read explicit unit details"})
Command.Event.Attach(Event.System.Update.Begin,update,owner.." NPC survey")
