-- Fullscreen HDR brightness workaround; see mpv-player/mpv#16053.
-- A native 2x2 corner window keeps the video covered without taking focus.
local mp = require 'mp'
local utils = require 'mp.utils'
local opts = {enabled=true}
require('mp.options').read_options(opts, 'hdr_composition_guard')
local job
local generation=0

local function stop()
    generation=generation+1
    if job then local old=job; job=nil; mp.abort_async_command(old) end
end
local function start()
    if not opts.enabled or job then return end
    -- This workaround belongs to the NVIDIA presentation path.
    if mp.get_property_native('user-data/animejanai-hardware/vendor') ~= 'nvidia' then return end
    generation=generation+1
    local current=generation
    job=mp.command_native_async({name='subprocess', playback_only=false,
        args={mp.command_native({'expand-path','~~/hdr-tools/hdr-composition-guard.exe'}),
              tostring(utils.getpid())}}, function(success,result,error)
        if current~=generation then return end
        job=nil
        if not success or (result and result.status~=0) then
            mp.msg.warn('HDR composition helper stopped: '..tostring(error or (result and result.error_string)))
        end
    end)
end
mp.register_event('file-loaded',start)
mp.register_event('end-file',stop)
mp.register_event('shutdown',stop)
