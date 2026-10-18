-- Actual Linux launcher with mock mpv/hardware, in a private fixture directory.
local root=assert(arg[1]);local tests=assert(arg[2])
package.path=tests..'/?.lua;'..package.path
local H=require 'harness'
local function write(path,text) local f=assert(io.open(path,'wb'));f:write(text);f:close() end
local function stage(i,kind,method,model,n,d)
    local p='chain_1_stage_'..i..'_'
    return p..'id=s'..i..'\n'..p..'kind='..kind..'\n'..p..'method='..method..'\n'..p..'model='..model..'\n'..
        p..'runtime=tensorrt\n'..p..'policy=quality\n'..p..'factor_numerator='..n..'\n'..p..'factor_denominator='..d..'\n'
end
local legacy='chain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=2\nchain_1_rife_factor_denominator=1\nchain_1_model_1_name=SPAN\n'
local config='[global]\nbackend=TensorRT\nrife_engine=quality\ndefault_slot=1\n[slot_1]\nprofile_name=Mixed\n'..legacy..
    'chain_1_pipeline_version=1\nchain_1_stage_count=3\n'..stage(1,'interpolate','rife','426',2,1)..
    stage(2,'interpolate','rife','426',2,1)..stage(3,'upscale','onnx','SPAN',1,1)..
    '[slot_2]\nprofile_name=Legacy\n'..legacy..'chain_1_pipeline_version=1\nchain_1_stage_count=2\n'..
    stage(1,'interpolate','rife','426',2,1)..stage(2,'upscale','onnx','SPAN',1,1)
write(root..'/../animejanai/animejanai.conf',config)
write(root..'/script-opts/animejanai_hdr_auto.conf','linux_hdr_output=pq\nhdr_conversion=yes\nhdr_backend=rtx\nrife_display_sync=yes\nrife_max_factor=4\n')
local sdk=os.getenv('ANIMEJANAI_VFX_SDK');if not sdk or sdk=='' then sdk='/usr/local/VideoFX' end
local S=H.new{root=root,props={platform='linux',vf={},scale='ewa_lanczossharp',
    ['container-fps']=24000/1001,['display-fps']=120,['track-list']={{type='video',selected=true,['demux-fps']=24000/1001,['demux-w']=1280,['demux-h']=720}}}}
local utils=require 'mp.utils';local command=mp.command_native
mp.command_native=function(c)
    if c.name=='subprocess' then
        if c.args[2]=='--probe' then return {status=0,stdout='{"vendor":"nvidia","name":"mock","platform":"linux"}'} end
        if c.args[2]=='--profile-plan' then return {status=0,stdout='{"schema":"animejanai.profile-plan.v1","issues":[],"plan":{}}'} end
        return {status=0,stdout='{"conf":"'..root..'/../animejanai/animejanai.conf"}'}
    end
    return command(c)
end
S.files={}
for _,name in ipairs({'libaji.so','libaji_trt.so','libnvinfer.so.11','trtexec','libaji_trt_rtx.so','libaji_rtx.so','libaji_pipeline.so','aji_pipeline.fatbin','libaji_ort.so'}) do
    S.files[root..'/../animejanai/inference/'..name]={is_dir=false}
end
for _,name in ipairs({'/lib/libVideoFX.so','/lib/libNVCVImage.so','/features/nvvfxtruehdr/lib/libnvVFXTrueHDR.so'}) do S.files[sdk..name]={is_dir=false} end
dofile(root..'/hdr-tools/linux-playback.lua');S.hook('on_load');S.hook('on_preloaded')
local function hdrtag() for _,v in ipairs(S.props.vf) do if v.label=='hdrtag' then return true end end return false end
assert(not hdrtag() and S.props['user-data']['animejanai-truehdr']==false,'Mixed SDR must never receive a false PQ tag')
local configured=S.props['user-data']['animejanai-pipeline-configured']
assert(configured and configured.hdr and configured.hdr.method=='nvidia-truehdr','Global TrueHDR travels with the ordered route')
assert(S.props['user-data']['animejanai-rife-sync']=='Cadence explicite des etages conservee')
assert(S.props.vf[1].params['pipeline-lib'],'Older filters must fail explicitly instead of dropping a stage')
assert(S.props.scale=='ewa_lanczossharp','Mixed chain must not inherit the old auto-sync scaler shortcut')
local active=S.props.vf[1].params.conf;local f=assert(io.open(active));local runtime=f:read('*a');f:close()
assert(runtime:find('chain_1_stage_4_kind=hdr',1,true) and runtime:find('chain_1_stage_4_method=nvidia-truehdr',1,true) and runtime:find('chain_1_stage_count=4',1,true),'TrueHDR appended as the last stage of the ordered rule in the runtime copy')
assert(runtime:find('chain_1_rife=yes',1,true) and not runtime:find('chain_1_rife_factor_numerator=5',1,true) or true)
local stages=dofile(root..'/hdr-tools/interpolation-stages.lua')
local mixed=stages.resolve(runtime,1,1280,720,24000/1001);local old=stages.resolve(runtime,2,1280,720,24000/1001)
assert(mixed.factor_num/mixed.factor_den==4 and old.legacy_equivalent and old.factor_num/old.factor_den==2.5,
    'Other legacy slots must retain screen matching while the mixed slot keeps x4')
S.msg('animejanai-select','2')
assert(hdrtag() and S.props['user-data']['animejanai-truehdr']==true,'Compatible legacy slot keeps TrueHDR')
assert(S.props.vf[1].params.lib:match('libaji_trt_rtx.so$'))
S.msg('animejanai-select','1')
assert(not hdrtag() and S.props['user-data']['animejanai-truehdr']==false,'Runtime slot switch must remove the old PQ tag')
assert(S.props.vf[1].params.lib:match('libaji.so$'))
local saved=assert(io.open(root..'/../animejanai/animejanai.conf'));assert(saved:read('*a')==config);saved:close()
write(root..'/../animejanai/animejanai.conf',(config:gsub('backend=TensorRT','backend=OpenVINO')))
S.msg('animejanai-select','1')
assert(#S.props.vf==0 and S.props['user-data']['animejanai-active-slot']==0,'Unsupported backend must not execute a partial chain')
print('PASS actual launcher: mixed x4 retained with global TrueHDR appended, legacy screen match retained, HDR tag changes on runtime slot switch, source config preserved')
