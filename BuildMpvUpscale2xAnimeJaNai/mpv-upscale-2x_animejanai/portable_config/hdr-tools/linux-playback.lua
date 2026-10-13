-- Linux SDR inference: NCNN/Vulkan on AMD/NVIDIA, optional TensorRT on NVIDIA, and the ONNX
-- Runtime engine for the vendor providers: backend=MIGraphX (AMD, ROCm) or OpenVINO (Intel).
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local sync = dofile(mp.command_native({'expand-path','~~/hdr-tools/rife-sync.lua'}))
local options = policy.options()
local hw = policy.detect(mp,utils,options)
local slot,loaded,last_conf,last_default = 0,false,nil,nil
local failed=false
local function path(p) return mp.command_native({'expand-path',p}) end
local function read(p) local f=io.open(p,'rb');if not f then return nil end;local s=f:read('*a');f:close();return s end
local function decoder(mode)
    -- mpv can restart decoding on an option write even when the value is unchanged.
    if mp.get_property('hwdec')~=mode then mp.set_property('hwdec',mode) end
end

mp.set_property('gpu-api','vulkan')
mp.set_property('gpu-context','waylandvk')
if hw.vulkan_device then mp.set_property('vulkan-device',hw.vulkan_device) end
decoder(hw.vendor=='nvidia' and 'nvdec' or 'auto-safe')

-- TrueHDR inside the TensorRT engine: libaji_trt_rtx.so (engine with the final stage) and
-- libaji_rtx.so (NVIDIA Maxine Video Effects, built on the machine that has the SDK). Used when
-- both are installed, the conversion is not forced to mpv and the output is set to PQ.
local rtx = dofile(path('~~/hdr-tools/rtx-stage.lua'))
local grade = dofile(path('~~/hdr-tools/hdr-grade.lua'))
local rtx_conf = path(rtx.file)
local stats_file = path('~~/../animejanai/currentanimejanai.log')
local stage_check
local function stage_wanted()
    return hw.backend=='tensorrt' and hw.vendor=='nvidia' and options.hdr_conversion
        and options.hdr_backend~='mpv' and options.linux_hdr_output=='pq'
        and utils.file_info(hw.inference_dir..'/libaji_trt_rtx.so')~=nil
        and utils.file_info(hw.inference_dir..'/libaji_rtx.so')~=nil
end
-- Writes the settings read by the engine at configure; without the file the stage is off.
local function write_stage(on)
    if not on then os.remove(rtx_conf);return end
    local f=io.open(rtx_conf,'w')
    if not f then return end
    f:write(rtx.text({hdr=true,vsr=false,contrast=options.rtx_contrast,saturation=options.rtx_saturation,
        middle_gray=options.rtx_middle_gray,
        -- display_peak=auto: the peak negotiated with the compositor, as on Windows.
        peak=tonumber(grade.display(options,hw.vendor).peak) or tonumber((mp.get_property_native('video-target-params/max-luma'))) or 1000,
        held=options.skip_held_frames,held_threshold=options.held_threshold}))
    f:close()
end
-- The converted frames are PQ / BT.2020; linux-hdr.lua follows user-data/animejanai-truehdr.
local function tag(list,on)
    for i=#list,1,-1 do if list[i].label=='hdrtag' then table.remove(list,i) end end
    if on then
        for i,f in ipairs(list) do
            if f.label=='aji' then
                table.insert(list,i+1,{name='format',label='hdrtag',enabled=true,params={gamma='pq',primaries='bt.2020'}})
                break
            end
        end
    end
    mp.set_property_native('user-data/animejanai-truehdr',on)
    return list
end
-- The tag follows the request first, then what the engine reports in its stats log.
local function confirm_stage()
    stage_check=nil
    if mp.get_property_native('user-data/animejanai-truehdr')~=true then return end
    if rtx.applied(read(stats_file) or '').hdr then return end
    mp.set_property_native('vf',tag(mp.get_property_native('vf') or {},false))
    mp.msg.warn('TrueHDR requested but not applied by the engine; mpv converts instead.')
    mp.osd_message('TrueHDR indisponible (voir le terminal) : conversion par mpv.',6)
