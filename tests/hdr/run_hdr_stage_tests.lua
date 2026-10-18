-- Global TrueHDR on the ordered route (docs/CONTRAT-PROFILS-V2.md): the launcher publishes the
-- request in the route; only PQ / BT.2020 output confirms it; the renderer never converts twice.
package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'))
local count=0
local function check(name,value) assert(value,name);count=count+1;print('PASS '..name) end
local function write(path,text) local f=assert(io.open(path,'wb'));f:write(text);f:close() end
write(ROOT..'/script-opts/animejanai_hdr_auto.conf','linux_hdr_output=pq\nhdr_conversion=yes\nhdr_backend=rtx\ngrade=yes\ngrade_native_hdr=yes\n')
local unrelated='~~/user-shaders/preserved-user-shader.hook'
local requested={explicit=true,legacy_equivalent=false,hdr={method='nvidia-truehdr',runtime='cuda'}}
local S=H.new{root=ROOT,props={platform='linux',['video-dec-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-out-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-target-params']={gamma='pq',['max-luma']=1000},['option-info/target-colorspace-hint-strict']={},['glsl-shaders']={unrelated},['user-data']={['animejanai-pipeline-configured']=requested}}}
dofile(ROOT..'/hdr-tools/linux-hdr.lua');S.fire('file-loaded');S.tick()
check('request alone is not confirmed and the renderer does not convert',S.props['user-data']['animejanai-pipeline-hdr']==false and not S.props['user-data']['animejanai-mpv-hdr'])
S.set('video-out-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.tick()
check('only actual PQ BT2020 output confirms the native HDR stage',S.props['user-data']['animejanai-pipeline-hdr']==true and S.props['user-data']['animejanai-linux-hdr'].grade=='rtx')
check('confirmed TrueHDR suppresses mpv SDR emulation and peak reconstruction',S.props['glsl-shader-opts']['anime-hdr-grade/emulate']=='0.0000' and S.props['hdr-compute-peak']=='no')
check('user shader survives native HDR activation',S.props['glsl-shaders'][1]==unrelated and #S.props['glsl-shaders']==2)
S.set('user-data/animejanai-pipeline-configured',{explicit=true,legacy_equivalent=false});S.set('video-out-params',{w=1280,h=720,gamma='bt.1886',primaries='bt.709'});S.tick()
check('without the engine stage the global conversion falls back to the renderer',not S.props['user-data']['animejanai-pipeline-hdr'] and S.props['user-data']['animejanai-mpv-hdr']==true and S.props['user-data']['animejanai-linux-hdr'].grade=='mpv')
S.set('user-data/animejanai-pipeline-configured',nil);S.tick()
check('legacy route without TrueHDR keeps the renderer conversion',S.props['user-data']['animejanai-linux-hdr'].grade=='mpv' and #S.props['glsl-shaders']==2)
S.set('user-data/animejanai-truehdr',true);S.tick()
check('legacy route TrueHDR tag selects the engine conversion',S.props['user-data']['animejanai-linux-hdr'].grade=='rtx' and not S.props['user-data']['animejanai-mpv-hdr'])
S.set('user-data/animejanai-truehdr',false);S.set('user-data/animejanai-pipeline-configured',requested);S.set('video-dec-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.set('video-out-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.tick()
check('native HDR source is not claimed as an SDR conversion',not S.props['user-data']['animejanai-pipeline-hdr'] and S.props['video-dec-params'].gamma=='pq')
local stages=dofile(ROOT..'/hdr-tools/interpolation-stages.lua')
local conf='[global]\nbackend=TensorRT\n[slot_1]\nhdr_stage_controlled=yes\nchain_1_pipeline_version=1\nchain_1_stage_count=2\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_factor_numerator=2\nchain_1_stage_2_kind=hdr\nchain_1_stage_2_method=nvidia-truehdr\nchain_1_stage_2_runtime=cuda\n'
local route=stages.resolve(conf,1,1280,720,24000/1001)
check('a profile HDR stage is ignored by the launch policy and does not multiply cadence',route.hdr==nil and route.hdr_stage_controlled==nil and route.factor_num==2 and route.legacy_equivalent)
local text,info=stages.normalize(conf,'linux')
check('normalization removes the HDR stage, the marker and regenerates the legacy keys',info.hdr_dropped==1 and info.hdr_active_dropped==1 and info.markers==1 and not text:find('kind=hdr',1,true) and not text:find('hdr_stage_controlled',1,true) and text:find('chain_1_stage_count=1',1,true) and text:find('chain_1_rife=yes',1,true) and text:find('chain_1_rife_factor_numerator=2',1,true))
local phantom='[global]\nbackend=TensorRT\n[slot_3]\nprofile_name=Ghost\nchain__min_resolution=0x0\nchain__rife=no\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_kind=upscale\nchain_1_stage_1_method=onnx\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_model=SPAN\nchain_1_rife=yes\nchain_1_model_1_name=OLD\n'
text,info=stages.normalize(phantom,'linux')
check('phantom rules and stale legacy keys are dropped, the projection follows the stages',info.phantom==2 and info.mirrors==2 and not text:find('chain__',1,true) and text:find('chain_1_rife=no',1,true) and text:find('chain_1_model_1_name=SPAN',1,true) and not text:find('OLD',1,true) and text:find('profile_name=Ghost',1,true))
local legacy_only='[global]\nbackend=TensorRT\n# kept\n[slot_1]\nprofile_name=Old\nchain_1_rife=yes\nchain_1_model_1_name=SPAN\n'
text,info=stages.normalize(legacy_only,'linux')
check('a legacy-only file is returned byte for byte',text==legacy_only and info.sections==0)
route=stages.resolve('[slot_1]\nhdr_stage_controlled=yes\nchain_1_rife=no\n',1,nil,nil,nil)
check('early routing without video geometry carries no HDR ownership',route.hdr_stage_controlled==nil and route.hdr==nil)
print('PASS '..count..' global HDR controller/launch checks')
