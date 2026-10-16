#!/usr/bin/env python3
"""Real Manager read/save/toggle, independently checked by the production native config parser."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

s=json.loads(Path(sys.argv[1]).read_text());out=Path(s['output']);out.mkdir(parents=True,exist_ok=True)
receipt=out/'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed'];print('Conclusive receipt exists; no repeat.');sys.exit()
results={};native={};elapsed={}
for label in ['before','after']:
    root=out/label;root.mkdir(exist_ok=True);start=time.monotonic()
    p=subprocess.run([s[label],str(root)],text=True,capture_output=True,timeout=20)
    (out/(label+'-stdout.log')).write_text(p.stdout);(out/(label+'-stderr.log')).write_text(p.stderr)
    assert p.returncode==0,p.stderr
    results[label]=json.loads(p.stdout.strip().splitlines()[-1]);elapsed[label]=time.monotonic()-start
    native[label]={}
    for row in results[label]['results']:
        expected='quality' if row['alias'] in ('old','quality') else 'fast'
        assert row['canonical']==expected and row['quality_checked']==(expected=='quality')
        assert row['fast_checked']==(expected=='fast') and row['drawings'] and row['spatial_sharp']
        for kind in ['input','saved']:
            path=root/(row['alias']+'-'+kind+'.conf')
            q=subprocess.run([s['native_parser'],str(path)],text=True,capture_output=True,check=True,timeout=3)
            parsed=json.loads(q.stdout);native[label][row['alias']+'-'+kind]=parsed
            assert parsed==dict(temporal=expected,drawings_configured=1,drawings_effective_policy=int(expected=='fast'),
                rife=1,model='2x_fixture_fp16',rife_model=426,ensemble=1,factor_num=5,factor_den=2,rife_before_upscale=1),parsed
    for mode in ['quality','fast']:
        q=subprocess.run([s['native_parser'],str(root/('toggle-'+mode+'.conf'))],text=True,capture_output=True,check=True,timeout=3)
        parsed=json.loads(q.stdout);assert parsed['temporal']==mode and parsed['ensemble']==1 and parsed['model']=='2x_fixture_fp16'
        native[label]['toggle-'+mode]=parsed
assert native['before']==native['after']
assert all(v is None for v in results['before']['notices'].values())
n=results['after']['notices'];assert all(n.values())
assert 'Spatial preset Quality' in n['SpatialQualityNotice']
assert 'Full RIFE (Quality)' in n['TemporalQualityNotice'] and 'Fast' in n['TemporalQualityNotice']
assert 'not available yet' in n['GlobalFidelityNotice']
assert 'ignored by temporal Quality' in n['RetimingNotice']
assert 'accumulator' in n['EnsemblePrecisionNotice']
summary=dict(passed=True,aliases=['old','quality','new','fast'],saved_modes_match_native_parser=True,
    real_ui_property_toggles_match_saved_modes=True,spatial_model_ensemble_factor_retimming_preserved=True,
    before_after_native_choices_identical=True,notices_distinguish_three_meanings=True,
    process_seconds=elapsed,fps_claimed=False,inference_repeated=False,
    qualification='UI/config semantics; existing Quality/Fast inference evidence reused')
(out/'manager-results.json').write_text(json.dumps(results,indent=2)+'\n')
(out/'native-parser-results.json').write_text(json.dumps(native,indent=2)+'\n')
receipt.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
