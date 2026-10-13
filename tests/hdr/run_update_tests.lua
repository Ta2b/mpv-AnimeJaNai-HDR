-- The update script (portable_config/scripts/animejanai_update.lua) with a mock updater: the
-- in-place update of Windows and Linux, the AppImage, and macOS where the application is
-- downloaded while the video plays and replaced once the player has closed.
package.path=(os.getenv('AJ_TEST_DIR') or '.')..'/?.lua;'..package.path
local H=require 'harness'
local ROOT=assert(os.getenv('AJ_ROOT'),'set AJ_ROOT to a scratch copy of portable_config')
local SCRIPT=(os.getenv('AJ_TEST_DIR') or '.')..'/../../BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/scripts/animejanai_update.lua'
local pass,fail=0,0
local function check(n,c,x) if c then pass=pass+1 else fail=fail+1 print('FAIL: '..n..(x and (' -> '..tostring(x)) or '')) end end
local real_getenv=os.getenv
local STATUS=ROOT..'/cache/animejanai-update-1234.status'

-- env: what the launcher gives; answer: the updater's reply to --check.
local function boot(platform,env,answer,props)
  for k in pairs(package.loaded) do if k:match('^mp') then package.loaded[k]=nil end end
  os.getenv=function(k) if env[k]~=nil then return env[k] or nil end; if k=='APPIMAGE' or k=='ANIMEJANAI_APPIMAGE' or k=='ANIMEJANAI_BUNDLE' then return nil end; return real_getenv(k) end
  props=props or {}; props.platform=platform
  local S=H.new{root=ROOT,props=props}
  S.runs={}; S.commands={}; S.keys={}
  local base=mp.command_native
  mp.command_native=function(c)
    if c.name=='subprocess' then
      S.runs[#S.runs+1]=c
      if c.args[2]=='--check' then return answer end
      return {status=0,stdout=''}
    end
    return base(c)
  end
  mp.command_native_async=function(c,cb) local r=mp.command_native(c); if cb then cb(r~=nil,r,nil) end; return {} end
  mp.command=function(c) S.commands[#S.commands+1]=c; return true end
  mp.add_key_binding=function(key,name,fn) S.keys[key]=fn end
  os.remove(STATUS); os.remove(STATUS..'.reopen')
  dofile(SCRIPT)
  return S
end
local function status(line) local f=assert(io.open(STATUS,'w')); f:write(line,'\n'); f:close() end
local function last(S) return S.osd[#S.osd] or '' end
local function applied(S) for _,c in ipairs(S.runs) do if c.args[2]=='--apply' then return c end end end

-- Windows: the updater next to the player, started detached; the player quits.
local S=boot('windows',{},{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'})
check('windows: updater at the install root', S.runs[1].args[1]==ROOT..'/../AnimeJaNaiUpdater.exe', S.runs[1].args[1])
check('windows: offer shown', last(S):match('3%.9%.0 available %- press Ctrl%+U to install')~=nil, last(S))
check('windows: no key bound by the script', next(S.keys)==nil)
S.msg('animejanai-update'); S.tick(2)
check('windows: apply detached', applied(S) and applied(S).detach==true and #applied(S).args==2)
check('windows: player quits', S.commands[1]=='quit', S.commands[1])

-- Linux folder install: same; AppImage: a link, nothing started.
S=boot('linux',{},{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'})
check('linux: updater name', S.runs[1].args[1]==ROOT..'/../AnimeJaNaiUpdater', S.runs[1].args[1])
S.msg('animejanai-update'); S.tick(2)
check('linux: apply and quit', applied(S)~=nil and S.commands[1]=='quit')
S=boot('linux',{ANIMEJANAI_APPIMAGE='1'},{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'})
S.msg('animejanai-update'); S.tick(2)
check('appimage: download link only', applied(S)==nil and #S.commands==0 and last(S):match('new AppImage')~=nil, last(S))

-- Up to date, offline, updater missing: quiet.
S=boot('darwin',{ANIMEJANAI_BUNDLE='/A/mpv AnimeJaNai.app/Contents/Resources',TMPDIR=ROOT..'/cache/'},{status=0,stdout='UP_TO_DATE 3.9.0\n'})
check('mac: updater inside the application', S.runs[1].args[1]=='/A/mpv AnimeJaNai.app/Contents/Resources/AnimeJaNaiUpdater', S.runs[1].args[1])
check('mac: quiet when up to date', #S.osd==0)
check('mac: Ctrl+u bound', type(S.keys['Ctrl+u'])=='function')
S.keys['Ctrl+u'](); S.tick(2)
check('mac: nothing to install', applied(S)==nil and last(S):match('up to date')~=nil, last(S))
S=boot('darwin',{ANIMEJANAI_BUNDLE='/A/X.app/Contents/Resources',TMPDIR=ROOT..'/cache'},{status=1,stdout='Updater error: offline\n'})
check('mac: quiet when the check fails', #S.osd==0)

-- macOS, update available: download while playing, then close on the current file.
local env={ANIMEJANAI_BUNDLE='/A/mpv AnimeJaNai.app/Contents/Resources',TMPDIR=ROOT..'/cache/'}
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'},{path='show/episode 01.mkv',['working-directory']='/Users/a/Videos'})
check('mac: offer shown', last(S):match('3%.9%.0 available')~=nil, last(S))
S.keys['Ctrl+u']()
local run=applied(S)
check('mac: apply with pid and status file', run and run.detach==true and table.concat(run.args,'|')==
  '/A/mpv AnimeJaNai.app/Contents/Resources/AnimeJaNaiUpdater|--apply|--wait-pid|1234|--status|'..STATUS, run and table.concat(run.args,'|'))
check('mac: says the video keeps playing', last(S):match('keeps playing')~=nil, last(S))
S.tick(3)
check('mac: player still open while nothing is reported', #S.commands==0)
S.keys['Ctrl+u']()
local count=0; for _,c in ipairs(S.runs) do if c.args[2]=='--apply' then count=count+1 end end
check('mac: a second Ctrl+u does not start a second download', count==1, count)
status('DOWNLOAD 42'); S.tick(1)
check('mac: download progress', last(S):match('downloading 42 %%')~=nil, last(S))
local shown=#S.osd; S.tick(2)
check('mac: unchanged status is not repeated', #S.osd==shown)
status('EXTRACT'); S.tick(1)
check('mac: verifying', last(S):match('verifying')~=nil, last(S))
check('mac: still playing before READY', #S.commands==0)
-- The user opened another file during the download: that one is reopened.
S.props.path='/Volumes/Disk/other.mkv'
status('READY 3.9.0'); S.tick(1)
local f=io.open(STATUS..'.reopen'); local reopen=f and f:read('*l'); if f then f:close() end
check('mac: file to reopen is the current one', reopen=='/Volumes/Disk/other.mkv', reopen)
check('mac: installing message', last(S):match('Installing AnimeJaNai 3%.9%.0')~=nil, last(S))
S.tick(1)
check('mac: closes keeping the position', S.commands[1]=='quit-watch-later', S.commands[1])
S.tick(3)
check('mac: closes once', #S.commands==1, #S.commands)

-- A relative path is made absolute; a stream address is kept as it is; no file: plain quit.
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'},{path='show/episode 01.mkv',['working-directory']='/Users/a/Videos'})
S.keys['Ctrl+u'](); status('READY 3.9.0'); S.tick(2)
f=io.open(STATUS..'.reopen'); reopen=f and f:read('*l'); if f then f:close() end
check('mac: relative path made absolute', reopen=='/Users/a/Videos/show/episode 01.mkv', reopen)
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'},{path='https://example.org/v.m3u8',['working-directory']='/Users/a'})
S.keys['Ctrl+u'](); status('READY 3.9.0'); S.tick(2)
f=io.open(STATUS..'.reopen'); reopen=f and f:read('*l'); if f then f:close() end
check('mac: stream address kept', reopen=='https://example.org/v.m3u8', reopen)
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'})
S.keys['Ctrl+u'](); status('READY 3.9.0'); S.tick(2)
check('mac: idle player quits without a file to reopen', S.commands[1]=='quit' and io.open(STATUS..'.reopen')==nil, S.commands[1])

-- Failure: said once, the player stays open, and Ctrl+u can try again.
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'},{path='/a.mkv'})
S.keys['Ctrl+u'](); status('DOWNLOAD 10'); S.tick(1)
status('FAILED The download is damaged (checksum mismatch). Nothing was changed.'); S.tick(2)
check('mac: failure shown', last(S):match('update failed: The download is damaged')~=nil, last(S))
check('mac: player stays open after a failure', #S.commands==0)
check('mac: status file removed after a failure', io.open(STATUS)==nil)
S.keys['Ctrl+u']()
count=0; for _,c in ipairs(S.runs) do if c.args[2]=='--apply' then count=count+1 end end
check('mac: Ctrl+u tries again after a failure', count==2, count)
-- The release was withdrawn between the check and the key.
status('UP_TO_DATE 3.8.0.20'); S.tick(1)
check('mac: up to date after all', last(S):match('up to date')~=nil and #S.commands==0, last(S))
S.keys['Ctrl+u'](); S.tick(1)
count=0; for _,c in ipairs(S.runs) do if c.args[2]=='--apply' then count=count+1 end end
check('mac: no further download once up to date', count==2, count)

-- The updater never reports: given up after thirty seconds, the player stays open.
S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\n'},{path='/a.mkv'})
S.keys['Ctrl+u'](); S.tick(29)
check('mac: waits for the updater', last(S):match('keeps playing')~=nil, last(S))
S.tick(3)
check('mac: gives up when the updater says nothing', last(S):match('did not start')~=nil and #S.commands==0, last(S))

-- The application cannot be replaced where it is: explained, nothing started.
for reason,word in pairs({translocated='temporary copy',readonly='cannot be written'}) do
  S=boot('darwin',env,{status=0,stdout='UPDATE_AVAILABLE 3.9.0\nUPDATE_BLOCKED '..reason..'\n'},{path='/a.mkv'})
  S.keys['Ctrl+u'](); S.tick(2)
  check('mac '..reason..': explained', last(S):match(word)~=nil and last(S):match('Applications folder')~=nil, last(S))
  check('mac '..reason..': nothing started', applied(S)==nil and #S.commands==0)
end

os.getenv=real_getenv
os.remove(STATUS); os.remove(STATUS..'.reopen')
print(pass..' passed, '..fail..' failed')
os.exit(fail==0 and 0 or 1)
