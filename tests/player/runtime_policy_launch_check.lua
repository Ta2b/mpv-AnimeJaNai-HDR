-- One Windows controller fixture: selected-rule deferral, private policy and switch.
local root,tests,controller=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.path=tests..'/?.lua;'..package.path;local H=require 'harness'
local function write(p,s)local f=assert(io.open(p,'wb'));f:write(s);f:close()end
local function read(p)local f=assert(io.open(p,'rb'));local s=f:read('*a');f:close();return s end
local config='[global]\nbackend=TensorRT\nrife_engine=fast\ndefault_slot=1\n[slot_1]\nprofile_name=Quality\nchain_1_max_resolution=1280x720\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=2\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=quality\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_model=426\nchain_1_stage_1_factor_numerator=2\nchain_1_stage_1_policy=quality\nchain_2_min_resolution=1920x1080\nchain_2_pipeline_version=1\nchain_2_stage_count=1\nchain_2_stage_1_id=unsupported\nchain_2_stage_1_kind=resize\nchain_2_stage_1_method=area\nchain_2_stage_1_runtime=cuda\nchain_2_stage_1_target_height=720\n[slot_2]\nprofile_name=Fast\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=2\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=fast\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime=tensorrt\nchain_1_stage_1_model=426\nchain_1_stage_1_factor_numerator=2\nchain_1_stage_1_policy=fast\n'
local conf=root..'/../animejanai/animejanai.conf';write(conf,config)
local S=H.new{root=root,props={platform='windows',['user-data']={['animejanai-hardware']={vendor='nvidia',conf=conf,conf_active=conf}}}}
dofile(controller)
S.hook('on_load')
assert(S.props['user-data']['animejanai-active-slot']==1,'Unknown rule must keep requested slot until preloaded')
S.props['track-list']={{type='video',selected=true,['demux-fps']=24,['demux-w']=1280,['demux-h']=720}}
S.hook('on_preloaded');S.tick()
local private=S.props.vf[1].params.conf
assert(private~=conf and read(private):find('rife_engine=quality',1,true),'Actual selected Quality rule must use private policy')
assert(S.props['user-data']['animejanai-active-slot']==1 and read(conf)==config)
S.msg('aji-slot','2');S.tick()
assert(S.props.vf[1].params.conf==conf and S.props['user-data']['animejanai-active-slot']==2,'Fast switch must restore matching source global')
S.msg('aji-slot','1');S.tick()
assert(S.props.vf[1].params.conf==private,'Same selection must reuse cached Quality config')
S.fire('shutdown')
assert(io.open(private)==nil and read(conf)==config,'Shutdown only cleans runtime copies')
print('PASS Windows controller: unknown rule deferred, demux selects Quality, private policy, Fast switch, cache and shutdown; no GPU')
