-- Pure launch policy for ordered stages. Actual execution/capabilities belong
-- to the native module. The stages are the only representation of a rule: the
-- legacy engine keys (chain_N_rife*, chain_N_model_M_*) are a projection
-- computed here for the runtime copy, never read as a source when a rule is
-- explicit. HDR is a global setting of the player, not a stage: a profile HDR
-- stage is ignored (docs/CONTRAT-PROFILS-V2.md).
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
local KNOWN={id=true,kind=true,method=true,runtime=true,enabled=true,model=true,policy=true,factor_numerator=true,factor_denominator=true}
local ORDER={'id','kind','method','runtime','enabled','model','factor_numerator','factor_denominator','policy'}
local RIFE_OPTIONS={ensemble=true,scene_detect_threshold=true}
local MODEL_OPTIONS={resize_factor_before_upscale=true,resize_height_before_upscale=true,frames=true,temporal_scene_threshold=true}
-- Legacy projection of a prepared (hoisted) explicit rule: what the legacy engine
-- needs (one RIFE before or after every ONNX model, known options only, runtime
-- equal to the backend), or nil when the rule is not expressible by it. Mirrors
-- legacy_equivalent() of the native pipeline configuration loader.
local function project(sec,chain,global)
    local p='chain_'..chain..'_'
    if sec[p..'pipeline_version']~='1' then return nil end
    local count=number(sec,p..'stage_count',-1)
    if count<0 or count>16 or count%1~=0 then return nil end
    local backend=(global.backend or 'TensorRT'):lower()
    local models,rife,rife_index={},nil,nil
    for i=1,count do
        local sp=p..'stage_'..i..'_'
        local kind=(sec[sp..'kind'] or ''):lower()
        if kind~='hdr' and enabled(sec[sp..'enabled'] or 'yes') then
            if (sec[sp..'runtime'] or ''):lower()~=backend then return nil end
            local options={}
            for key,value in pairs(sec) do if key:sub(1,#sp)==sp and not KNOWN[key:sub(#sp+1)] then options[key:sub(#sp+1)]=value end end
            if kind=='interpolate' then
                if rife or (sec[sp..'method'] or ''):lower()~='rife' then return nil end
                for key in pairs(options) do if not RIFE_OPTIONS[key] then return nil end end
                local policy=(sec[sp..'policy'] or 'quality'):lower()
                if policy~='quality' and policy~='fast' then return nil end
                rife={model=sec[sp..'model'] or '',num=sec[sp..'factor_numerator'] or '1',den=sec[sp..'factor_denominator'] or '1',
                    before=#models==0,ensemble=enabled(options.ensemble),scd=options.scene_detect_threshold,policy=policy}
                rife_index=i
            elseif kind=='upscale' then
                if (sec[sp..'method'] or ''):lower()~='onnx' then return nil end
                for key in pairs(options) do if not MODEL_OPTIONS[key] then return nil end end
                if rife and not rife.before then return nil end
                models[#models+1]={name=sec[sp..'model'] or '',options=options}
            else return nil end
        end
    end
    return {rife=rife,models=models,policy=rife and rife.policy or nil},rife_index
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
        if enabled(stage.enabled or 'yes') and stage.kind~='hdr' then active[#active+1]=stage end
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
-- Projectable explicit rule: true, the source index of its RIFE stage, its
-- policy (owned by the stage, supplied through the runtime copy) and the
-- projection itself; false otherwise.
local function legacy(sec,chain,global,platform)
    local prepared,mapping=lower_for_inference(sec,chain,platform)
    local projection,index=project(prepared,chain,global)
    if not projection then return false end
    return true,index and mapping[index],projection.policy,projection
end
-- The legacy keys of one explicit rule, regenerated from its stages. A rule the
-- legacy engine cannot express gets rife=no and no model: the native ordered
-- pipeline executes it from the stage keys.
local function projection_lines(sec,chain,global,platform)
    local p='chain_'..chain..'_'
    local same,_,_,projection=legacy(sec,chain,global,platform)
    if not same then return {p..'rife=no'},false end
    local lines,r={},projection.rife
    lines[#lines+1]=p..'rife='..(r and 'yes' or 'no')
    if r then
        lines[#lines+1]=p..'rife_model='..r.model
        lines[#lines+1]=p..'rife_factor_numerator='..r.num
        lines[#lines+1]=p..'rife_factor_denominator='..r.den
        lines[#lines+1]=p..'rife_before_upscale='..(r.before and 'yes' or 'no')
        lines[#lines+1]=p..'rife_ensemble='..(r.ensemble and 'yes' or 'no')
        if r.scd then lines[#lines+1]=p..'rife_scene_detect_threshold='..r.scd end
    end
    for i,m in ipairs(projection.models) do local mp=p..'model_'..i..'_'
        lines[#lines+1]=mp..'name='..m.name
        for _,key in ipairs({'resize_factor_before_upscale','resize_height_before_upscale','frames','temporal_scene_threshold'}) do
            if m.options[key] then lines[#lines+1]=mp..key..'='..m.options[key] end
        end
    end
    return lines,true
end
local function rebuild_section(entries,global,platform,info)
    local sec={};for _,e in ipairs(entries) do if e.key then sec[e.key]=e.value end end
    local chains=ids(sec,'chain_','_');local explicit={}
    for _,i in ipairs(chains) do explicit[i]=sec['chain_'..i..'_pipeline_version']=='1' end
    local out={}
    for _,e in ipairs(entries) do
        local n=e.key and tonumber(e.key:match('^chain_(%d+)_'))
        if not e.key then out[#out+1]=e.raw
        elseif e.key:match('^chain__') then info.phantom=info.phantom+1
        elseif e.key=='hdr_stage_controlled' then info.markers=info.markers+1
        elseif not n or not explicit[n] then out[#out+1]=e.raw
        elseif e.key:match('^chain_%d+_stage_') then -- re-emitted below, HDR stages removed
        elseif e.key:match('^chain_%d+_rife') or e.key:match('^chain_%d+_model_%d+_') then info.mirrors=info.mirrors+1
        else out[#out+1]=e.raw end
    end
    for _,i in ipairs(chains) do if explicit[i] then
        local p='chain_'..i..'_';local stages={}
        for j=1,math.min(16,number(sec,p..'stage_count',0)) do local sp=p..'stage_'..j..'_'
            if (sec[sp..'kind'] or ''):lower()=='hdr' then
                info.hdr_dropped=info.hdr_dropped+1
                if enabled(sec[sp..'enabled'] or 'yes') then info.hdr_active_dropped=info.hdr_active_dropped+1 end
            else
                local stage={}
                for key,value in pairs(sec) do if key:sub(1,#sp)==sp then stage[key:sub(#sp+1)]=value end end
                stages[#stages+1]=stage
            end
        end
        local view={};for key,value in pairs(sec) do if not key:match('^'..p..'stage_') then view[key]=value end end
        view[p..'stage_count']=tostring(#stages)
        out[#out+1]=p..'stage_count='..#stages
        for j,stage in ipairs(stages) do local sp=p..'stage_'..j..'_'
            for _,key in ipairs(ORDER) do if stage[key] then out[#out+1]=sp..key..'='..stage[key];view[sp..key]=stage[key] end end
            local rest={};for key in pairs(stage) do if not KNOWN[key] then rest[#rest+1]=key end end;table.sort(rest)
            for _,key in ipairs(rest) do out[#out+1]=sp..key..'='..stage[key];view[sp..key]=stage[key] end
        end
        for _,line in ipairs(projection_lines(view,i,global,platform)) do out[#out+1]=line end
    end end
    return out
end
-- The runtime view of a profile file: HDR stages, profile HDR markers and phantom
-- rules (empty number) removed; for every explicit rule the legacy keys are
-- regenerated from its stages. Sections without an explicit rule are kept byte
-- for byte and so is a file with nothing to change. The source file itself is
-- never written. Returns the text and what was changed.
function M.normalize(text,platform)
    platform=platform_name(platform)
    local all=parse(text);local global=all.global or {}
    local info={hdr_dropped=0,hdr_active_dropped=0,phantom=0,markers=0,mirrors=0,sections=0}
    local touch={}
    for name,sec in pairs(all) do if name:match('^slot_%d+$') then
        for key,value in pairs(sec) do
            if key:match('^chain__') or key=='hdr_stage_controlled' or key:match('^chain_%d+_pipeline_version$') or
                (key:match('^chain_%d+_stage_%d+_kind$') and value:lower()=='hdr') then touch[name]=true end
        end
    end end
    if not next(touch) then return text,info end
    local lines={};for line in (text..'\n'):gmatch('([^\n]*)\n') do lines[#lines+1]=line end
    if lines[#lines]=='' then lines[#lines]=nil end
    -- Entries of a touched section, merged over its repeated occurrences.
    local entries,first,section={},{},nil
    for index,line in ipairs(lines) do
        local s=trim(line);local name=s:match('^%[([^%]]+)%]$')
        if name then section=trim(name):lower();if touch[section] and not first[section] then first[section]=index;entries[section]={} end
        elseif section and touch[section] then
            local k,v
            if s:sub(1,1)~='#' and s:sub(1,1)~=';' then k,v=s:match('^([^=]+)=(.*)$') end
            local list=entries[section];list[#list+1]={raw=line,key=k and trim(k):lower() or nil,value=v and trim(v) or nil}
        end
    end
    local out,skip={},false;section=nil
    for index,line in ipairs(lines) do
        local s=trim(line);local name=s:match('^%[([^%]]+)%]$')
        if name then
            section=trim(name):lower();skip=false
            if touch[section] then
                if first[section]==index then
                    out[#out+1]=line;info.sections=info.sections+1
                    for _,rebuilt in ipairs(rebuild_section(entries[section],global,platform,info)) do out[#out+1]=rebuilt end
                end
                skip=true
            else out[#out+1]=line end
        elseif not skip then out[#out+1]=line end
    end
    return table.concat(out,'\n')..'\n',info
end
-- The configuration handed to the filter. The filter asks the native ordered pipeline first
-- whenever stage keys are present, and that pipeline does not fold an exact-size downscale
-- (legacy_geometry) into the following upscale: it rejected such a rule and the filter
-- failed, leaving every profile unapplied. A rule the legacy engine runs as it is therefore
-- keeps only its regenerated legacy keys: the pipeline hands it to the classic chain (held
-- drawings timeline, Fast warp). Rules that need the ordered pipeline keep their stages.
function M.filter_view(text,platform)
    platform=platform_name(platform)
    local all=parse(text);local global=all.global or {};local strip={}
    for name,sec in pairs(all) do if name:match('^slot_%d+$') then
        for _,i in ipairs(ids(sec,'chain_','_')) do
            if sec['chain_'..i..'_pipeline_version']=='1' and legacy(sec,i,global,platform) then
                strip[name]=strip[name] or {};strip[name][i]=true
            end
        end
    end end
    if not next(strip) then return text end
    local out,section={},nil
    for line in (text..'\n'):gmatch('([^\n]*)\n') do
        local name=line:match('^%s*%[([^%]]+)%]')
        if name then section=trim(name):lower() end
        local key=line:match('^%s*([^=%s#;]+)%s*=');key=key and key:lower()
        local chain=key and tonumber(key:match('^chain_(%d+)_pipeline_version$') or key:match('^chain_(%d+)_stage_'))
        if not (chain and section and strip[section] and strip[section][chain]) then out[#out+1]=line end
    end
    if out[#out]=='' then out[#out]=nil end
    return table.concat(out,'\n')..'\n'
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
                    if enabled(sec[sp..'enabled'] or 'yes') and (sec[sp..'kind'] or ''):lower()~='hdr' then empty=false end
                end
            elseif enabled(sec[p..'rife']) or #ids(sec,p..'model_','_')>0 then empty=false end
        end
        if empty then return {explicit=true,legacy_equivalent=true,inference_empty=true} end
        -- Before on_preloaded there may be no selected stream geometry yet.
        -- Defer a potentially mixed rule; legacy-only banks unchanged.
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            if sec[p..'pipeline_version'] and not legacy(sec,i,all.global or {},platform) then
                return {explicit=true,legacy_equivalent=false,unknown=true}
            end
        end
        return {explicit=false,legacy_equivalent=true}
    end
    if not selected then return {explicit=false,legacy_equivalent=true,inference_empty=true} end
    local p='chain_'..selected..'_';local explicit=sec[p..'pipeline_version']~=nil
    local equivalent,_,runtime_policy=true,nil,nil
    if explicit then equivalent,_,runtime_policy=legacy(sec,selected,all.global or {},platform) end
    local route={explicit=explicit,legacy_equivalent=equivalent,chain=selected,runtime_policy=runtime_policy,factor_num=1,factor_den=1,stages={},inference_empty=true}
    if explicit then for i=1,math.min(16,number(sec,p..'stage_count',0)) do local sp=p..'stage_'..i..'_'
        local kind=(sec[sp..'kind'] or ''):lower()
        if enabled(sec[sp..'enabled'] or 'yes') and kind~='hdr' then route.inference_empty=false end
        if enabled(sec[sp..'enabled'] or 'yes') and kind=='interpolate' then
            local n,d=number(sec,sp..'factor_numerator',1),number(sec,sp..'factor_denominator',1)
            route.stages[#route.stages+1]={method=sec[sp..'method'],numerator=n,denominator=d}
            if sec[sp..'method']=='nvidia-fruc' then route.error='FRUC has been removed. Disable or remove the preserved FRUC step in this profile.' end
            route.factor_num=route.factor_num*n;route.factor_den=route.factor_den*d
        end
    end end
    if not explicit then route.inference_empty=not enabled(sec[p..'rife']) and #ids(sec,p..'model_','_')==0 end
    if not explicit and enabled(sec[p..'rife']) then
        route.factor_num=number(sec,p..'rife_factor_numerator',1)
        route.factor_den=number(sec,p..'rife_factor_denominator',1)
    end
    return route
end
-- Keep stage factors synchronized ONLY for a genuinely projectable rule.
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
    -- The configuration the engines read for one selection: the rule's own RIFE
    -- policy in [global] when the rule is projectable, and, for a rule the
    -- ordered pipeline executes, the global TrueHDR conversion appended as its
    -- last stage (hdr = {sdk_root, peak, contrast, saturation, middle_gray}).
    -- A legacy route receives TrueHDR through animejanai-rtx.conf instead.
    function runtime.prepare(path,text,route,slot,hdr)
        if not text then
            if not route or not route.chain or route.inference_empty then return path end
            return nil,'Cannot read the selected profile configuration.'
        end
        -- Every copy handed to the filter is its view, also before the rule is known.
        text=M.filter_view(text)
        local view_path
        local function plain()
            view_path=view_path or runtime.store(text,'filter-view')
            return view_path
        end
        if not route or not route.chain or route.inference_empty then return plain() end
        local policy=route.legacy_equivalent and route.runtime_policy or nil
        local global=(parse(text).global or {}).rife_engine or 'fast'
        global=global:lower();if global=='old' then global='quality' elseif global=='new' then global='fast' end
        if global==policy then policy=nil end
        local inject=hdr and not route.legacy_equivalent and route.explicit or false
        if not policy and not inject then return plain() end
        local target,pre='slot_'..tostring(slot),'chain_'..tostring(route.chain)..'_'
        local count=inject and number(parse(text)[target] or {},pre..'stage_count',0) or 0
        local lines,section,inserted,counted={},nil,false,false
        for line in (text..'\n'):gmatch('([^\n]*)\n') do
            local name=line:match('^%s*%[([^%]]+)%]%s*$')
            if name then section=trim(name):lower() end
            local key=line:match('^%s*([^=%s]+)%s*=');key=key and key:lower()
            if policy and section=='global' and key=='rife_engine' then -- replaced below
            elseif inject and section==target and key==pre..'stage_count' then lines[#lines+1]=pre..'stage_count='..(count+1);counted=true
            else lines[#lines+1]=line end
            if name and section=='global' and policy then lines[#lines+1]='rife_engine='..policy;inserted=true end
        end
        if lines[#lines]=='' then lines[#lines]=nil end
        if policy and not inserted then lines[#lines+1]='[global]';lines[#lines+1]='rife_engine='..policy end
        if inject then
            local sp=pre..'stage_'..(count+1)..'_'
            lines[#lines+1]='['..target..']'
            if not counted then lines[#lines+1]=pre..'stage_count='..(count+1) end
            for _,kv in ipairs({{'id','global-hdr'},{'kind','hdr'},{'method','nvidia-truehdr'},{'runtime','cuda'},{'enabled','yes'},{'model',''},
                {'factor_numerator','1'},{'factor_denominator','1'},{'policy','quality'}}) do lines[#lines+1]=sp..kv[1]..'='..kv[2] end
            for _,key in ipairs({'sdk_root','peak','contrast','saturation','middle_gray'}) do
                if hdr[key]~=nil then lines[#lines+1]=sp..key..'='..tostring(hdr[key]) end
            end
        end
        return runtime.store(table.concat(lines,'\n')..'\n',tostring(slot)..':'..tostring(route.chain)..':'..tostring(policy)..(inject and ':hdr' or ''))
    end
    function runtime.cleanup()
        for _,path in ipairs(files) do os.remove(path) end
        cache,files={},{}
    end
    mp.register_event('shutdown',runtime.cleanup)
    return runtime
end
return M
