#!/usr/bin/env python3
"""Real CUDA result-reserve budget check. SPEC.json: mpv,input,conf,models,lib,out,
reference_dir (the unchanged lot34 off pixel/PTS/seek receipts). phase: budget|sequence.
Successful receipts prevent repetition. Runtime CUDA/TRT libraries are inherited.
The bounded case is 12 frames128x72 ->256x144, same SPAN plan/config as its reference.
"""
import hashlib,json,os,socket,subprocess,sys,time
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());phase=sys.argv[2]
assert phase in ('budget','sequence')
art=Path(spec['out']);art.mkdir(parents=True,exist_ok=True)
previous=Path(spec['reference_dir']);exe=Path(spec['mpv']);models=Path(spec['models'])
lib=Path(spec['lib']);conf=Path(spec['conf']);input_file=Path(spec['input'])
identity=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()+exe.read_bytes()+lib.read_bytes()+conf.read_bytes()+input_file.read_bytes()).hexdigest()
receipt=art/(phase+'-passed.json')
if receipt.exists():
 result=json.loads(receipt.read_text());assert result['identity']==identity,'Inputs changed; use a fresh output directory'
 print(json.dumps(result));sys.exit(0)
def run_budget():
 for budget in [0,65536]:
  prefetch=8
  name=f'budget-{budget}';sockpath=art/(name+'.sock');log=art/(name+'.log');counter=0
  if sockpath.exists():sockpath.unlink()
  vf=f'@aji:animejanai=conf={conf}:model-dir={models}:lib={lib}:trtexec=/bin/false:slot=1:queue-depth=1:output-444=no:passthrough=no:prefetch={prefetch}:prefetch-bytes={budget}'
  args=[str(exe),'--no-config','--load-scripts=no','--vo=null','--ao=null','--audio=no','--pause=yes','--screenshot-sw=yes','--keep-open=yes','--idle=yes','--hwdec=nvdec','--hwdec-codecs=all','--stop-screensaver=no',f'--input-ipc-server={sockpath}',f'--log-file={log}',f'--vf={vf}',str(input_file)]
  stdout=open(art/(name+'-stdout.log'),'wb');p=subprocess.Popen(args,stdout=stdout,stderr=subprocess.STDOUT);conn=None
  try:
   deadline=time.monotonic()+12
   while not sockpath.exists():
    assert p.poll() is None,log.read_text()[-1500:] if log.exists() else 'startup exited'
    assert time.monotonic()<deadline;time.sleep(.02)
   conn=socket.socket(socket.AF_UNIX);conn.settimeout(5);conn.connect(str(sockpath));reader=conn.makefile('rb')
   def cmd(command):
    nonlocal counter
    counter+=1;conn.sendall((json.dumps({'command':command,'request_id':counter})+'\n').encode())
    while True:
     response=json.loads(reader.readline())
     if response.get('request_id')==counter:return response
   def prop(name):return cmd(['get_property',name]).get('data')
   state={}
   while time.monotonic()<deadline:
    state={'pause':prop('pause'),'time_pos':prop('time-pos'),'meta':prop('vf-metadata/aji'),'video_out':prop('video-out-params'),'hwdec':prop('hwdec-current')}
    m=state.get('meta') or {}
    frame_bytes=int(m.get('prefetch-last-frame-bytes',0))
    target=prefetch if budget==0 else ((budget+frame_bytes-1)//frame_bytes if frame_bytes else 0)
    if state['time_pos'] is not None and m.get('prefetch-format')=='cuda' and target>0 and int(m.get('prefetch-ready',0))==target:break
    time.sleep(.02)
   (art/(name+'.json')).write_text(json.dumps(state,indent=2)+'\n');print(json.dumps({'case':name,**state}),flush=True)
   assert state['pause'] is True and state['time_pos'] is not None and state['hwdec']=='nvdec',state
   assert state['meta']['prefetch-format']=='cuda' and int(state['meta']['prefetch-ready'])==target,state
   assert state['video_out']['w']==256 and state['video_out']['h']==144,state
   meta=state['meta'];reserved=int(meta['prefetch-reserved-bytes'])
   assert reserved==target*frame_bytes,meta
   assert int(meta['prefetch-budget-bytes'])==budget,meta
   assert frame_bytes>=256*144*3//2,meta
   if budget:
    assert budget<=reserved<=budget+int(meta['prefetch-max-frame-bytes']),meta
    assert target<8,meta
    old_epoch=int(meta['prefetch-epoch'])
    cmd(['seek','0.3','absolute+exact']);deadline=time.monotonic()+5
    while time.monotonic()<deadline:
     after={'pause':prop('pause'),'time_pos':prop('time-pos'),'meta':prop('vf-metadata/aji')};m=after['meta'] or {}
     if after['time_pos'] is not None and after['time_pos']>=.3 and int(m.get('prefetch-epoch',0))>old_epoch and int(m.get('prefetch-reserved-bytes',0))>0:break
     time.sleep(.02)
    assert after['pause'] is True and int(after['meta']['prefetch-epoch'])>old_epoch,after
    assert int(after['meta']['prefetch-reserved-bytes'])<=budget+int(after['meta']['prefetch-max-frame-bytes']),after
    png=art/'budget-seek-target.png';assert cmd(['screenshot-to-file',str(png),'video'])['error']=='success'
    import hashlib
    expected=json.loads((previous/'seek-0-result.json').read_text())['target_png_sha256']
    assert hashlib.sha256(png.read_bytes()).hexdigest()==expected
    (art/'budget-seek.json').write_text(json.dumps(after,indent=2)+'\n')
   cmd(['quit']);p.wait(timeout=5);assert p.returncode==0
  finally:
   if conn:conn.close()
   if p.poll() is None:p.terminate()
   p.wait(timeout=5);stdout.close()

def run_sequence():
 results=[]
 for capacity in [8]:
  name='budget-sequence';output=art/(name+'.nut')
  assert not (art/(name+'.json')).exists(),'Conclusive receipt exists; no repeat'
  vf=f'@aji:animejanai=conf={conf}:model-dir={models}:lib={lib}:trtexec=/bin/false:slot=1:queue-depth=1:output-444=no:passthrough=no:prefetch={capacity}:prefetch-bytes=65536'
  args=[str(exe),'--no-config','--load-scripts=no','--ao=null','--audio=no','--hwdec=nvdec','--hwdec-codecs=all','--stop-screensaver=no',f'--log-file={art}/{name}.log',f'--vf={vf}',f'--o={output}','--of=nut','--ovc=rawvideo',str(input_file)]
  t=time.monotonic()
  with open(art/(name+'-stdout.log'),'wb') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=20)
  assert r.returncode==0,(name,r.returncode)
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',str(output)]))
  raw=art/(name+'.nv12')
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(output),'-pix_fmt','nv12','-f','rawvideo',str(raw)],check=True)
  data=raw.read_bytes();size=256*144*3//2
  frames=[{'pts':f['pts'],'time_base':probe['streams'][0]['time_base'],'sha256':hashlib.sha256(data[i*size:(i+1)*size]).hexdigest()} for i,f in enumerate(probe['frames'])]
  assert len(frames)==12 and len(data)==12*size,(len(frames),len(data))
  assert probe['streams'][0]['width']==256 and probe['streams'][0]['height']==144
  log=(art/(name+'.log')).read_text();assert 'Decoder format: 128x72 [0:1] cuda[nv12]' in log and 'backend: TensorRT' in log
  result={'capacity':capacity,'duration_s':time.monotonic()-t,'frames':frames,'raw_sha256':hashlib.sha256(data).hexdigest(),'args':args,'returncode':r.returncode,'width':256,'height':144}
  (art/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');results.append(result)
 reference=json.loads((previous/'sequence-0.json').read_text())
 assert results[0]['frames']==reference['frames'],'pixels or PTS changed'
 (art/'sequence-summary.json').write_text(json.dumps({'frames':12,'pixels_exact':True,'pts_exact':True,'reference_reused':str(previous/'sequence-0.json'),'on_s':results[0]['duration_s'],'raw_sha256':results[0]['raw_sha256']},indent=2)+'\n')
 print((art/'sequence-summary.json').read_text())

started=time.monotonic()
(run_budget if phase=='budget' else run_sequence)()
receipt.write_text(json.dumps({'phase':phase,'passed':True,'identity':identity,'duration_s':time.monotonic()-started},indent=2)+'\n')