end

-- backend=migraphx / openvino: same host-frame bridge as Vulkan, another engine library.
local function onnxruntime() return hw.backend=='migraphx' or hw.backend=='openvino' end
local function bridged() return hw.backend=='vulkan' or onnxruntime() end
local function ready()
    hw.backend=(policy.read_bank(hw.conf) or {}).backend or 'tensorrt'
    hw.inference_available = not failed and not hw.bank_conflict and hw.backend=='tensorrt' and hw.vendor=='nvidia' and utils.file_info(hw.inference_dir..'/libaji.so')~=nil
        and utils.file_info(hw.inference_dir..'/libnvinfer.so.11')~=nil
        and utils.file_info(hw.inference_dir..'/libaji_trt.so')~=nil and utils.file_info(hw.inference_dir..'/trtexec')~=nil
    if hw.backend=='vulkan' then
        hw.inference_available=not failed and not hw.bank_conflict and hw.vulkan_device~=nil and utils.file_info(hw.inference_dir..'/libaji_vulkan.so')~=nil
    end
    if onnxruntime() then
        -- The provider itself is checked by the engine at configure, with its own message.
        hw.inference_available=not failed and not hw.bank_conflict and utils.file_info(hw.inference_dir..'/libaji_ort.so')~=nil
    end
    mp.set_property_native('user-data/animejanai-hardware',hw)
    return hw.inference_available
end
local function select(value, preload)
    local wanted = tonumber(value)
    if not wanted or wanted~=math.floor(wanted) or wanted<0 then return end
    local bank=policy.read_bank(hw.conf)
    if wanted>0 and not ready() then
        mp.osd_message(onnxruntime() and 'Moteur ONNX Runtime absent (libaji_ort.so). Lecture normale conservee.'
            or hw.backend=='vulkan' and 'Moteur Vulkan indisponible ou GPU non detecte. Lecture normale conservee.'
            or 'TensorRT indisponible : NVIDIA et composants TensorRT requis. Choisir Vulkan pour AMD.',5)
        wanted=0
    end
    if wanted>=1000 and hw.backend=='vulkan' then
        mp.osd_message('Vulkan : utiliser les profils Linux 1 a 4 ; profils ONNX integres indisponibles.',5);return
    end
    if wanted>0 and wanted<1000 and (not bank or not bank.slots[wanted] or bank.slots[wanted].name=='New Profile') then
        mp.osd_message('Profil Linux '..wanted..' vide',4);return
    end
    local list=mp.get_property_native('vf') or {}
    local index
    for i,f in ipairs(list) do if f.label=='aji' then index=i end end
    if wanted==0 then
        if index then table.remove(list,index);mp.set_property_native('vf',tag(list,false)) end
    elseif index and not preload and hw.backend=='tensorrt' and list[index].name=='animejanai' then
        local ok,result=pcall(mp.commandv,'vf-command','aji','slot',tostring(wanted))
        if not ok or not result then mp.osd_message('Selection AnimeJaNai impossible',5);return end
        if mp.get_property_native('pause') then mp.command('no-osd seek 0 exact') end
    else
        local vulkan=hw.backend=='vulkan'
        local ort=onnxruntime()
        local f={name=(vulkan or ort) and 'animejanai-vulkan' or 'animejanai',label='aji',enabled=true,params={
            lib=hw.inference_dir..(ort and '/libaji_ort.so' or vulkan and '/libaji_vulkan.so' or '/libaji.so'),conf=hw.conf_active or hw.conf,
            ['model-dir']=path('~~/../animejanai/onnx'),['rife-model-dir']=path('~~/../animejanai/rife'),
            stats=path('~~/../animejanai/currentanimejanai.log'),slot=tostring(wanted)}}
        if vulkan then
            f.params.device=hw.vulkan_device
            f.params['rife-model-dir']=path('~~/../animejanai/rife-vulkan')
            -- The host-frame bridge requires software decoding; keep Vulkan rendering.
            decoder('no')
        elseif ort then
            -- Original ONNX models; the device (GPU, GPU.1, a HIP device id) may be forced.
            f.params.device=os.getenv('ANIMEJANAI_ORT_DEVICE') or ''
            decoder('no')
        else f.params.trtexec=hw.inference_dir..'/trtexec' end
        local stage=not vulkan and not ort and stage_wanted()
        -- Same C interface as the dispatcher, loaded directly like aji_trt_rtx.dll on Windows.
        if stage then f.params.lib=hw.inference_dir..'/libaji_trt_rtx.so' end
        write_stage(stage)
        if index then list[index]=f else table.insert(list,1,f) end
        mp.set_property_native('vf',tag(list,stage))
        if stage_check then stage_check:kill();stage_check=nil end
        if stage and loaded then stage_check=mp.add_timeout(3,confirm_stage) end
    end
    slot=wanted
    if wanted==0 then decoder(hw.vendor=='nvidia' and 'nvdec' or 'auto-safe') end
    mp.set_property_native('user-data/animejanai-active-slot',slot)
    mp.set_property_native('user-data/animejanai-interpolation',slot>0 and bank and bank.slots[slot]
        and bank.slots[slot].rife and 'RIFE configure' or 'cadence originale')
