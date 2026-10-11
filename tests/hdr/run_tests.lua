package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'),'set AJ_ROOT to a scratch copy of portable_config')
local pass,fail=0,0
local function check(name,cond,extra)
  if cond then pass=pass+1 else fail=fail+1; print('FAIL: '..name..(extra and (' -> '..tostring(extra)) or '')) end
end
local function has_shader(S) for _,p in ipairs(S.props['glsl-shaders']) do if p:match('anime%-hdr%-grade') then return true end end return false end
local function labels(S) local t={} for _,f in ipairs(S.props.vf) do t[#t+1]=f.label end return table.concat(t,',') end

local function boot(vendor, extra)
  for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
  local S=H.new{root=ROOT,vendor=vendor,props=extra}
  dofile(ROOT..'/user-scripts/animejanai_hdr_auto.lua')
  return S
end
local function play(S, src)
  S.fire('start-file'); S.fire('file-loaded')
  S.set('video-params',{w=1920,h=1080,gamma=src or 'bt.1886',primaries='bt.709',par=1})
  S.set('video-dec-params',{w=1920,h=1080,gamma=src or 'bt.1886'})
  S.set('user-data/display-info/uid','DISP1'); S.set('user-data/display-info/hdr-status','on'); S.set('user-data/display-info/hdr-supported',true)
  S.set('display-width',3840); S.set('display-height',2160)
  S.set('video-out-params',{w=2560,h=1440,gamma=src=='pq' and 'pq' or 'bt.1886',par=1,rotate=0})
  S.set('video-target-params',{gamma='pq',['max-luma']=1000})
  S.tick(4)
end

-- 1. NVIDIA, SDR, RTX TrueHDR
local S=boot('nvidia')
check('nvidia single detection', S.detect_calls==1, S.detect_calls)
play(S)
check('conversion on: configured mode', S.acquire_mode=='follow', S.acquire_mode)
check('rtx tail', labels(S):match('bridge,truehdr$')~=nil, labels(S))
local th=S.props.vf[#S.props.vf]
check('rtx vsr scale 1.5', tonumber(th.params.scale) and math.abs(tonumber(th.params.scale)-1.5)<1e-6, th.params.scale)
check('rtx display peak', S.props['target-peak']=='1000', S.props['target-peak'])
check('rtx oled contrast', S.props['target-contrast']=='inf')
check('rtx gamut p3', S.props['target-gamut']=='display-p3')
check('rtx keeps target-trc auto', S.props['target-trc']=='auto', S.props['target-trc'])
check('rtx no shader before TrueHDR PQ confirmed', not has_shader(S))
S.set('video-out-params',{w=3840,h=2160,gamma='pq',par=1,rotate=0}); S.tick(3)
check('rtx shader active', has_shader(S))
check('rtx: no peak detection on TrueHDR', S.props['hdr-compute-peak']=='no', S.props['hdr-compute-peak'])
local o=S.props['glsl-shader-opts']
check('rtx in_max = peak', o['anime-hdr-grade/in_max']=='1000.0000', o['anime-hdr-grade/in_max'])
check('rtx area gain 1', o['anime-hdr-grade/area_gain']=='1.0000')
check('rtx spec gain', o['anime-hdr-grade/spec_gain']=='1.6000', o['anime-hdr-grade/spec_gain'])
check('rtx vibrance', o['anime-hdr-grade/vibrance']=='0.2000')
check('rtx gamut param', o['anime-hdr-grade/gamut_p3']=='1.0000')
check('rtx paper untouched', S.props['hdr-reference-white']=='203')
check('rtx highlight pivot half peak', o['anime-hdr-grade/paper']=='500.0000', o['anime-hdr-grade/paper'])
check('rtx shadow knee from paper white', o['anime-hdr-grade/shadow_knee']=='50.7500', o['anime-hdr-grade/shadow_knee'])
local n=#S.sets; S.tick(3)
local churn=0; for i=n+1,#S.sets do if S.sets[i]~='vf' then churn=churn+1 end end
check('rtx steady state: no property churn', churn==0, churn)
S.msg('animejanai-grade-toggle')
check('Ctrl+G 1: natural preset keeps the shader', has_shader(S))
check('Ctrl+G 1: natural vibrance', S.props['glsl-shader-opts']['anime-hdr-grade/vibrance']=='0.1000', S.props['glsl-shader-opts']['anime-hdr-grade/vibrance'])
S.msg('animejanai-grade-toggle')
check('Ctrl+G 2: off removes shader', not has_shader(S))
check('Ctrl+G 2: keeps TrueHDR', labels(S):match('truehdr')~=nil)
check('Ctrl+G 2: keeps display peak', S.props['target-peak']=='1000')
S.msg('animejanai-grade-toggle')
check('Ctrl+G 3: back to custom', has_shader(S) and S.props['glsl-shader-opts']['anime-hdr-grade/vibrance']=='0.2000')
check('subtitles at subtitle_white', S.props['sub-hdr-peak']=='200' and S.props['image-subs-hdr-peak']=='200', S.props['sub-hdr-peak'])
S.msg('animejanai-hdr-status')
check('diagnostic mentions grading', (S.osd[#S.osd] or ''):match('Grading : sur sortie RTX TrueHDR')~=nil, S.osd[#S.osd])
S.fire('end-file')
check('end-file removes shader', not has_shader(S))
check('end-file restores peak', S.props['target-peak']=='auto')
check('end-file restores gamut', S.props['target-gamut']=='auto')
check('end-file clears opts', next(S.props['glsl-shader-opts'])==nil)

-- 1c. live reload from the Manager
S=boot('nvidia'); play(S); S.set('video-out-params',{w=3840,h=2160,gamma='pq',par=1,rotate=0}); S.tick(3)
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
local cf=io.open(conf); local saved=cf:read('*a'); cf:close()
cf=io.open(conf,'w'); cf:write((saved:gsub('vibrance_rtx=[%d.]+','vibrance_rtx=0.55'):gsub('peak_nvidia=%d+','peak_nvidia=800'))); cf:close()
S.msg('animejanai-reload-options')
cf=io.open(conf,'w'); cf:write(saved); cf:close()
check('reload: new vibrance applied live', S.props['glsl-shader-opts']['anime-hdr-grade/vibrance']=='0.5500', S.props['glsl-shader-opts']['anime-hdr-grade/vibrance'])
check('reload: new display peak applied live', S.props['target-peak']=='800', S.props['target-peak'])
check('reload: OSD confirmation', (S.osd[#S.osd] or ''):match('appliques')~=nil)

-- 1b. coordinator is not spawned every second once the lease is settled
S=boot('nvidia'); play(S); local c0=S.coord; S.tick(30)
check('coordinator calls reduced', S.coord-c0<=7, S.coord-c0)
S.set('user-data/display-info/hdr-status','off'); S.windows='off'; S.tick(2)
check('coordinator asked again on display change', S.coord-c0>=1)
check('hdr off after display change: no shader', not has_shader(S))

-- 1d. calibration pattern
S=boot('nvidia'); play(S); S.set('video-out-params',{w=3840,h=2160,gamma='pq',par=1,rotate=0}); S.tick(3)
S.msg('animejanai-calibration')
local function has(path) for _,p in ipairs(S.props['glsl-shaders']) do if p:match(path) then return true end end end
check('calibration: pattern shader on', has('anime%-hdr%-calibration'))
check('calibration: grade off under the pattern', not has('anime%-hdr%-grade'))
check('calibration: labels shown', (S.overlay or ''):match('Eclats')~=nil)
S.msg('animejanai-calibration')
check('calibration off: grade back', has('anime%-hdr%-grade') and not has('anime%-hdr%-calibration'))
check('calibration off: labels removed', S.overlay==nil)
check('oled display: abl param', S.props['glsl-shader-opts']['anime-hdr-grade/abl']=='0.6000', S.props['glsl-shader-opts']['anime-hdr-grade/abl'])
S.msg('animejanai-calibration')
local ok_end=pcall(S.fire,'end-file')
check('calibration: end-file closes the pattern', ok_end and S.overlay==nil)

-- 2. NVIDIA, native HDR source
S=boot('nvidia'); play(S,'pq')
check('native hdr: no truehdr', not labels(S):match('truehdr'), labels(S))
check('native hdr: display peak', S.props['target-peak']=='1000')
check('native hdr: no grade by default', not has_shader(S))

-- 3. Windows HDR off
S=boot('nvidia'); S.windows='off'; play(S)
check('hdr off: no shader', not has_shader(S))
check('hdr off: peak auto', S.props['target-peak']=='auto')
check('hdr off: no truehdr', not labels(S):match('truehdr'), labels(S))

-- 4. AMD, SDR, MPV HDR
S=boot('amd'); play(S)
check('amd: enable mode', S.acquire_mode=='enable', S.acquire_mode)
check('amd: no truehdr', not labels(S):match('truehdr'), labels(S))
check('amd: target-trc pq', S.props['target-trc']=='pq')
check('amd: paper white', S.props['hdr-reference-white']=='203')
check('amd: peak auto kept', S.props['target-peak']=='auto', S.props['target-peak'])
check('amd: contrast auto', S.props['target-contrast']=='auto')
check('amd: gamut p3', S.props['target-gamut']=='display-p3')
check('amd: shader', has_shader(S))
o=S.props['glsl-shader-opts']
check('amd: peak from target', o['anime-hdr-grade/peak']=='1000.0000', o['anime-hdr-grade/peak'])
check('amd: in_max paper', o['anime-hdr-grade/in_max']=='203.0000')
check('amd: spec gain to peak', math.abs(tonumber(o['anime-hdr-grade/spec_gain'])-(1+0.85*(1000/203-1)))<1e-3, o['anime-hdr-grade/spec_gain'])
check('amd: vibrance', o['anime-hdr-grade/vibrance']=='0.3000')
S.set('video-target-params',{gamma='pq',['max-luma']=600}); S.tick(2)
o=S.props['glsl-shader-opts']
check('amd: follows 600-nit display', o['anime-hdr-grade/peak']=='600.0000', o['anime-hdr-grade/peak'])
check('amd: tail is amd videosr', labels(S):match('amdsr')~=nil, labels(S))
S.fire('end-file')
check('amd end: trc restored', S.props['target-trc']=='auto')

-- 4b. AMD on a 250-nit display: paper white follows
S=boot('amd'); play(S); S.set('video-target-params',{gamma='pq',['max-luma']=250}); S.tick(3)
check('low peak: paper = 0.75 peak', S.props['hdr-reference-white']=='188', S.props['hdr-reference-white'])
check('low peak: shader paper', S.props['glsl-shader-opts']['anime-hdr-grade/paper']=='188.0000', S.props['glsl-shader-opts']['anime-hdr-grade/paper'])

-- 5. Other shaders and options preserved
S=boot('amd',{['glsl-shaders']={'~~/shaders/other.hook'},['glsl-shader-opts']={['other/x']='1'}}); play(S)
check('other shader kept', S.props['glsl-shaders'][1]=='~~/shaders/other.hook' and #S.props['glsl-shaders']==2)
check('other opt kept', S.props['glsl-shader-opts']['other/x']=='1')
S.fire('end-file')
check('other shader kept after end', #S.props['glsl-shaders']==1 and S.props['glsl-shader-opts']['other/x']=='1')

-- 5b. SDR -> HDR conversion disabled
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
local f=io.open(conf); local saved=f:read('*a'); f:close()
f=io.open(conf,'w'); f:write((saved:gsub('hdr_conversion=yes','hdr_conversion=no'):gsub('\nmode=follow','\nmode=enable'))); f:close()
S=boot('nvidia'); play(S)
check('conversion off: no truehdr', not labels(S):match('truehdr'), labels(S))
check('conversion off: no shader', not has_shader(S))
check('conversion off: display peak still set', S.props['target-peak']=='1000')
check('conversion off: Windows HDR follow', S.acquire_mode=='follow', S.acquire_mode)
local acquire_mode
for _,l in ipairs(S.log) do end
S.msg('animejanai-hdr-status')
check('conversion off: diagnostic', (S.osd[#S.osd] or ''):match('conversion SDR %-> HDR : desactivee')~=nil)
S=boot('amd'); play(S)
check('conversion off amd: no pq forcing', S.props['target-trc']=='auto')
check('conversion off amd: no shader', not has_shader(S))
f=io.open(conf,'w'); f:write(saved); f:close()

-- 6. unknown options in conf
local unknown=false; for _,l in ipairs(S.log) do if l:match('unknown option') then unknown=l end end
check('conf has no unknown option', not unknown, unknown)

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail==0 and 0 or 1)
