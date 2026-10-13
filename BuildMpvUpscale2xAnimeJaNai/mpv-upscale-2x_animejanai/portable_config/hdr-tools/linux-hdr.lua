-- Wayland HDR has no Windows lease or D3D11 tail. The compositor owns the display.
local mp = require 'mp'
local utils = require 'mp.utils'
local policy = dofile(mp.command_native({'expand-path','~~/hdr-tools/gpu-policy.lua'}))
local grade = dofile(mp.command_native({'expand-path','~~/hdr-tools/hdr-grade.lua'}))
local options = policy.options()
local hw = policy.detect(mp,utils,options)
local original = {}
for _,key in ipairs(grade.render_keys) do original[key]=mp.get_property(key) end
local shader = mp.command_native({'expand-path',grade.shader})
local pattern='~~/user-shaders/anime-hdr-calibration.hook'
local pattern_expanded=mp.command_native({'expand-path',pattern})
local choice,calibration,loaded='custom',false,false
local pending
local state={mode='off'}
local function native(name) return (mp.get_property_native(name)) end
local function source()
    local p=native('video-dec-params') or native('video-params')
    if p and (not p.gamma or p.gamma=='auto' or p.gamma=='unknown') then p=native('video-params') or p end
    if type(p)~='table' or not p.w then return 'unknown' end
    if p.gamma=='pq' or p.gamma=='hlg' or p.colormatrix=='dolbyvision' then return 'hdr' end
    if not p.gamma or p.gamma=='auto' or p.gamma=='unknown' then return 'unknown' end
    return 'sdr'
end
local function set(key,value) if value and mp.get_property(key)~=value then mp.set_property(key,value) end end
local function output()
    -- Auto follows the compositor's preferred color space, not source metadata.
    local mode=options.linux_hdr_output
    set('target-trc',mode=='pq' and 'pq' or mode=='sdr' and 'bt.1886' or 'auto')
    set('target-prim',mode=='pq' and 'bt.2020' or mode=='sdr' and 'bt.709' or 'auto')
    set('target-colorspace-hint','yes')
    if native('option-info/target-colorspace-hint-mode') then set('target-colorspace-hint-mode','target') end
    -- The negotiated swapchain must take precedence when supported by this mpv build.
    if native('option-info/target-colorspace-hint-strict') then set('target-colorspace-hint-strict','yes') end
