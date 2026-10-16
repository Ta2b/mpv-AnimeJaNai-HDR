-- Shared playback control; holds are opt-in, scoped to one media generation.
local mp = require 'mp'
local State = dofile(mp.command_native({'expand-path','~~/hdr-tools/playback-state.lua'}))
local control=State.new({
    get_pause=function() return mp.get_property_bool('pause',false) end,
    set_pause=function(value) mp.set_property_bool('pause',value) end,
    publish=function(value) mp.set_property_native('user-data/animejanai-playback',value) end,
})
local function generation(value)
    if value==nil or value=='' then return control.generation end
    return tonumber(value)
end
mp.observe_property('pause','bool',function(_,value) control:observe_pause(value) end)
mp.observe_property('seeking','bool',function(_,value) control:seek(value or false) end)
mp.register_event('start-file',function() control:start_file() end)
mp.register_event('file-loaded',function() control:file_loaded() end)
mp.register_event('end-file',function(e)
    control:end_file(e.reason=='error' and (e.error or 'reader-error') or nil)
end)
mp.register_script_message('aji-playback-hold',function(owner,kind,epoch,blocking)
    if owner then control:hold(owner,kind,generation(epoch),blocking~='no') end
end)
mp.register_script_message('aji-playback-release',function(owner,epoch)
    if owner then control:release(owner,generation(epoch)) end
end)
mp.register_script_message('aji-playback-error',function(owner,reason,epoch)
    if owner then control:fail(owner,reason or 'preparation-error',generation(epoch)) end
end)
local function user_pause(value)
    if value=='toggle' or not value then
        control:user_pause(not mp.get_property_bool('pause',false))
    elseif value=='yes' or value=='true' then control:user_pause(true)
    elseif value=='no' or value=='false' then control:user_pause(false) end
end
mp.register_script_message('aji-playback-user-pause',user_pause)
mp.add_key_binding(nil,'user-pause',function() user_pause('toggle') end)
control:publish()
