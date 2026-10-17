local root=assert(arg[1]);package.path=assert(arg[2])..'/?.lua;'..package.path
local H=require 'harness';local stages=dofile(root..'/hdr-tools/interpolation-stages.lua');local router=dofile(root..'/hdr-tools/pipeline-hdr.lua');local grade=dofile(root..'/hdr-tools/hdr-grade.lua')
local function write(path,text)local f=assert(io.open(path,'wb'));f:write(text);f:close()end
local count=0;local function check(name,value)assert(value,name);count=count+1;print('PASS '..name)end
local function stage(c,i,kind,method,runtime)
 local p='chain_'..c..'_stage_'..i..'_';return p..'id=s'..c..'_'..i..'\n'..p..'kind='..kind..'\n'..p..'method='..method..'\n'..p..'runtime='..runtime..'\n'
end
local pure='[global]\nbackend=TensorRT\ndefault_slot=1\n[slot_1]\nprofile_name=HDR only\nhdr_stage_controlled=yes\nchain_1_pipeline_version=1\nchain_1_stage_count=1\n'..stage(1,1,'hdr','mpv','gpu-next')..'chain_1_stage_1_contrast=120\nchain_1_stage_1_saturation=90\nchain_1_stage_1_middle_gray=55\n'
if arg[3]=='--retired-only' then
 write(root..'/script-opts/animejanai_hdr_auto.conf','conversion_in_profiles=yes\nlinux_hdr_output=pq\ngrade=yes\n')
 local options=dofile(root..'/hdr-tools/gpu-policy.lua').options()
 check('retired global conversion remains off even though old defaults were enabled',options.conversion_in_profiles and not options.hdr_conversion and not router.options(options,{hdr_stage_controlled=false}).hdr_conversion)
 check('an explicit mpv HDR stage still activates conversion after retirement',router.options(options,stages.resolve(pure,1,1280,720,24)).hdr_conversion)
 return
end
if arg[3]=='--native-only' then
 local S=H.new{root=root,props={platform='linux',vf={},['container-fps']=24,
 ['video-dec-params']={w=1280,h=720,gamma='pq',primaries='bt.2020'},['video-params']={w=1280,h=720,gamma='pq',primaries='bt.2020'},
 ['video-out-params']={w=1280,h=720,gamma='pq',primaries='bt.2020'},['video-target-params']={gamma='pq',['max-luma']=1000},['option-info/target-colorspace-hint-strict']={},
 ['user-data']={['animejanai-active-slot']=1,['animejanai-pipeline-configured']=stages.resolve(pure,1,1280,720,24)}}}
 dofile(root..'/hdr-tools/linux-hdr.lua');S.fire('file-loaded');S.tick()
 local emulate=S.props['glsl-shader-opts']['anime-hdr-grade/emulate']
 check('native HDR is not converted again',not S.props['user-data']['animejanai-mpv-hdr'] and (emulate==nil or emulate=='0.0000'))
 return
