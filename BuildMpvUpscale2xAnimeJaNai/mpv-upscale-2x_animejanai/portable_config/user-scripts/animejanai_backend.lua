-- Run the updated official backend inside this client, with the GPU-selected
-- configuration path. This retains upstream fixes and new backend features.
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local hardware = policy.detect(mp,utils,policy.options())
if policy.is_linux(mp) then return end -- Linux must never fall back to DirectML or NVDEC on AMD.
local official = mp.command_native({'expand-path','~~/scripts/animejanai_backend.lua'})

local adapted = setmetatable({command_native=function(command,...)
    if type(command)=='table' and command[1]=='expand-path'
            and command[2]=='~~/../animejanai/animejanai.conf' then
        return hardware.conf
    end
    return mp.command_native(command,...)
end},{__index=mp})

-- require() is local to this script's Lua state. Restore it after loading;
-- the official backend keeps its own local reference to the adapted API.
local previous = package.loaded['mp']
package.loaded['mp'] = adapted
local ok,err = pcall(dofile,official)
package.loaded['mp'] = previous
if not ok then error('Official AnimeJaNai backend failed: '..tostring(err)) end
