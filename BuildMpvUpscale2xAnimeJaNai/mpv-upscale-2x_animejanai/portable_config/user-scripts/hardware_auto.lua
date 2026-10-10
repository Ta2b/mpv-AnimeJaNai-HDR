-- Select the inference configuration before the first GPU frame is decoded.
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local options = policy.options()
local hw = policy.detect(mp,utils,options)

local function prepare()
    if hw.vendor ~= 'nvidia' then
        mp.set_property('gpu-api','d3d11')
        mp.set_property('gpu-context','d3d11')
        mp.set_property('hwdec','d3d11va')
        if hw.vendor == 'amd' then mp.set_property('d3d11va-zero-copy','yes') end
        if hw.vendor ~= 'unknown' then mp.set_property('d3d11-adapter',hw.name) end
    end
    local bank=policy.read_bank(hw.conf)
    local vf, changed = policy.configure_filters(mp.get_property_native('vf') or {},hw.vendor,hw.conf,
        bank and bank.default_slot or 3)
    if changed then mp.set_property_native('vf',vf) end
end

mp.add_hook('on_load',-50,prepare)
-- input.conf owns the keys. Selection delegates to the existing slot controller,
-- which already handles recovery and chooses the correct inference bank.
mp.register_script_message('animejanai-select',function(value)
    local slot=tonumber(value)
    if not slot or slot~=math.floor(slot) or slot<0 or slot>4 then return end
    if slot==4 and hw.vendor~='amd' then
        mp.osd_message('Ctrl+4 : interpolation AMF reservee a AMD',4)
        return
    end
    mp.commandv('script-message','aji-slot',tostring(slot))
    local bank=policy.read_bank(hw.conf)
    local profile=bank and bank.slots[slot]
    local label=slot==0 and 'AnimeJaNai desactive' or
        'Profil '..slot..' : '..tostring(profile and profile.name or 'personnalise')
    if slot>0 then
        label=label..' | '..(slot==4 and 'AMF x2 demande (essai)' or
            (profile and (profile.rife and 'RIFE configure' or 'cadence originale') or 'interpolation inconnue'))
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
