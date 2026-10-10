-- Source-aware HDR controller for NVIDIA and AMD/Intel.
--   * Windows HDR ownership is shared through hdr-coordinator.exe.
--   * Video tail after AnimeJaNai: TrueHDR (RTX), RTX VSR, AMD VideoSR or D3D11.
--   * One HDR grade for every GPU: hdr-tools/hdr-grade.lua + anime-hdr-grade.hook.
local mp = require 'mp'
local msg = require 'mp.msg'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local grade = dofile(mp.command_native({'expand-path','~~/hdr-tools/hdr-grade.lua'}))
local options = policy.options()
local hardware = policy.detect(mp,utils,options)
local upscaler = policy.upscaler(hardware.vendor,options.vsr)
if (options.vsr=='nvidia' or options.vsr=='amd') and upscaler~=options.vsr then
    msg.warn('Requested '..options.vsr..' upscale on '..hardware.vendor..'; using classic')
end
options.mode = policy.settings(hardware.vendor,options).mode
local hdr_backend = policy.hdr_backend(hardware.vendor,options.hdr_backend,options.hdr_conversion)
-- Without SDR -> HDR conversion the player never changes the Windows HDR setting.
if hdr_backend == 'none' then options.mode = 'follow' end
if options.mode ~= 'enable' and options.mode ~= 'follow' then
    msg.error('Invalid mode='..tostring(options.mode)..'; using follow')
    options.mode='follow'
end
options.max_attempts=math.max(1,math.min(5,math.floor(tonumber(options.max_attempts) or 3)))
options.idle_restore_seconds=math.max(0,tonumber(options.idle_restore_seconds) or 2)

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
local grade_enabled = true
local grade_state = {active=false,mode='off'}
local grade_shader = mp.command_native({'expand-path',grade.shader})
local original = {}
for _,name in ipairs(grade.render_keys) do original[name]=mp.get_property(name) end

local function count(label)
    local n=0
    for _,f in ipairs(native('vf') or {}) do if f.label==label then n=n+1 end end
    return n
end
local function truehdr_output()
    for _,f in ipairs(native('vf') or {}) do
        if f.label=='truehdr' and f.enabled~=false then
            return native('video-out-params/gamma')=='pq'
        end
    end
    return false
