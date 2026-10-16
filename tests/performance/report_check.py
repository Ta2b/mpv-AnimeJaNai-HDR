#!/usr/bin/env python3
"""Independent hand-computed fixtures: statistics/units, exclusions, context, unknowns and destination."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

tool=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed']
    if '--nested-context-only' not in sys.argv[3:]:
        print('Conclusive receipt exists; no repeat.');sys.exit()
    partial=json.loads((out/'before.json').read_text());partial['identity']['models_sha256']['model']='unknown'
    source=out/'nested-unknown-input.json';source.write_text(json.dumps(partial)+'\n')
    single=out/'nested-unknown-single.json';comparison=out/'nested-unknown-comparison.json'
    p=subprocess.run([sys.executable,str(tool),str(source),'--output',str(single)],text=True,capture_output=True,timeout=5)
    assert p.returncode==0,p.stderr
    assert json.loads(single.read_text())['runs'][0]['missing_context']==['identity.models_sha256']
    p=subprocess.run([sys.executable,str(tool),str(out/'before.json'),str(source),'--output',str(comparison)],text=True,capture_output=True,timeout=5)
    assert p.returncode!=0 and 'identity.models_sha256' in p.stderr and not comparison.exists()
    (out/'nested-context-summary.json').write_text(json.dumps(dict(passed=True,unknown_nested_model_context_refused=True,only_new_case_run=True))+'\n')
    print('Nested context guard passed; previous conclusive cases not repeated.');sys.exit()
identity=dict(media_sha256='a'*64,models_sha256={'model':'b'*64},settings_sha256='c'*64,
    machine_id='fixture-machine',runtime='fixture-runtime',driver='fixture-driver',output_contract='NV12 128x72')
trace=dict(schema='animejanai.measurements.v1',scope='chain_offscreen',data_origin='fixture',identity=identity,
    session=dict(desktop_load='fixture idle',player_state='offscreen',power_mode='fixed fixture'),
    provenance=dict(player_source='fixture-before',backend_source='fixture-backend'),timing_source='wall_completion',
    warmup_policy='explicit warmup excluded before measured wall window',sample_unit='output',
    window=dict(wall_seconds=2,media_seconds=3,excludes_compile_warmup=True),
    samples=[dict(phase='measure',completed=True,duration_ms=n) for n in [1,2,3,4]]
        +[dict(phase='compile',duration_ms=10000),dict(phase='warmup',duration_ms=1000),
          dict(phase='measure',completed=False,duration_ms=200)],
    pairs=[dict(phase='measure',completed=True,cost_ms=n) for n in [5,7]],
    resources=dict(allocations_count=dict(value=4,source='fixture allocator'),
        peak_ram_bytes=dict(value=1024,source='fixture RSS'),peak_vram_bytes=dict(value=2048,source='fixture GPU'),
        energy_joules=dict(value=120,source='fixture energy counter delta')),
    temperatures_celsius=[dict(wall_seconds=t,value=v,source='fixture sensor') for t,v in [(0,50),(1,52),(2,54)]])
def save(name,value):
    path=out/name;path.write_text(json.dumps(value,indent=2)+'\n');return path
before=save('before.json',trace);after_trace=copy.deepcopy(trace)
for row in after_trace['samples']:
    if row['phase']=='measure' and row.get('completed'):row['duration_ms']/=2
after_trace['provenance']['player_source']='fixture-after';after=save('after.json',after_trace)
def invoke(label,paths,destination=None):
    destination=destination or out/(label+'.json')
    p=subprocess.run([sys.executable,str(tool),*map(str,paths),'--output',str(destination)],text=True,capture_output=True,timeout=5)
    (out/(label+'.log')).write_text(json.dumps(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr),indent=2)+'\n')
    return p,destination
p,dest=invoke('comparison',[before,after]);assert p.returncode==0,p.stderr
report=json.loads(dest.read_text());a,b=report['runs']
assert a['latency']['count']==4 and a['latency']['median']==2.5 and a['latency']['maximum']==4
assert abs(a['latency']['p95']-3.85)<1e-12 and abs(a['latency']['p99']-3.97)<1e-12
assert a['excluded_samples']==dict(compile=1,warmup=1,incomplete=1)
assert a['pair_cost']['median']==6 and a['media_seconds_per_wall_second']==1.5
assert a['resources']['average_watts']['value']==60 and a['thermal']['delta_celsius']==4
assert a['thermal']['slope_celsius_per_second']==2 and a['thermal']['stability']=='not_established'
assert report['comparison']['latency_median_speed_ratio']==2
assert report['comparison']['media_throughput_change']==0 and not report['comparison']['gain_established']
assert a['evidence']['sha256']==hashlib.sha256(before.read_bytes()).hexdigest()
# A single partial trace remains exportable, but unknown context cannot certify a pair.
partial=copy.deepcopy(trace);partial.pop('resources');partial.pop('temperatures_celsius');partial['session']['desktop_load']='unknown'
unknown=save('unknown-input.json',partial);p,unknown_out=invoke('unknown',[unknown]);assert p.returncode==0,p.stderr
j=json.loads(unknown_out.read_text())['runs'][0]
assert j['resources']['energy_joules']['status']==j['thermal']['status']=='not_measured'
assert not j['comparable_context_complete'] and 'session.desktop_load' in j['missing_context']
for label,changed,needle in [('scope-mismatch',dict(scope='network_resident'),'scope'),
                              ('context-mismatch',dict(session=partial['session']),'session.desktop_load')]:
    bad=copy.deepcopy(trace);bad.update(changed);path=save(label+'-input.json',bad)
    p,failed=invoke(label,[before,path]);assert p.returncode!=0 and needle in p.stderr and not failed.exists()
bad=copy.deepcopy(trace);bad['window']['excludes_compile_warmup']=False
p,failed=invoke('warm-window',[save('bad-window-input.json',bad)]);assert p.returncode!=0 and 'exclude' in p.stderr and not failed.exists()
original=dest.read_bytes();p,_=invoke('existing',[before,after],dest)
assert p.returncode!=0 and 'exists' in p.stderr and dest.read_bytes()==original
summary=dict(passed=True,hand_computed_statistics_and_units=True,warmup_compile_incomplete_excluded=True,
    explicit_pair_cost_no_rife_remultiplication=True,latency_not_confused_with_wall_throughput=True,
    incompatible_scope_unknown_context_rejected=True,missing_sensors_unknown=True,thermal_stability_not_invented=True,
    destination_preserved=True,data_origin='fixture',image_calculation_changed=False,fps_claimed=False)
receipt.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
