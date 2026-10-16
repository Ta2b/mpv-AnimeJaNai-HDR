#!/usr/bin/env python3
"""Real Linux mpv control check, without a model/GPU. SPEC.json: mpv,input,out.
The input is a short local video; before_ref defaults to the .66 reference.
Successful receipts prevent repetition of conclusive trials.
"""
import json,socket,subprocess,time
from pathlib import Path
import sys,hashlib
spec=json.loads(Path(sys.argv[1]).read_text())
wt=Path(__file__).resolve().parents[2]
art=Path(spec['out']);art.mkdir(parents=True,exist_ok=True)
exe=Path(spec['mpv']);scripts=wt/'BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/scripts'
old=art/'old_monitor.lua';old.write_bytes(subprocess.check_output(['git','show',spec.get('before_ref','ac407bca07771db0bf9da0b4e37ce245fea895cd')+':BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/scripts/animejanai_engine_monitor.lua'],cwd=wt))
identity=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()+exe.read_bytes()+Path(spec['input']).read_bytes()+
    (scripts/'animejanai_playback.lua').read_bytes()+(scripts/'animejanai_engine_monitor.lua').read_bytes()+
    (scripts.parent/'hdr-tools/playback-state.lua').read_bytes()).hexdigest()
results={}
for candidate in [False,True]:
 name='on' if candidate else 'before'
 receipt=art/(name+'-result.json')
 if receipt.exists():
  result=json.loads(receipt.read_text());assert result.get('_identity')==identity,'Inputs changed; use a fresh output directory'
  results[name]=result;continue
 path=art/(name+'.sock');path.unlink(missing_ok=True)
 stats=art/(name+'-stats.log');stats.write_text('Ready\n');log=open(art/(name+'-stdout.log'),'wb')
 args=[str(exe),'--no-config',f'--config-dir={scripts.parent}','--load-scripts=no','--hwdec=no','--vo=null','--ao=null','--audio=no','--keep-open=yes','--idle=yes',f'--input-ipc-server={path}',f'--script={scripts/"animejanai_engine_monitor.lua" if candidate else old}',f'--script-opts=animejanai_engine_monitor-stats_path={stats},animejanai_engine_monitor-poll_interval=0.2',spec['input']]
 if candidate:
  import shutil
  config=art/'runtime-config';(config/'scripts').mkdir(parents=True,exist_ok=True);(config/'hdr-tools').mkdir(exist_ok=True)
  for script in ['animejanai_playback.lua','animejanai_engine_monitor.lua']:
   shutil.copy2(scripts/script,config/'scripts'/script)
  shutil.copy2(scripts.parent/'hdr-tools/playback-state.lua',config/'hdr-tools/playback-state.lua')
  args=[a for a in args if a!='--no-config' and a!='--load-scripts=no' and not a.startswith('--script=') and not a.startswith('--config-dir=')]
  args.insert(1,f'--config-dir={config}')
 p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT);connection=None;request_id=0;started=time.monotonic()
 try:
  deadline=time.monotonic()+5
  while not path.exists():
   assert p.poll() is None and time.monotonic()<deadline;time.sleep(.01)
  connection=socket.socket(socket.AF_UNIX);connection.settimeout(3);connection.connect(str(path));reader=connection.makefile('rb')
  def cmd(command):
   global request_id
   request_id+=1;connection.sendall((json.dumps({'command':command,'request_id':request_id})+'\n').encode())
   while True:
    r=json.loads(reader.readline())
    if r.get('request_id')==request_id:return r
  def prop(name):return cmd(['get_property',name]).get('data')
  def until(fn):
   stop=time.monotonic()+3
   while not fn():
    assert time.monotonic()<stop,(prop('pause'),prop('user-data/animejanai-playback'));time.sleep(.01)
  until(lambda:prop('time-pos') is not None)
  if candidate:until(lambda:(prop('user-data/animejanai-playback') or {}).get('state')=='LECTURE')
  stats.write_text('Building TensorRT engine for model for 128x72\n')
  until(lambda:prop('pause') is True)
  cmd(['set_property','pause',False]);cmd(['set_property','pause',True])
  stats.write_text('Upscale Profile: 1\n')
  if candidate:
   until(lambda:(prop('user-data/animejanai-playback') or {}).get('holders')==[])
   state=prop('user-data/animejanai-playback');assert prop('pause') is True and state['state']=='PAUSE_UTILISATEUR',state
  else:
   until(lambda:prop('pause') is False);state=None
  result={'pause_after_completion':prop('pause'),'state':state,'duration_s':time.monotonic()-started,'args':args,'_identity':identity}
  if candidate:
   epoch=state['generation']
   cmd(['script-message','aji-playback-user-pause','no'])
   cmd(['script-message','aji-playback-hold','reserve','refill',str(epoch)])
   until(lambda:(prop('user-data/animejanai-playback') or {}).get('state')=='REMPLISSAGE')
   cmd(['script-message','aji-playback-user-pause','yes'])
   until(lambda:(prop('user-data/animejanai-playback') or {}).get('state')=='PAUSE_UTILISATEUR')
   cmd(['script-message','aji-playback-release','reserve',str(epoch)])
   until(lambda:(prop('user-data/animejanai-playback') or {}).get('holders')==[])
   assert prop('pause') is True
   cmd(['script-message','aji-playback-hold','new','preparation',str(epoch)])
   cmd(['script-message','aji-playback-release','new',str(epoch-1)])
   until(lambda:'new' in (prop('user-data/animejanai-playback') or {}).get('holders',[]))
   cmd(['script-message','aji-playback-error','new','targeted-error',str(epoch)])
   until(lambda:(prop('user-data/animejanai-playback') or {}).get('state')=='ERREUR')
   assert prop('pause') is True
   result['final_state']=prop('user-data/animejanai-playback')
  cmd(['quit']);p.wait(timeout=3);assert p.returncode==0
  results[name]=result;(art/(name+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
 finally:
  if connection:connection.close()
  if p.poll() is None:p.terminate();p.wait(timeout=3)
  log.close()
(art/'runtime-summary.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
