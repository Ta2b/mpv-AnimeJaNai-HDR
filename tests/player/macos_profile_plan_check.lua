-- Real macOS controller, async resolver failures and immutable policy snapshot.
local root,repo=assert(arg[1]),assert(arg[2])
package.path=repo..'/tests/hdr/?.lua;'..package.path;local H=require 'harness'
local data,bundle=root..'/../animejanai',root..'/../bundle'
local getenv=os.getenv;os.getenv=function(k)
    if k=='ANIMEJANAI_DATA_DIR' then return data elseif k=='ANIMEJANAI_BUNDLE' then return bundle
    elseif k=='ANIMEJANAI_CACHE' then return root..'/../cache' end
    return getenv(k)
end
local function write(p,s)local f=assert(io.open(p,'wb'));assert(f:write(s));f:close()end
local function read(p)local f=assert(io.open(p,'rb'));local s=f:read('*a');f:close();return s end
local config='[ global ]\n backend = CoreMLNative\n apple_device = CPU\n rife_engine = fast\n default_slot = 1\n apple_auto_profile = no\n[ slot_1 ]\n profile_name = Quality\n chain_1_rife = yes\n chain_1_rife_model = 426\n chain_1_rife_factor_numerator = 2\n chain_1_pipeline_version = 1\n chain_1_stage_count = 1\n chain_1_stage_1_id = r\n chain_1_stage_1_kind = interpolate\n chain_1_stage_1_method = rife\n chain_1_stage_1_runtime = coremlnative\n chain_1_stage_1_model = 426\n chain_1_stage_1_factor_numerator = 2\n chain_1_stage_1_policy = quality\n'
local conf=data..'/animejanai.conf';write(conf,config)
local S=H.new{root=root,props={platform='macos',vf={},['container-fps']=24,['track-list']={{type='video',selected=true,['demux-fps']=24,['demux-w']=1280,['demux-h']=720}}}}
S.files={[bundle..'/AnimeJaNaiPlatform']={},[bundle..'/animejanai/inference/libaji_ort.dylib']={},[data..'/onnx']={is_dir=true},[data..'/rife']={is_dir=true}}
local utils=require 'mp.utils';local queue,aborted={},{}
mp.command_native_async=function(command,callback) local id={};queue[#queue+1]={command=command,callback=callback,id=id};return id end
mp.abort_async_command=function(id)aborted[id]=true end
local response
utils.parse_json=function(text)if text=='malformed' then return nil end;return response end
local function plan(issues)
 return {schema='animejanai.profile-plan.v1',slot=1,rule=1,issues=issues or {},plan={schema='animejanai.profile-plan.v1',legacy_compatible=true,can_execute=not issues}}
end
local function complete(item,value,ok)
 response=value;item.callback(ok~=false,{status=0,stdout='response'})
end
local function flag(item,name)
 for i,v in ipairs(item.command.args)do if v==name then return item.command.args[i+1]end end
end
dofile(repo..'/installer/macos/config/scripts/animejanai_mac.lua')
if arg[3]=='hdr-only' then
    write(conf,'[global]\nbackend=CoreMLNative\n[slot_1]\nprofile_name=HDR\nchain_1_max_resolution=1x1\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=h\nchain_1_stage_1_kind=hdr\nchain_1_stage_1_method=mpv\nchain_1_stage_1_runtime=gpu-next\nchain_1_stage_1_policy=quality\n')
    S.hook('on_preloaded');assert(#queue==1 and flag(queue[1],'--rule')=='0')
    complete(queue[1],{schema='animejanai.profile-plan.v1',slot=1,rule=0,issues={},profile_hdr={schema='animejanai.profile-plan.v1',can_execute=true}})
    assert(#S.props.vf==0 and S.props['user-data']['animejanai-active-slot']==1 and S.props['user-data']['animejanai-pipeline-configured'].hdr.method=='mpv')
    S.fire('shutdown');print('PASS no matching inference rule requests rule0; profile mpv HDR remains active without engine filter');return
end
S.hook('on_preloaded');assert(#queue==1 and #S.props.vf==0,'selection must await canonical plan asynchronously')
local request=queue[1];local snapshot=flag(request,'--conf');assert(snapshot~=conf and read(snapshot)==config)
assert(flag(request,'--slot')=='1' and flag(request,'--rule')=='1' and flag(request,'--platform')=='macos')
assert(flag(request,'--models-dir')==data..'/onnx' and flag(request,'--rife-dir')==data..'/rife' and flag(request,'--inference-dir')==bundle..'/animejanai/inference')
-- An edit while the helper runs must not change the bank used by that request.
write(conf,config:gsub('profile_name = Quality','profile_name = Edited'))
complete(request,plan());assert(#S.props.vf==1 and S.props.vf[1].params.device=='CPU')
local private=S.props.vf[1].params.conf;assert(private~=snapshot and read(private):find('rife_engine=quality',1,true),'stage Quality must own private legacy policy')
assert(read(private):find('profile_name = Quality',1,true) and read(conf):find('profile_name = Edited',1,true))
local active=S.props.vf[1]
-- Missing exact model and unknown schema keep the active filter/profile.
S.msg('animejanai-select','1');complete(queue[#queue],plan({'Missing model: requested.onnx'}));assert(S.props.vf[1]==active)
S.msg('animejanai-select','1');local future=plan();future.schema='future';complete(queue[#queue],future);assert(S.props.vf[1]==active)
S.msg('animejanai-select','1');local bad=queue[#queue];bad.callback(true,{status=0,stdout='malformed'});assert(S.props.vf[1]==active)
-- A timeout aborts the async process; its late callback cannot apply a filter.
S.msg('animejanai-select','1');local timed=queue[#queue];S.tick(1);assert(aborted[timed.id] and S.props.vf[1]==active)
complete(timed,plan());assert(S.props.vf[1]==active)
-- New selection/off cancels an earlier in-flight request without starting another helper.
S.msg('animejanai-select','1');local stale=queue[#queue];local calls=#queue
S.msg('animejanai-select','0');assert(aborted[stale.id] and #queue==calls and #S.props.vf==0)
complete(stale,plan());assert(#S.props.vf==0 and S.props['user-data']['animejanai-active-slot']==0)
S.files[bundle..'/AnimeJaNaiPlatform']=nil;S.msg('animejanai-select','1');assert(#queue==calls and #S.props.vf==0)
S.fire('shutdown');assert(io.open(snapshot)==nil and io.open(private)==nil and read(conf):find('Edited',1,true))
print('PASS real macOS controller: selected canonical plan, frozen source/private Quality, exact paths, missing model/schema/JSON/timeout/stale/off/helper errors, source preserved; no GPU')
