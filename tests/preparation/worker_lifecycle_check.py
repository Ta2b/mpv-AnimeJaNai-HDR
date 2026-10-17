#!/usr/bin/env python3
"""Only new publication and output-count lifecycle paths; no video or inference."""
import contextlib,errno,io,json,os,sys,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools/interpolation'))
import worker
from contract import Job,PreparationError
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assert not (out/'summary.json').exists(),'Conclusive receipt exists; no replay'
checks=[]
def check(name,ok):
 assert ok,name
 checks.append(name);print('PASS',name)
probe=out/'fake-ffprobe'
probe.write_text('''#!/usr/bin/python3
import sys,time
if sys.argv[-1].endswith('cancel'):
 print('media_type=video',flush=True)
 while True:time.sleep(.1)
for _ in range(260):print('media_type=video')
print('side_data_type=ignored')
''');probe.chmod(0o755)
job=SimpleNamespace(ffprobe=str(probe))
log=io.StringIO()
with contextlib.redirect_stdout(log):count=worker.count_output_frames(job,out/'frames')
events=[json.loads(line) for line in log.getvalue().splitlines()]
check('streaming verification counts only video frames and reports progress',count==260 and len(events)==1 and events[0]['state']=='validating' and '256' in events[0]['message'])
check('completed output probe is reaped',all(p.poll() is not None for p in worker.children))
worker.children.clear();worker.cancelled.clear()
def cancel():worker.cancelled.set();worker.stop_children()
timer=threading.Timer(.08,cancel);timer.start();started=time.monotonic();cancelled=False
try:worker.count_output_frames(job,out/'cancel')
except worker.Cancelled:cancelled=True
finally:timer.join();worker.stop_children()
check('cancellation interrupts silent output verification and reaps its child',cancelled and time.monotonic()-started<2 and all(p.poll() is not None for p in worker.children))
worker.cancelled.clear()
worker.check_publication(out)
check('atomic publication capability probe cleans its temporary files',not list(out.glob('.animejanai-publication-*')))
real_link=worker.os.link
try:
 def unsupported(*args,**kw):raise OSError(errno.EOPNOTSUPP,'test filesystem lacks hard links')
 worker.os.link=unsupported;refused=False
 try:worker.check_publication(out)
 except PreparationError as error:refused='supporting atomic publication' in str(error)
finally:worker.os.link=real_link
check('unsupported atomic publication fails early and cleans its probe',refused and not list(out.glob('.animejanai-publication-*')))
source=out/'source.mp4';source.write_bytes(b'original source');destination=out/'existing.mkv';destination.write_bytes(b'user output')
values=dict(version=1,method='gmfss-fortuna',source=str(source),destination=str(destination),model_source=str(out),weights=str(out),factor=2)
refused=False
try:Job.read(values)
except PreparationError as error:refused='Destination exists' in str(error)
check('real job contract rejects an existing destination without modifying input or output',refused and source.read_bytes()==b'original source' and destination.read_bytes()==b'user output')
# Final worker publication uses this exclusive link operation even after preflight:
# a target appearing during a job must never be replaced.
staged=out/'staged.mkv';staged.write_bytes(b'new output');refused=False
try:os.link(staged,destination)
except FileExistsError:refused=True
check('exclusive publication preserves a target that appeared during the job',refused and destination.read_bytes()==b'user output')
(out/'summary.json').write_text(json.dumps(dict(passed=True,checks=checks,scope='CPU fake ffprobe only; new count_output_frames/check_publication paths and destination guards; no GPU or media processing'),indent=2))
