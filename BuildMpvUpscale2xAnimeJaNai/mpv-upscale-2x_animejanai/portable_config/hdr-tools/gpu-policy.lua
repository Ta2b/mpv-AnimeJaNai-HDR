-- Shared hardware policy. Selection/planning functions do not change MPV.
local M = {}

local function bool(v)
    if type(v) == 'boolean' then return v end
    v = tostring(v):lower()
    return v == 'yes' or v == 'true' or v == '1' or v == 'on'
end

local function number(v, default, lo, hi)
    local n = tonumber(v)
    if not n or n ~= n then return default end
    return math.max(lo, math.min(hi, n))
end

function M.options()
    local o = {mode='follow',amd_mode='enable',diagnostic=true,max_attempts=3,idle_restore_seconds=2,
        vsr='auto',target_resolution='auto',frame_generation='off',gpu_vendor='auto',hdr_conversion=true,hdr_backend='auto',
        -- Display description, per GPU: *_nvidia = this PC, *_amd = AMD/Intel PC.
        peak_nvidia='1000',peak_amd='auto',gamut_nvidia='display-p3',gamut_amd='display-p3',
        oled_nvidia='yes',oled_amd='auto',
        -- HDR grade shared by every GPU; *_rtx values apply on top of TrueHDR.
        grade=true,paper_white=203,shadows=0.30,highlights=0.85,highlights_rtx=0.50,
        vibrance=0.30,vibrance_rtx=0.20,grade_native_hdr=false}
    require('mp.options').read_options(o,'animejanai_hdr_auto')
    local warn = require('mp.msg').warn
    local vsr=tostring(o.vsr):lower()
    if vsr=='true' or vsr=='yes' or vsr=='on' then vsr='auto' end
    if vsr=='false' or vsr=='off' then vsr='no' end
    if vsr~='no' and vsr~='auto' and vsr~='nvidia' and vsr~='amd' and vsr~='classic' then
        warn('Invalid vsr='..vsr..'; using auto')
        vsr='auto'
    end
    o.vsr=vsr
    o.hdr_backend = tostring(o.hdr_backend):lower()
    if o.hdr_backend ~= 'auto' and o.hdr_backend ~= 'rtx' and o.hdr_backend ~= 'mpv' then
        warn('Invalid hdr_backend='..o.hdr_backend..'; using auto')
        o.hdr_backend = 'auto'
    end
    o.gpu_vendor = tostring(o.gpu_vendor):lower()
    if o.gpu_vendor ~= 'auto' and o.gpu_vendor ~= 'nvidia' and o.gpu_vendor ~= 'amd' and o.gpu_vendor ~= 'intel' then
        o.gpu_vendor = 'auto'
    end
    o.target_resolution=tostring(o.target_resolution):lower():gsub('%s','')
    if o.target_resolution~='auto' then
        local w,h=o.target_resolution:match('^(%d+)x(%d+)$')
        w,h=tonumber(w),tonumber(h)
        if not w or not h or w<2 or h<2 or w>32768 or h>32768 then
            warn('Invalid target_resolution='..o.target_resolution..'; using auto')
            o.target_resolution='auto'
        end
    end
    for _, gpu in ipairs({'nvidia','amd'}) do
        local peak = tostring(o['peak_'..gpu]):lower()
        if peak ~= 'auto' and not tonumber(peak) then warn('Invalid peak_'..gpu..'='..peak..'; using auto'); peak = 'auto' end
        o['peak_'..gpu] = peak
        local gamut = tostring(o['gamut_'..gpu]):lower()
        if gamut ~= 'auto' and gamut ~= 'display-p3' and gamut ~= 'bt.2020' then
            warn('Invalid gamut_'..gpu..'='..gamut..'; using auto'); gamut = 'auto'
        end
        o['gamut_'..gpu] = gamut
        local oled = tostring(o['oled_'..gpu]):lower()
        o['oled_'..gpu] = (oled == 'yes' or oled == 'no') and oled or 'auto'
    end
    o.frame_generation = tostring(o.frame_generation):lower() == 'amf' and 'amf' or 'off'
    o.hdr_conversion = bool(o.hdr_conversion)
    o.grade = bool(o.grade)
    o.grade_native_hdr = bool(o.grade_native_hdr)
    o.paper_white = number(o.paper_white, 203, 80, 400)
    o.shadows = number(o.shadows, .30, 0, .8)
    o.highlights = number(o.highlights, .85, 0, 1)
    o.highlights_rtx = number(o.highlights_rtx, .50, 0, 1)
    o.vibrance = number(o.vibrance, .30, 0, .8)
    o.vibrance_rtx = number(o.vibrance_rtx, .20, 0, .8)
    return o
end

function M.select_gpu(adapters, override)
    local chosen, best = nil, -1
    for _, a in ipairs(adapters or {}) do
        local name, id = tostring(a.Name or ''), tostring(a.PNPDeviceID or ''):upper()
        local vendor = id:find('VEN_10DE',1,true) and 'nvidia'
            or id:find('VEN_1002',1,true) and 'amd'
            or id:find('VEN_8086',1,true) and 'intel'
        if vendor and (not a.Status or a.Status == 'OK') then
            local lower = name:lower()
            local discrete = lower:find('geforce',1,true) or lower:find('radeon rx',1,true)
                or lower:find('arc',1,true) or lower:find('quadro',1,true)
            local score = (discrete and 100 or 0) + (vendor == 'nvidia' and 1 or 0)
            if override and override ~= 'auto' and vendor == override then score = score + 1000 end
            if score > best then
                chosen, best = {vendor=vendor,name=name}, score
            end
        end
    end
    chosen = chosen or {vendor='unknown',name='GPU non detecte'}
    if override and override ~= 'auto' then chosen.vendor = override end
    return chosen
