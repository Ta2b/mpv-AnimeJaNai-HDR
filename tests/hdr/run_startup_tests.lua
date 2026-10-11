package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'),'set AJ_ROOT to a scratch copy of portable_config')
local pass,fail=0,0
local function check(n,c,x) if c then pass=pass+1 else fail=fail+1 print('FAIL: '..n..(x and (' -> '..tostring(x)) or '')) end end
os.execute('mkdir -p '..ROOT..'/cache '..ROOT..'/profiles/nvidia '..ROOT..'/profiles/amd '..ROOT..'/../animejanai')
os.remove(ROOT..'/cache/animejanai-hardware.json')
local function write(p,d) local f=io.open(p,'wb'); f:write(d); f:close() end
local bank='[global]\nbackend=TensorRT\ndefault_slot=3\n[slot_3]\nprofile_name=2K\n'
write(ROOT..'/profiles/nvidia/animejanai.conf',bank); write(ROOT..'/../animejanai/animejanai.conf',bank)
local sha=dofile(ROOT..'/hdr-tools/sha256.lua')
if not sha('') then print('skipped: no bit library (the player falls back to PowerShell)'); os.exit(0) end
write(ROOT..'/profiles/active-bank.json','{"hash":"'..sha(bank)..'","vendor":"nvidia"}')
local function boot(vendor,computer)
  for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
  local S=H.new{root=ROOT,vendor=vendor,computer=computer}
  local policy=dofile(ROOT..'/hdr-tools/gpu-policy.lua')
  local hw=policy.detect(mp,package.loaded['mp.utils'],policy.options())
  return S,hw
end
local S,hw=boot('nvidia','PC1')
check('first start: synchronous detection', S.detect_calls==1 and hw.vendor=='nvidia', S.detect_calls)
check('bank unchanged: no bank PowerShell', (S.bank_calls or 0)==0, S.bank_calls)
check('cache written', io.open(ROOT..'/cache/animejanai-hardware.json')~=nil)
S,hw=boot('nvidia','PC1')
check('second start: cached vendor', hw.vendor=='nvidia')
check('second start: background check only', S.detect_calls==1 and #S.osd==0, #S.osd)
S,hw=boot('amd','PC1')
check('GPU swapped: cached vendor this start, OSD asks restart', hw.vendor=='nvidia' and (S.osd[1] or ''):match('relancer')~=nil, S.osd[1])
S,hw=boot('amd','PC1')
check('after swap: new vendor', hw.vendor=='amd')
S,hw=boot('nvidia','PC2')
check('other computer: synchronous detection', hw.vendor=='nvidia' and S.detect_calls==1)
write(ROOT..'/../animejanai/animejanai.conf',bank..'; edited by Manager\n')
S,hw=boot('nvidia','PC2')
check('Manager edit: bank PowerShell runs', (S.bank_calls or 0)==1, S.bank_calls)
write(ROOT..'/../animejanai/animejanai.conf',bank)
print(pass..' passed, '..fail..' failed')
os.exit(fail==0 and 0 or 1)
