#!/usr/bin/env python3
"""Prepare/verify a RIFE x2 -> FRUC x2 comparison without replaying inference.

SPEC: rife_spec (path to the conclusive median spec), output (case directory),
median_dir (five acquired RIFE .5 outputs). prepare writes RGBA sources and a
quarter-phase native spec. Run FRUC/native probes separately, then verify.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024): h.update(block)
    return h.hexdigest()


def encoded(rgb):
    assert np.isfinite(rgb).all()
    return np.clip(rgb * 255, 0, 255).astype(np.uint8)


def write_or_match(path, data):
    if path.exists():
        assert path.stat().st_size == len(data) and sha(path) == hashlib.sha256(data).hexdigest(), path
    else:
        path.write_bytes(data)


def main():
    s = json.loads(Path(sys.argv[1]).read_text()); action = sys.argv[2]
    assert action in ('prepare', 'verify')
    base = json.loads(Path(s['rife_spec']).read_text())
    out = Path(s['output']); out.mkdir(parents=True, exist_ok=True)
    w, h = base['width'], base['height']
    sources = np.fromfile(base['input'], np.uint8).reshape(-1, h, w, 3)
    medians = Path(s['median_dir'])
    acquired = json.loads((medians / 'summary.json').read_text())
    assert acquired['passed'] and acquired['outputs'] == len(sources) - 1
    assert acquired['identity']['files']['input'] == sha(base['input'])
    fps = Fraction(*s.get('source_fps', [24000, 1001]))
    expanded = np.ones((len(sources) * 2 - 1, h, w, 4), np.uint8)
    expanded[::2, :, :, :3] = sources
    for i in range(len(sources) - 1):
        expanded[2 * i + 1, :, :, :3] = encoded(np.load(medians / f'{i:03}.npy'))
    write_or_match(out / 'rife2x-sources.rgba', expanded.tobytes())
    quarters = dict(base, timesteps=[.25, .75], output=str((out / 'rife-quarters').resolve()))
    spec_path = out / 'rife-quarters.spec.json'
    if spec_path.exists(): assert json.loads(spec_path.read_text()) == quarters
    else: spec_path.write_text(json.dumps(quarters, indent=2) + '\n')
    timebase = 1 / (4 * fps)
    count = (len(sources) - 1) * 4 + 1
    timeline = []
    for i in range(count):
        entry = {'pts': i, 'duration': 4 if i == count - 1 else 1}
        if i % 4 == 0: entry.update(kind='source', source_index=i // 4)
        else: entry.update(kind='rife' if i % 4 == 2 else 'fruc', pair=i // 4,
                           phase=str(Fraction(i % 4, 4)))
        timeline.append(entry)
    assert sum(x['duration'] for x in timeline) * timebase == len(sources) / fps
    assert all(a['pts'] + a['duration'] == b['pts'] for a, b in zip(timeline, timeline[1:]))
    planning = {'source_fps': [fps.numerator, fps.denominator],
                'timebase': [timebase.numerator, timebase.denominator],
                'stage_factors': [[2, 1], [2, 1]], 'output_fps': [4 * fps.numerator, fps.denominator],
                'frames': timeline, 'sdk_timestamp_policy': 'SDK uses a constant epoch offset; media PTS use this exact rational schedule',
                'tail_policy': 'last original keeps its source duration; no fictitious future source'}
    (out / 'timeline.json').write_text(json.dumps(planning, indent=2) + '\n')
    if action == 'prepare':
        print(json.dumps({'prepared_sources': len(expanded), 'fruc_fps': float(2 * fps),
                          'rife_quarter_spec': str(spec_path), 'expected_frames': count})); return
    r = json.loads((out / 'rife-quarters/summary.json').read_text())
    f = json.loads((out / 'fruc-quarters.json').read_text())
    needed = 2 * (len(sources) - 1)
    assert r['passed'] and r['outputs'] == needed and r['identity']['timesteps'] == [.25, .75]
    assert f['passed'] and f['cleanup_success'] and f['outputs'] == needed
    fruc = np.fromfile(out / 'fruc-quarters.rgba', np.uint8).reshape(needed, h, w, 4)
    calls = [x for x in f['calls'] if not x['prime']]
    assert len(calls) == needed
    # Each final sequence has identical sources and RIFE medians, with only the
    # quarter-stage technology changed. Raw outputs are review artifacts, not CFR videos.
    raw_paths = [out / 'rife4x.rgb', out / 'hybrid4x.rgb']
    handles = [p.open('wb') for p in raw_paths]
    shared_equal = True
    try:
        for frame in timeline:
            if frame['kind'] == 'source':
                a = b = sources[frame['source_index']]
            elif frame['kind'] == 'rife':
                a = b = expanded[frame['pair'] * 2 + 1, :, :, :3]
            else:
                i = 2 * frame['pair'] + (frame['phase'] == '3/4')
                a = encoded(np.load(out / f'rife-quarters/{i:03}.npy'))
                b = fruc[i, :, :, :3]
            if frame['kind'] != 'fruc': shared_equal &= np.array_equal(a, b)
            for handle, pixels in zip(handles, (a, b)): handle.write(pixels.tobytes())
    finally:
        for handle in handles: handle.close()
    assert shared_equal
    pairs = []
    for i in range(len(sources) - 1):
        rc = r['calls'][2 * i:2 * i + 2]; fc = calls[2 * i:2 * i + 2]
        assert [x['pair_or_input'] for x in rc] == [i, i] and [x['phase'] for x in rc] == [.25, .75]
        pairs.append({'pair': i, 'contains_cold_rife': any(x['cold'] for x in rc),
                      'rife_quarters_ms': sum(x['complete_wall_ms'] for x in rc),
                      'fruc_quarters_ms': sum(x['complete_ms'] for x in fc)})
    result = {'passed': True, 'source_frames': len(sources), 'output_frames': count,
              'reused_rife_medians': len(sources) - 1, 'new_quarters_per_method': needed,
              'shared_sources_medians_exact': bool(shared_equal), 'fruc_repetitions': f['repetitions'],
              'duration_exact': True, 'pairs': pairs, 'artifacts': {p.name: sha(p) for p in raw_paths},
              'scope': 'Additional quarter-stage costs only; no claim of integrated player FPS or quality equivalence'}
    (out / 'cascade-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
