package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'),'set AJ_ROOT to a scratch copy of portable_config')
local pass,fail=0,0
local function check(n,c,x) if c then pass=pass+1 else fail=fail+1 print('FAIL: '..n..(x and (' -> '..tostring(x)) or '')) end end
local function labels(S) local t={} for _,f in ipairs(S.props.vf) do t[#t+1]=f.label end return table.concat(t,',') end
local function has_shader(S) for _,p in ipairs(S.props['glsl-shaders']) do if p:match('anime%-hdr%-grade') then return true end end return false end
local function read(p) local f=io.open(p,'r'); if not f then return nil end; local s=f:read('*a'); f:close(); return s end
local function write(p,d) local f=io.open(p,'w'); f:write(d); f:close() end
os.execute('mkdir -p '..ROOT..'/../animejanai '..ROOT..'/cache')
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
local saved=read(conf)
local stats=ROOT..'/../animejanai/currentanimejanai.log'
local rtxconf=ROOT..'/../animejanai/animejanai-rtx.conf'
os.remove(ROOT..'/cache/animejanai-rtx-state.json')

-- Pure functions
local R=dofile(ROOT..'/hdr-tools/rtx-stage.lua')
local want={hdr=true,vsr=true,w=3840,h=2160,quality=2,contrast=100,saturation=100,middle_gray=50,peak=1000}
check('echo format', R.echo(want)=='RTX Video Settings: hdr=yes vsr=yes target=3840x2160 vsr_quality=2 contrast=100 saturation=100 middle_gray=50 peak=1000', R.echo(want))
check('text has one key per line', R.text(want):match('\nhdr=yes\nvsr=yes\ntarget=3840x2160\n')~=nil, R.text(want))
check('no target: no upscale', R.echo({hdr=true,vsr=true}):match('vsr=no target=0x0')~=nil, R.echo({hdr=true,vsr=true}))
check('values clamped like the engine', R.echo({peak=5000,quality=9,middle_gray=1}):match('vsr_quality=4 .*middle_gray=10 peak=2000')~=nil)
local a=R.applied('x\n'..R.echo(want)..'\n\n1. Applied Model: m\n2. Applied RTX Video: Super Resolution (quality 2) and TrueHDR (peak 1000 nits);    New Video Resolution: 3840x2160\n')
check('applied: both stages', a.hdr and a.vsr and a.echo==R.echo(want))
a=R.applied('Upscale Profile: Off\nNo Chains Activated\n')
check('applied: nothing', not a.hdr and not a.vsr and a.echo==nil)

local function boot(api)
  for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
  write(conf,(saved:gsub('render_api=%w+','render_api='..api)))
  local S=H.new{root=ROOT,vendor='nvidia'}
  S.files={}
  dofile(ROOT..'/user-scripts/animejanai_hdr_auto.lua')
  return S
end
local function start(S)
  S.fire('start-file'); S.fire('file-loaded')
  S.set('user-data/animejanai-active-slot',4)
  S.set('video-params',{w=1920,h=1080,gamma='bt.1886',primaries='bt.709',par=1})
  S.set('video-dec-params',{w=1920,h=1080,gamma='bt.1886'})
  S.set('user-data/display-info/uid','DISP1'); S.set('user-data/display-info/hdr-status','on'); S.set('user-data/display-info/hdr-supported',true)
  S.set('display-width',3840); S.set('display-height',2160)
  S.set('video-out-params',{w=3840,h=2160,gamma='bt.1886',par=1,rotate=0})
  S.set('video-target-params',{gamma='pq',['max-luma']=1000})
  S.tick(4)
end

-- Vulkan: settings written, frames tagged, no D3D11 filter
local S=boot('vulkan')
start(S)
check('vulkan: settings file', read(rtxconf)==R.text(want), read(rtxconf))
check('vulkan: tagged before the engine reports', labels(S)=='aji,hdrtag', labels(S))
check('vulkan: no D3D11 tail', not labels(S):match('truehdr') and not labels(S):match('bridge'), labels(S))
check('vulkan: display remembered', (read(ROOT..'/cache/animejanai-rtx-state.json') or ''):match('3840')~=nil)

-- Engine configured with these settings: grade on top of TrueHDR
write(stats,'Upscale Profile: 4\n'..R.echo(want)..'\n\n1. Applied RTX Video: TrueHDR (peak 1000 nits)\n')
S.files[stats]={mtime=os.time()+5}
S.set('video-out-params',{w=3840,h=2160,gamma='pq',par=1,rotate=0}); S.tick(3)
check('vulkan: tag kept', labels(S)=='aji,hdrtag', labels(S))
check('vulkan: grade attached', has_shader(S))
check('vulkan: no peak detection on TrueHDR', S.props['hdr-compute-peak']=='no', S.props['hdr-compute-peak'])
check('vulkan: no reconfigure when settings match', not table.concat(S.log,'\n'):match('vf%-command aji slot'))

-- Engine configured with other settings: asked to configure again
write(stats,'Upscale Profile: 4\n'..R.echo({hdr=true,vsr=true,w=3840,h=2160,peak=800})..'\n\n1. Applied RTX Video: TrueHDR (peak 800 nits)\n')
S.tick(2)
check('vulkan: reconfigure on changed settings', table.concat(S.log,'\n'):match('vf%-command aji slot')~=nil)

-- No active chain: MPV converts, tag removed
write(stats,'Upscale Profile: Off\nNo Chains Activated\n')
S.set('video-out-params',{w=1920,h=1080,gamma='bt.1886',par=1,rotate=0}); S.tick(3)
check('no chain: tag removed', labels(S)=='aji', labels(S))
check('no chain: MPV conversion', S.props['target-trc']=='pq' and has_shader(S), S.props['target-trc'])

-- Next session starts from the remembered display state
S=boot('vulkan')
S.fire('start-file')
check('next session: settings before any window', read(rtxconf)==R.text(want), read(rtxconf))

-- The Vulkan engine library is selected only when it is installed
for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
write(conf,(saved:gsub('render_api=%w+','render_api=vulkan')))
S=H.new{root=ROOT,vendor='nvidia'}
local policy=dofile(ROOT..'/hdr-tools/gpu-policy.lua')
local utils=package.loaded['mp.utils']
check('engine: not installed', not policy.select_engine(mp,utils,'nvidia',policy.options()) and policy.engine_lib==nil)
local vf=select(1,policy.configure_filters(S.props.vf,'nvidia','c.conf',4,true))
check('engine: stock library kept', vf[1].params.lib==nil, vf[1].params.lib)
S.files={[ROOT..'/../animejanai/inference/aji_trt_rtx.dll']={},[ROOT..'/../animejanai/inference/aji_rtx.dll']={}}
check('engine: installed', policy.select_engine(mp,utils,'nvidia',policy.options()))
vf=select(1,policy.configure_filters(S.props.vf,'nvidia','c.conf',4,true))
check('engine: Vulkan library selected', tostring(vf[1].params.lib):match('aji_trt_rtx%.dll$')~=nil, vf[1].params.lib)
check('engine: never on AMD', not policy.select_engine(mp,utils,'amd',policy.options()))

-- D3D11: the engine gets no settings, the D3D11 tail is used
S=boot('d3d11')
check('d3d11: settings file removed', read(rtxconf)==nil)
start(S)
check('d3d11: usual tail', labels(S):match('bridge,truehdr$')~=nil, labels(S))
check('d3d11: no tag', not labels(S):match('hdrtag'), labels(S))

write(conf,saved)
os.remove(stats); os.remove(rtxconf); os.remove(ROOT..'/cache/animejanai-rtx-state.json')
print(pass..' passed, '..fail..' failed')
os.exit(fail==0 and 0 or 1)
