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
local function ids(sec,prefix,suffix)
    local seen,out={},{}
    for key in pairs(sec) do local n=tonumber(key:match('^'..prefix..'(%d+)'..suffix))
        if n and n>0 and not seen[n] then seen[n]=true;out[#out+1]=n end
    end
    table.sort(out);return out
end
local function number(s,k,d) return tonumber(s[k]) or d end
local function enabled(v) return (v or ''):lower()=='yes' end
local function legacy(sec,chain,global)
    local p='chain_'..chain..'_'
    if sec[p..'pipeline_version']~='1' then return false end
    local model_ids=ids(sec,p..'model_','_');local models={}
    -- Match the existing backend's sequential model-index interpretation.
    for i=1,#model_ids do models[i]=p..'model_'..i..'_' end
    local model,rife,rife_index=0,false,nil
    local count=number(sec,p..'stage_count',-1)
    if count<0 or count>16 or count%1~=0 then return false end
    local backend=(global.backend or 'TensorRT'):lower()
    local policy=(global.rife_engine or ''):lower();policy=(policy=='quality' or policy=='old') and 'quality' or 'fast'
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
local function resolution(value,maximum)
    local a,b=(value or ''):match('^([^x]+)x([^x]+)$');a=a and a:lower()=='inf' and math.huge or tonumber(a) or 0;b=b and b:lower()=='inf' and math.huge or tonumber(b) or 0
    if maximum then if a==0 then a=math.huge end;if b==0 then b=math.huge end end
    return a*b
end
function M.resolve(text,slot,w,h,fps)
    local all=parse(text);local sec=all['slot_'..tostring(slot)]
    if not sec then return {explicit=false,legacy_equivalent=true} end
    local chains=ids(sec,'chain_','_');local selected
    local hdr_owned=enabled(sec.hdr_stage_controlled)
    for _,i in ipairs(chains) do local cp='chain_'..i..'_'
        for j=1,math.min(16,number(sec,cp..'stage_count',0)) do
            if sec[cp..'stage_'..j..'_kind']=='hdr' then hdr_owned=true end
        end
    end
    w,h,fps=tonumber(w),tonumber(h),tonumber(fps)
    if w and h and fps and w>0 and h>0 and fps>0 then
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            local maxfps=number(sec,p..'max_fps',math.huge);if maxfps==0 then maxfps=math.huge end
            if resolution(sec[p..'min_resolution'],false)<=w*h and w*h<=resolution(sec[p..'max_resolution'],true) and
                number(sec,p..'min_fps',0)<=fps and fps<=maxfps then selected=i;break end
        end
    else
        -- Before on_preloaded there may be no selected stream geometry yet.
        -- Defer HDR for a potentially mixed rule; legacy-only banks unchanged.
        for _,i in ipairs(chains) do local p='chain_'..i..'_'
            if sec[p..'pipeline_version'] and not legacy(sec,i,all.global or {}) then
                return {explicit=true,legacy_equivalent=false,unknown=true,hdr_stage_controlled=hdr_owned}
            end
        end
        return {explicit=false,legacy_equivalent=true,hdr_stage_controlled=hdr_owned}
    end
    if not selected then return {explicit=false,legacy_equivalent=true,hdr_stage_controlled=hdr_owned} end
    local p='chain_'..selected..'_';local explicit=sec[p..'pipeline_version']~=nil
    local equivalent=not explicit or legacy(sec,selected,all.global or {})
    local route={explicit=explicit,legacy_equivalent=equivalent,chain=selected,factor_num=1,factor_den=1,stages={},hdr_stage_controlled=hdr_owned}
    if explicit then for i=1,math.min(16,number(sec,p..'stage_count',0)) do local sp=p..'stage_'..i..'_'
        if enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']=='interpolate' then
            local n,d=number(sec,sp..'factor_numerator',1),number(sec,sp..'factor_denominator',1)
            route.stages[#route.stages+1]={method=sec[sp..'method'],numerator=n,denominator=d}
            route.factor_num=route.factor_num*n;route.factor_den=route.factor_den*d
        elseif enabled(sec[sp..'enabled'] or 'yes') and sec[sp..'kind']=='hdr' then
            route.hdr={method=sec[sp..'method'],runtime=sec[sp..'runtime'],peak=number(sec,sp..'peak',1000)}
        end
    end end
    if not explicit and enabled(sec[p..'rife']) then
        route.factor_num=number(sec,p..'rife_factor_numerator',1)
        route.factor_den=number(sec,p..'rife_factor_denominator',1)
    end
    return route
end
-- Keep stage factors synchronized ONLY for a genuinely equivalent legacy rule.
-- True mixed chains retain their explicit factors. The source file is untouched.
function M.sync_rewrite(text,p,q,rewrite_legacy)
    local all=parse(text);local replacements={}
    for section,sec in pairs(all) do if section:match('^slot_%d+$') then
        for _,i in ipairs(ids(sec,'chain_','_')) do local same,index=legacy(sec,i,all.global or {})
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
return M
