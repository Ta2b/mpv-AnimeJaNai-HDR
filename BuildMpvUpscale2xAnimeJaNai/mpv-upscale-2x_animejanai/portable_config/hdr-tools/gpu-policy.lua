-- Shared hardware policy. Selection/planning functions do not change MPV.
local M = {}

function M.is_linux(mp) return mp.get_property('platform') == 'linux' end

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
    local o = {mode='follow',amd_mode='follow',windows_hdr='',diagnostic=false,max_attempts=3,idle_restore_seconds=2,
        vsr='auto',target_resolution='auto',frame_generation='off',gpu_vendor='auto',hdr_conversion=true,hdr_backend='auto',
        -- One display description. Empty shared keys allow older per-GPU files to work.
        display_peak='',display_gamut='',display_oled='',
        peak_nvidia='auto',peak_amd='auto',gamut_nvidia='auto',gamut_amd='auto',
        oled_nvidia='no',oled_amd='no',
        -- HDR grade shared by every GPU; *_rtx values apply on top of TrueHDR.
        grade=true,paper_white=203,shadows=0.15,highlights=0.50,highlights_rtx=0.25,
        vibrance=0.15,vibrance_rtx=0.10,grade_native_hdr=false,subtitle_white=200,
        -- RIFE output rate matched to the display refresh (factor p/q, at most rife_max_factor).
        rife_display_sync=false,rife_max_factor=2,
        -- Vulkan output (NVIDIA): RTX Video runs inside the engine instead of D3D11 filters.
        render_api='d3d11',rtx_vsr_quality=2,rtx_contrast=100,rtx_saturation=100,rtx_middle_gray=50,
        -- Vulkan engine: a frame identical to the last processed one reuses its result.
        skip_held_frames=true,held_threshold=0.40,
        -- One HDR look: when MPV converts, it follows RTX TrueHDR's curve with the same
        -- rtx_contrast / rtx_saturation / rtx_middle_gray. mpv_contrast, mpv_saturation and
        -- mpv_middle_gray are retired: still accepted in old files, no longer used.
        mpv_truehdr_look=true,mpv_contrast=100,mpv_saturation=100,mpv_middle_gray=50,
        linux_hdr_output='auto'}
    require('mp.options').read_options(o,'animejanai_hdr_auto')
    local warn = require('mp.msg').warn
    local vsr=tostring(o.vsr):lower()
    if vsr=='true' or vsr=='yes' or vsr=='on' then vsr='auto' end
    if vsr=='false' or vsr=='off' then vsr='no' end
    if vsr~='no' and vsr~='auto' and vsr~='nvidia' and vsr~='amd' and vsr~='classic' then
        warn('Invalid vsr='..vsr..'; using auto')
        vsr='auto'
    end
    -- Validate shared settings without filling absent keys: legacy files retain their meaning.
    for _, key in ipairs({'display_peak','display_gamut','display_oled','windows_hdr'}) do
        local value = tostring(o[key]):lower()
        if value ~= '' then
            local valid = key == 'display_peak' and (value == 'auto' or (tonumber(value) and tonumber(value) >= 100 and tonumber(value) <= 10000))
                or key == 'display_gamut' and (value == 'auto' or value == 'display-p3' or value == 'bt.2020')
                or key == 'display_oled' and (value == 'yes' or value == 'no' or value == 'auto')
                or key == 'windows_hdr' and (value == 'follow' or value == 'enable')
            if not valid then
                warn('Invalid '..key..'='..value..'; using default')
                value = key == 'display_oled' and 'no' or key == 'windows_hdr' and 'follow' or 'auto'
            end
        end
        o[key] = value
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
    o.shadows = number(o.shadows, .15, 0, .8)
    o.highlights = number(o.highlights, .50, 0, 1)
    o.highlights_rtx = number(o.highlights_rtx, .25, 0, 1)
    o.vibrance = number(o.vibrance, .15, 0, .8)
    o.vibrance_rtx = number(o.vibrance_rtx, .10, 0, .8)
    o.subtitle_white = number(o.subtitle_white, 200, 80, 1000)
    o.rife_display_sync = bool(o.rife_display_sync)
    o.rife_max_factor = number(o.rife_max_factor, 2, 1, 8)
    o.render_api = tostring(o.render_api):lower() == 'vulkan' and 'vulkan' or 'd3d11'
    o.rtx_vsr_quality = number(o.rtx_vsr_quality, 2, 1, 4)
    o.rtx_contrast = number(o.rtx_contrast, 100, 0, 200)
    o.rtx_saturation = number(o.rtx_saturation, 100, 0, 200)
    o.rtx_middle_gray = number(o.rtx_middle_gray, 50, 10, 100)
    o.skip_held_frames = bool(o.skip_held_frames)
    o.held_threshold = number(o.held_threshold, 0.40, 0, 2)
    o.mpv_truehdr_look = bool(o.mpv_truehdr_look)
    o.linux_hdr_output = o.linux_hdr_output == 'pq' and 'pq' or o.linux_hdr_output == 'sdr' and 'sdr' or 'auto'
    return o