end
local route=stages.resolve(pure,1,1280,720,24)
check('pure mpv HDR is render-only, SDK-free and cadence-neutral',route.legacy_equivalent and route.inference_empty and route.factor_num==1 and route.hdr.method=='mpv')
check('HDR-only routing remains available before geometry or GPU engine initialization',stages.resolve(pure,1,nil,nil,nil).inference_empty)
local legacy='chain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=5\nchain_1_rife_factor_denominator=2\nchain_1_model_1_name=SPAN\nchain_1_model_1_resize_height_before_upscale=720\n'
local composite='[global]\nbackend=TensorRT\nrife_engine=quality\n[slot_1]\n'..legacy..'chain_1_pipeline_version=1\nchain_1_stage_count=4\n'..stage(1,1,'resize','spline36','tensorrt')..'chain_1_stage_1_target_height=720\nchain_1_stage_1_legacy_geometry=linux:tensorrt\n'..stage(1,2,'interpolate','rife','tensorrt')..'chain_1_stage_2_model=426\nchain_1_stage_2_factor_numerator=5\nchain_1_stage_2_factor_denominator=2\n'..stage(1,3,'upscale','onnx','tensorrt')..'chain_1_stage_3_model=SPAN\n'..stage(1,4,'hdr','mpv','gpu-next')
route=stages.resolve(composite,1,1280,720,24)
check('historical Spline36 before RIFE and mpv HDR retain original rational routing',route.legacy_equivalent and route.factor_num==5 and route.factor_den==2)
local shared=pure..'chain_1_min_resolution=1920x1080\nchain_2_pipeline_version=1\nchain_2_stage_count=0\n';route=stages.resolve(shared,1,1280,720,24)
check('unique HDR belongs to the profile after its selected resolution rule',route.chain==2 and route.hdr.method=='mpv' and route.inference_empty)
check('duplicate inactive HDR is refused before rendering',stages.resolve(pure..'chain_2_pipeline_version=1\nchain_2_stage_count=1\n'..stage(2,1,'hdr','mpv','gpu-next')..'chain_2_stage_1_enabled=no\n',1,1280,720,24).error~=nil)
write(root..'/../animejanai/animejanai.conf',pure)
write(root..'/script-opts/animejanai_hdr_auto.conf','linux_hdr_output=pq\nhdr_conversion=no\nhdr_backend=none\ngrade=yes\nrtx_contrast=33\nrtx_saturation=44\nrtx_middle_gray=22\n')
local unrelated='~~/user-shaders/user-preserved.hook'
local S=H.new{root=root,props={platform='linux',vf={},['video-dec-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['video-out-params']={w=1280,h=720,gamma='bt.1886',primaries='bt.709'},['container-fps']=24,['video-target-params']={gamma='bt.1886'},['option-info/target-colorspace-hint-strict']={},['glsl-shaders']={unrelated},['user-data']={['animejanai-active-slot']=1,['animejanai-pipeline-configured']=stages.resolve(pure,1,1280,720,24)}}}
dofile(root..'/hdr-tools/linux-hdr.lua');S.fire('file-loaded');S.tick()
check('request alone cannot tag SDR or attach the conversion shader on SDR output',S.props['video-out-params'].gamma=='bt.1886' and #S.props['glsl-shaders']==1 and not S.props['user-data']['animejanai-mpv-hdr'])
S.set('video-target-params',{gamma='pq',['max-luma']=1000});S.tick()
check('negotiated PQ activates render conversion and preserves the user shader',S.props['user-data']['animejanai-mpv-hdr'] and #S.props['glsl-shaders']==2 and S.props['glsl-shaders'][1]==unrelated and S.props['video-out-params'].gamma=='bt.1886')
local before_opts={};for k,v in pairs(S.props['glsl-shader-opts'])do before_opts[k]=v end
local policy=dofile(root..'/hdr-tools/gpu-policy.lua');local reference=policy.options();reference.hdr_conversion=true;reference.hdr_backend='mpv';reference.rtx_contrast=120;reference.rtx_saturation=90;reference.rtx_middle_gray=55
local expected=grade.plan(reference,{vendor='nvidia',backend='mpv',source='sdr',output_hdr=true,target_gamma='pq',target_peak=1000,enabled=true,original={}},nil)
check('stage route produces the exact acquired conversion parameters with unchanged shader arithmetic',grade.same_map(before_opts,grade.shader_opts({},expected.params)))
S.set('user-data/animejanai-pipeline-configured',{explicit=true,hdr_stage_controlled=true});S.tick()
check('removing the stage removes only its shader and does not resurrect old global conversion',#S.props['glsl-shaders']==1 and S.props['glsl-shaders'][1]==unrelated and not S.props['user-data']['animejanai-mpv-hdr'])
S.set('user-data/animejanai-pipeline-configured',stages.resolve(pure,1,1280,720,24));S.set('video-dec-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.set('video-params',{w=1280,h=720,gamma='pq',primaries='bt.2020'});S.tick()
check('native HDR is not converted again',not S.props['user-data']['animejanai-mpv-hdr'] and (S.props['glsl-shader-opts']['anime-hdr-grade/emulate']==nil or S.props['glsl-shader-opts']['anime-hdr-grade/emulate']=='0.0000'))
print('PASS '..count..' new HDR render/route checks; existing conclusive suites not replayed')
