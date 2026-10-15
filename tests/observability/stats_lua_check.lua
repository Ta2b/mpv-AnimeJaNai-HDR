-- Targeted Lua contracts: visible snapshots refresh, absence does not finish a build.
local root=assert(arg[1])
local content=nil
local timer,key,osd,paused
local events={}
local properties={vf='aji'}
local mp={}
function mp.get_property(name)return properties[name]end
function mp.get_property_bool(name)return name=='pause' and paused or false end
function mp.set_property_bool(name,value)if name=='pause' then paused=value end end
function mp.command_native()return 'stats' end
function mp.osd_message(text)osd=text end
function mp.add_periodic_timer(interval,fn)
 assert(interval==0.25);timer={fn=fn,active=true,kill=function(t)t.active=false end,resume=function(t)t.active=true end};return timer
end
function mp.add_key_binding(_,_,fn)key=fn end
function mp.get_time()return 1 end
function mp.commandv()end
function mp.enable_messages()end
function mp.register_event(name,fn)events[name]=fn end
package.loaded.mp=mp
package.loaded['mp.msg']={info=function()end,warn=function()end}
package.loaded['mp.options']={read_options=function()end}
_G.mp=mp
local real_open=io.open
io.open=function(path,mode)
 if path~='stats' then return real_open(path,mode) end
 if not content then return nil end
 return {read=function()return content end,close=function()end}
end
local scripts=root..'/BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/scripts/'
dofile(scripts..'animejanaistats.lua')
assert(not timer.active);key();assert(timer.active and osd:find('Waiting',1,true))
content='Frames: 1\n';timer.fn();assert(osd==content)
content='Frames: 30\n';timer.fn();assert(osd==content)
key();assert(not timer.active and osd=='')
content='Building TensorRT engine for model for 128x72\n'
dofile(scripts..'animejanai_engine_monitor.lua');timer.fn();assert(paused)
content=nil;timer.fn();assert(paused)
content='';timer.fn();assert(paused)
events['log-message']({text='configure failed: missing model\n'});assert(not paused and osd:find('missing model',1,true))
content='Building TensorRT engine for other for 128x72\n';timer.fn();assert(paused)
content='Upscale Profile: 1\n';timer.fn();assert(not paused)
io.open=real_open
print('visible refresh, idle timer, missing/empty read, immediate error, completed build: PASS')