end

-- Vulkan output is the NVIDIA path only: TensorRT frames stay in CUDA up to the VO, and
-- RTX Video runs inside the engine. AMD/Intel always use D3D11 (DirectML).
function M.vulkan(vendor, o)
    return vendor == 'nvidia' and o.render_api == 'vulkan'
end

-- Engine with the RTX Video stage, used only by the Vulkan output. The stock engine and its
-- dispatcher are left as they are, so the D3D11 output and updates are not affected.
M.rtx_engine = '~~/../animejanai/inference/aji_trt_rtx.dll'
-- Call once per script: later configure_filters calls point the filter at that engine when
-- the Vulkan output is selected and the engine is installed.
function M.select_engine(mp, utils, vendor, o)
    M.engine_lib = nil
    if M.is_linux(mp) then return false end
    if not M.vulkan(vendor, o) then return false end
    local needed = {M.rtx_engine, '~~/../animejanai/inference/aji_rtx.dll'}
    for _, path in ipairs(needed) do
        if not utils.file_info(mp.command_native({'expand-path', path})) then return false end
    end
    M.engine_lib = M.rtx_engine
    return true
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
    return {mode=o.windows_hdr and o.windows_hdr ~= '' and o.windows_hdr or (vendor=='nvidia' and o.mode or o.amd_mode)}
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
            if key and section=='global' and key=='backend' then bank.backend=value:lower() end
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

-- Point the aji filter at the GPU's bank. With preload (before a file starts), also set the
-- wanted slot so the filter does not first load the built-in slot baked into the vf line
-- (1002). During playback, slots switch with vf-command instead: no filter rebuild.
function M.configure_filters(list, vendor, conf, slot, preload)
    local output = copy(list)
    local wanted = tostring(M.map_slot(vendor,slot))
    for _, f in ipairs(output) do
        if f.label == 'aji' and f.name == 'animejanai' then
            f.params = f.params or {}
            local lib = M.engine_lib or f.params.lib
            if f.params.conf == conf and f.params.lib == lib
                and (not preload or tostring(f.params.slot) == wanted) then return list, false end
            f.params.conf = conf
            f.params.lib = lib
            f.params.slot = wanted
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

local function read_file(path)
    local f = path and io.open(path, 'rb')
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

