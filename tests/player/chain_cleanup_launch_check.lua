local root=assert(arg[1]);local tests=assert(arg[2]);local player=assert(arg[3]);local mode=arg[4] or 'linux'
package.path=tests..'/?.lua;'..package.path;local H=require 'harness'
local function write(p,s)local f=assert(io.open(p,'wb'));f:write(s);f:close()end
local config='[global]\nbackend=TensorRT\ndefault_slot=1\n[slot_1]\nprofile_name=SDK-free HDR\nhdr_stage_controlled=yes\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=hdr\nchain_1_stage_1_kind=hdr\nchain_1_stage_1_method=mpv\nchain_1_stage_1_runtime=gpu-next\n'
write(root..'/../animejanai/animejanai.conf',config);write(root..'/script-opts/animejanai_hdr_auto.conf','hdr_conversion=no\nhdr_backend=none\nlinux_hdr_output=pq\n')
local S=H.new{root=root,props={platform=mode,vf={},['container-fps']=24,['video-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['track-list']={{type='video',selected=true,['demux-fps']=24,['demux-w']=1280,['demux-h']=720}},['user-data']={['animejanai-hardware']={vendor='nvidia',conf=root..'/../animejanai/animejanai.conf',conf_active=root..'/../animejanai/animejanai.conf',inference_dir=root..'/../animejanai/inference'}}}}
S.files={}
local count=0;local function check(name,value)assert(value,name);count=count+1;print('PASS '..mode..': '..name)end
if mode=='linux' then
 local utils=require 'mp.utils';local command=mp.command_native
 mp.command_native=function(c)
  if c.name=='subprocess' then
   if c.args[2]=='--profile-plan' then return {status=0,stdout='{"schema":"animejanai.profile-plan.v1","issues":[]}'} end
   if c.args[2]=='--probe' then return {status=0,stdout='{"vendor":"nvidia","name":"mock","platform":"linux"}'} end
   return {status=0,stdout='{"conf":"'..root..'/../animejanai/animejanai.conf"}'}
  end
  return command(c)
 end
 dofile(root..'/hdr-tools/linux-playback.lua');S.hook('on_load');S.hook('on_preloaded')
elseif mode=='windows' then
 dofile(player..'/user-scripts/animejanai_slot.lua');S.hook('on_load')
elseif mode=='macos' then
 dofile(assert(arg[5]));S.hook('on_preloaded')
end
local data=S.props['user-data']
check('HDR-only profile stays selected without an inference engine or SDK',data['animejanai-active-slot']==1 and #S.props.vf==0)
local cfg=data['animejanai-pipeline-configured']
check('profile HDR stage is ignored: the conversion is a global setting (CONTRAT-PROFILS-V2)',(cfg==nil or cfg.hdr==nil) and S.props['video-params'].gamma=='bt.1886')
if mode=='linux' then S.msg('animejanai-select','0')
elseif mode=='windows' then S.msg('aji-slot','0')
elseif mode=='macos' then S.msg('animejanai-select','0') end
check('Off clears the profile HDR request',data['animejanai-active-slot']==0 and not data['animejanai-pipeline-configured'])
if mode=='linux' then S.msg('animejanai-select','1002');check('removed built-in cannot be activated',data['animejanai-active-slot']==0)
elseif mode=='windows' then S.msg('aji-slot','1002');check('removed built-in cannot be activated',data['animejanai-active-slot']==0) end
print('PASS '..count..' new '..mode..' launch checks; no GPU/model execution')
