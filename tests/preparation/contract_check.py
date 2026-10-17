#!/usr/bin/env python3
"""Short CPU check of actual media timing and preparation policy, no inference."""
import importlib.util,json,sys
from pathlib import Path
from fractions import Fraction
p=Path(__file__).resolve().parents[2]/'tools/interpolation/contract.py'
spec=importlib.util.spec_from_file_location('preparation_contract',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
assert not (out/'contract.json').exists(),'Conclusive receipt exists; no replay.'
job=m.Job.read(s['job']);identity=job.identity();media=m.probe(job);records=list(m.timeline(media,job.factor))
assert (media.width,media.height,media.source_frames,media.fps)==(1280,720,3,Fraction(24000,1001))
assert len(records)==6 and [x['kind'] for x in records]==['original','synthesized','original','synthesized','original','hold']
assert sum(x['duration'] for x in records)==media.duration==Fraction(1001,8000)
assert records[-1]['pts']+records[-1]['duration']==media.first_pts+media.duration
assert records[-1]['next'] is None and 'torch' not in sys.modules and 'cupy' not in sys.modules
failures=[]
def refused(name,fn):
 try:fn()
 except (m.PreparationError,FileNotFoundError):failures.append(name);return
 raise AssertionError(name+' accepted')
refused('unknown_version',lambda:m.Job.read({**s['job'],'version':2}))
refused('input_overwrite',lambda:m.Job.read({**s['job'],'destination':s['job']['source']}))
refused('fractional_factor',lambda:m.Job.read({**s['job'],'factor':2.5}))
refused('unknown_option',lambda:m.Job.read({**s['job'],'approximate':True}))
frames=[dict(best_effort_timestamp=t,duration=2002,width=1280,height=720) for t in [0,2002,4500]]
refused('VFR',lambda:m.validate_cfr(iter(frames),media.fps,media.timebase,1280,720))
frames[-1]['best_effort_timestamp']=4004;frames[-1]['duration']=1001
refused('short_final_duration',lambda:m.validate_cfr(iter(frames),media.fps,media.timebase,1280,720))
result=dict(passed=True,scope='CPU preflight/timing only; executor and Manager qualified separately',media=media.json(),identity=identity,output_frames=len(records),final_source_hold=True,no_inference_import=True,refusals=failures)
(out/'contract.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS exact CFR preparation schedule, original EOF duration, pinned identities and explicit refusals; no GPU inference')
