-- Select the inference configuration before the first GPU frame is decoded.
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local rife_sync = dofile(mp.command_native({'expand-path','~~/hdr-tools/rife-sync.lua'}))
local options = policy.options()
local hw = policy.detect(mp,utils,options)

local function read_file(path)
    local f = io.open(path, 'rb')
    if not f then return nil end
    local data = f:read('*a')
    f:close()
    return data
end
local function write_file(path, data)
    local f = io.open(path, 'wb')
    if not f then return false end
    f:write(data)
    f:close()
    return true
end
-- Effective conf of the aji filter: the GPU's bank, or its runtime copy with RIFE factors
-- matched to the display. Shared with animejanai_slot.lua through user-data.
local function set_active_conf(path)
    hw.conf_active = path
    mp.set_property_native('user-data/animejanai-hardware/conf_active', path)
end
set_active_conf(hw.conf)

-- Vulkan output must be chosen before the VO exists; it is not switched during a session.
local vulkan = policy.vulkan(hw.vendor, options)
local function select_api()
    if not vulkan then return end
    mp.set_property('gpu-api','vulkan')
    mp.set_property('gpu-context','winvk')
end
select_api()

local function prepare()
    select_api()
    if hw.vendor ~= 'nvidia' then
        mp.set_property('gpu-api','d3d11')
        mp.set_property('gpu-context','d3d11')
        mp.set_property('hwdec','d3d11va')
        if hw.vendor == 'amd' then mp.set_property('d3d11va-zero-copy','yes') end
        if hw.vendor ~= 'unknown' then mp.set_property('d3d11-adapter',hw.name) end
    end
    -- The slot chosen during this session (Ctrl+0..4) wins over the bank's default slot.
    local bank=policy.read_bank(hw.conf)
    local slot=mp.get_property_native('user-data/animejanai-active-slot') or (bank and bank.default_slot) or 3
    local vf, changed = policy.configure_filters(mp.get_property_native('vf') or {},hw.vendor,hw.conf_active,slot,true)
    if changed then mp.set_property_native('vf',vf) end
end

-- Last known refresh rate, for the first file of a session (no video window yet).
local display_cache = mp.command_native({'expand-path','~~/cache/animejanai-display.json'})
mp.observe_property('display-fps','native',function(_,fps)
    fps=tonumber(fps)
    if fps and fps>20 then write_file(display_cache,utils.format_json({fps=fps})) end
end)

-- get_property_native returns nil plus an error text while a property is unavailable.
local function number(name) return tonumber((mp.get_property_native(name))) end
-- No video track is selected yet in on_preloaded: container-fps is still unavailable there,
-- so read the rate of the first real video track from the demuxer.
local function source_fps()
    local fps=number('container-fps')
    if fps and fps>0 then return fps end
    for _,track in ipairs(mp.get_property_native('track-list') or {}) do
        fps=tonumber(track['demux-fps'])
        if track.type=='video' and not track.albumart and not track.image and fps and fps>0 then return fps end
    end
    return nil
end

-- After the file is opened (frame rate known), before the filters start: RIFE factor p/q so
-- that every interpolated frame stays on screen for the same number of refreshes.
local function match_rife()
    local text=read_file(hw.conf)
    local wanted=hw.conf
    local status
    if not options.rife_display_sync then
        status=nil
    elseif not text then
        status='banque illisible'
    elseif rife_sync.display_rate_match(text) then
        status='frequence automatique d AnimeJaNai active : facteur du profil conserve'
    else
        local source=source_fps()
        local display=number('display-fps')
        if not display then
            local cached=utils.parse_json(read_file(display_cache) or '')
            display=type(cached)=='table' and tonumber(cached.fps) or nil
        end
        local p,q,out,n=rife_sync.choose(source,display,options.rife_max_factor)
        if p then
            local runtime=mp.command_native({'expand-path','~~/../animejanai/animejanai-runtime.conf'})
            local new=rife_sync.rewrite(text,p,q)
            if read_file(runtime)==new or write_file(runtime,new) then wanted=runtime end
            status=string.format('x%d/%d -> %.3f i/s, %d rafraichissement(s) par image a %.3f Hz',p,q,out,n,display)
        else
            status=string.format('aucun facteur exact (source %s i/s, ecran %s Hz, max x%s) : facteur du profil',
                tostring(source),tostring(display),tostring(options.rife_max_factor))
        end
    end
    mp.set_property_native('user-data/animejanai-rife-sync',status)
    set_active_conf(wanted)
    local bank=policy.read_bank(hw.conf)
    local slot=mp.get_property_native('user-data/animejanai-active-slot') or (bank and bank.default_slot) or 3
    local vf,changed=policy.configure_filters(mp.get_property_native('vf') or {},hw.vendor,wanted,slot,true)
    if changed then mp.set_property_native('vf',vf) end
end

mp.add_hook('on_load',-50,prepare)
mp.add_hook('on_preloaded',-50,match_rife)
mp.register_script_message('animejanai-reload-options',function() options=policy.options() end)
-- input.conf owns the keys. Selection delegates to the existing slot controller,
-- which already handles recovery and chooses the correct inference bank.
mp.register_script_message('animejanai-select',function(value)
    local slot=tonumber(value)
    if not slot or slot~=math.floor(slot) or slot<0 or slot>4 then return end
    local bank=policy.read_bank(hw.conf)
    local profile=bank and bank.slots[slot]
    -- A readable bank without this slot (or an untouched "New Profile"): nothing to select.
    if slot>0 and bank and (not profile or not profile.name or profile.name=='New Profile') then
        mp.osd_message('Profil '..slot..' vide dans la banque '..(hw.vendor=='nvidia' and 'NVIDIA' or 'AMD')..' (AnimeJaNai Manager, Ctrl+E)',4)
        return
    end
    mp.commandv('script-message','aji-slot',tostring(slot))
    local label=slot==0 and 'AnimeJaNai desactive' or
        'Profil '..slot..' : '..tostring(profile and profile.name or 'personnalise')
    if slot>0 then
        label=label..' | '..(profile and (profile.rife and 'RIFE configure' or 'cadence originale') or 'interpolation inconnue')
        if options.frame_generation=='amf' and hw.vendor=='amd' then label=label..' + AMD AMF x2' end
    end
    local w,h=policy.target_resolution(options,mp.get_property_native('display-width'),mp.get_property_native('display-height'))
    local target=w and string.format('%dx%d',w,h) or hw.target
    mp.osd_message('Anime : '..target..' | '..label,4)
end)
mp.msg.info('Hardware auto: '..hw.name..' | '..hw.vendor..' | cible '..hw.target)

-- Ctrl+E: the Manager with the display upscaling / HDR settings when it is installed,
-- otherwise the official Manager, with an on-screen hint instead of silently failing.
mp.register_script_message('animejanai-manager',function()
    local custom=mp.command_native({'expand-path','~~/../AnimeJaNaiManager-HDR.exe'})
    local official=mp.command_native({'expand-path','~~/../AnimeJaNaiManager.exe'})
    if utils.file_info(custom) then
        mp.osd_message('Launching AnimeJaNai Manager (HDR)...',3)
        mp.commandv('run',custom)
    elseif utils.file_info(official) then
        mp.osd_message('AnimeJaNaiManager-HDR.exe not found - launching AnimeJaNai Manager...',5)
        mp.commandv('run',official)
    else
        mp.osd_message('AnimeJaNai Manager not found',5)
    end
end)
