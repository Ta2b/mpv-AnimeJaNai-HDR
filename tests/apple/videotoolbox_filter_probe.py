#!/usr/bin/env python3
"""Real mpv VideoToolbox import probe: exact post-download planes/PTS/color,
explicit unsupported fallback. No inference or timing benchmark.
"""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
mpv,library,clips,output=sys.argv[1:];out=Path(output);out.mkdir(exist_ok=True);receipt={'cases':{},'scope':'Real mpv/VideoToolbox/Metal import probe and software fallback; no inference/macvk renderer/FPS claim'}
def save():(out/'filter-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
def run(label,clip,fmt,probe):
 filters='format='+fmt+',lavfi=[showinfo]'
 if probe:filters='animejanai-vulkan=lib='+str(Path(library).resolve())+':slot=0:apple-import-probe=yes,'+filters
 cmd=[mpv,'--no-config','--load-scripts=no','--audio=no','--vo=null','--hwdec=videotoolbox','--hwdec-codecs=all','--untimed','--frames=3','--msg-level=all=debug','--vf='+filters,str(Path(clips)/clip)]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=30);log=r.stdout+r.stderr;(out/(label+'.log')).write_text(log)
 assert r.returncode==0,(label,r.returncode,log[-5000:])
 assert 'Using hardware decoding (videotoolbox)' in log,(label,'No VideoToolbox frames, do not qualify a software-decoder-only path',log[-6000:])
 frames=re.findall(r'n:\s*(\d+).*?pts:\s*(-?\d+).*?fmt:(\S+).*?s:(\d+x\d+).*?checksum:([0-9A-F]+).*?plane_checksum:\[([^\]]+)\]',log)
 assert len(frames)==3,(label,'Expected three actual plane checksums',frames,log[-6000:])
 colors=re.findall(r'color_range:(\S+) color_space:(\S+) color_primaries:(\S+) color_trc:(\S+)',log)
 assert colors,(label,'missing color metadata')
 return frames,colors,log
try:
 for name,clip,fmt,imported in [('nv12','sdr709.mp4','nv12',True),('matrix-fallback','sdr601.mp4','nv12',False),('p010-hdr-fallback','hdr10.mp4','yuv420p10',False)]:
  base,base_colors,_=run(name+'-base',clip,fmt,False)
  actual,colors,log=run(name+'-probe',clip,fmt,True)
  assert actual==base and colors==base_colors,(name,'planes/PTS/format/color differ')
  closed=re.search(r'Apple import probe closed: imports=(\d+) fallback=(\d+) software=(\d+) live=(\d+) resets=(\d+) sampled-bytes=(\d+)',log)
  assert closed,(name,'missing lifecycle receipt',log[-5000:])
  imports,fallback,software,live,resets,sampled=map(int,closed.groups());assert live==0 and resets>=1
  if imported:assert imports==3 and fallback==software==0 and sampled==9,closed.group(0)
  else:assert imports==0 and fallback+software==3 and sampled==0,closed.group(0)
  if 'hdr10' in clip:assert all('10' in row[2] for row in actual) and any('2084' in c[3] for c in colors)
  receipt['cases'][name]={'planes_pts_format_exact':True,'color_exact':True,'frame_records':actual,'color_records':colors,'imports':imports,'fallbacks':fallback,'software':software,'live':live,'resets':resets,'sampled_bytes':sampled};save()
 receipt['passed']=True;receipt['module_sha256']=hashlib.file_digest(open(library,'rb'),'sha256').hexdigest()
finally:save()
print(json.dumps(receipt,indent=2))
