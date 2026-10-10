-- Slot switching without audio dropouts.
--
-- input.conf used to follow each `vf-command aji slot N` with an
-- unconditional `seek 0 exact` so the on-screen frame refreshes through
-- the newly selected slot. An exact seek flushes the audio pipeline
-- too, which is audible as a dropout on every switch. During playback
-- the new slot takes over within a few frames on its own (the filter
-- swaps chains without leaving the graph), so the refresh-seek is only
-- needed while paused - where audio is silent and the flush inaudible.

local mp = require 'mp'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local selection_generation = 0
local amf_requested = false

local function remove_amf()
    for _,label in ipairs({'amf','amfinput'}) do
        for _,f in ipairs(mp.get_property_native('vf') or {}) do
            if f.label==label then
                local ok,result=pcall(mp.commandv,'vf','remove','@'..label)
                if not ok or not result then return false end
            end
        end
    end
    return true
end

mp.register_script_message('aji-slot', function(slot)
    selection_generation = selection_generation + 1
    local current = selection_generation
    local hw = mp.get_property_native('user-data/animejanai-hardware') or {vendor='nvidia'}
    slot = policy.map_slot(hw.vendor,slot)
    local bank=policy.read_bank(hw.conf)
    local profile=bank and bank.slots[slot]
    if hw.vendor ~= 'nvidia' then
        -- Replace our previous FRC pair before applying the selected profile.
        if not remove_amf() then
            mp.msg.warn('Could not remove the previous AMD FRC; slot change cancelled')
            return
        end
        amf_requested = hw.vendor == 'amd' and slot == 4
        mp.set_property_native('user-data/animejanai-interpolation',
            profile and (profile.rife and 'RIFE configure' or 'cadence originale') or 'interpolation inconnue')
    end
    local vf = mp.get_property_native('vf') or {}
    local found = false
    for _, f in ipairs(vf) do if f.label == 'aji' then found = true end end
    if not found then
        mp.commandv('apply-profile',policy.upscale_profile(hw.vendor))
        vf = mp.get_property_native('vf') or {}
    end
    local prepared, changed = policy.configure_filters(vf,hw.vendor,hw.conf,slot)
    if changed then mp.set_property_native('vf',prepared) end
    local function apply()
        if current ~= selection_generation then return end
        local selected=mp.commandv('vf-command','aji','slot',tostring(slot))
        if not selected then return end
        mp.set_property_native('user-data/animejanai-active-slot',slot)
        if hw.vendor == 'amd' and slot == 4 then
            local native_fps=mp.get_property_native('container-fps')
            local fps=tonumber(native_fps) or 0
            if fps>0 and fps<=31 then
                -- Native MPV AMF filter shares D3D11 textures on the GPU.
                -- Run after AI, so AnimeJaNai processes only source frames.
                local spec='@amf:amf_frc=profile=high:mv-search=native'..
                    ':fallback=no:future-frame=yes:indicator=no'
                -- The native FRC supports P010 but not every AI output format.
                local ok,result=pcall(mp.commandv,'vf','append','@amfinput:d3d11vpp=format=p010')
                if ok and result then ok,result=pcall(mp.commandv,'vf','append',spec) end
                if ok and result then
                    mp.set_property_native('user-data/animejanai-interpolation','AMD AMF x2 : filtre present (essai)')
                else
                    remove_amf()
                    amf_requested=false
                    mp.commandv('script-message','aji-slot','2')
                    mp.msg.warn('AMD AMF insertion failed; returning to the original-cadence preset')
                    mp.osd_message('AMD AMF indisponible ; Ctrl+2 pour la cadence originale',5)
                end
            else
                mp.osd_message('AMD AMF : cadence inconnue ou >31 images/s ; interpolation ignoree',5)
            end
        end
        if mp.get_property_native('pause') then mp.command('no-osd seek 0 exact') end
    end
    if changed or not found then mp.add_timeout(0.1,apply) else apply() end
end)

mp.register_event('end-file',function(event)
    -- FRC format initialization happens after vf append may have succeeded.
    -- Recover the selection for subsequent files; never auto-reload in a loop.
    if event.reason=='error' and amf_requested then
        selection_generation=selection_generation+1
        amf_requested=false
        remove_amf()
        mp.commandv('script-message','aji-slot','2')
        mp.osd_message('Echec du mode AMD AMF ; retour Ctrl+2. Rouvrir la video si necessaire.',8)
        mp.msg.warn('Playback failed with AMD AMF selected; reset to slot 2. Reopen the file if needed.')
    end
end)

mp.register_event('start-file',function()
    selection_generation=selection_generation+1
    local hw=mp.get_property_native('user-data/animejanai-hardware') or {}
    if hw.vendor~='nvidia' then remove_amf() end
end)
