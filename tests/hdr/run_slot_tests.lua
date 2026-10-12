package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'),'set AJ_ROOT to a scratch copy of portable_config')
local pass,fail=0,0
local function check(n,c,x) if c then pass=pass+1 else fail=fail+1 print('FAIL: '..n..(x and (' -> '..tostring(x)) or '')) end end
local function labels(S) local t={} for _,f in ipairs(S.props.vf) do t[#t+1]=f.label end return table.concat(t,',') end
-- write a bank and conf variants
local bank=ROOT..'/../animejanai/animejanai.conf'
os.execute('mkdir -p '..ROOT..'/../animejanai')
local f=io.open(bank,'w'); f:write('[global]\nbackend=DirectML\ndefault_slot=3\n[slot_1]\nprofile_name=1080p - AMD\nchain_1_rife=no\n[slot_2]\nprofile_name=4K - AMD\n[slot_3]\nprofile_name=2K - AMD\n[slot_4]\nprofile_name=New Profile\n'); f:close()
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
local cf=io.open(conf); local saved=cf:read('*a'); cf:close()
local function boot(vendor,amf)
  for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
  local c=io.open(conf,'w'); c:write((saved:gsub('frame_generation=%w+','frame_generation='..(amf and 'amf' or 'off')))); c:close()
  local S=H.new{root=ROOT,vendor=vendor,props={['container-fps']=23.976,pause=false}}
  S.props['user-data/animejanai-hardware']=nil
  dofile(ROOT..'/user-scripts/hardware_auto.lua')
  dofile(ROOT..'/user-scripts/animejanai_slot.lua')
  return S
end
local S=boot('amd',true)
S.msg('animejanai-select','3'); S.tick(2)
check('amd amf: filters appended', labels(S):match('amfinput,amf')~=nil, labels(S))
check('amd amf: label', tostring(mp.get_property_native('user-data/animejanai-interpolation')):match('AMD AMF x2')~=nil, mp.get_property_native('user-data/animejanai-interpolation'))
S.msg('animejanai-select','1'); S.tick(2)
local n=0; for _ in labels(S):gmatch('amf,') do n=n+1 end
check('amd amf: no duplicates after slot change', select(2,labels(S):gsub('@?amfinput',''))==1, labels(S))
S.msg('animejanai-select','0'); S.tick(2)
check('amd amf: also with AnimeJaNai off', labels(S):match('amf')~=nil, labels(S))
S.msg('animejanai-select','4'); S.tick(2)
check('empty slot refused', (S.osd[#S.osd] or ''):match('vide')~=nil, S.osd[#S.osd])
S=boot('amd',false); S.msg('animejanai-select','3'); S.tick(2)
check('amd off: no amf', not labels(S):match('amf'), labels(S))
S=boot('nvidia',true); S.msg('animejanai-select','3'); S.tick(2)
check('nvidia: amf never', not labels(S):match('amf'), labels(S))
-- preload: the filter starts on the bank's default slot, then on the last selected one
S=boot('nvidia',false)
local f0=io.open(bank,'w'); f0:write('[global]\nbackend=TensorRT\ndefault_slot=3\n[slot_1]\nprofile_name=1080p\n[slot_2]\nprofile_name=4K\n[slot_3]\nprofile_name=2K\n'); f0:close()
S.hook('on_load')
check('preload: default slot', S.props.vf[1].params.slot=='3', S.props.vf[1].params.slot)
local sets=#S.sets
S.msg('animejanai-select','2'); S.tick(2)
local rebuilt=false; for i=sets+1,#S.sets do if S.sets[i]=='vf' then rebuilt=true end end
check('runtime slot switch: no vf rebuild', not rebuilt)
check('runtime slot switch uses vf-command', table.concat(S.log,'\n'):match('vf%-command aji slot')~=nil)
S.hook('on_load')
check('preload: next file keeps the selected slot', S.props.vf[1].params.slot=='2', S.props.vf[1].params.slot)
-- Profile 9 is the start-up profile of new installs: it must stay reachable from the keyboard
f0=io.open(bank,'w'); f0:write('[global]
backend=TensorRT
default_slot=9
[slot_4]
profile_name=2K Performance
[slot_5]
profile_name=New Profile
[slot_9]
profile_name=Performance
'); f0:close()
S.msg('animejanai-select','4'); S.tick(2)
S.msg('animejanai-select','9'); S.tick(2)
check('profile 9 selectable', mp.get_property_native('user-data/animejanai-active-slot')==9, mp.get_property_native('user-data/animejanai-active-slot'))
S.msg('animejanai-select','5'); S.tick(2)
check('empty profile 5 refused', (S.osd[#S.osd] or ''):match('vide')~=nil and mp.get_property_native('user-data/animejanai-active-slot')==9, S.osd[#S.osd])
S.msg('animejanai-select','10'); S.tick(2)
check('profile numbers above 9 ignored', mp.get_property_native('user-data/animejanai-active-slot')==9)
-- RIFE matched to the display
local c=io.open(conf,'w'); c:write((saved:gsub('rife_display_sync=%w+','')..'\nrife_display_sync=yes\nrife_max_factor=3\n')); c:close()
local rb='[global]\nbackend=TensorRT\ndefault_slot=3\n[slot_3]\nprofile_name=2K\nchain_1_rife=yes\nchain_1_rife_factor_numerator=2\nchain_1_rife_factor_denominator=1\n'
local f1=io.open(bank,'w'); f1:write(rb); f1:close()
for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
S=H.new{root=ROOT,vendor='nvidia',props={['container-fps']=23.976,['display-fps']=60,pause=false}}
dofile(ROOT..'/user-scripts/hardware_auto.lua'); dofile(ROOT..'/user-scripts/animejanai_slot.lua')
S.hook('on_load'); S.hook('on_preloaded')
check('rife sync: filter uses the runtime conf', tostring(S.props.vf[1].params.conf):match('animejanai%-runtime%.conf$')~=nil, S.props.vf[1].params.conf)
local rt=io.open(ROOT..'/../animejanai/animejanai-runtime.conf'):read('*a')
check('rife sync: 5/2 written for 60 Hz', rt:match('chain_1_rife_factor_numerator=5') and rt:match('chain_1_rife_factor_denominator=2'), rt)
check('rife sync: status for diagnostic', tostring(mp.get_property_native('user-data/animejanai-rife-sync')):match('x5/2')~=nil)
local sets=#S.sets
S.msg('animejanai-select','3'); S.tick(2)
local rebuilt=false; for i=sets+1,#S.sets do if S.sets[i]=='vf' then rebuilt=true end end
check('rife sync: slot switch does not rebuild', not rebuilt)
S.props['display-fps']=165; S.hook('on_preloaded')
check('rife sync: 165 Hz without exact factor keeps the bank', tostring(S.props.vf[1].params.conf):match('animejanai%.conf$')~=nil, S.props.vf[1].params.conf)
f1=io.open(bank,'w'); f1:write(rb:gsub('default_slot=3','default_slot=3\ndisplay_rate_match=yes')); f1:close()
S.props['display-fps']=60; S.hook('on_preloaded')
check('rife sync: off while automatic refresh is active', tostring(S.props.vf[1].params.conf):match('animejanai%.conf$')~=nil and tostring(mp.get_property_native('user-data/animejanai-rife-sync')):match('automatique')~=nil)
-- Real player: no video track is selected yet in on_preloaded, so container-fps is unavailable.
f1=io.open(bank,'w'); f1:write(rb); f1:close()
for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
S=H.new{root=ROOT,vendor='nvidia',props={['display-fps']=120,pause=false,
  ['track-list']={{type='video',albumart=true,['demux-fps']=1},{type='audio'},{type='video',albumart=false,['demux-fps']=23.976}}}}
dofile(ROOT..'/user-scripts/hardware_auto.lua'); dofile(ROOT..'/user-scripts/animejanai_slot.lua')
S.hook('on_load')
local ok,err=pcall(S.hook,'on_preloaded')
check('rife sync: no error without container-fps', ok, err)
check('rife sync: rate read from the video track (5/2 at 120 Hz, max 3)', tostring(mp.get_property_native('user-data/animejanai-rife-sync')):match('x5/2')~=nil, mp.get_property_native('user-data/animejanai-rife-sync'))
S.props['track-list']=nil; S.props['display-fps']=nil; os.remove(ROOT..'/cache/animejanai-display.json')
ok,err=pcall(S.hook,'on_preloaded')
check('rife sync: no error without any rate', ok, err)
check('rife sync: unknown rates keep the bank', tostring(S.props.vf[1].params.conf):match('animejanai%.conf$')~=nil, S.props.vf[1].params.conf)
local c=io.open(conf,'w'); c:write(saved); c:close()
print(pass..' passed, '..fail..' failed')
os.exit(fail==0 and 0 or 1)
