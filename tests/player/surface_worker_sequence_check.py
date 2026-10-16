#!/usr/bin/env python3
"""SPEC.json: mpv,input,conf,models,lib,out,identity_files (selected ONNX+plan).
Phase nv12 (12 frames) or444 (one frame): same128x72 SPAN chain ->256x144.
Never repeat a successful receipt on unchanged inputs. CUDA/TRT LD_LIBRARY_PATH inherited.
"""
import hashlib,json,subprocess,sys,time
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());phase=sys.argv[2]
assert phase in ('nv12','444')
art=Path(spec['out']);art.mkdir(parents=True,exist_ok=True)
exe=Path(spec['mpv']);input_file=Path(spec['input']);conf=Path(spec['conf']);models=Path(spec['models']);lib=Path(spec['lib'])
identity=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()+b''.join(Path(p).read_bytes() for p in [exe,input_file,conf,lib,*spec['identity_files']])).hexdigest()
receipt=art/(phase+'-passed.json')
if receipt.exists():
 result=json.loads(receipt.read_text());assert result['identity']==identity,'Inputs changed; use fresh output directory'
 print(json.dumps(result));sys.exit(0)
output444='yes' if phase=='444' else 'no'
rawformat='yuv444p16le' if phase=='444' else 'nv12'
frame_size=256*144*6 if phase=='444' else 256*144*3//2
frame_count=1 if phase=='444' else 12
results=[]
for worker in ['no','yes']:
 capacity=3
 name=f'sequence-{worker}';output=art/(name+'.nut')
 assert not (art/(name+'.json')).exists(),'Conclusive receipt exists; no repeat'
 vf=f'@aji:animejanai=conf={conf}:model-dir={models}:lib={lib}:trtexec=/bin/false:slot=1:queue-depth=3:output-444={output444}:passthrough=no:prefetch={capacity}:surface-worker={worker}'
 args=[str(exe),'--no-config','--load-scripts=no','--ao=null','--audio=no','--hwdec=nvdec','--hwdec-codecs=all','--stop-screensaver=no',f'--log-file={art}/{name}.log',f'--vf={vf}',f'--o={output}','--of=nut','--ovc=rawvideo',str(input_file)]
 if phase=='444':args.insert(-1,'--frames=1')
 t=time.monotonic()
 with open(art/(name+'-stdout.log'),'wb') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=20)
 assert r.returncode==0,(name,r.returncode)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',str(output)]))
 raw=art/(name+'.nv12')
 subprocess.run(['ffmpeg','-v','error','-y','-i',str(output),'-pix_fmt',rawformat,'-f','rawvideo',str(raw)],check=True)
 data=raw.read_bytes();size=frame_size
 frames=[{'pts':f['pts'],'time_base':probe['streams'][0]['time_base'],'sha256':hashlib.sha256(data[i*size:(i+1)*size]).hexdigest()} for i,f in enumerate(probe['frames'])]
 assert len(frames)==frame_count and len(data)==frame_count*size,(len(frames),len(data))
 assert probe['streams'][0]['width']==256 and probe['streams'][0]['height']==144
 log=(art/(name+'.log')).read_text();assert 'Decoder format: 128x72 [0:1] cuda[nv12]' in log and 'backend: TensorRT' in log
 if worker=='yes':assert 'Surface CUDA worker active: 3 job slots' in log
 result={'worker':worker,'capacity':capacity,'duration_s':time.monotonic()-t,'frames':frames,'raw_sha256':hashlib.sha256(data).hexdigest(),'args':args,'returncode':r.returncode,'width':256,'height':144}
 (art/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');results.append(result)
assert results[0]['frames']==results[1]['frames'],'pixels or PTS changed'
(art/'sequence-summary.json').write_text(json.dumps({'frames':frame_count,'pixels_exact':True,'pts_exact':True,'off_s':results[0]['duration_s'],'on_s':results[1]['duration_s'],'raw_sha256':results[0]['raw_sha256']},indent=2)+'\n')
print((art/'sequence-summary.json').read_text())
receipt.write_text(json.dumps({'passed':True,'identity':identity,'phase':phase},indent=2)+'\n')
