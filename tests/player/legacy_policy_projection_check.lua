-- Targeted launch contract only: no GPU, models, video or subprocess builds.
local base=assert(arg[1],'hdr-tools path required')
local dir=assert(arg[2],'existing temporary fixture directory required')
local stages=dofile(base..'/interpolation-stages.lua')
local sync=dofile(base..'/rife-sync.lua')
local checks=0
local function check(name,value) assert(value,name);checks=checks+1;print('PASS '..name) end
local function stage(i,kind,method,runtime,options)
 local p='chain_1_stage_'..i..'_'
 local text=p..'id=s'..i..'\n'..p..'kind='..kind..'\n'..p..'method='..method..'\n'..p..'runtime='..runtime..'\n'..p..'policy=quality\n'
 for k,v in pairs(options or {}) do text=text..p..k..'='..v..'\n' end
 return text
end
local function bank(runtime,method,origin,order,frames)
 local definitions={
  down={'resize',method,{target_height='720',legacy_geometry=origin}},
  rife={'interpolate','rife',{model='426',factor_numerator='2'}},
  up={'upscale','onnx',{model='SPAN',frames=frames or '0'}}
 }
 local text='[global]\nbackend='..runtime..'\nrife_engine=fast\n# source preserved\n[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=3\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=2\nchain_1_rife_before_upscale='..(order[3]=='rife' and 'no' or 'yes')..'\nchain_1_model_1_name=SPAN\nchain_1_model_1_resize_height_before_upscale=720\nchain_1_model_1_frames='..(frames or '0')..'\n'
 for i,name in ipairs(order) do local d=definitions[name];text=text..stage(i,d[1],d[2],runtime,d[3]) end
 return text
end
local function route(text,platform)return stages.resolve(text,1,1920,1080,24,platform or 'linux')end
local text=bank('tensorrt','spline36','linux:tensorrt',{'down','rife','up'})
local result=route(text)
check('projectable stage Quality owns policy despite hidden global Fast',result.legacy_equivalent and result.runtime_policy=='quality')
check('wrong historical method cannot silently project',not route(text:gsub('method=spline36','method=bilinear')).legacy_equivalent)
check('resize runtime must match following model',not route(text:gsub('chain_1_stage_1_runtime=tensorrt','chain_1_stage_1_runtime=cuda')).legacy_equivalent)
local win=bank('migraphx','spline36','windows:migraphx',{'down','rife','up'})
check('Windows MIGraphX Spline36 projects only on matching current geometry',route(win,'windows').legacy_equivalent and not route(win,'linux').legacy_equivalent)
local linux=bank('migraphx','bilinear','linux:migraphx',{'down','rife','up'})
check('Linux MIGraphX Bilinear cannot become Windows Spline36',route(linux,'linux').legacy_equivalent and not route(linux,'windows').legacy_equivalent)
check('RIFE then resize cannot be hoisted silently',not route(bank('tensorrt','spline36','linux:tensorrt',{'rife','down','up'})).legacy_equivalent)
check('resize then temporal model then RIFE remains projectable',route(bank('tensorrt','spline36','linux:tensorrt',{'down','up','rife'},'3')).legacy_equivalent)
check('frames contract matches C sharp exact0/1 before RIFE',not route(bank('tensorrt','spline36','linux:tensorrt',{'down','rife','up'},'0.0')).legacy_equivalent)
check('new independent downscale never uses historical projection',not route(text:gsub('chain_1_stage_1_legacy_geometry=linux:tensorrt\n','')).legacy_equivalent)
local rewritten=stages.sync_rewrite(text,3,1,sync.rewrite,'linux')
check('cadence rewrite maps back to original RIFE index after resize',rewritten:find('chain_1_stage_2_factor_numerator=3',1,true) and route(rewritten).legacy_equivalent and route(rewritten).factor_num==3)
local function read(path)local f=assert(io.open(path,'rb'));local value=f:read('*a');f:close();return value end
local source=dir..'/source.conf';local file=assert(io.open(source,'wb'));file:write(text);file:close()
local shutdown={}
local mp={get_property_native=function(key)if key=='pid' then return 123 end end,register_event=function(event,fn)assert(event=='shutdown');shutdown[#shutdown+1]=fn end}
local runtime=stages.runtime_configs(mp,{getpid=function()return 123 end},dir,'test-profile')
local private=assert(runtime.prepare(source,text,result,1))
check('private config changes global policy and preserves source',private~=source and read(source)==text and read(private):find('rife_engine=quality',1,true) and not read(private):find('rife_engine=fast',1,true))
check('identical content and selected rule reuse the same private file',runtime.prepare(source,text,result,1)==private)
local changed=assert(runtime.prepare(source,text..'# saved edit\n',result,1))
check('changed content creates an immutable new private file',changed~=private and read(private):find('# saved edit',1,true)==nil)
local slot2=assert(runtime.prepare(source,text,result,2))
check('cache distinguishes selected slots',slot2~=private)
local fast=text:gsub('policy=quality','policy=fast');local fast_route=route(fast)
check('Fast profile with matching global uses its original config',runtime.prepare(source,fast,fast_route,1)==source)
local bad=route(text:gsub('chain_1_stage_3_kind=upscale','chain_1_stage_3_kind=interpolate'))
check('nonprojectable graph never receives a policy override',not bad.legacy_equivalent and runtime.prepare(source,text,bad,1)==source)
local source_mp={get_property_native=function(key)
 if key=='track-list' then return {{type='video',selected=true,['demux-w']=1920,['demux-h']=1080,['demux-fps']=24}} end
end}
local w,h,fps=stages.source(source_mp)
check('preloaded demux geometry available before video params',w==1920 and h==1080 and fps==24)
for _,fn in ipairs(shutdown) do fn() end
check('shutdown removes only owned runtime files',io.open(private)==nil and io.open(changed)==nil and io.open(slot2)==nil and read(source)==text)
os.remove(source)
print('PASS '..checks..' projection/policy/cache checks; no engine execution')
