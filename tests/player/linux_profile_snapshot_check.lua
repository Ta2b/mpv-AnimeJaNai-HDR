-- Real Linux launcher + mpv mock; no GPU, models or native subprocess runs.
local root,tests=assert(arg[1]),assert(arg[2])
package.path=tests..'/?.lua;'..package.path
local H=require 'harness'
local function write(path,text)local f=assert(io.open(path,'wb'));f:write(text);f:close()end
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a');f:close();return s end
local conf=root..'/../animejanai/animejanai.conf'
local initial='[global]\nbackend=TensorRT\nrife_engine=quality\ndefault_slot=1\n[slot_1]\nprofile_name=Snapshot\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=2\nchain_1_model_1_name=SPAN\n'
local edited=initial:gsub('rife_engine=quality','rife_engine=fast')..'# user edit at the same path\n'
write(conf,initial)
write(root..'/script-opts/animejanai_hdr_auto.conf','hdr_conversion=no\nrife_display_sync=no\n')
local inf=root..'/../animejanai/inference'
local S=H.new{root=root,props={platform='linux',vf={},['container-fps']=24,
 ['track-list']={{type='video',selected=true,['demux-fps']=24,['demux-w']=1280,['demux-h']=720}},
 ['user-data']={['animejanai-hardware']={vendor='nvidia',backend='tensorrt',conf=conf,conf_active=conf,inference_dir=inf}}}}
S.files={};for _,name in ipairs({'libaji.so','libaji_trt.so','libnvinfer.so.11','trtexec'})do S.files[inf..'/'..name]={}end
local command=mp.command_native;local observed={}
mp.command_native=function(c)
 if c.name=='subprocess' and c.args[2]=='--profile-plan' then
  local path;for i,v in ipairs(c.args)do if v=='--conf' then path=c.args[i+1]end end
  assert(path~=conf,'resolver must consume an immutable copy')
  if #observed==0 then write(conf,edited)end -- concurrent save after snapshot
  observed[#observed+1]={path=path,text=read(path)}
  return {status=0,stdout='{"schema":"animejanai.profile-plan.v1","issues":[],"plan":{}}'}
 end
 return command(c)
end
dofile(root..'/hdr-tools/linux-playback.lua')
S.hook('on_load')
S.hook('on_preloaded') -- selected demux geometry is available at this hook
assert(#observed==1 and observed[1].text==initial)
local quality=S.props.vf[1].params.conf
assert(read(quality)==initial and S.props.vf[1].params['rife-policy']=='quality')
assert(read(conf)==edited,'original save must be preserved')
S.msg('aji-slot','1') -- direct selection, without reload-options/preload=true
local fast=S.props.vf[1].params.conf
assert(fast~=quality and fast~=conf and read(fast)==edited)
assert(S.props.vf[1].params['rife-policy']=='fast' and #observed==2)
assert(read(quality)==initial,'a live old snapshot is immutable')
S.msg('aji-slot','1')
assert(S.props.vf[1].params.conf==fast and #observed==2,'identical content reuses snapshot/plan')
local stages=dofile(root..'/hdr-tools/interpolation-stages.lua')
for alias,expected in pairs({old='quality',quality='quality',new='fast',fast='fast',other='auto'})do
 assert(stages.temporal_policy('[global]\nrife_engine='..alias)==expected)
end
assert(stages.temporal_policy(initial,{runtime_policy='fast'})=='fast','selected rule policy owns the projection')
S.fire('shutdown')
assert(io.open(quality)==nil and io.open(fast)==nil and read(conf)==edited)
print('PASS Linux snapshot: single version for resolver/native, same-path direct edit reload, stable reuse, policies/aliases, original and old snapshots preserved, owned cleanup only')
