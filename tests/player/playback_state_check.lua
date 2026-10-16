local root=assert(arg[1])
local State=dofile(root..'/BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/hdr-tools/playback-state.lua')
local pause, published, changes, control
local function reset(initial)
    pause=initial; changes={}
    control=State.new({get_pause=function()return pause end,
        set_pause=function(value)pause=value;changes[#changes+1]=value end,
        publish=function(value)published=value end})
    control:publish()
end
local function observe()control:observe_pause(pause)end
reset(false);control:file_loaded();assert(published.state=='LECTURE')
assert(control:hold('build','preparation',1));observe();assert(pause and not published.user_paused and published.state=='PREPARATION')
control:release('build',1);observe();assert(not pause and published.state=='LECTURE')
-- Explicit pause while already automatically paused must survive completion.
control:hold('build','preparation',1);observe();control:user_pause(true)
control:release('build',1);assert(pause and published.state=='PAUSE_UTILISATEUR')
-- Both manual changes happen before the next build poll.
reset(false);control:file_loaded();control:hold('build','preparation',1);observe()
pause=false;control:observe_pause(false);pause=true;control:observe_pause(true)
control:release('build',1);assert(pause and published.user_paused)
-- A deliberate manual unpause during preparation remains respected.
control:user_pause(false);control:hold('build','preparation',1);observe()
control:user_pause(false);assert(not pause and published.manual_override)
control:release('build',1);assert(not pause and not published.manual_override)
-- Independent owners and stale completions cannot release another hold.
control:hold('reserve','refill',1);observe();assert(published.state=='REMPLISSAGE')
control:hold('build','preparation',1);control:release('reserve',1);assert(pause)
control:seek(true);assert(published.state=='SEEK');control:user_pause(true)
control:seek(false);assert(published.state=='PAUSE_UTILISATEUR')
control:start_file();assert(pause and published.generation==2)
assert(not control:release('build',1));assert(not control:hold('late','refill',1))
control:hold('new','refill',2);control:fail('new','build-failed',2)
assert(pause and published.state=='ERREUR' and published.user_paused)
control:end_file(nil);control:user_pause(false);control:file_loaded();assert(not pause and published.state=='LECTURE')
-- auto_pause=no still reports preparation, without stopping playback.
control:hold('observe','preparation',3,false);assert(not pause and published.state=='PREPARATION' and not published.automatic_pause)
control:release('observe',3);assert(not pause and published.state=='LECTURE')
print('pause intent, rapid takeover, independent holds, seek, errors, stale generation and nonblocking preparation: PASS')
