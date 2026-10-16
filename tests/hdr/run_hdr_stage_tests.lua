package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'))
local count=0
local function check(name,value) assert(value,name);count=count+1;print('PASS '..name) end
local function write(path,text) local f=assert(io.open(path,'wb'));f:write(text);f:close() end
write(ROOT..'/script-opts/animejanai_hdr_auto.conf','linux_hdr_output=pq\nhdr_conversion=yes\nhdr_backend=mpv\ngrade=yes\ngrade_native_hdr=yes\n')
if arg[1]~='--resume-policy' then
local unrelated='~~/user-shaders/preserved-user-shader.hook'
local S=H.new{root=ROOT,props={platform='linux',['video-dec-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-out-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-target-params']={gamma='pq',['max-luma']=1000},['option-info/target-colorspace-hint-strict']={},['glsl-shaders']={unrelated},['user-data']={['animejanai-pipeline-configured']={explicit=true,hdr_stage_controlled=true,hdr={method='nvidia-truehdr'}}}}}
dofile(ROOT..'/hdr-tools/linux-hdr.lua');S.fire('file-loaded');S.tick()
if arg[1]~='--resume-legacy' then
check('request alone does not tag HDR or run a second conversion',S.props['user-data']['animejanai-pipeline-hdr']==false and #S.props['glsl-shaders']==1)
S.set('video-out-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.tick()
check('only actual PQ BT2020 output confirms the native HDR stage',S.props['user-data']['animejanai-pipeline-hdr']==true and S.props['user-data']['animejanai-linux-hdr'].grade=='rtx')
check('staged TrueHDR suppresses mpv SDR emulation and peak reconstruction',S.props['glsl-shader-opts']['anime-hdr-grade/emulate']=='0.0000' and S.props['hdr-compute-peak']=='no')
check('user shader survives native HDR activation',S.props['glsl-shaders'][1]==unrelated and #S.props['glsl-shaders']==2)
S.set('user-data/animejanai-pipeline-configured',{explicit=true,hdr_stage_controlled=true});S.set('video-out-params',{w=1280,h=720,gamma='bt.1886',primaries='bt.709'});S.tick()
check('removing HDR while retaining ownership keeps conversion off',not S.props['user-data']['animejanai-pipeline-hdr'] and #S.props['glsl-shaders']==1)
end
S.set('user-data/animejanai-pipeline-configured',nil);S.tick()
check('legacy profile transition restores its unchanged global conversion',S.props['user-data']['animejanai-linux-hdr'].grade=='mpv' and #S.props['glsl-shaders']==2)
S.set('user-data/animejanai-pipeline-configured',{explicit=true,hdr_stage_controlled=true,hdr={method='nvidia-truehdr'}});S.set('video-dec-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.set('video-out-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.tick()
check('native HDR source is not claimed as an SDR conversion',not S.props['user-data']['animejanai-pipeline-hdr'] and S.props['video-dec-params'].gamma=='pq')
end
local stages=dofile(ROOT..'/hdr-tools/interpolation-stages.lua')
local conf='[global]\nbackend=TensorRT\n[slot_1]\nhdr_stage_controlled=yes\nchain_1_pipeline_version=1\nchain_1_stage_count=2\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_factor_numerator=2\nchain_1_stage_2_kind=hdr\nchain_1_stage_2_method=nvidia-truehdr\nchain_1_stage_2_runtime=cuda\n'
local route=stages.resolve(conf,1,1280,720,24000/1001)
check('launch policy carries HDR separately without multiplying cadence',route.hdr_stage_controlled and route.hdr.method=='nvidia-truehdr' and route.factor_num==2)
route=stages.resolve('[slot_1]\nhdr_stage_controlled=yes\nchain_1_rife=no\n',1,1280,720,24)
check('profile marker persists when no HDR stage remains',route.hdr_stage_controlled and not route.hdr)
route=stages.resolve('[slot_1]\nhdr_stage_controlled=yes\nchain_1_rife=no\n',1,nil,nil,nil)
check('early routing without video geometry retains HDR ownership',route.hdr_stage_controlled and not route.hdr)
print('PASS '..count..' new HDR stage controller/launch checks; previous suites not replayed')
