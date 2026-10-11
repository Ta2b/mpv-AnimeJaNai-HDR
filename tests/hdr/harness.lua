-- Minimal mpv mock to run the real controller scripts.
local H = {}
function H.new(opts)
  local S = {props={}, events={}, observers={}, timers={}, messages={}, osd={}, log={}, sets={}, root=opts.root, vendor=opts.vendor or 'nvidia'}
  local P = S.props
  P['vf'] = {{label='aji', name='animejanai', enabled=true, params={conf=opts.root..'/../animejanai/animejanai.conf', slot='1002'}}}
  P['glsl-shaders'] = {}; P['glsl-shader-opts'] = {}
  for k,v in pairs({['target-trc']='auto',['target-peak']='auto',['target-contrast']='auto',['target-gamut']='auto',['hdr-compute-peak']='auto',
      ['hdr-reference-white']='203',['tone-mapping']='bt.2390',['inverse-tone-mapping']='no',pid=1234}) do P[k]=v end
  for k,v in pairs(opts.props or {}) do P[k]=v end
  local function split(name)
    local t={} for part in name:gmatch('[^/]+') do t[#t+1]=part end return t end
  local function getn(name)
    if P[name]~=nil then return P[name] end
    local parts=split(name); local v=P[parts[1]]
    for i=2,#parts do if type(v)~='table' then return nil end v=v[parts[i]] end
    return v
  end
  local function notify(name)
    for _,o in ipairs(S.observers) do if o.name==name or name:sub(1,#o.name+1)==o.name..'/' then o.fn(o.name,getn(o.name)) end end
  end
  local function setn(name,v)
    local parts=split(name)
    if #parts==1 then P[name]=v else
      local t=P[parts[1]] or {}; P[parts[1]]=t
      for i=2,#parts-1 do t[parts[i]]=t[parts[i]] or {}; t=t[parts[i]] end
      t[parts[#parts]]=v
    end
    S.sets[#S.sets+1]=name; notify(parts[1])
  end
  S.set=setn
  local mp = {}
  -- Like mpv: an unavailable property returns nil plus an error text (a second value that
  -- breaks tonumber(mp.get_property_native(...))).
  mp.get_property_native=function(n) local v=getn(n); if v==nil then return nil,'property unavailable' end; return v end
  mp.get_property=function(n) local v=getn(n); if v==nil then return nil end; if type(v)=='table' then return 'table' end; return tostring(v) end
  mp.get_property_number=function(n,d) return tonumber(getn(n)) or d end
  mp.get_property_bool=function(n) return getn(n)==true end
  mp.set_property=function(n,v) setn(n,v); return true end
  mp.set_property_native=function(n,v) setn(n,v); return true end
  mp.set_property_bool=mp.set_property
  mp.command_native=function(c)
    if c[1]=='expand-path' then return (c[2]:gsub('^~~',S.root)) end
    if c.name=='subprocess' then
      local exe=c.args[1]
      if exe=='powershell.exe' then
        local script=c.args[#c.args]
        for i,a in ipairs(c.args) do if a=='-File' then script=c.args[i+1] end end
        if script:match('detect%-gpu') then
          S.detect_calls=(S.detect_calls or 0)+1
          local id=S.vendor=='nvidia' and 'PCI_VEN_10DE' or 'PCI_VEN_1002'
          local name=S.vendor=='nvidia' and 'NVIDIA GeForce RTX 4070 Ti' or 'AMD Radeon RX 9070 XT'
          return {status=0,stdout='[{"Name":"'..name..'","PNPDeviceID":"'..id..'","Status":"OK"}]'}
        end
        S.bank_calls=(S.bank_calls or 0)+1
        return {status=0,stdout='{"conf":"'..S.root..'/../animejanai/animejanai.conf"}'}
      end
      if exe:match('hdr%-coordinator') then
        S.coord=(S.coord or 0)+1
        if c.args[2]=='acquire' then S.acquire_mode=c.args[6] end
        if c.args[2]=='release' then return {status=0,stdout='{"state":"off","reason":"released"}'} end
        return {status=0,stdout='{"state":"'..(S.windows or 'on')..'","reason":"leased","supported":true,"attempts":1,"owned":true}'}
      end
      return {status=0,stdout=''}
    end
    return nil
  end
  mp.command_native_async=function(c,cb) local r=mp.command_native(c); if cb then cb(true,r,nil) end; return {} end
  mp.abort_async_command=function() end
  mp.commandv=function(cmd,a,b,...)
    S.log[#S.log+1]=table.concat({cmd,tostring(a),tostring(b)},' ')
    if cmd=='vf' then
      local vf=P.vf
      if a=='append' then
        local label,rest=b:match('^@([^:]+):(.*)$'); local name=rest:match('^([^=:]+)')
        local params={}; for k,v in rest:gmatch('([%w%-]+)=([^:]+)') do params[k]=v end
        vf[#vf+1]={label=label,name=name,enabled=true,params=params}; notify('vf'); return true
      elseif a=='remove' then
        for i,f in ipairs(vf) do if '@'..f.label==b then table.remove(vf,i); notify('vf'); return true end end
        return false
      end
    end
    if cmd=='script-message' then S.messages[#S.messages+1]=a; if type(S.messages[a])=='function' then S.messages[a](b,...) end end
    return true
  end
  mp.command=function() return true end
  mp.register_event=function(e,fn) S.events[e]=S.events[e] or {}; table.insert(S.events[e],fn) end
  mp.observe_property=function(n,_,fn) S.observers[#S.observers+1]={name=n,fn=fn} end
  mp.add_timeout=function(t,fn) local tm={fn=fn,once=true}; tm.kill=function() tm.dead=true end; S.timers[#S.timers+1]=tm; return tm end
  mp.add_periodic_timer=function(t,fn) local tm={fn=fn}; tm.kill=function() tm.dead=true end; S.timers[#S.timers+1]=tm; return tm end
  mp.register_script_message=function(n,fn) S.messages[n]=fn end
  mp.osd_message=function(t) S.osd[#S.osd+1]=t end
  S.hooks={}
  mp.add_hook=function(name,prio,fn) S.hooks[name]=S.hooks[name] or {}; table.insert(S.hooks[name],fn) end
  mp.add_key_binding=function() end
  mp.create_osd_overlay=function() local o={}; o.update=function(self) S.overlay=self.data end; o.remove=function() S.overlay=nil end; return o end
  S.clock=0
  mp.get_time=function() return S.clock end
  local msgm={}; for _,l in ipairs({'info','warn','error','verbose','debug'}) do msgm[l]=function(s) S.log[#S.log+1]=l..': '..tostring(s) end end
  mp.msg=msgm
  local options={read_options=function(o,id)
    local f=io.open(S.root..'/script-opts/'..id..'.conf'); if not f then return end
    for line in f:lines() do
      local k,v=line:match('^%s*([%w_]+)=(.*)$')
      if k and o[k]~=nil then
        if type(o[k])=='boolean' then o[k]=(v=='yes') elseif type(o[k])=='number' then o[k]=tonumber(v) else o[k]=v end
      elseif k then S.log[#S.log+1]='unknown option '..k end
    end f:close() end}
  local utils={parse_json=function(s)
      -- tiny JSON for our fixtures
      s=s:gsub('^%s+','')
      if s=='' then return nil end
      local lua=s:gsub('%[','{'):gsub('%]','}'):gsub('"([%w_]+)":','["%1"]='):gsub('\\\\','\\')
      local f=loadstring and loadstring('return '..lua) or load('return '..lua)
      local ok,v=pcall(f); return ok and v or nil end,
    format_json=function(t) local parts={} for k,v in pairs(t) do parts[#parts+1]='"'..k..'":"'..tostring(v)..'"' end return '{'..table.concat(parts,',')..'}' end,
    join_path=function(a,b) return a..'/'..b end, getpid=function() return 1234 end,
    readdir=function() return {} end, file_info=function() return nil end}
  package.loaded['mp']=mp; package.loaded['mp.msg']=msgm; package.loaded['mp.options']=options; package.loaded['mp.utils']=utils
  _G.mp=mp
  if opts.computer ~= nil then
    local real=os.getenv
    os.getenv=function(k) if k=='COMPUTERNAME' then return opts.computer end return real(k) end
  end
  function S.fire(e,arg) for _,fn in ipairs(S.events[e] or {}) do fn(arg or {}) end end
  function S.tick(n) for _=1,(n or 3) do S.clock=S.clock+1; local list=S.timers; S.timers={}
      for _,tm in ipairs(list) do if not tm.dead then tm.fn(); if not tm.once then S.timers[#S.timers+1]=tm end end end end end
  function S.hook(name) for _,fn in ipairs(S.hooks[name] or {}) do fn() end end
  function S.msg(name,...) S.messages[name](...) end
  return S
end
return H
