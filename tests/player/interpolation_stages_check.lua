-- Pure Lua launch-policy checks; no video/GPU or subprocess builds.
local base=assert(arg[1],'hdr-tools path required')
local stages=dofile(base..'/interpolation-stages.lua')
local sync=dofile(base..'/rife-sync.lua')
local function stage(i,kind,method,model,n,d)
    local p='chain_1_stage_'..i..'_'
    return p..'id=s'..i..'\n'..p..'kind='..kind..'\n'..p..'method='..method..'\n'..p..'model='..model..'\n'..
        p..'runtime=tensorrt\n'..p..'policy=quality\n'..p..'factor_numerator='..n..'\n'..p..'factor_denominator='..d..'\n'
end
local classic='[global]\nbackend=TensorRT\nrife_engine=quality\n\n# preserve this comment\n[slot_1]\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=5\nchain_1_rife_factor_denominator=2\nchain_1_model_1_name=SPAN\n'
local legacy=classic..'chain_1_pipeline_version=1\nchain_1_stage_count=2\n'..stage(1,'interpolate','rife','426',5,2)..stage(2,'upscale','onnx','SPAN',1,1)
assert(stages.resolve(legacy,1,1280,720,24000/1001).legacy_equivalent)
local rewritten=stages.sync_rewrite(legacy,3,1,sync.rewrite)
local route=stages.resolve(rewritten,1,1280,720,24000/1001)
assert(route.legacy_equivalent and route.factor_num==3 and route.factor_den==1)
assert(rewritten:find('\n\n# preserve this comment',1,true))
local mixed=classic..'chain_1_pipeline_version=1\nchain_1_stage_count=3\n'..stage(1,'interpolate','rife','426',2,1)..
    stage(2,'interpolate','nvidia-fruc','',2,1)..'chain_1_stage_2_runtime=cuda\nchain_1_stage_2_policy=fast\n'..stage(3,'upscale','onnx','SPAN',1,1)
route=stages.resolve(mixed,1,1280,720,24000/1001)
assert(route.explicit and not route.legacy_equivalent and route.factor_num==4 and route.factor_den==1)
assert(not stages.resolve(mixed,1).legacy_equivalent,'Unknown preloaded geometry must not permit a false PQ tag')
local preserved=stages.sync_rewrite(mixed,5,2,sync.rewrite)
route=stages.resolve(preserved,1,1280,720,24000/1001)
assert(route.factor_num==4 and route.factor_den==1 and not route.legacy_equivalent)
local conditional=mixed..'chain_1_min_resolution=1920x1080\nchain_2_max_resolution=1280x720\n'
assert(stages.resolve(conditional,1,1280,720,24).legacy_equivalent)
local unsupported=legacy..'chain_1_stage_1_future_option=not-implemented\n'
assert(not stages.resolve(unsupported,1,1280,720,24).legacy_equivalent)
print('PASS ordered launch policy: exact legacy sync rewrite, explicit mixed cadence, conservative HDR, conditional selection, comments and unknown options')
