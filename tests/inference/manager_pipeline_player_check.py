#!/usr/bin/env python3
"""Consume the Manager-generated mixed profile on one NVDEC interval.
No performance/quality replay of the already qualified reader implementation.
"""
import hashlib,json,re,subprocess,sys
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True);receipt=out/'summary.json'
 if receipt.exists():raise RuntimeError('Conclusive receipt exists; do not replay.')
 source=Path(s['input_video'])
 # Preserve the known source cadence; packet-truncating a B-frame stream can
 # remove rate metadata. Limit output to the first interpolated interval.
 params={'conf':s['conf'],'model-dir':s['models'],'rife-model-dir':s['rife'],'lib':s['trt'],'pipeline-lib':s['library'],'pipeline-kernels':s['kernel'],'fruc-lib':s['fruc'],'trtexec':'/bin/false','slot':'1','passthrough':'no','output-444':'yes'}
 vf='@aji:animejanai='+':'.join(k+'=%'+str(len(v.encode()))+'%'+v for k,v in params.items())
 log=out/'mpv.log';frames=out/'frames.md5'
 args=[s['mpv'],'--no-config','--load-scripts=no','--audio=no','--hwdec=nvdec','--hwdec-codecs=all','--stop-screensaver=no','--frames=4','--msg-level=all=v,ffmpeg=warn,vf=debug',f'--log-file={log}',f'--vf={vf}',f'--o={frames}','--of=framemd5','--ovc=rawvideo',str(source)]
 if '--verify-only' not in sys.argv[2:]:
  (out/'executed-inputs.json').write_text(json.dumps({k:digest(s[k]) for k in ['mpv','conf','trt','library','kernel','fruc']},indent=2)+'\n')
  with (out/'stdout.log').open('w') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=30)
  assert r.returncode==0,r.returncode
 else:
  # Inspect the saved run after correcting a harness assertion; no GPU replay.
  assert 'finished playback, success' in log.read_text()
  assert all(v in log.read_text() for v in params.values())
 text=log.read_text();native=[(float(a),float(b),int(c)) for a,b,c in re.findall(r'Ordered output pts=([0-9.-]+) duration=([0-9.-]+) provenance=([0-9]+)',text)]
 assert 'cuda[nv12]' in text and 'Ordered GPU pipeline active: 3 stages, x4' in text,text[-3000:]
 assert len(native) in (4,8) and [x[2] for x in native]==[17,20,18,20]*(len(native)//4),native
 period=1001/24000
 for i,(pts,duration,flags) in enumerate(native):
  assert abs(pts-period*i/4)<=1e-9,(pts,i)
  assert abs(duration-period/4)<=1e-9,(duration,i)
 rows=[x for x in frames.read_text().splitlines() if x and not x.startswith('#')];assert len(rows)==4,rows
 assert '2560x1440' in frames.read_text()
 owners=re.search(r'Surface worker shutdown ownership: live=(\d+) retain=(\d+) release=(\d+)',text);assert owners and owners[1]=='0' and owners[2]==owners[3]
 result={'passed':True,'identity':{k:digest(s[k]) for k in ['mpv','conf','trt','library','kernel','fruc']},'args':args,'source_intervals_executed':len(native)//4,'native_produced_frames':len(native),'output_limit':4,'output_frames':4,'factor':4,'stages':3,'native_pts_durations':native,'owners_balanced':True,'dimensions':[2560,1440],'scope':'Actual Manager serialization consumed by native mpv/NVDEC; no new FPS/Quality/HDR claim'}
 receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
