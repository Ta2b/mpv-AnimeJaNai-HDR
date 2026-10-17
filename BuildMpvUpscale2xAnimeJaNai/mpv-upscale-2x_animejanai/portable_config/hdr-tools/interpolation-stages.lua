-- Pure launch policy for ordered stages. Actual execution/capabilities belong
-- to the native module. Explicit chains own cadence and HDR stage requests;
-- only successful native pixel conversion can establish actual HDR output.
local M = {}
local function trim(s) return (s or ''):match('^%s*(.-)%s*$') end
local function parse(text)
    local sections,section={},nil
    for line in (text or ''):gmatch('[^\n]+') do
        local s=trim(line)
        if s:sub(1,1)~='#' and s:sub(1,1)~=';' then
            local name=s:match('^%[([^%]]+)%]$')
            if name then section=trim(name):lower();sections[section]=sections[section] or {}
            elseif section then
                local k,v=s:match('^([^=]+)=(.*)$')
                if k then sections[section][trim(k):lower()]=trim(v) end
            end
        end
    end
    return sections
end
function M.temporal_policy(text,route)
    local value=route and route.runtime_policy or (parse(text).global or {}).rife_engine or 'fast'
    value=value:lower();if value=='old' then value='quality' elseif value=='new' then value='fast' end
    return (value=='quality' or value=='fast') and value or 'auto'
