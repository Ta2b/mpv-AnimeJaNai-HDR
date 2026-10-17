-- Linux SDR inference: NCNN/Vulkan on AMD/NVIDIA, optional TensorRT on NVIDIA, and the ONNX
-- Runtime engine for the vendor providers: backend=MIGraphX (AMD, ROCm) or OpenVINO (Intel).
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local sync = dofile(mp.command_native({'expand-path','~~/hdr-tools/rife-sync.lua'}))
local stages = dofile(mp.command_native({'expand-path','~~/hdr-tools/interpolation-stages.lua'}))
local runtime=stages.runtime_configs(mp,utils,mp.command_native({'expand-path','~~/../animejanai'}),'linux-profile')
local media = {}
local light_scale=false
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
local function ort_library()
    local native=hw.inference_dir..'/libaji_migraphx_rgb.so'
    return hw.backend=='migraphx' and utils.file_info(native) and native or hw.inference_dir..'/libaji_ort.so'
end
local function ready(conf)
    hw.backend=(policy.read_bank(conf or hw.conf) or {}).backend or 'tensorrt'
    hw.inference_available = not failed and not hw.bank_conflict and hw.backend=='tensorrt' and hw.vendor=='nvidia' and utils.file_info(hw.inference_dir..'/libaji.so')~=nil
        and utils.file_info(hw.inference_dir..'/libnvinfer.so.11')~=nil
        and utils.file_info(hw.inference_dir..'/libaji_trt.so')~=nil and utils.file_info(hw.inference_dir..'/trtexec')~=nil
    if hw.backend=='vulkan' then
        hw.inference_available=not failed and not hw.bank_conflict and hw.vulkan_device~=nil and utils.file_info(hw.inference_dir..'/libaji_vulkan.so')~=nil
    end
    if onnxruntime() then
        -- The provider itself is checked by the engine at configure, with its own message.
        hw.inference_available=not failed and not hw.bank_conflict and utils.file_info(ort_library())~=nil
    end
    mp.set_property_native('user-data/animejanai-hardware',hw)
    return hw.inference_available
end
local resolved_cache={}
local function pipeline_route(wanted, text, conf)
    local source=text or read(conf or hw.conf_active or hw.conf)
    local route=stages.resolve(source,wanted,media.w,media.h,media.fps,'linux')
    -- Resolve once per actual profile/rule/configuration. Manager and launcher
    -- consume this same versioned contract; per-frame work stays native.
    if (not text or conf) and wanted>0 and route.chain and not route.unknown then
        local key=tostring(wanted)..':'..tostring(route.chain)..':'..(source or '')
        local resolved=resolved_cache[key]
        if not resolved then
            local helper=path('~~/../AnimeJaNaiPlatform')
            local ok,result=pcall(mp.command_native,{name='subprocess',playback_only=false,capture_stdout=true,capture_stderr=true,
                args={helper,'--profile-plan','--root',path('~~/..'),'--conf',conf or hw.conf_active or hw.conf,
                    '--slot',tostring(wanted),'--rule',tostring(route.chain),'--inference-dir',hw.inference_dir}})
            if ok and type(result)=='table' and result.status==0 then resolved=utils.parse_json(result.stdout or '') end
            if resolved and resolved.schema=='animejanai.profile-plan.v1' then
                resolved_cache={[key]=resolved}
            else route.error='Profile resolver unavailable; update the player components.' end
        end
        if resolved then
            route.resolved_plan=resolved.plan
            if resolved.issues and #resolved.issues>0 then route.error=table.concat(resolved.issues,' ') end
        end
    end
    return route
