-- Source-aware HDR controller for NVIDIA and AMD/Intel.
--   * Windows HDR ownership is shared through hdr-coordinator.exe.
--   * Video tail after AnimeJaNai: TrueHDR (RTX), RTX VSR, AMD VideoSR or D3D11.
--   * One HDR grade for every GPU: hdr-tools/hdr-grade.lua + anime-hdr-grade.hook.
local mp = require 'mp'
local msg = require 'mp.msg'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
if policy.is_linux(mp) then
    return dofile(mp.command_native({'expand-path','~~/hdr-tools/linux-hdr.lua'}))
end
local grade = dofile(mp.command_native({'expand-path','~~/hdr-tools/hdr-grade.lua'}))
local base_options = policy.options()
local options=base_options
local hdr_route=dofile(mp.command_native({"expand-path","~~/hdr-tools/pipeline-hdr.lua"}))
local hardware = policy.detect(mp,utils,options)
local upscaler, hdr_backend
-- Derived settings; re-run when the Manager asks for a live reload.
local function derive_options()
    options=hdr_route.options(base_options,hdr_route.route(mp,hardware))
    upscaler = policy.upscaler(hardware.vendor,options.vsr)
    if (options.vsr=='nvidia' or options.vsr=='amd') and upscaler~=options.vsr then
        msg.warn('Requested '..options.vsr..' upscale on '..hardware.vendor..'; using classic')
    end
    options.mode = policy.settings(hardware.vendor,options).mode
    hdr_backend = policy.hdr_backend(hardware.vendor,options.hdr_backend,options.hdr_conversion)
    -- Without SDR -> HDR conversion the player never changes the Windows HDR setting.
    if hdr_backend == 'none' then options.mode = 'follow' end
    if options.mode ~= 'enable' and options.mode ~= 'follow' then
        msg.error('Invalid mode='..tostring(options.mode)..'; using follow')
        options.mode='follow'
    end
    options.max_attempts=math.max(1,math.min(5,math.floor(tonumber(options.max_attempts) or 3)))
    options.idle_restore_seconds=math.max(0,tonumber(options.idle_restore_seconds) or 2)
end
derive_options()

local helper=mp.command_native({'expand-path','~~/hdr-tools/hdr-coordinator.exe'})
local pid=tostring(mp.get_property_native('pid') or utils.getpid())
local active, loaded, generation, token = false, false, 0, '0'
local pending, restore_timer, last_line, last_result, leased_uid
local stopped=false
local filter_failures, filter_context = 0, nil
local remove_failures=0
local vsr_input, vsr_expected, vsr_wait, vsr_errors = nil, nil, false, 0
local amd_sr_failed, amdsr_scale = false, 1
local target_width,target_height
-- Vulkan output: RTX Video runs inside the engine (hdr-tools/rtx-stage.lua).
local rtx = dofile(mp.command_native({'expand-path','~~/hdr-tools/rtx-stage.lua'}))
local vulkan = policy.vulkan(hardware.vendor,options)
local stage = {applied=rtx.applied(''),fresh=false,backend=nil}

local function native(name) return (mp.get_property_native(name)) end
local function support(v) return v==true or v=='true' or v=='yes' or v=='1' end
local function target_text()
    return target_width and string.format('%dx%d',target_width,target_height) or 'attente ecran'
end
local function update_target()
    local w,h=policy.target_resolution(options,native('display-width'),native('display-height'))
    -- During VO startup/transitions, keep a known target; never invent a 4K fallback.
    if not w or (w==target_width and h==target_height) then return end
    target_width,target_height=w,h
    filter_failures,remove_failures,vsr_errors=0,0,0
    vsr_wait=false
    hardware.target=target_text()
    mp.set_property_native('user-data/animejanai-hardware/target',hardware.target)
    msg.info('Upscale target: '..hardware.target..' ('..options.target_resolution..')')
end

-- ===== HDR grade (both backends) =====
-- Ctrl+G cycles: the Manager's values ("custom") -> a natural preset -> off.
local grade_cycle = {'custom','natural','off'}
local grade_labels_cycle = {custom='personnalise (Manager)',natural='naturel',off='coupe (comparaison)'}
local grade_choice = 'custom'
local grade_state = {active=false,mode='off'}
local grade_shader = mp.command_native({'expand-path',grade.shader})
local calibration = false
local calibration_shader = '~~/user-shaders/anime-hdr-calibration.hook'
local calibration_osd = mp.create_osd_overlay('ass-events')
local original = {}
for _,name in ipairs(grade.render_keys) do original[name]=mp.get_property(name) end

