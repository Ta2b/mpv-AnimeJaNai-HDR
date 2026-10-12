-- User-owned entry point. The updater can refresh scripts/ without replacing
-- our runtime in user-scripts/. Keep each script in its own MPV client.
local mp = require 'mp'
local utils = require 'mp.utils'
local root = mp.command_native({'expand-path','~~/'})
local personal_dir = utils.join_path(root,'user-scripts')
local official_dir = utils.join_path(root,'scripts')
local linux = mp.get_property('platform') == 'linux'

-- Retired scripts. An update does not delete files, so an older copy can still be there.
local retired = {['hdr_composition_guard.lua']=true}

local function discover(dir)
    local entries = {}
    for _,name in ipairs(utils.readdir(dir) or {}) do
        if name:sub(1,1) ~= '.' and not retired[name:lower()] then
            local path = utils.join_path(dir,name)
            local info = utils.file_info(path)
            local ext = name:lower():match('%.([^%.]+)$')
            local supported = info and not info.is_dir and
                (ext == 'lua' or ext == 'js' or (ext == 'dll' and not linux))
            if info and info.is_dir then
                supported = utils.file_info(utils.join_path(path,'main.lua')) ~= nil or
                    utils.file_info(utils.join_path(path,'main.js')) ~= nil
            end
            if supported then entries[#entries+1] = {name=name,path=path} end
        end
    end
    table.sort(entries,function(a,b) return a.name:lower() < b.name:lower() end)
    return entries
end

local personal = discover(personal_dir)
local overrides = {}
for _,entry in ipairs(personal) do overrides[entry.name:lower()] = true end
local required={'animejanai_backend.lua','animejanai_slot.lua','hardware_auto.lua','animejanai_hdr_auto.lua'}
if not linux then required[#required+1]='display-info.dll' end
for _,name in ipairs(required) do
    if not overrides[name] then
        mp.msg.error('Missing personal runtime: user-scripts/'..name)
        mp.osd_message('Configuration incomplete : user-scripts/'..name..' absent',10)
        return
    end
end

-- Detect the GPU and activate its profile bank once, before the scripts start
-- in parallel: they all read the cached user-data/animejanai-hardware.
local policy = dofile(utils.join_path(root,'hdr-tools/gpu-policy.lua'))
policy.detect(mp,utils,policy.options())

local loaded, replaced = {}, {}
local function start(entry)
    local ok,result = pcall(mp.commandv,'load-script',entry.path)
    if not ok or not result then
        mp.msg.error('Cannot load '..entry.path..': '..tostring(result))
        return false
    end
    loaded[#loaded+1] = entry.name
    return true
end

-- MPV waits for script initialization before the first file. load-script
-- preserves client names, so existing script-message-to shortcuts still work.
local successful = true
for _,entry in ipairs(personal) do if not start(entry) then successful=false end end
for _,entry in ipairs(discover(official_dir)) do
    if overrides[entry.name:lower()] then
        replaced[#replaced+1] = entry.name
    elseif not start(entry) then
        successful=false
    end
end
mp.set_property_native('user-data/animejanai-user-runtime',
    {loaded=loaded,overrides=replaced,started=successful})
mp.msg.info(string.format('User runtime: %d scripts; %d official controllers overridden',#loaded,#replaced))
