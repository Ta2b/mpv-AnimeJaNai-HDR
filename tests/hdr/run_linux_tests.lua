package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'))
local pass,fail=0,0
local function check(name,c) if c then pass=pass+1 else fail=fail+1;print('FAIL: '..name) end end
local function write(path,data) local f=assert(io.open(path,'wb'));f:write(data);f:close() end
local function boot(vendor,libs)
    local S=H.new{root=ROOT,props={platform='linux',vf={},['option-info/target-colorspace-hint-strict']={}}}
    local u=require 'mp.utils'
    local command=mp.command_native
    mp.command_native=function(c)
        if c.name=='subprocess' then
            check('subprocess never invokes Windows tools', not c.args[1]:match('%.exe$'))
            if c.args[2]=='--probe' then return {status=0,stdout='{"vendor":"'..vendor..'","name":"GPU test","vulkan_device":"Vulkan '..vendor..'","adapters":[],"display_pci":["0000:00:02.0"]}'} end
            return {status=0,stdout='{"conf":"'..ROOT..'/../animejanai/animejanai.conf"}'}
        end
        return command(c)
    end
    S.files={}
    if libs then for _,name in ipairs({'libaji.so','libaji_trt.so','libnvinfer.so.11','trtexec'}) do
        S.files[ROOT..'/../animejanai/inference/'..name]={is_dir=false}
    end end
    return S,u
end
write(ROOT..'/../animejanai/animejanai.conf','[global]\nbackend=TensorRT\ndefault_slot=0\n[slot_1]\nprofile_name=Performance\nchain_1_rife=no\n')
local S,u=boot('amd',true)
dofile(ROOT..'/user-scripts/hardware_auto.lua')
S.hook('on_load')
check('AMD starts without inference',#S.props.vf==0)
check('AMD auto-safe decoding',S.props.hwdec=='auto-safe')
check('explicit Vulkan adapter',S.props['vulkan-device']=='Vulkan amd')
S.msg('animejanai-select','1')
check('AMD refuses inference even when libs present',#S.props.vf==0 and S.props['user-data']['animejanai-active-slot']==0)
S,u=boot('nvidia',false)
dofile(ROOT..'/user-scripts/hardware_auto.lua');S.hook('on_load');S.msg('animejanai-select','1')
check('missing TensorRT retains normal playback',#S.props.vf==0)
check('NVIDIA requests NVDEC',S.props.hwdec=='nvdec')
S,u=boot('nvidia',true)
dofile(ROOT..'/user-scripts/hardware_auto.lua');S.hook('on_load')
check('NVIDIA inference opt-in',#S.props.vf==0)
S.props.vf={{label='other',name='scale'}};S.msg('animejanai-select','1')
check('opt-in adds Linux aji without losing other filters',#S.props.vf==2 and S.props.vf[1].params.lib:match('libaji%.so$'))
S.msg('animejanai-select','0');check('disable retains unrelated filter',#S.props.vf==1 and S.props.vf[1].label=='other')
-- Vulkan works independently of TensorRT on both vendors, and uses its own ABI.
write(ROOT..'/../animejanai/animejanai.conf','[global]\nbackend=Vulkan\ndefault_slot=0\n[slot_1]\nprofile_name=Performance\nchain_1_rife=no\n[slot_2]\nprofile_name=RIFE\nchain_1_rife=yes\n')
for _,vendor in ipairs({'amd','nvidia'}) do
    S,u=boot(vendor,false)
    S.files[ROOT..'/../animejanai/inference/libaji_vulkan.so']={is_dir=false}
    dofile(ROOT..'/user-scripts/hardware_auto.lua');S.hook('on_load');S.msg('animejanai-select','1')
    check(vendor..' Vulkan works without TensorRT',#S.props.vf==1 and S.props.vf[1].name=='animejanai-vulkan')
    check(vendor..' explicit inference GPU',S.props.vf[1].params.device=='Vulkan '..vendor)
    check(vendor..' Vulkan uses host decoding',S.props.hwdec=='no')
    check(vendor..' Vulkan does not receive CUDA tools',S.props.vf[1].params.trtexec==nil)
    S.msg('animejanai-select','2')
    check(vendor..' Vulkan slot changes recreate filter',S.props.vf[1].params.slot=='2')
    check(vendor..' RIFE reflected in diagnostics',S.props['user-data']['animejanai-interpolation']=='RIFE configure')
    S.msg('animejanai-select','0')
    check(vendor..' disable restores decoder',#S.props.vf==0 and S.props.hwdec==(vendor=='nvidia' and 'nvdec' or 'auto-safe'))
end
S,u=boot('amd',false);dofile(ROOT..'/user-scripts/hardware_auto.lua');S.hook('on_load');S.msg('animejanai-select','1')
check('missing Vulkan preserves normal playback',#S.props.vf==0)
S,u=boot('amd',false)
dofile(ROOT..'/user-scripts/animejanai_hdr_auto.lua')
S.set('video-dec-params',{w=1920,h=1080,gamma='pq'})
S.set('video-target-params',{gamma='bt.1886', ['max-luma']=100})
S.fire('file-loaded');S.tick()
check('HDR source does not imply HDR display',#S.props['glsl-shaders']==0)
check('default output follows compositor',S.props['target-trc']=='auto')
local conf=ROOT..'/script-opts/animejanai_hdr_auto.conf'
write(conf,'linux_hdr_output=pq\nhdr_conversion=yes\ngrade=yes\ngrade_native_hdr=yes\n')
S.msg('animejanai-reload-options');S.tick()
check('unconfirmed PQ does not enable grade',#S.props['glsl-shaders']==0)
S.set('video-target-params',{gamma='pq',['max-luma']=1000});S.tick()
check('negotiated PQ enables native HDR grade',#S.props['glsl-shaders']==1)
check('diagnostic separates requested and negotiated',S.props['user-data']['animejanai-linux-hdr'].requested=='pq')
S.msg('animejanai-calibration');check('calibration replaces grading',#S.props['glsl-shaders']==1 and S.props['glsl-shaders'][1]:match('calibration'))
write(conf,'linux_hdr_output=sdr\n');S.msg('animejanai-reload-options');S.tick()
check('SDR restores output and removes HDR shaders',S.props['target-trc']=='bt.1886' and #S.props['glsl-shaders']==0)
S,u=boot('amd',false)
local scripts={'hardware_auto.lua','animejanai_slot.lua','animejanai_backend.lua','animejanai_hdr_auto.lua','display-info.dll'}
u.readdir=function(path) if path:match('user%-scripts$') then return scripts end;return {'shared.lua','windows.dll'} end
u.file_info=function() return {is_dir=false} end
dofile(ROOT..'/hdr-tools/user-script-loader.lua')
local loaded=S.props['user-data']['animejanai-user-runtime'].loaded
check('loader works without display-info.dll',#loaded==5)
for _,name in ipairs(loaded) do check('loader excludes Windows DLL '..name,not name:match('%.dll$')) end
-- ONNX Runtime engine: backend=MIGraphX / OpenVINO uses the bridged filter with libaji_ort.so
do
  local playback=io.open(ROOT..'/hdr-tools/linux-playback.lua'):read('*a')
  check('ort: engine library selected for the vendor providers', playback:find("ort and '/libaji_ort.so'",1,true)~=nil)
  check('ort: availability follows the engine library', playback:find("/libaji_ort.so')~=nil",1,true)~=nil)
  check('ort: software decoding with the host-frame bridge', playback:find("elseif ort then",1,true)~=nil)
end
print(string.format('%d passed, %d failed',pass,fail));os.exit(fail==0 and 0 or 1)