local function count(label)
    local n=0
    for _,f in ipairs(native('vf') or {}) do if f.label==label then n=n+1 end end
    return n
end
local function truehdr_output()
    if vulkan then
        return stage.fresh and stage.applied.hdr and count('hdrtag')>0
            and native('video-out-params/gamma')=='pq'
    end
    for _,f in ipairs(native('vf') or {}) do
        if f.label=='truehdr' and f.enabled~=false then
            return native('video-out-params/gamma')=='pq'
        end
    end
    return false
end
local function apply_grade(kind,state)
    derive_options()
    local plan=grade.plan(options,{vendor=hardware.vendor,backend=stage.backend or hdr_backend,source=kind,
        windows=state,truehdr=truehdr_output(),target_gamma=native('video-target-params/gamma'),
        target_peak=native('video-target-params/max-luma'),enabled=grade_choice~='off',original=original},
        grade_choice=='natural' and grade.presets.natural or nil)
    for _,name in ipairs(grade.render_keys) do
        local value=plan.render[name]
        if value and mp.get_property(name)~=value then mp.set_property(name,value) end
    end
    -- Parameters first: a newly attached shader then compiles with its final values.
    local opts=native('glsl-shader-opts') or {}
    local wanted_opts=grade.shader_opts(opts,plan.params)
    if not grade.same_map(opts,wanted_opts) then mp.set_property_native('glsl-shader-opts',wanted_opts) end
    local shaders=native('glsl-shaders') or {}
    -- Calibration pattern: replaces the picture, so the grade must not run on top of it.
    local wanted=grade.shader_list(shaders,plan.active and not calibration,grade_shader)
    local with_pattern={}
    for _,path in ipairs(wanted) do if path~=calibration_shader then with_pattern[#with_pattern+1]=path end end
    if calibration then with_pattern[#with_pattern+1]=calibration_shader end
    if not grade.same_list(shaders,with_pattern) then mp.set_property_native('glsl-shaders',with_pattern) end
    grade_state=plan
end

local function source()
    local p=native('video-dec-params')
    -- This fork reports gamma=auto in raw NVDEC params; video-params fills the
    -- source defaults, still BEFORE vf (unlike video-out-params).
    if type(p)=='table' and (not p.gamma or p.gamma=='auto' or p.gamma=='unknown') then
        p=native('video-params') or p
    end
    if type(p)~='table' or (tonumber(p.w) or 0)<=0 then return 'unknown',p end
    if p.gamma=='pq' or p.gamma=='hlg' or p.colormatrix=='dolbyvision' then return 'hdr',p end
    if not p.gamma or p.gamma=='auto' or p.gamma=='unknown' then return 'unknown',p end
    return 'sdr',p
end
local function call(action)
    local args={helper,action,pid,action=='release' and 'all' or token}
    if action=='acquire' then
        args[#args+1]=tostring(native('user-data/display-info/uid'))
        args[#args+1]=options.mode; args[#args+1]=tostring(options.max_attempts)
    end
    local ok,r=pcall(mp.command_native,{name='subprocess',args=args,playback_only=false,capture_stdout=true,capture_stderr=true})
    if not ok or type(r)~='table' then return {state='error',reason='helper-command-error: '..tostring(r)} end
    local result=utils.parse_json(r.stdout or '')
    if not result then return {state='error',reason='helper-invalid-result: '..tostring(r.error_string or r.stderr)} end
    if r.status~=0 then msg.error(result.reason or 'helper failed') end
    return result
end

-- ===== Video tail: TrueHDR / VSR / AMD VideoSR / D3D11 =====
local function vf_command(...)
    local ok,result,err=pcall(mp.commandv,'vf',...)
    if not ok or not result then msg.error('vf command failed: '..tostring(ok and err or result)); return false end
    return true
end
local function remove_pair()
    -- Never write the vf list or reconstruct aji. Only these labels are owned.
    for _,label in ipairs({'truehdr','vsr','qhd','amdsr','bridge'}) do
        for _=1,count(label) do if not vf_command('remove','@'..label) then return false end end
    end
    return true
end
local function adaptive_scale(list)
    if upscaler=='no' or vsr_errors>=3 then return 1 end
    if not target_width then return 1 end
    if vsr_wait then return nil end
    local out=native('video-out-params')
    if type(out)~='table' or not out.w or not out.h then return nil end
    local applied,amd_present=1,false
    for _,f in ipairs(list) do
        if f.label=='truehdr' or f.label=='vsr' or f.label=='qhd' then applied=tonumber((f.params or {}).scale) or 1 end
        if f.label=='amdsr' then applied=amdsr_scale;amd_present=true end
    end
    if math.abs(applied-1)>0.000001 then
        -- Never treat VSR's enlarged output as the next input. On a slot change,
        -- temporarily remove only our tail and measure the new upstream output.
        if not vsr_expected or math.abs(out.w-vsr_expected.w)>2 or math.abs(out.h-vsr_expected.h)>2 then
            if amd_present then
                amd_sr_failed=true
                msg.warn('AMD VideoSR output did not reach requested size; classic fallback for this file')
            end
            vsr_errors=vsr_errors+1;vsr_wait=true;vsr_input=nil;vsr_expected=nil
            if not remove_pair() then vsr_wait=false end
            return nil
        end
        vsr_errors=0
    else
        vsr_input={w=out.w,h=out.h,par=out.par or 1,rotate=out.rotate or 0}
    end
    if not vsr_input then return nil end
    local w,h=vsr_input.w*vsr_input.par,vsr_input.h
    if vsr_input.rotate%180~=0 then w,h=h,w end
    local factor=policy.scale_factor(upscaler,w,h,target_width,target_height)
    -- Match the decimal passed to the filter, avoiding accumulating rounding errors.
    return tonumber(string.format('%.8f',factor))
end
local function filters(want,allow_vsr)
    if vulkan then return end  -- no D3D11 filter exists on a Vulkan output
    local list=native('vf') or {}
    for _,f in ipairs(list) do
        -- FFmpeg initialization can fail after vf append has returned success.
        if f.label=='amdsr' and f.enabled==false then
            amd_sr_failed=true
            if not remove_pair() then return end
            vsr_input=nil;vsr_expected=nil;vsr_wait=false;amdsr_scale=1
            list=native('vf') or {}
            msg.warn('AMD VideoSR disabled by MPV; classic fallback for this file')
            break
        end
    end
    local factor=1
    if allow_vsr then factor=adaptive_scale(list) end
    if factor==nil then return end
    local resize=math.abs(factor-1)>0.000001
    if not want and not resize then
        if remove_failures>=3 then return end
        if count('bridge')>0 or count('truehdr')>0 or count('vsr')>0 or count('qhd')>0 or count('amdsr')>0 then
            if remove_pair() then remove_failures=0;msg.info('TrueHDR/P010 removed; aji preserved')
            else remove_failures=remove_failures+1 end
        end
        return
    end
    if filter_failures>=3 then return end
    local n=#list
    local amd_sr=upscaler=='amd' and factor>1 and not amd_sr_failed
    local label=want and 'truehdr' or (amd_sr and 'amdsr' or (upscaler=='nvidia' and 'vsr' or 'qhd'))
    local bridge=want or amd_sr or (upscaler=='nvidia' and source()=='sdr')
    local last=list[n]
    if count(label)==1 and count('truehdr')+count('vsr')+count('qhd')+count('amdsr')==1
        and count('bridge')==(bridge and 1 or 0) and last and last.label==label
        and (not bridge or (n>=2 and list[n-1].label=='bridge'))
        and math.abs((amd_sr and amdsr_scale or tonumber((last.params or {}).scale) or 1)-factor)<0.000001 then return end
    filter_failures=filter_failures+1
    if not remove_pair() then return end
    if not bridge or vf_command('append',amd_sr and '@bridge:d3d11vpp=format=p010' or '@bridge:format=p010') then
        local spec=want and '@truehdr:d3d11vpp=format=x2bgr10:nvidia-true-hdr'
            or (upscaler=='nvidia' and '@vsr:d3d11vpp=format=p010' or '@qhd:d3d11vpp=format=p010')
        local output_width,output_height
        if amd_sr then
            output_width=math.max(2,math.floor(vsr_input.w*factor/2)*2)
            output_height=math.max(2,math.floor(vsr_input.h*factor/2)*2)
            -- FFmpeg returns AMF surfaces, which this MPV VO cannot display directly.
            -- Download in 10-bit P010; the VO uploads it for HDR rendering.
            spec=string.format('@amdsr:lavfi=graph=[sr_amf=w=%d:h=%d:algorithm=sr1-0:sharpness=0.25,hwdownload,format=p010]',
                output_width,output_height)
        elseif resize then
            spec=spec..':scale='..string.format('%.8f',factor)
            if upscaler=='nvidia' then spec=spec..':scaling-mode=nvidia' end
        end
        if not vf_command('append',spec) then
            remove_pair()
            if amd_sr then
                amd_sr_failed=true
                msg.warn('AMD VideoSR failed; classic fallback for this file')
                filters(want,allow_vsr)
            end
        else
            filter_failures=0
            if amd_sr then amdsr_scale=factor end
            if resize and vsr_input then
                vsr_expected={w=output_width or math.floor(vsr_input.w*factor),h=output_height or math.floor(vsr_input.h*factor)}
                vsr_wait=true
            else vsr_expected=nil end
            msg.info(string.format('Video tail: TrueHDR=%s upscale=%s scale=%.8f target=%s',
                tostring(want),amd_sr and 'amd' or (upscaler=='amd' and 'classic' or upscaler),factor,target_text()))
        end
    elseif amd_sr then
        remove_pair()
        amd_sr_failed=true
        msg.warn('AMD VideoSR P010 input conversion failed; classic fallback for this file')
        filters(want,allow_vsr)
    end
    if filter_failures>=3 then msg.error('Filter failure budget exhausted; retry on next file or display-state change') end
end

-- ===== Vulkan output: RTX Video inside the engine =====
-- The engine applies Super Resolution and TrueHDR itself (aji_rtx, CUDA). This script only
-- writes its settings, tags the converted frames as PQ / BT.2020 and keeps the two in step.
local rtx_path = mp.command_native({'expand-path',rtx.file})
local stats_path = mp.command_native({'expand-path','~~/../animejanai/currentanimejanai.log'})
local state_path = mp.command_native({'expand-path','~~/cache/animejanai-rtx-state.json'})
local rtx_written, rtx_wanted, file_started, reconfigured = nil, nil, 0, 0
local function read_all(path)
    local f=io.open(path,'r')
    if not f then return nil end
    local s=f:read('*a')
    f:close()
    return s
end
local remembered = utils.parse_json(read_all(state_path) or '')
if type(remembered)~='table' then remembered={} end
-- Before the first window exists, the display size and the Windows HDR state are the ones
-- of the last session.
local function stage_settings(state)
    local w,h=target_width,target_height
    if not w then w,h=policy.target_resolution(options,remembered.w,remembered.h) end
    state=state or native('user-data/display-info/hdr-status') or remembered.hdr
    local display=grade.display(options,hardware.vendor)
    return {hdr=hdr_backend=='rtx' and state=='on',vsr=upscaler=='nvidia',w=w,h=h,
        quality=options.rtx_vsr_quality,contrast=options.rtx_contrast,saturation=options.rtx_saturation,
        middle_gray=options.rtx_middle_gray,
        held=options.skip_held_frames,held_threshold=options.held_threshold,
        peak=tonumber(display.peak) or tonumber(native('video-target-params/max-luma')) or 1000},state
end
local function write_stage(state)
    if not vulkan then
        -- D3D11 output: the engine must not convert anything.
        if rtx_written~='' then os.remove(rtx_path); rtx_written='' end
        return
    end
    local settings,known=stage_settings(state)
    rtx_wanted=settings
    local text=rtx.text(settings)
    if text~=rtx_written then
        local f=io.open(rtx_path,'w')
        if f then f:write(text); f:close(); rtx_written=text end
    end
    if target_width and (known=='on' or known=='off')
        and (remembered.w~=target_width or remembered.h~=target_height or remembered.hdr~=known) then
        remembered={w=target_width,h=target_height,hdr=known}
        local f=io.open(state_path,'w')
        if f then f:write(utils.format_json(remembered)); f:close() end
    end
end
local function set_tag(want)
    local n=count('hdrtag')
    if want and n==0 then vf_command('append',rtx.tag)
    elseif not want then for _=1,n do vf_command('remove','@hdrtag') end end
end
-- Returns false while the engine has to configure again with new settings.
local function vulkan_tail(kind,state)
    if count('bridge')+count('truehdr')+count('vsr')+count('qhd')+count('amdsr')>0 then remove_pair() end
    write_stage(state)
    local info=utils.file_info(stats_path)
    stage.fresh=info~=nil and (info.mtime or 0)>=file_started
    stage.applied=rtx.applied(stage.fresh and read_all(stats_path) or '')
    stage.backend=nil
    if not stage.fresh then
        -- Engine not configured yet for this file: tag according to what was requested.
        set_tag(rtx_wanted.hdr and kind~='hdr')
        return true
    end
    if stage.applied.echo and stage.applied.echo~=rtx.echo(rtx_wanted) then
        if mp.get_time()-reconfigured>3 then
            reconfigured=mp.get_time()
            local slot=tonumber(native('user-data/animejanai-active-slot'))
            if slot and slot~=0 then
                msg.info('RTX Video settings changed; engine reconfigured')
                mp.commandv('vf-command','aji','slot','0')
                mp.add_timeout(.3,function() mp.commandv('vf-command','aji','slot',tostring(slot)) end)
            end
        end
        return false
    end
    set_tag(stage.applied.hdr and kind=='sdr')
    -- No active chain, or the stage is not installed: MPV converts, as on AMD.
    if hdr_backend=='rtx' and kind=='sdr' and not stage.applied.hdr then stage.backend='mpv' end
    return true
end
write_stage()

-- ===== Diagnostic (Ctrl+Alt+H) =====
local grade_labels={off='inactif (pas de sortie HDR)',neutral='neutre (sortie HDR sans grading)',
    mpv='SDR -> HDR par MPV',rtx='sur sortie RTX TrueHDR',native='sur source HDR native'}
local function resolution(w,h)
    if not w or not h or w<=0 or h<=0 then return 'indisponible' end
    return string.format('%dx%d',w,h)
end
local function rate(value,unit)
    value=tonumber(value)
    return value and value>0 and string.format('%.3f %s',value,unit) or 'indisponible'
end
local function ai_status(p)
    local ai
    for _,f in ipairs(native('vf') or {}) do
        if f.label=='aji' and f.enabled~=false then ai=f;break end
    end
    if not ai then return 'inactif' end
    local path=mp.command_native({'expand-path',(ai.params or {}).stats or '~~/../animejanai/currentanimejanai.log'})
    local file=io.open(path,'r')
    local stats=file and file:read(16384)
    if file then file:close() end
    local w,h
    if stats then w,h=stats:match('Original Video Resolution:%s*(%d+)x(%d+)') end
    if not (stats and p and tonumber(w)==p.w and tonumber(h)==p.h) then return 'etat indisponible' end
    local state=stats:match('Upscale Profile:%s*([^\r\n]+)') or 'etat indisponible'
    local model=stats:match('Applied Model:%s*([^;\r\n]+)')
    local rife=stats:match('(RIFE[^;\r\n]+)')
    if model then state=state..'\nModele : '..model end
    if rife then state=state..'\nInterpolation filtre : '..rife end
    return state
end
local function report(reason,force)
    local kind,p=source()
    local r=last_result or {}
    local line=string.format('backend=%s mode=%s active=%s loaded=%s source=%s gamma=%s uid=%s support=%s state=%s coordinator=%s attempts=%s/%d owned=%s grade=%s reason=%s',
        hdr_backend,options.mode,tostring(active),tostring(loaded),kind,tostring(p and p.gamma),
        tostring(native('user-data/display-info/uid')),tostring(native('user-data/display-info/hdr-supported')),
        tostring(native('user-data/display-info/hdr-status')),tostring(r.state),tostring(r.attempts or 0),
        options.max_attempts,tostring(r.owned or false),grade_state.mode,reason or r.reason or 'initializing')
    if force or (options.diagnostic and line~=last_line) then msg.info(line); last_line=line end
    if not force then return end
    update_target()
    local out=native('video-out-params') or {}
    local applied
    for _,f in ipairs(native('vf') or {}) do
        local params=f.params or {}
        if (f.label=='vsr' or f.label=='truehdr') and f.enabled~=false
            and params['scaling-mode']=='nvidia' and (tonumber(params.scale) or 1)>1 then
            applied=tonumber(params.scale)
        end
    end
    local vsr_status=applied and string.format('NVIDIA RTX VSR : filtre present, x%.4f (pilote non confirme)',applied)
        or 'inactif (taille native ou attente)'
    if count('amdsr')>0 then vsr_status=string.format('AMD VideoSR 1.0 : filtre present, x%.4f | transit P010 par RAM',amdsr_scale)
    elseif count('qhd')>0 then vsr_status='D3D11 classique : filtre present'
    elseif upscaler=='no' then vsr_status='desactive (mise a l echelle finale du VO conservee)' end
    if amd_sr_failed then vsr_status=vsr_status..' | repli apres echec AMD VideoSR' end
    if vulkan then
        vsr_status=stage.applied.vsr and 'NVIDIA RTX VSR dans le moteur (CUDA)'
            or (upscaler=='nvidia' and 'inactif (taille deja atteinte, ou aucune chaine)' or 'desactive')
    end
    local lines={
        string.format('Sortie video (apres filtres) : %s | %s (estime)',resolution(out.w,out.h),rate(native('estimated-vf-fps'),'images/s')),
        string.format('Ecran : %s | %s',resolution(native('display-width'),native('display-height')),rate(native('display-fps'),'Hz')),
        'VSR : '..vsr_status..' | choix='..options.vsr,
        string.format('Apres AnimeJaNai : %s | cible : %s',vsr_input and resolution(vsr_input.w,vsr_input.h) or resolution(out.w,out.h),target_text()),
        string.format('GPU : %s | rendu : %s | conversion SDR -> HDR : %s',hardware.name,
            vulkan and 'Vulkan' or 'D3D11',
            ({rtx='RTX TrueHDR',mpv='MPV',none='desactivee'})[stage.backend or hdr_backend]),
        string.format('HDR Windows : %s | TrueHDR : %s | signal : %s',tostring(r.state or native('user-data/display-info/hdr-status') or 'inconnu'),
            vulkan and (stage.applied.hdr and 'dans le moteur (CUDA)' or 'inactif')
                or (count('truehdr')>0 and 'filtre present' or 'inactif'),
            tostring(native('video-target-params/gamma') or 'indisponible')),
        string.format('Cible MPV : pic %s nits | contraste %s | gamut %s | blanc SDR %s nits',tostring(native('target-peak')),
            tostring(native('target-contrast')),tostring(native('target-gamut')),tostring(native('hdr-reference-white'))),
        'Grading : '..(grade_labels[grade_state.mode] or grade_state.mode)..' | Ctrl+G : '..grade_labels_cycle[grade_choice],
    }
    local gp=grade_state.params
    if gp then
        lines[#lines+1]=string.format('  pic %.0f | papier %.0f | noirs %.2f | eclats aplats x%.2f, isoles x%.2f | vibrance %.2f | gamut %s',
            gp.peak,gp.paper,gp.shadows,gp.area_gain,gp.spec_gain,gp.vibrance,gp.gamut_p3==1 and 'P3' or 'BT.2020')
    end
    lines[#lines+1]='Profil AnimeJaNai : '..ai_status(p)
    lines[#lines+1]='Interpolation : '..tostring(native('user-data/animejanai-interpolation') or 'cadence originale')
    local rife_status=native('user-data/animejanai-rife-sync')
    if rife_status then lines[#lines+1]='RIFE cale sur l ecran : '..tostring(rife_status) end
    lines[#lines+1]='Lecture : '..tostring(native('hwdec-current') or 'logiciel')..' | source='..rate(native('container-fps'),'images/s')
    lines[#lines+1]='Images perdues : sortie='..tostring(native('frame-drop-count') or 0)..
        ' | decodage='..tostring(native('decoder-frame-drop-count') or 0)
    local display=table.concat(lines,'\n')
    msg.info(display)
    -- Same report in a file, to attach to a bug report or compare two sessions.
    local path=mp.command_native({'expand-path','~~/../animejanai/diagnostic-hdr.txt'})
    local file=io.open(path,'w')
    if file then
        file:write(os.date('%Y-%m-%d %H:%M:%S'),'\n',line,'\n\n',display,'\n')
        file:close()
        display=display..'\n(copie : animejanai/diagnostic-hdr.txt)'
    end
    mp.osd_message(display,12)
end

-- ===== Reconciliation =====
-- The coordinator is a separate process (lock + JSON state on disk). Leases follow the
-- player PID, so a stable lease does not need renewing every second: ask again only when
-- the context changes, while a request is still settling, or every 5 s (the display
-- plugin can miss an external Windows change; the coordinator reads DisplayConfig).
local acquire_key, acquire_time
local function acquire(kind,uid,state)
    local key=table.concat({token,kind,tostring(uid),tostring(state)},'|')
    local r=last_result
    local settled=r and r.state~='error' and r.state==state
        and not tostring(r.reason or ''):match('^awaiting')
    if settled and key==acquire_key and mp.get_time()-(acquire_time or 0)<5 then return r end
    acquire_key,acquire_time=key,mp.get_time()
    return call('acquire')
end
local function release()
    acquire_key=nil
    last_result=call('release')
    apply_grade('unknown','off')
    if last_result.reason=='released' or last_result.reason=='restored-off' then leased_uid=nil end
    report(last_result.reason)
end
local function reconcile()
    derive_options()
    if stopped or not active or not loaded then return end
    -- The last frame can disappear before Lua receives end-file/shutdown.
    -- Do not rebuild GPU filters while VO is already being torn down.
    if native('eof-reached') or native('idle-active') then return end
    update_target()
    local kind=source()
    if kind=='unknown' then filters(false);apply_grade(kind,'off');report('waiting-for-source-video-dec-params');return end
    local uid=native('user-data/display-info/uid')
    local state=native('user-data/display-info/hdr-status')
    local supported=native('user-data/display-info/hdr-supported')
    if state==nil or uid==nil then filters(false,true);apply_grade(kind,'off');report('plugin-or-display-uninitialized');return end
    if not support(supported) or state=='unsupported' then
        if vulkan then vulkan_tail(kind,'off') end
        filters(false,true);apply_grade(kind,'off');if leased_uid then release() end;report('hdr-unsupported');return
    end
    if state~='on' and state~='off' then report('display-transition-no-filter-mutation'); return end
    last_result=acquire(kind,uid,state); leased_uid=uid
    if last_result.state=='error' then filters(false);apply_grade(kind,'off');report(last_result.reason);return end
    -- Source classification never reads video-out-params (TrueHDR's own output).
    -- The coordinator queries DisplayConfig directly after every request.
    if last_result.reason=='awaiting-confirmation' then
        apply_grade(kind,'off')
        report('awaiting-windows-confirmation'); return
    end
    local context=kind..':'..tostring(uid)..':'..tostring(last_result.state)
    if context~=filter_context then filter_context=context; filter_failures=0;remove_failures=0 end
    if vulkan then
        if not vulkan_tail(kind,last_result.state) then report('engine-reconfigure'); return end
    else
        filters(hdr_backend=='rtx' and kind=='sdr' and last_result.state=='on' and last_result.supported~=false,true)
    end
    apply_grade(kind,last_result.state)
    report(last_result.reason)
end
local function schedule()
    if pending then return end
    pending=mp.add_timeout(.25,function() pending=nil; reconcile() end)
end
mp.register_event('start-file',function()
    if restore_timer then restore_timer:kill(); restore_timer=nil end
    active=true; loaded=false; generation=generation+1; token=tostring(generation)
    vsr_input=nil;vsr_expected=nil;vsr_wait=false;vsr_errors=0
    amd_sr_failed=false;amdsr_scale=1
    -- Before any new source reaches the filters, discard conversion from the previous file.
    filter_failures=0;remove_failures=0;filter_context=nil;remove_pair();last_result=nil;acquire_key=nil
    file_started=os.time();stage.fresh=false;stage.backend=nil;stage.applied=rtx.applied('')
    write_stage()
    apply_grade('unknown','off')
end)
mp.register_event('file-loaded',function()
    loaded=true
    -- Tag before the first frame: the engine converts from its very first output.
    if vulkan and rtx_wanted and rtx_wanted.hdr then set_tag(true) end
    schedule()
end)
mp.register_event('video-reconfig',function() vsr_wait=false;schedule() end)
mp.register_event('end-file',function()
    active=false; loaded=false
    if calibration then calibration=false; calibration_osd:remove() end
    apply_grade('unknown','off')
    if restore_timer then restore_timer:kill() end
    restore_timer=mp.add_timeout(options.idle_restore_seconds,function()
        restore_timer=nil; if not active then release() end
    end)
end)
mp.register_event('shutdown',function()
    stopped=true
    if pending then pending:kill() end
    if restore_timer then restore_timer:kill() end
    -- Direct, serialized Windows call: no dying plugin/window is needed here.
    release()
end)
for _,p in ipairs({'video-dec-params','video-params','user-data/display-info/uid','user-data/display-info/hdr-status',
    'user-data/display-info/hdr-supported','video-out-params','video-target-params','vf',
    'display-width','display-height','display-names'}) do mp.observe_property(p,'native',schedule) end
local last_slot
mp.observe_property('user-data/animejanai-active-slot','native',function(_,slot)
    if slot==last_slot then return end
    last_slot=slot
    -- A fixed-size AMF output hides changes to AnimeJaNai's upstream dimensions.
    if count('amdsr')>0 then
        if not remove_pair() then return end
        vsr_input=nil;vsr_expected=nil;vsr_wait=true
        amd_sr_failed=false;amdsr_scale=1;filter_failures=0;vsr_errors=0
    end
    schedule()
end)
mp.add_periodic_timer(1,function()
    if active then reconcile() elseif leased_uid and not restore_timer then release() end
end)
mp.register_script_message('animejanai-hdr-status',function() report(nil,true) end)
-- A/B comparison: the HDR output and the video tail stay; only the grade changes.
mp.register_script_message('animejanai-grade-toggle',function()
    for i,name in ipairs(grade_cycle) do
        if name==grade_choice then grade_choice=grade_cycle[i%#grade_cycle+1]; break end
    end
    mp.osd_message('Grading HDR : '..grade_labels_cycle[grade_choice],3)
    reconcile()
end)
-- Calibration pattern (Ctrl+Alt+P): absolute-luminance patches with their values, to set
-- the peak, the black depth and the paper white by eye on this display.
local function calibration_labels()
    local rows = {
        {y=0.08, values={'0,005','0,01','0,02','0,05','0,1','0,2','0,5','1'}, title='Noirs (nits) : le dernier patch visible = limite des ombres'},
        {y=0.62, values={'5','10','20','50','100','150','203','300'}, title='Rampe 0 -> 203 nits (blanc papier) et gris de reference'},
        {y=0.94, values={'400','600','800','1000','1200','1500','2000','4000'}, title='Eclats (nits) : le premier patch qui ne s eclaircit plus = pic reel'},
    }
    local events = {}
    for _, row in ipairs(rows) do
        events[#events+1] = string.format('{\\an8\\pos(960,%d)\\fs28\\bord2}%s', math.floor(row.y*1080 - 40), row.title)
        for i, v in ipairs(row.values) do
            events[#events+1] = string.format('{\\an8\\pos(%d,%d)\\fs30\\bord2}%s', math.floor((i-0.5)*240), math.floor(row.y*1080), v)
        end
    end
    events[#events+1] = '{\\an2\\pos(960,1075)\\fs24\\bord2}Ctrl+Alt+P pour quitter la mire'
    calibration_osd.res_x, calibration_osd.res_y = 1920, 1080
    calibration_osd.data = table.concat(events, '\n')
    calibration_osd:update()
end
mp.register_script_message('animejanai-calibration',function()
    if not calibration and native('video-target-params/gamma')~='pq' then
        mp.osd_message('Mire HDR : la sortie n est pas en HDR (lancer une video avec le HDR Windows actif)',4)
        return
    end
    calibration = not calibration
    if calibration then calibration_labels() else calibration_osd:remove() end
    reconcile()
    if not loaded then apply_grade('unknown','off') end
end)

-- Live reload (sent by the Manager through the IPC pipe after it saves the settings).
-- Display, grade, subtitle, backend and upscaling settings apply to the current video.
mp.register_script_message('animejanai-reload-options',function()
    base_options = policy.options()
    derive_options()
    if policy.vulkan(hardware.vendor,options)~=vulkan then
        mp.osd_message('API de rendu modifiee : relancer le lecteur',6)
    end
    filter_failures,remove_failures,vsr_errors=0,0,0
    vsr_wait=false; acquire_key=nil; filter_context=nil
    target_width,target_height=nil,nil
    reconcile()
    mp.osd_message('Reglages HDR appliques',2)
end)
msg.info('Source-aware HDR initialized; GPU='..hardware.name..'; backend='..hdr_backend..'; mode='..options.mode..'; grade='..tostring(options.grade))