end
local function ids(sec,prefix,suffix)
    local seen,out={},{}
    for key in pairs(sec) do local n=tonumber(key:match('^'..prefix..'(%d+)'..suffix))
        if n and n>0 and not seen[n] then seen[n]=true;out[#out+1]=n end
    end
    table.sort(out);return out
end
local function number(s,k,d) return tonumber(s[k]) or d end
local function enabled(v) return (v or ''):lower()=='yes' end
local function legacy_core(sec,chain,global)
    local p='chain_'..chain..'_'
    if sec[p..'pipeline_version']~='1' then return false end
    local model_ids=ids(sec,p..'model_','_');local models={}
    -- Match the existing backend's sequential model-index interpretation.
    for i=1,#model_ids do models[i]=p..'model_'..i..'_' end
    local model,rife,rife_index=0,false,nil
    local count=number(sec,p..'stage_count',-1)
    if count<0 or count>16 or count%1~=0 then return false end
    local backend=(global.backend or 'TensorRT'):lower()
    local policy=(global.rife_engine or 'fast'):lower();if policy=='old' then policy='quality' elseif policy=='new' then policy='fast' end
    if policy~='quality' and policy~='fast' then return false end
    for i=1,count do
        local sp=p..'stage_'..i..'_'
        if enabled(sec[sp..'enabled'] or 'yes') then
            local kind=(sec[sp..'kind'] or ''):lower()
            if (sec[sp..'runtime'] or ''):lower()~=backend then return false end
            if kind=='interpolate' then
                if rife or not enabled(sec[p..'rife']) or (sec[sp..'method'] or ''):lower()~='rife' or
                    number(sec,sp..'model',-1)~=number(sec,p..'rife_model',414) or
                    number(sec,sp..'factor_numerator',1)*number(sec,p..'rife_factor_denominator',1)~=
                        number(sec,sp..'factor_denominator',1)*number(sec,p..'rife_factor_numerator',1) or
                    (sec[sp..'policy'] or 'quality'):lower()~=policy or
                    enabled(sec[sp..'ensemble'])~=enabled(sec[p..'rife_ensemble']) or
                    number(sec,sp..'scene_detect_threshold',.150)~=number(sec,p..'rife_scene_detect_threshold',.150) then return false end
                if enabled(sec[p..'rife_before_upscale'] or 'yes') and model~=0 or
                    not enabled(sec[p..'rife_before_upscale'] or 'yes') and model~=#models then return false end
                rife,rife_index=true,i
            elseif kind=='upscale' then
                model=model+1;local mp=models[model]
                if not mp or (sec[sp..'method'] or ''):lower()~='onnx' or (sec[sp..'model'] or '')~=(sec[mp..'name'] or '') then return false end
                for key,default in pairs({resize_factor_before_upscale=100,resize_height_before_upscale=0,frames=0,temporal_scene_threshold=.150}) do
                    if number(sec,sp..key,default)~=number(sec,mp..key,default) then return false end
                end
            else return false end
            local known={id=true,kind=true,method=true,runtime=true,enabled=true,model=true,policy=true,factor_numerator=true,factor_denominator=true}
            if kind=='interpolate' then known.ensemble=true;known.scene_detect_threshold=true
            else known.resize_factor_before_upscale=true;known.resize_height_before_upscale=true;known.frames=true;known.temporal_scene_threshold=true end
            for key in pairs(sec) do if key:sub(1,#sp)==sp and not known[key:sub(#sp+1)] then return false end end
        end
    end
    return model==#models and rife==enabled(sec[p..'rife']),rife_index
end
local function platform_name(value)
    if not value then
        local player=rawget(_G,'mp') or package.loaded.mp
        if player then
            if player.get_property_native then value=player.get_property_native('platform') end
            if not value and player.get_property then value=player.get_property('platform') end
        end
    end
    value=type(value)=='string' and value:lower() or nil
    return value=='darwin' and 'macos' or value
end
local function historical_resize_method(runtime,platform)
    if runtime=='tensorrt' or runtime=='directml' then return 'spline36' end
    if runtime=='migraphx' then
        if not platform then return nil end -- no OS assumption for imported MIGraphX
        return platform=='windows' and 'spline36' or 'bilinear'
    end
    return 'bilinear'
end
local function lower_for_inference(sec,chain,platform)
    local copy={};for k,v in pairs(sec) do copy[k]=v end
    local pre='chain_'..chain..'_';local active={};local mapping={}
    local count=number(sec,pre..'stage_count',0)
    for i=1,count do
        local sp=pre..'stage_'..i..'_';local stage={source=i}
        for k,v in pairs(sec) do if k:sub(1,#sp)==sp then stage[k:sub(#sp+1)]=v end end
        for _,key in ipairs({'kind','method','runtime','policy'}) do if stage[key] then stage[key]=stage[key]:lower() end end
        if enabled(stage.enabled or 'yes') and not (stage.kind=='hdr' and
            (stage.method=='mpv' and stage.runtime=='gpu-next' or stage.method=='nvidia-truehdr' and stage.runtime=='rtx-video')) then active[#active+1]=stage end
    end
    local out={};local i=1
    while i<=#active do
        local stage=active[i]
        local origin,origin_runtime=(stage.legacy_geometry or ''):match('^([a-z]+):([a-z0-9_-]+)$')
        local known_origin=origin=='linux' or origin=='windows' or origin=='macos'
        if stage.kind=='resize' and known_origin and origin_runtime and
            stage.method==historical_resize_method(stage.runtime,origin) and
            stage.method==historical_resize_method(stage.runtime,platform) then
            local model=i+1;local before=active[model] and active[model].kind=='interpolate' and active[model].method=='rife'
            if before then model=model+1 end
            local up=active[model];local frames=up and (up.frames or '0')
            local compatible=up and up.kind=='upscale' and up.method=='onnx' and up.runtime==stage.runtime and
                not (before and (i~=1 or active[i+1].runtime~=stage.runtime or frames~='0' and frames~='1')) and
                not (not before and #out==1 and out[1].kind=='interpolate')
            if compatible then
                if stage.target_height then up.resize_height_before_upscale=stage.target_height
                else up.resize_factor_before_upscale=stage.target_percent or '100' end
                if before then out[#out+1]=active[i+1] end
                out[#out+1]=up;i=model
            else out[#out+1]=stage end
        else out[#out+1]=stage end
        i=i+1
    end
    for key in pairs(copy) do if key:match('^'..pre..'stage_%d+_') then copy[key]=nil end end
    for n,stage in ipairs(out) do local dest=pre..'stage_'..n..'_';mapping[n]=stage.source
        for k,v in pairs(stage) do if k~='source' then copy[dest..k]=v end end
    end
    copy[pre..'stage_count']=tostring(#out);return copy,mapping
end
local function legacy(sec,chain,global,platform)
    local prepared,mapping=lower_for_inference(sec,chain,platform)
    -- A projectable explicit RIFE stage owns its policy. The launcher supplies
    -- it through a private runtime config, never through a hidden user setting.
    local effective={};for k,v in pairs(global) do effective[k]=v end
    local pre='chain_'..chain..'_';local policy
    for i=1,number(prepared,pre..'stage_count',0) do local sp=pre..'stage_'..i..'_'
        if prepared[sp..'kind']=='interpolate' then
            if policy then return false end
            policy=(prepared[sp..'policy'] or 'quality'):lower()
            if policy~='quality' and policy~='fast' then return false end
        end
    end
    if policy then effective.rife_engine=policy end
    local same,index=legacy_core(prepared,chain,effective)
    return same,index and mapping[index],same and policy or nil
end
local function resolution(value,maximum)
    local a,b=(value or ''):match('^([^x]+)x([^x]+)$');a=a and a:lower()=='inf' and math.huge or tonumber(a) or 0;b=b and b:lower()=='inf' and math.huge or tonumber(b) or 0
    if maximum then if a==0 then a=math.huge end;if b==0 then b=math.huge end end
    return a*b
end
function M.resolve(text,slot,w,h,fps,platform)
    platform=platform_name(platform)
    local all=parse(text);local sec=all['slot_'..tostring(slot)]
    if not sec then return {explicit=false,legacy_equivalent=true} end
    local chains=ids(sec,'chain_','_');local selected
    local hdr_owned=enabled(sec.hdr_stage_controlled);local profile_hdr;local hdr_count=0
    for _,i in ipairs(chains) do local cp='chain_'..i..'_'
        for j=1,math.min(16,number(sec,cp..'stage_count',0)) do
            local hp=cp..'stage_'..j..'_'
            if sec[hp..'kind']=='hdr' then
                hdr_owned=true;hdr_count=hdr_count+1
                if enabled(sec[hp..'enabled'] or 'yes') then
                    profile_hdr={method=sec[hp..'method'],runtime=sec[hp..'runtime'],peak=number(sec,hp..'peak',1000),options={}}
                    for k,v in pairs(sec) do if k:sub(1,#hp)==hp then profile_hdr.options[k:sub(#hp+1)]=v end end
                end
            end
        end
    end
    if hdr_count>1 then return {explicit=true,legacy_equivalent=false,hdr_stage_controlled=true,error='Only one HDR stage is allowed per profile.'} end
    w,h,fps=tonumber(w),tonumber(h),tonumber(fps)
    if w and h and fps and w>0 and h>0 and fps>0 then
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            local maxfps=number(sec,p..'max_fps',math.huge);if maxfps==0 then maxfps=math.huge end
            if resolution(sec[p..'min_resolution'],false)<=w*h and w*h<=resolution(sec[p..'max_resolution'],true) and
                number(sec,p..'min_fps',0)<=fps and fps<=maxfps then selected=i;break end
        end
    else
        local empty=true
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            if sec[p..'pipeline_version']=='1' then
                for j=1,math.min(16,number(sec,p..'stage_count',0)) do local sp=p..'stage_'..j..'_'
                    if enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']~='hdr' then empty=false end
                end
            elseif enabled(sec[p..'rife']) or #ids(sec,p..'model_','_')>0 then empty=false end
        end
        if empty then return {explicit=true,legacy_equivalent=true,hdr_stage_controlled=hdr_owned,hdr=profile_hdr,inference_empty=true} end
        -- Before on_preloaded there may be no selected stream geometry yet.
        -- Defer HDR for a potentially mixed rule; legacy-only banks unchanged.
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            if sec[p..'pipeline_version'] and not legacy(sec,i,all.global or {},platform) then
                return {explicit=true,legacy_equivalent=false,unknown=true,hdr_stage_controlled=hdr_owned}
            end
        end
        return {explicit=false,legacy_equivalent=true,hdr_stage_controlled=hdr_owned}
    end
    if not selected then return {explicit=false,legacy_equivalent=true,hdr_stage_controlled=hdr_owned,hdr=profile_hdr,inference_empty=true} end
    local p='chain_'..selected..'_';local explicit=sec[p..'pipeline_version']~=nil
    local equivalent,_,runtime_policy=true,nil,nil
    if explicit then equivalent,_,runtime_policy=legacy(sec,selected,all.global or {},platform) end
    local route={explicit=explicit,legacy_equivalent=equivalent,chain=selected,runtime_policy=runtime_policy,factor_num=1,factor_den=1,stages={},hdr_stage_controlled=hdr_owned,hdr=profile_hdr,inference_empty=true}
    if explicit then for i=1,math.min(16,number(sec,p..'stage_count',0)) do local sp=p..'stage_'..i..'_'
        if enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']~='hdr' then route.inference_empty=false end
        if enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']=='interpolate' then
            local n,d=number(sec,sp..'factor_numerator',1),number(sec,sp..'factor_denominator',1)
            route.stages[#route.stages+1]={method=sec[sp..'method'],numerator=n,denominator=d}
            if sec[sp..'method']=='nvidia-fruc' then route.error='FRUC has been removed. Disable or remove the preserved FRUC step in this profile.' end
            route.factor_num=route.factor_num*n;route.factor_den=route.factor_den*d
        elseif enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']=='hdr' then
            -- The unique profile HDR request is carried independently of its rule.
        end
    end end
    if not explicit then route.inference_empty=not enabled(sec[p..'rife']) and #ids(sec,p..'model_','_')==0 end
    if profile_hdr and profile_hdr.method=='nvidia-truehdr' and profile_hdr.runtime=='cuda' then route.legacy_equivalent=false;route.inference_empty=false end
    if not explicit and enabled(sec[p..'rife']) then
        route.factor_num=number(sec,p..'rife_factor_numerator',1)
        route.factor_den=number(sec,p..'rife_factor_denominator',1)
    end
    return route
end
-- Keep stage factors synchronized ONLY for a genuinely equivalent legacy rule.
-- True mixed chains retain their explicit factors. The source file is untouched.
function M.sync_rewrite(text,p,q,rewrite_legacy,platform)
    platform=platform_name(platform)
    local all=parse(text);local replacements={}
    for section,sec in pairs(all) do if section:match('^slot_%d+$') then
        for _,i in ipairs(ids(sec,'chain_','_')) do local same,index=legacy(sec,i,all.global or {},platform)
            if same and index then local pre='chain_'..i..'_stage_'..index..'_factor_'
                replacements[section]=replacements[section] or {}
                replacements[section][pre..'numerator']=p;replacements[section][pre..'denominator']=q
            end
        end
    end end
    local rewritten,changed=rewrite_legacy(text,p,q);local lines,section,seen={},nil,{}
    for source_line in (rewritten..'\n'):gmatch('([^\n]*)\n') do
        local line=source_line
        local name=line:match('^%s*%[([^%]]+)%]');if name then section=trim(name):lower();seen[section]=seen[section] or {} end
        local key=line:match('^%s*([^=%s]+)%s*=');local target=section and key and replacements[section] and replacements[section][key:lower()]
        if target then local value=key..'='..tostring(target);changed=changed or line~=value;line=value;seen[section][key:lower()]=true end
        lines[#lines+1]=line
    end
    if lines[#lines]=='' then lines[#lines]=nil end
    -- Optional factor keys default to1; if absent add a repeated INI section
    -- containing just the missing keys (the readers merge repeated sections).
    for name,values in pairs(replacements) do local extra={}
        for key,value in pairs(values) do if not (seen[name] or {})[key] then extra[#extra+1]=key..'='..value;changed=true end end
        if #extra>0 then lines[#lines+1]='['..name..']';for _,line in ipairs(extra) do lines[#lines+1]=line end end
    end
    return table.concat(lines,'\n')..'\n',changed
end
-- Geometry is available from demux tracks before video-params exists.
function M.source(mp)
    local source=mp.get_property_native('video-params') or {}
    local w,h=tonumber(source.w),tonumber(source.h)
    local fps=tonumber((mp.get_property_native('container-fps')))
    for _,track in ipairs(mp.get_property_native('track-list') or {}) do
        if track.type=='video' and not track.albumart and not track.image and track.selected~=false then
            w=w or tonumber(track['demux-w']);h=h or tonumber(track['demux-h']);fps=fps or tonumber(track['demux-fps']);break
        end
    end
    return w,h,fps
end

-- One immutable file per effective content/selection. Old files remain alive
-- while a native context may still read them; this process removes them at exit.
function M.runtime_configs(mp,utils,directory,label)
    local pid=tostring(mp.get_property_native('pid') or utils.getpid())
    local cache,files,serial={},{},0
    local runtime={}
    function runtime.store(text,key)
        key=tostring(key)..'\0'..text
        if cache[key] then return cache[key] end
        serial=serial+1
        local path=directory..'/animejanai-'..label..'-'..pid..'-'..serial..'.conf'
        local file,error=io.open(path,'wb');if not file then return nil,error end
        local ok,why=file:write(text);local closed,close_error=file:close()
        if not ok or not closed then os.remove(path);return nil,why or close_error end
        cache[key]=path;files[#files+1]=path;return path
    end
    function runtime.prepare(path,text,route,slot)
        if not route or not route.legacy_equivalent or not route.chain or not route.runtime_policy then return path end
        if not text then return nil,'Cannot read the selected profile configuration.' end
        local global=(parse(text).global or {}).rife_engine or 'fast'
        global=global:lower();if global=='old' then global='quality' elseif global=='new' then global='fast' end
        if global==route.runtime_policy then return path end
        local lines,section,inserted={},nil,false
        for line in (text..'\n'):gmatch('([^\n]*)\n') do
            local name=line:match('^%s*%[([^%]]+)%]%s*$')
            if name then section=trim(name):lower() end
            local key=line:match('^%s*([^=%s]+)%s*=')
            if not (section=='global' and key and key:lower()=='rife_engine') then lines[#lines+1]=line end
            if name and section=='global' then lines[#lines+1]='rife_engine='..route.runtime_policy;inserted=true end
        end
        if not inserted then lines[#lines+1]='[global]';lines[#lines+1]='rife_engine='..route.runtime_policy end
        return runtime.store(table.concat(lines,'\n'),tostring(slot)..':'..tostring(route.chain)..':'..route.runtime_policy)
    end
    function runtime.cleanup()
        for _,path in ipairs(files) do os.remove(path) end
        cache,files={},{}
    end
    mp.register_event('shutdown',runtime.cleanup)
    return runtime
end
return M
