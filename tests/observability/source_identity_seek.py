"""Short real-player lifecycle probe; no installed configuration is touched."""
import hashlib,json,os,socket,subprocess,time,tempfile,sys
from pathlib import Path
from fractions import Fraction
root=Path(sys.argv[1]).resolve();base=root
reference=json.loads((root/'bridge-runs.json').read_text())[0]
class Player:
 def __init__(self,label,start,ids):
  self.label=label;self.events=[];self.index=0;self.started=time.perf_counter()
  self.ipc_dir=tempfile.TemporaryDirectory(prefix='aji-seek-');self.ipc=Path(self.ipc_dir.name)/'mpv.sock'
  vf=next(x for x in reference['command'] if x.startswith('--vf='))
  self.command=[str(base/'mpv'),'--no-config','--hwdec=no','--vo=gpu-next','--gpu-api=opengl','--geometry=480x270','--pause=yes','--keep-open=yes','--idle=yes','--audio=no','--framedrop=no','--interpolation=no','--osd-level=0','--sub=no','--screenshot-high-bit-depth=yes','--screenshot-png-compression=0',vf,'--start='+str(start),'--input-ipc-server='+str(self.ipc),'--msg-level=vd=v,animejanai=debug',str(base.parent/'lot-07/input128.mp4')]
  self.env={**reference['env'],'AJI_FRAME_IDS':str(ids),'AJI_VK_SAME':'exact'}
  self.log=(root/(label+'.log')).open('w')
  self.proc=subprocess.Popen(self.command,env={**os.environ,**self.env},stdout=self.log,stderr=subprocess.STDOUT)
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(10)
  deadline=time.monotonic()+10
  while not self.ipc.exists():
   if self.proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('player failed to create IPC')
   time.sleep(.02)
  self.sock.connect(str(self.ipc));self.stream=self.sock.makefile('rwb',buffering=0)
  self.wait_for(lambda: self.get('video-out-params') and self.get('time-pos') is not None)
  assert self.get('video-out-params')['h']==144
  assert self.get('pause')
 def read(self):
  line=self.stream.readline()
  if not line: raise RuntimeError('IPC closed')
  data=json.loads(line)
  if 'event' in data:self.events.append(data)
  return data
 def cmd(self,*args):
  self.index+=1;idx=self.index
  self.stream.write((json.dumps({'command':args,'request_id':idx})+'\n').encode())
  while True:
   data=self.read()
   if data.get('request_id')==idx:
    if data['error']!='success':raise RuntimeError(str(args)+': '+str(data))
    return data.get('data')
 def get(self,name):return self.cmd('get_property',name)
 def wait_for(self,predicate):
  deadline=time.monotonic()+10
  while True:
   try:
    if predicate():return
   except RuntimeError as e:
    if 'property unavailable' not in str(e):raise
   if time.monotonic()>deadline:raise TimeoutError('state did not settle: '+self.label)
   time.sleep(.01)
 def step(self):
  previous=self.get('time-pos');self.cmd('frame-step')
  self.wait_for(lambda:self.get('time-pos')>previous+1e-6 and self.get('pause'))
 def capture(self,name):
  path=root/(self.label+'-'+name+'.png')
  self.cmd('screenshot-to-file',str(path),'video')
  self.wait_for(lambda:path.exists() and path.stat().st_size>0)
  # screenshot-to-file reply is delivered after the completed encode.
  from PIL import Image
  with Image.open(path) as image:
   pixels=image.tobytes();size=image.size;mode=image.mode
  return {'name':name,'pts':self.get('time-pos'),'pixels_sha256':hashlib.sha256(pixels).hexdigest(),'png_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'png_bit_depth':path.read_bytes()[24],'size':size,'mode':mode,'path':str(path)}
 def seek(self,target):
  count=len(self.events);started=time.perf_counter();self.cmd('seek',target,'absolute+exact')
  self.wait_for(lambda:not self.get('seeking') and self.get('time-pos')>=target-1e-6 and any(x.get('event')=='playback-restart' for x in self.events[count:]))
  return {'target':target,'pts':self.get('time-pos'),'seconds':time.perf_counter()-started}
 def close(self):
  self.cmd('quit');self.proc.wait(timeout=10);self.stream.close();self.sock.close();self.log.close()
  player_unlinked=not self.ipc.exists();self.ipc_dir.cleanup();cleaned=not self.ipc.exists()
  return {'seconds':time.perf_counter()-self.started,'returncode':self.proc.returncode,'command':self.command,'env':self.env,'socket_cleaned':cleaned,'player_unlinked_socket':player_unlinked}
results={}
for name,start,ids in [('id-seek-reference',.0417,0),('id-seek-candidate',0,1)]:
 p=Player(name,start,ids)
 try:
  case={'captures':[]}
  if ids:
   for _ in range(3):p.step()
   case['seek']=p.seek(.0417)
  for j in range(3):
   if j:p.step()
   case['captures'].append(p.capture(str(j)))
  results[name]=case
 finally:
  results.setdefault(name,{})['process']=p.close()
  (root/'bridge-seek-summary.json').write_text(json.dumps(results,indent=2)+'\n')
a,b=[results[k]['captures'] for k in ['id-seek-reference','id-seek-candidate']]
assert all(x['png_sha256']==y['png_sha256'] and x['pts']==y['pts'] and x['png_bit_depth']==16 for x,y in zip(a,b))
results['same_png16_and_pts']=True
(root/'bridge-seek-summary.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'same_png16_and_pts':True,'pts':[x['pts'] for x in a],'seconds':[results[k]['process']['seconds'] for k in ['id-seek-reference','id-seek-candidate']]}))