end
local function select(value, preload)
    local wanted = tonumber(value)
    if not wanted or wanted~=math.floor(wanted) or wanted<0 then return end
    local selection_conf=hw.conf_active or hw.conf
    local selected_text=read(selection_conf)
    if wanted>0 and wanted<1000 then
        local snapshot,error
        if selected_text then snapshot,error=runtime.store(selected_text,'source-config')
        else error='Cannot read the selected profile configuration.' end
        if snapshot then selection_conf=snapshot
        else mp.msg.error(tostring(error));mp.osd_message('Configuration temporaire indisponible : '..tostring(error),6);wanted=0 end
    end
    -- The bank, resolver and native context consume this same immutable text.
    -- A direct selection after an edit also gets a new path/context; unchanged
    -- content still reuses the snapshot and existing slot-switch behavior.
    local bank=policy.read_bank(selection_conf)
    local selected_route=pipeline_route(wanted,selected_text,selection_conf)
    if selected_route.error then mp.osd_message(selected_route.error,6);wanted=0;selected_route=pipeline_route(0) end
    if wanted>=1000 then mp.osd_message("Les anciens profils integres ont ete retires. Choisir un profil personnalise.",5);wanted=0;selected_route=pipeline_route(0) end
    if wanted>0 and not selected_route.inference_empty and not ready(selection_conf) then
        mp.osd_message(onnxruntime() and 'Moteur ONNX Runtime absent (libaji_ort.so). Lecture normale conservee.'
            or hw.backend=='vulkan' and 'Moteur Vulkan indisponible ou GPU non detecte. Lecture normale conservee.'
            or 'TensorRT indisponible : NVIDIA et composants TensorRT requis. Choisir Vulkan pour AMD.',5)
        wanted=0
    end
    if wanted>0 and wanted<1000 and (not bank or not bank.slots[wanted] or bank.slots[wanted].name=='New Profile') then
        mp.osd_message('Profil Linux '..wanted..' vide',4);return
    end
    local mixed=selected_route.explicit and not selected_route.legacy_equivalent
    if wanted>0 and mixed and hw.backend~='tensorrt' then
        mp.msg.error('Etages ordonnes indisponibles sur ce backend ; TensorRT/CUDA est requis actuellement.')
        mp.osd_message('Chaine non prise en charge sur ce moteur. Lecture originale conservee.',6)
        wanted=0;selected_route=pipeline_route(0);mixed=false
    elseif wanted>0 and mixed and (not utils.file_info(hw.inference_dir..'/libaji_pipeline.so')
        or not utils.file_info(hw.inference_dir..'/aji_pipeline.fatbin')) then
        mp.msg.error('Module de chaine ordonnee absent ; mettre le lecteur et ses moteurs a jour.')
        mp.osd_message('Module de chaine absent. Lecture originale conservee.',6)
        wanted=0;selected_route=pipeline_route(0);mixed=false
    end
    local effective_conf=selection_conf
    if wanted>0 and not selected_route.inference_empty then
        local prepared,error=runtime.prepare(effective_conf,selected_text,selected_route,wanted)
        if not prepared then
            mp.osd_message('Configuration temporaire indisponible : '..tostring(error),6)
            wanted=0;selected_route=pipeline_route(0);mixed=false
        else effective_conf=prepared end
    end
    local list=mp.get_property_native('vf') or {}
    local requested_policy=stages.temporal_policy(selected_text,selected_route)
    local legacy_rife=not mixed and (selected_route.factor_num or 1)>(selected_route.factor_den or 1)
    local index
    local hdr_wanted=wanted>0 and stage_wanted() and selected_route.legacy_equivalent and not selected_route.hdr_stage_controlled
    for i,f in ipairs(list) do if f.label=='aji' then index=i end end
    if wanted==0 or selected_route.inference_empty then
        if index then table.remove(list,index);mp.set_property_native('vf',tag(list,false)) end
    elseif index and not preload and hw.backend=='tensorrt' and list[index].name=='animejanai'
        and list[index].params.conf==effective_conf
        and (not legacy_rife or list[index].params['rife-policy']==requested_policy)
        and hdr_wanted==(mp.get_property_native('user-data/animejanai-truehdr')==true)
        and (not mixed or list[index].params['pipeline-lib']) then
        local ok,result=pcall(mp.commandv,'vf-command','aji','slot',tostring(wanted))
        if not ok or not result then mp.osd_message('Selection AnimeJaNai impossible',5);return end
        if mp.get_property_native('pause') then mp.command('no-osd seek 0 exact') end
    else
        local vulkan=hw.backend=='vulkan'
        local ort=onnxruntime()
        local f={name=(vulkan or ort) and 'animejanai-vulkan' or 'animejanai',label='aji',enabled=true,params={
            lib=ort and ort_library() or hw.inference_dir..(vulkan and '/libaji_vulkan.so' or '/libaji.so'),conf=effective_conf,
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
        if legacy_rife and not vulkan and not ort then f.params['rife-policy']=requested_policy end
        if mixed then
            -- Forces older filters to reject the unsupported option explicitly,
            -- instead of silently executing only the legacy RIFE keys.
            f.params['pipeline-lib']=hw.inference_dir..'/libaji_pipeline.so'
            f.params['pipeline-kernels']=hw.inference_dir..'/aji_pipeline.fatbin'
        end
        local stage=not vulkan and not ort and hdr_wanted
        if selected_route.explicit and not selected_route.legacy_equivalent and stage_wanted() then
            mp.msg.info('Cette chaine produit du SDR ; mpv assure la conversion HDR.')
        end
        -- Same C interface as the dispatcher, loaded directly like aji_trt_rtx.dll on Windows.
        if stage then f.params.lib=hw.inference_dir..'/libaji_trt_rtx.so' end
        write_stage(stage)
        if index then list[index]=f else table.insert(list,1,f) end
        mp.set_property_native('vf',tag(list,stage))
        if stage_check then stage_check:kill();stage_check=nil end
        if stage and loaded then stage_check=mp.add_timeout(3,confirm_stage) end
    end
    slot=wanted
    local rate=media.fps and media.fps*(selected_route.factor_num or 1)/(selected_route.factor_den or 1)
    if slot>0 and options.rife_display_sync and not mixed and rate and rate>=100 and options.rife_light_scale then
        if mp.get_property('scale')=='ewa_lanczossharp' then mp.set_property('scale','spline36');light_scale=true end
    elseif light_scale then
        if mp.get_property('scale')=='spline36' then mp.set_property('scale','ewa_lanczossharp') end
        light_scale=false
    end
    if wanted==0 or selected_route.inference_empty then decoder(hw.vendor=='nvidia' and 'nvdec' or 'auto-safe') end
    mp.set_property_native('user-data/animejanai-active-slot',slot)
    local route=selected_route -- diagnostics describe the configuration actually loaded
    mp.set_property_native('user-data/animejanai-pipeline-configured',slot>0 and (route.explicit or route.hdr_stage_controlled) and route or nil)
    local description='cadence originale'
    if slot>0 and route.explicit and not route.legacy_equivalent then
        description=string.format('Chaine configuree x%s/%s',route.factor_num or '?',route.factor_den or '?')
    elseif slot>0 and bank and bank.slots[slot] and bank.slots[slot].rife then description='RIFE configure' end
    mp.set_property_native('user-data/animejanai-interpolation',description)
end
mp.add_hook('on_load',-50,function()
    media={}
    hw.conf_active=hw.conf
    local bank=policy.read_bank(hw.conf)
    last_conf=read(hw.conf);last_default=bank and bank.default_slot or 0
    select(mp.get_property_native('user-data/animejanai-active-slot') or last_default,true)
end)
mp.add_hook('on_preloaded',-50,function()
    hw.conf_active=hw.conf
    local text=read(hw.conf)
    if light_scale and mp.get_property('scale')=='spline36' then mp.set_property('scale','ewa_lanczossharp') end
    light_scale=false
    media.fps=tonumber((mp.get_property_native('container-fps')))
    for _,track in ipairs(mp.get_property_native('track-list') or {}) do
        if track.type=='video' and not track.albumart and not track.image and track.selected~=false then
            media.fps=media.fps or tonumber(track['demux-fps'])
            media.w,media.h=tonumber(track['demux-w']),tonumber(track['demux-h']);break
        end
    end
    local route=pipeline_route(slot,text)
    if text and options.rife_display_sync then
        local fps=media.fps
        if not fps then
            for _,t in ipairs(mp.get_property_native('track-list') or {}) do
                if t.type=='video' and not t.albumart and not t.image then fps=tonumber(t['demux-fps']);break end
            end
        end
        local p,q,out,n=sync.choose(fps,tonumber((mp.get_property_native('display-fps'))),options.rife_max_factor)
        if p then
            local rewritten=stages.sync_rewrite(text,p,q,sync.rewrite,'linux')
            local prepared,error=runtime.store(rewritten,'display-sync')
            if prepared then hw.conf_active=prepared
            else mp.msg.error('Cannot prepare display cadence: '..tostring(error)) end
            mp.set_property_native('user-data/animejanai-rife-sync',route.explicit and not route.legacy_equivalent
                and 'Cadence explicite des etages conservee'
                or string.format('x%d/%d -> %.3f i/s (%d rafraichissements)',p,q,out,n))
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