local function powershell(mp, script, extra)
    local args = {'powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
        '-File', mp.command_native({'expand-path','~~/hdr-tools/'..script})}
    for _, a in ipairs(extra or {}) do args[#args+1] = a end
    return {name='subprocess', playback_only=false, capture_stdout=true, capture_stderr=true, args=args}
end

-- Startup cost: each PowerShell launch takes roughly half a second. Both are skipped in the
-- common case: the GPU is cached per computer (verified in the background), and the bank
-- script only runs when there is something to synchronize.
function M.detect(mp, utils, options)
    local cached = mp.get_property_native('user-data/animejanai-hardware')
    if type(cached) == 'table' and cached.vendor then return cached end
    if mp.get_property('platform') == 'darwin' then
        -- macOS: one GPU family, no bank selection; inference is handled by animejanai_mac.lua.
        local hw = {vendor='apple', name='Apple Silicon', platform='macos', backend='coreml'}
        mp.set_property_native('user-data/animejanai-hardware', hw)
        return hw
    end
    if M.is_linux(mp) then
        local helper = mp.command_native({'expand-path','~~/../AnimeJaNaiPlatform'})
        local root = mp.command_native({'expand-path','~~/..'})
        local function call(args)
            local ok,r = pcall(mp.command_native,{name='subprocess',args=args,
                playback_only=false,capture_stdout=true,capture_stderr=true})
            if not ok or type(r)~='table' or r.status~=0 then return nil, type(r)=='table' and r.stderr or tostring(r) end
            return utils.parse_json(r.stdout or '')
        end
        local hw,err = call({helper,'--probe','--root',root,'--vendor',options.gpu_vendor})
        hw = hw or {vendor='unknown',name='GPU non detecte',platform='linux'}
        local bank = hw.vendor=='nvidia' and 'linux-nvidia' or 'linux-amd'
        hw.bank = mp.command_native({'expand-path','~~/profiles/'..bank..'/animejanai.conf'})
        local selected,bankerr = call({helper,'--activate-bank',bank,'--root',root})
        local active=mp.command_native({'expand-path','~~/../animejanai/animejanai.conf'})
        hw.bank_conflict = bankerr~=nil
        hw.conf = selected and selected.conf or (read_file(active) and active or hw.bank)
        hw.conf_active = hw.conf
        hw.target = options.target_resolution=='auto' and 'ecran (auto)' or options.target_resolution
        local inference = os.getenv('ANIMEJANAI_INFERENCE_DIR') or
            mp.command_native({'expand-path','~~/../animejanai/inference'})
        hw.inference_dir = inference
        hw.backend = (M.read_bank(hw.conf) or {}).backend or 'tensorrt'
        hw.inference_available = not hw.bank_conflict and hw.backend=='tensorrt' and hw.vendor=='nvidia' and utils.file_info(inference..'/libaji.so')~=nil
            and utils.file_info(inference..'/libnvinfer.so.11')~=nil
            and utils.file_info(inference..'/libaji_trt.so')~=nil and utils.file_info(inference..'/trtexec')~=nil
        if hw.backend=='vulkan' then
            hw.inference_available = not hw.bank_conflict and hw.vulkan_device~=nil and utils.file_info(inference..'/libaji_vulkan.so')~=nil
        end
        if err or bankerr then mp.msg.warn('Linux platform: '..tostring(err or bankerr));mp.osd_message('Banque Linux indisponible ou en conflit : inference desactivee. '..tostring(err or bankerr),8) end
        mp.set_property_native('user-data/animejanai-hardware',hw)
        return hw
    end
    local computer = os.getenv('COMPUTERNAME') or ''
    local cache_path = mp.command_native({'expand-path','~~/cache/animejanai-hardware.json'})
    local disk = utils.parse_json(read_file(cache_path) or '')
    local function remember(hw)
        if hw.vendor ~= 'unknown' and computer ~= '' then
            write_file(cache_path, utils.format_json({computer=computer, vendor=hw.vendor, name=hw.name}))
        end
    end
    local hw
    if options.gpu_vendor == 'auto' and computer ~= '' and type(disk) == 'table'
            and disk.computer == computer and disk.vendor then
        hw = {vendor=disk.vendor, name=disk.name}
        mp.command_native_async(powershell(mp, 'detect-gpu.ps1'), function(ok, result)
            local adapters = ok and type(result) == 'table' and result.status == 0
                and utils.parse_json(result.stdout or '')
            if not adapters then return end
            local now = M.select_gpu(adapters, options.gpu_vendor)
            if now.vendor ~= 'unknown' and (now.vendor ~= hw.vendor or now.name ~= hw.name) then
                remember(now)
                mp.msg.warn('GPU changed: '..tostring(hw.name)..' -> '..tostring(now.name))
                mp.osd_message('Carte graphique changee ('..tostring(now.name)..') : relancer le lecteur', 8)
            end
        end)
    else
        local ok, result = pcall(mp.command_native, powershell(mp, 'detect-gpu.ps1'))
        local adapters = ok and type(result) == 'table' and result.status == 0
            and utils.parse_json(result.stdout or '') or nil
        hw = M.select_gpu(adapters, options.gpu_vendor)
        remember(hw)
    end
    hw.target = options.target_resolution=='auto' and 'ecran (auto)' or options.target_resolution
    local bank = hw.vendor=='nvidia' and 'nvidia' or 'amd'
    hw.bank = mp.command_native({'expand-path','~~/profiles/'..bank..'/animejanai.conf'})
    local active = mp.command_native({'expand-path','~~/../animejanai/animejanai.conf'})
    -- Same test as select-profile-bank.ps1 for "nothing to do": the state names this bank and
    -- both the active copy and the bank still carry the recorded SHA-256.
    local sha256 = dofile(mp.command_native({'expand-path','~~/hdr-tools/sha256.lua'}))
    local state = utils.parse_json(read_file(mp.command_native({'expand-path','~~/profiles/active-bank.json'})) or '')
    local active_data, bank_data = read_file(active), read_file(hw.bank)
    local helper=mp.command_native({'expand-path','~~/../AnimeJaNaiPlatform.exe'})
    local recorded = type(state) == 'table' and (state.bank or state.vendor) == bank and tostring(state.hash or ''):upper()
    if recorded and (state.bank or not utils.file_info(helper)) and active_data and bank_data and sha256(active_data) == recorded and sha256(bank_data) == recorded then
        hw.conf = active
    else
        local command=utils.file_info(helper) and {name='subprocess',args={helper,'--activate-bank',bank},
            playback_only=false,capture_stdout=true,capture_stderr=true}
            or powershell(mp, 'select-profile-bank.ps1', {'-Vendor', bank})
        local activated, activation = pcall(mp.command_native, command)
        local selected = activated and type(activation) == 'table' and activation.status == 0
            and utils.parse_json(activation.stdout or '')
        hw.conf = type(selected) == 'table' and selected.conf or hw.bank
        if hw.conf == hw.bank then
            mp.msg.error('Profile bank activation failed; using bank directly. '..
                tostring(type(activation) == 'table' and activation.stderr or activation))
        end
    end
    mp.set_property_native('user-data/animejanai-hardware', hw)
    if hw.vendor == 'unknown' then
        mp.msg.warn('GPU detection failed; using the portable DirectML path. Set gpu_vendor if needed.')
    end
    return hw
end

return M