end

function M.settings(vendor, o)
    return {mode=vendor=='nvidia' and o.mode or o.amd_mode}
end

function M.upscaler(vendor, requested)
    if requested=='no' or requested=='classic' then return requested end
    if requested=='auto' then
        return (vendor=='nvidia' or vendor=='amd') and vendor or 'classic'
    end
    return requested==vendor and requested or 'classic'
end

function M.target_resolution(o, display_width, display_height)
    local w,h=display_width,display_height
    if o.target_resolution~='auto' then w,h=o.target_resolution:match('^(%d+)x(%d+)$') end
    w,h=tonumber(w),tonumber(h)
    if not w or not h or w~=w or h~=h or w<2 or h<2 or w>32768 or h>32768 then return nil end
    return math.floor(w),math.floor(h)
end

function M.map_slot(vendor, slot)
    slot = tonumber(slot) or 2
    if vendor ~= 'nvidia' then
        if slot == 1001 or slot == 1002 then return 2 end
        if slot == 1003 then return 1 end
    end
    return slot
end

function M.upscale_profile(vendor)
    return vendor == 'nvidia' and 'upscale-on' or 'upscale-on-amd'
end

-- Read the editable bank, rather than guessing interpolation from a slot number.
function M.read_bank(conf)
    local f=conf and io.open(conf,'r')
    if not f then return nil end
    local bank={slots={}}
    local section,profile
    for line in f:lines() do
        local sec=line:match('^%s*%[([^%]]+)%]')
        if sec then
            section=sec
            local slot=tonumber(sec:match('^slot_(%d+)$'))
            profile=slot and {rife=false} or nil
            if profile then bank.slots[slot]=profile end
        else
            local key,value=line:match('^%s*([^=%s]+)%s*=%s*(.-)%s*$')
            if key and section=='global' and key=='default_slot' then bank.default_slot=tonumber(value) end
            if key and profile then
                if key=='profile_name' then profile.name=value end
                if key:match('^chain_%d+_rife$') then
                    local v=value:lower()
                    if v=='yes' or v=='true' or v=='1' then profile.rife=true end
                end
            end
        end
    end
    f:close()
    return bank
end

function M.scale_factor(vendor,w,h,width,height)
    local factor = math.min(width/w,height/h)
    return vendor == 'nvidia' and math.max(1,factor) or factor
end

local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}
    for k, v in pairs(value) do out[k] = copy(v) end
    return out
end

function M.configure_filters(list, vendor, conf, slot)
    local output = copy(list)
    for _, f in ipairs(output) do
        if f.label == 'aji' and f.name == 'animejanai' then
            f.params = f.params or {}
            if f.params.conf == conf then return list, false end
            f.params.conf = conf
            f.params.slot = tostring(M.map_slot(vendor,slot))
            return output, true
        end
    end
    return list, false
end

function M.hdr_backend(vendor, requested, conversion)
    if conversion == false then return 'none' end
    if requested == 'mpv' then return 'mpv' end
    -- RTX requires NVIDIA; auto and unsupported RTX requests use MPV HDR.
    return vendor == 'nvidia' and 'rtx' or 'mpv'
end

function M.detect(mp, utils, options)
    local cached = mp.get_property_native('user-data/animejanai-hardware')
    if type(cached) == 'table' and cached.vendor then return cached end
    local ok, result = pcall(mp.command_native,{name='subprocess',playback_only=false,
        capture_stdout=true,capture_stderr=true,args={
            'powershell.exe','-NoLogo','-NoProfile','-NonInteractive',
            '-ExecutionPolicy','Bypass','-File',
            mp.command_native({'expand-path','~~/hdr-tools/detect-gpu.ps1'})}})
    local adapters = ok and type(result) == 'table' and result.status == 0 and utils.parse_json(result.stdout or '') or nil
    local hw = M.select_gpu(adapters,options.gpu_vendor)
    hw.target = options.target_resolution=='auto' and 'ecran (auto)' or options.target_resolution
    local bank=hw.vendor=='nvidia' and 'nvidia' or 'amd'
    hw.bank=mp.command_native({'expand-path','~~/profiles/'..bank..'/animejanai.conf'})
    local activated, activation=pcall(mp.command_native,{name='subprocess',playback_only=false,
        capture_stdout=true,capture_stderr=true,args={
            'powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
            mp.command_native({'expand-path','~~/hdr-tools/select-profile-bank.ps1'}),'-Vendor',bank}})
    local selected=activated and type(activation)=='table' and activation.status==0
        and utils.parse_json(activation.stdout or '')
    hw.conf=type(selected)=='table' and selected.conf or hw.bank
    if hw.conf==hw.bank then
        mp.msg.error('Profile bank activation failed; using bank directly. '..
            tostring(type(activation)=='table' and activation.stderr or activation))
    end
    mp.set_property_native('user-data/animejanai-hardware',hw)
    if hw.vendor == 'unknown' then
        mp.msg.warn('GPU detection failed; using the portable DirectML path. Set gpu_vendor if needed.')
    end
    return hw
end

return M