end
local function apply(kind,enabled)
    output()
    local confirmed=enabled and native('option-info/target-colorspace-hint-strict')~=nil and options.linux_hdr_output~='sdr' and native('video-target-params/gamma')=='pq'
    -- TrueHDR applied inside the engine (linux-playback.lua): frames arrive as PQ / BT.2020.
    local truehdr=native('user-data/animejanai-truehdr')==true
    local backend=truehdr and 'rtx' or options.hdr_conversion and 'mpv' or 'none'
    state=grade.plan(options,{vendor=hw.vendor,backend=backend,source=kind,output_hdr=confirmed,truehdr=truehdr,
        target_gamma=native('video-target-params/gamma'),target_peak=native('video-target-params/max-luma'),
        enabled=choice~='off',original=original},choice=='natural' and grade.presets.natural or nil)
    for _,key in ipairs(grade.render_keys) do
        -- Output TRC is selected above, not restored to a Windows-style auto value.
        if key~='target-trc' then set(key,state.render[key]) end
    end
    local current=native('glsl-shader-opts') or {}
    local wanted=grade.shader_opts(current,state.params)
    if not grade.same_map(current,wanted) then mp.set_property_native('glsl-shader-opts',wanted) end
    local shaders=native('glsl-shaders') or {}
    wanted=grade.shader_list(shaders,state.active and not calibration,shader)
    local list={}
    for _,s in ipairs(wanted) do if s~=pattern and s~=pattern_expanded then list[#list+1]=s end end
    if calibration and confirmed then list[#list+1]=pattern end
    if not grade.same_list(shaders,list) then mp.set_property_native('glsl-shaders',list) end
    mp.set_property_native('user-data/animejanai-linux-hdr',{requested=options.linux_hdr_output,
        negotiated=native('video-target-params/gamma') or 'unknown',display='not-physically-verified',grade=state.mode})
end
local function reconcile() apply(loaded and source() or 'unknown',loaded) end
local function schedule()
    if pending then return end
    pending=mp.add_timeout(.1,function() pending=nil;reconcile() end)
end
local function report()
    local h=native('user-data/animejanai-hardware') or hw
    local out=native('video-out-params') or {}
    local function rate(name,unit) local v=tonumber(native(name));return v and v>0 and string.format('%.3f %s',v,unit) or 'indisponible' end
    -- What really runs: the engine marks its TrueHDR output, and a failed filter is reported as such.
    local truehdr=native('user-data/animejanai-truehdr')==true
    local filter='aucun'
    for _,f in ipairs(native('vf') or {}) do if f.label=='aji' then filter=f.enabled and 'AnimeJaNai' or 'AnimeJaNai (desactive)' end end
    local lines={
        (h.platform=='macos' and 'macOS' or 'Linux / Wayland')..' | GPU inference : '..h.name,
        'GPU ecran (connecteurs PCI) : '..table.concat(h.display_pci or {},', '),
        'Rendu Vulkan : '..tostring(h.vulkan_device or native('vulkan-device') or 'selection automatique'),
        'Sortie demandee : '..options.linux_hdr_output..' | negociee : '..tostring(native('video-target-params/gamma') or 'inconnue'),
        h.platform=='macos' and 'Ecran HDR : verification physique requise ; un ecran XDR recoit le HDR par macOS (EDR).'
            or 'Ecran HDR : verification physique requise ; activer HDR dans le bureau (GNOME, KDE) avant de choisir PQ.',
        'Sortie video (apres filtres) : '..tostring(out.w or '?')..'x'..tostring(out.h or '?')..' | '..rate('estimated-vf-fps','images/s')..' (estime)',
        'Source : '..rate('container-fps','images/s')..' | ecran : '..rate('display-fps','Hz'),
        'Grading : '..state.mode..' | comparaison : '..choice,
        'Filtre : '..filter..' | conversion SDR -> HDR : '..(truehdr and 'TrueHDR (moteur)' or options.hdr_conversion and 'mpv' or 'desactivee'),
        'Profil : '..tostring(native('user-data/animejanai-active-slot') or 0)..' | '..tostring(native('user-data/animejanai-interpolation') or 'cadence originale'),
        'Decodage : '..tostring(native('hwdec-current') or 'logiciel')..' | images perdues : sortie='..tostring(native('frame-drop-count') or 0)..' decodage='..tostring(native('decoder-frame-drop-count') or 0),
        'RIFE : '..tostring(native('user-data/animejanai-rife-sync') or 'facteur du profil'),
        -- The driver layer works after mpv: only the request is known here, not its effect.
    }
    if h.platform~='macos' then
        lines[#lines+1]='Smooth Motion (pilote NVIDIA) : '..(os.getenv('NVPRESENT_ENABLE_SMOOTH_MOTION')=='1' and 'demande au lancement' or 'non demande')
    end
    local text=table.concat(lines,'\n')
    mp.msg.info(text);mp.osd_message(text,12)
    local f=io.open(mp.command_native({'expand-path','~~/../animejanai/diagnostic-hdr.txt'}),'w')
    if f then f:write(text,'\n');f:close() end
end
local function warn_options()
    -- TrueHDR exists on Linux when libaji_rtx.so is installed (NVIDIA Maxine): no warning then.
    local truehdr=utils.file_info(mp.command_native({'expand-path','~~/../animejanai/inference/libaji_rtx.so'}))~=nil
        or (hw.inference_dir and utils.file_info(hw.inference_dir..'/libaji_rtx.so')~=nil)
    if (options.hdr_backend=='rtx' and not truehdr) or options.vsr=='nvidia' or options.vsr=='amd' or options.frame_generation=='amf' then
        mp.msg.warn('Linux : RTX Video / AMD VideoSR / AMF indisponibles ; rendu mpv utilise.')
        mp.osd_message('Linux : fonctions RTX/AMF indisponibles, repli sur mpv.',5)
    end
end
output();warn_options()
if not native('option-info/target-colorspace-hint-strict') then mp.msg.warn('mpv trop ancien pour verifier la negociation HDR Wayland : grading desactive.') end
mp.register_event('file-loaded',function() loaded=true;schedule() end)
mp.register_event('start-file',function() loaded=false;calibration=false;reconcile() end)
mp.register_event('end-file',function() loaded=false;calibration=false;reconcile() end)
mp.register_event('shutdown',function() loaded=false;calibration=false;if pending then pending:kill() end end)
for _,name in ipairs({'video-dec-params','video-params','video-target-params','glsl-shaders','display-names','user-data/animejanai-truehdr'}) do
    mp.observe_property(name,'native',schedule)
end
mp.register_script_message('animejanai-reload-options',function()
    options=policy.options();warn_options();reconcile();mp.osd_message('Reglages HDR appliques',2)
end)
mp.register_script_message('animejanai-grade-toggle',function()
    choice=choice=='custom' and 'natural' or choice=='natural' and 'off' or 'custom';reconcile()
    mp.osd_message('Grading HDR : '..choice,3)
end)
mp.register_script_message('animejanai-calibration',function()
    if options.linux_hdr_output~='pq' or native('video-target-params/gamma')~='pq' then
        mp.osd_message('Mire HDR : activer HDR dans GNOME et choisir la sortie PQ dans le Manager.',5);return
    end
    calibration=not calibration;reconcile()
    if calibration then mp.osd_message('Mire : noirs 0,005-1 | gris 5-300 | eclats 400-4000 nits. Ctrl+Alt+P pour quitter.',8) end
end)
mp.register_script_message('animejanai-hdr-status',report)
