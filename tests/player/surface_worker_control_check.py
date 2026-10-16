#!/usr/bin/env python3
"""Real worker/legacy response to a controlled200ms fence delay, seek and one
terminal failure. SPEC.json: mpv,input,conf,models,lib,out,gate_library,
seek_png_sha256 (valid reference),identity_files (selected ONNX+plan).
Compile cuda_completion_gate.c with cc -shared -fPIC -O2 -pthread -ldl.
The injected interval proves control behavior, never a real GPU speed gain.
"""
import hashlib,json,os,re,socket,subprocess,sys,tempfile,time
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());art=Path(spec['out']);art.mkdir(parents=True,exist_ok=True)
exe=Path(spec['mpv']);input_file=Path(spec['input']);conf=Path(spec['conf']);models=Path(spec['models']);lib=Path(spec['lib'])
identity=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()+b''.join(Path(p).read_bytes() for p in [exe,input_file,conf,lib,spec['gate_library'],*spec['identity_files']])).hexdigest()
results={}
for mode in ['no','yes','fail']:
 worker='no' if mode=='no' else 'yes';name='ui-'+mode
 receipt=art/(name+'-result.json')
 if receipt.exists():
  saved=json.loads(receipt.read_text());assert saved.get('_identity')==identity,'Inputs changed; use fresh output directory'
  results[mode]=saved;continue
 endpoint=Path(tempfile.gettempdir())/f'aji-{os.getpid()}-{name}.sock';endpoint.unlink(missing_ok=True)
 gate=art/(name+'.arm');marker=art/(name+'.marker');error=art/(name+'.error')
 for path in [gate,marker,error]:path.unlink(missing_ok=True)
 env=os.environ.copy();env['LD_PRELOAD']=spec['gate_library'];env['AJI_TEST_GATE_FILE']=str(gate);env['AJI_TEST_GATE_MARKER']=str(marker);env['AJI_TEST_GATE_ERROR']=str(error)
 vf=f'@aji:animejanai=conf={conf}:model-dir={models}:lib={lib}:trtexec=/bin/false:slot=1:queue-depth=3:output-444=no:passthrough=no:prefetch=3:surface-worker={worker}'
 logpath=art/(name+'.log');args=[str(exe),'--no-config','--load-scripts=no','--vo=null','--ao=null','--audio=no','--pause=yes','--keep-open=yes','--idle=yes','--hwdec=nvdec','--hwdec-codecs=all','--screenshot-sw=yes','--stop-screensaver=no',f'--input-ipc-server={endpoint}',f'--log-file={logpath}',f'--vf={vf}',str(input_file)]
 stream=open(art/(name+'-stdout.log'),'wb');p=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,env=env);connection=None;request_id=0;started=time.monotonic()
 try:
  deadline=time.monotonic()+5
  while not endpoint.exists():
   assert p.poll() is None and time.monotonic()<deadline;time.sleep(.01)
  connection=socket.socket(socket.AF_UNIX);connection.settimeout(4);connection.connect(str(endpoint));reader=connection.makefile('rb')
  def cmd(command):
   global request_id
   request_id+=1;connection.sendall((json.dumps({'command':command,'request_id':request_id})+'\n').encode())
   while True:
    line=reader.readline();assert line,'IPC disconnected';r=json.loads(line)
    if r.get('request_id')==request_id:return r
  def prop(name):return cmd(['get_property',name]).get('data')
  def until(fn):
   end=time.monotonic()+4
   while not fn():
    assert time.monotonic()<end,(name,prop('vf-metadata/aji'));time.sleep(.005)
  until(lambda:prop('time-pos') is not None and int((prop('vf-metadata/aji') or {}).get('prefetch-ready',0))==3)
  if worker=='yes':
   until(lambda:int((prop('vf-metadata/aji') or {}).get('surface-worker-live-owners',-1))==0)
   assert prop('vf-metadata/aji')['surface-worker-active']=='yes'
  before=prop('vf-metadata/aji');result={'before':before,'args':args}
  if mode=='fail':
   error.write_text('inject once after actual event success\n');cmd(['seek','0.3','absolute+exact'])
   until(lambda:marker.exists() and 'Disabling filter aji' in logpath.read_text())
   until(lambda:(prop('video-out-params') or {}).get('w')==128)
   assert 'Surface worker completion failed: -3' in logpath.read_text() or 'Surface worker submission failed: -3' in logpath.read_text()
   result.update(error_marker=marker.read_text(),failed_output_discarded=True)
  else:
   gate.write_text('withhold terminal completion for200ms\n');cmd(['set_property','pause',False])
   until(lambda:marker.exists())
   t=time.monotonic();response=cmd(['get_property','pause']);latency=time.monotonic()-t
   assert response['error']=='success';meta=prop('vf-metadata/aji')
   result.update(property_response_s=latency,pending_meta=meta,gate_marker=marker.read_text())
   (art/(name+'-diagnostic.json')).write_text(json.dumps(result,indent=2)+'\n')
   if worker=='yes':assert int(meta['surface-worker-live-owners'])>0,(latency,meta)
   cmd(['set_property','pause',True])
   if worker=='yes':
    until(lambda:int((prop('vf-metadata/aji') or {}).get('surface-worker-live-owners',-1))==0)
    old_generation=int(prop('vf-metadata/aji')['surface-worker-generation'])
    cmd(['seek','0.3','absolute+exact'])
    until(lambda:prop('time-pos') is not None and prop('time-pos')>=.3 and int((prop('vf-metadata/aji') or {}).get('surface-worker-generation',0))>old_generation and int((prop('vf-metadata/aji') or {}).get('prefetch-ready',0))>0)
    shot=art/'worker-seek.png';assert cmd(['screenshot-to-file',str(shot),'video'])['error']=='success'
    expected=spec['seek_png_sha256']
    assert hashlib.sha256(shot.read_bytes()).hexdigest()==expected
    result['seek_meta']=prop('vf-metadata/aji');assert prop('pause') is True
  cmd(['quit']);p.wait(timeout=5);assert p.returncode==0
  if worker=='yes':
   matches=re.findall(r'Surface worker shutdown ownership: live=(\d+) retain=(\d+) release=(\d+)',logpath.read_text());assert matches,logpath.read_text()[-2000:]
   assert all(live=='0' and retained==released and int(retained)>=2 for live,retained,released in matches),matches
   result['shutdown_ownership']=matches
  result['duration_s']=time.monotonic()-started
  result['_identity']=identity
  results[mode]=result;(art/(name+'-result.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'mode':mode,**result}),flush=True)
 finally:
  if connection:connection.close()
  if p.poll() is None:p.terminate();p.wait(timeout=5)
  stream.close();endpoint.unlink(missing_ok=True)
assert results['no']['property_response_s']>.1,results
assert results['yes']['property_response_s']<results['no']['property_response_s']/4,results
(art/'responsive-summary.json').write_text(json.dumps(results,indent=2)+'\n')
