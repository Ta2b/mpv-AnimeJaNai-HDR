local ROOT=assert(os.getenv('AJ_ROOT'))
local H=dofile(os.getenv('AJ_TEST_DIR')..'/harness.lua')
local pass=0
local function check(name,condition) assert(condition,name);pass=pass+1 end
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
local f=assert(io.open(conf));local fresh=f:read('*a');f:close()
local function write(text) local f=assert(io.open(conf,'w'));f:write(text);f:close() end
local function policy()
    for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
    local S=H.new{root=ROOT,vendor='amd'}
    return dofile(ROOT..'/hdr-tools/gpu-policy.lua'),S
end
local p,S=policy();local o=p.options()
local grade=dofile(ROOT..'/hdr-tools/hdr-grade.lua')
for _,vendor in ipairs({'amd','intel','nvidia'}) do
    local d=grade.display(o,vendor)
    check(vendor..' automatic display',d.peak=='auto' and d.gamut=='auto' and d.oled=='no')
    check(vendor..' follows system HDR',p.settings(vendor,o).mode=='follow')
end
check('HDR conversion and grading enabled',o.hdr_conversion and o.grade)
check('Natural defaults',o.shadows==.15 and o.highlights==.50 and o.highlights_rtx==.25 and o.vibrance==.15 and o.vibrance_rtx==.10)
check('experimental processing off',o.frame_generation=='off' and not o.rife_display_sync and not o.grade_native_hdr and not o.smooth_motion)
check('no diagnostic logging by default',not o.diagnostic)
check('Wayland follows system by default',o.linux_hdr_output=='auto')

-- Defaults are also correct with no file; canonical settings override old hardware branches.
write('');p,S=policy();o=p.options()
check('missing file uses automatic display',grade.display(o,'nvidia').peak=='auto' and grade.display(o,'nvidia').oled=='no')
write('peak_nvidia=1000\noled_nvidia=yes\ngamut_nvidia=display-p3\namd_mode=enable\n')
p,S=policy();o=p.options()
check('legacy NVIDIA settings retained',grade.display(o,'nvidia').peak=='1000' and grade.display(o,'nvidia').oled=='yes')
check('legacy AMD mode retained',p.settings('amd',o).mode=='enable')
write('peak_nvidia=1000\npeak_amd=700\nwindows_hdr=follow\ndisplay_peak=600\ndisplay_gamut=bt.2020\ndisplay_oled=no\n')
p,S=policy();o=p.options()
for _,vendor in ipairs({'nvidia','amd','intel'}) do
    local d=grade.display(o,vendor)
    check('shared settings on '..vendor,d.peak=='600' and d.gamut=='bt.2020' and d.oled=='no')
end
write('display_peak=-1\ndisplay_gamut=bad\ndisplay_oled=bad\nwindows_hdr=bad\n')
p,S=policy();o=p.options()
check('invalid shared fields use safe defaults',o.display_peak=='auto' and o.display_gamut=='auto' and o.display_oled=='no' and o.windows_hdr=='follow')

write(fresh)
for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
S=H.new{root=ROOT,vendor='amd',props={platform='linux',
    ['option-info/target-colorspace-hint-strict']={},['option-info/target-colorspace-hint-mode']={},
    ['video-dec-params']={w=1280,h=720,gamma='bt.1886'},['video-target-params']={gamma='srgb',['max-luma']=203}}}
dofile(ROOT..'/hdr-tools/linux-hdr.lua')
S.fire('file-loaded');S.tick(3)
check('auto does not force PQ',S.props['target-trc']=='auto' and S.props['target-prim']=='auto')
check('hints use compositor target',S.props['target-colorspace-hint-mode']=='target')
check('SDR output disables grading',S.props['user-data']['animejanai-linux-hdr'].grade=='off')
S.set('video-target-params',{gamma='pq',['max-luma']=600});S.tick(3)
check('auto negotiated PQ enables conversion and grade',S.props['user-data']['animejanai-linux-hdr'].grade=='mpv')
check('automatic peak follows negotiated display',S.props['glsl-shader-opts']['anime-hdr-grade/peak']=='600.0000')
S.set('video-target-params',{gamma='srgb',['max-luma']=203});S.tick(3)
check('HDR off restores normal output',S.props['user-data']['animejanai-linux-hdr'].grade=='off' and S.props['target-trc']=='auto')
S.set('video-dec-params',{w=1280,h=720,gamma='pq'});S.tick(3)
check('HDR source alone never enables grading',S.props['user-data']['animejanai-linux-hdr'].grade=='off')

print(string.format('%d passed, 0 failed',pass))