end
local function apply_grade(kind,state)
    local plan=grade.plan(options,{vendor=hardware.vendor,backend=hdr_backend,source=kind,
        windows=state,truehdr=truehdr_output(),target_gamma=native('video-target-params/gamma'),
        target_peak=native('video-target-params/max-luma'),enabled=grade_enabled,original=original})
    for _,name in ipairs(grade.render_keys) do
        local value=plan.render[name]
        if value and mp.get_property(name)~=value then mp.set_property(name,value) end
    end
    -- Parameters first: a newly attached shader then compiles with its final values.
    local opts=native('glsl-shader-opts') or {}
    local wanted_opts=grade.shader_opts(opts,plan.params)
    if not grade.same_map(opts,wanted_opts) then mp.set_property_native('glsl-shader-opts',wanted_opts) end
    local shaders=native('glsl-shaders') or {}
    local wanted=grade.shader_list(shaders,plan.active,grade_shader)
    if not grade.same_list(shaders,wanted) then mp.set_property_native('glsl-shaders',wanted) end
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
    local lines={
        string.format('Sortie video (apres filtres) : %s | %s (estime)',resolution(out.w,out.h),rate(native('estimated-vf-fps'),'images/s')),
        string.format('Ecran : %s | %s',resolution(native('display-width'),native('display-height')),rate(native('display-fps'),'Hz')),
        'VSR : '..vsr_status..' | choix='..options.vsr,
        string.format('Apres AnimeJaNai : %s | cible : %s',vsr_input and resolution(vsr_input.w,vsr_input.h) or resolution(out.w,out.h),target_text()),
        string.format('GPU : %s | conversion SDR -> HDR : %s',hardware.name,
            ({rtx='RTX TrueHDR',mpv='MPV',none='desactivee'})[hdr_backend]),
        string.format('HDR Windows : %s | TrueHDR : %s | signal : %s',tostring(r.state or native('user-data/display-info/hdr-status') or 'inconnu'),
            count('truehdr')>0 and 'filtre present' or 'inactif',tostring(native('video-target-params/gamma') or 'indisponible')),
        string.format('Cible MPV : pic %s nits | contraste %s | gamut %s | blanc SDR %s nits',tostring(native('target-peak')),
            tostring(native('target-contrast')),tostring(native('target-gamut')),tostring(native('hdr-reference-white'))),
        'Grading : '..(grade_labels[grade_state.mode] or grade_state.mode)..(grade_enabled and '' or ' | coupe (Ctrl+G)'),
    }
    local gp=grade_state.params
    if gp then
        lines[#lines+1]=string.format('  pic %.0f | papier %.0f | noirs %.2f | eclats aplats x%.2f, isoles x%.2f | vibrance %.2f | gamut %s',
            gp.peak,gp.paper,gp.shadows,gp.area_gain,gp.spec_gain,gp.vibrance,gp.gamut_p3==1 and 'P3' or 'BT.2020')
    end
    lines[#lines+1]='Profil AnimeJaNai : '..ai_status(p)
    lines[#lines+1]='Interpolation : '..tostring(native('user-data/animejanai-interpolation') or 'cadence originale')
    lines[#lines+1]='Lecture : '..tostring(native('hwdec-current') or 'logiciel')..' | source='..rate(native('container-fps'),'images/s')
    lines[#lines+1]='Images perdues : sortie='..tostring(native('frame-drop-count') or 0)..
        ' | decodage='..tostring(native('decoder-frame-drop-count') or 0)
    local display=table.concat(lines,'\n')
    msg.info(display)
    mp.osd_message(display,12)
end

-- ===== Reconciliation =====
local function release()
    last_result=call('release')
    apply_grade('unknown','off')
    if last_result.reason=='released' or last_result.reason=='restored-off' then leased_uid=nil end
    report(last_result.reason)
end
local function reconcile()
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
        filters(false,true);apply_grade(kind,'off');if leased_uid then release() end;report('hdr-unsupported');return
    end
    if state~='on' and state~='off' then report('display-transition-no-filter-mutation'); return end
    last_result=call('acquire'); leased_uid=uid
    if last_result.state=='error' then filters(false);apply_grade(kind,'off');report(last_result.reason);return end
    -- Source classification never reads video-out-params (TrueHDR's own output).
    -- The coordinator queries DisplayConfig directly after every request.
    if last_result.reason=='awaiting-confirmation' then
        apply_grade(kind,'off')
        report('awaiting-windows-confirmation'); return
    end
    local context=kind..':'..tostring(uid)..':'..tostring(last_result.state)
    if context~=filter_context then filter_context=context; filter_failures=0;remove_failures=0 end
    filters(hdr_backend=='rtx' and kind=='sdr' and last_result.state=='on' and last_result.supported~=false,true)
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
    filter_failures=0;remove_failures=0;filter_context=nil;remove_pair();last_result=nil
    apply_grade('unknown','off')
end)
mp.register_event('file-loaded',function() loaded=true; schedule() end)
mp.register_event('video-reconfig',function() vsr_wait=false;schedule() end)
mp.register_event('end-file',function()
    active=false; loaded=false
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
-- A/B comparison: the HDR output and the video tail stay; only the grade is switched.
mp.register_script_message('animejanai-grade-toggle',function()
    grade_enabled=not grade_enabled
    mp.osd_message('Grading HDR : '..(grade_enabled and 'actif' or 'coupe (comparaison)'),3)
    reconcile()
end)
msg.info('Source-aware HDR initialized; GPU='..hardware.name..'; backend='..hdr_backend..'; mode='..options.mode..'; grade='..tostring(options.grade))