end
mp.add_hook('on_load',-50,function()
    local bank=policy.read_bank(hw.conf)
    last_conf=read(hw.conf);last_default=bank and bank.default_slot or 0
    select(mp.get_property_native('user-data/animejanai-active-slot') or last_default,true)
end)
mp.add_hook('on_preloaded',-50,function()
    hw.conf_active=hw.conf
    local text=read(hw.conf)
    if text and options.rife_display_sync then
        local fps=tonumber((mp.get_property_native('container-fps')))
        if not fps then
            for _,t in ipairs(mp.get_property_native('track-list') or {}) do
                if t.type=='video' and not t.albumart and not t.image then fps=tonumber(t['demux-fps']);break end
            end
        end
        local p,q,out,n=sync.choose(fps,tonumber((mp.get_property_native('display-fps'))),options.rife_max_factor)
        if p then
            local runtime=path('~~/../animejanai/animejanai-runtime.conf')
            local f=io.open(runtime,'wb')
            if f then f:write((sync.rewrite(text,p,q)));f:close();hw.conf_active=runtime end
            mp.set_property_native('user-data/animejanai-rife-sync',string.format('x%d/%d -> %.3f i/s (%d rafraichissements)',p,q,out,n))
        else mp.set_property_native('user-data/animejanai-rife-sync','aucun facteur exact : profil conserve') end
    else mp.set_property_native('user-data/animejanai-rife-sync',nil) end
    select(slot,true)
end)
mp.register_script_message('animejanai-select',function(value) select(value,false) end)
mp.register_script_message('aji-slot',function(value) select(value,false) end)
mp.register_script_message('animejanai-reload-options',function()
    options=policy.options()
    local text=read(hw.conf)
    if loaded and text~=last_conf then
        local bank=policy.read_bank(hw.conf)
        local default=bank and bank.default_slot or 0
        local wanted=default~=last_default and default or slot
        hw.conf_active=hw.conf;select(wanted,true)
        last_conf,last_default=text,default
    end
end)
mp.register_event('file-loaded',function()
    loaded=true
    if stage_check then stage_check:kill() end
    stage_check=mp.add_timeout(3,confirm_stage)
end)
mp.register_event('end-file',function(event)
    loaded=false
    if event.reason=='error' and slot>0 then
        select(0,false)
        failed=true -- disable inference for this session, without changing saved profiles
        mp.msg.error('Linux inference initialization failed. Disabled for this session; reopen the video for normal playback.')
        mp.osd_message('Echec inference : desactivee pour cette session. Rouvrir la video pour la lecture normale.',8)
    end
end)
mp.register_script_message('animejanai-manager',function()
    for _,name in ipairs({'AnimeJaNaiManager-HDR','AnimeJaNaiManager'}) do
        local exe=path('~~/../'..name)
        if utils.file_info(exe) then mp.commandv('run',exe);return end
    end
    mp.osd_message('AnimeJaNai Manager introuvable',5)
end)
