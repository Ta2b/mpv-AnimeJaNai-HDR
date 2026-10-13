#!/usr/bin/env python3
"""Byte parity of the shared engine's pixel workers and RIFE CPU preparation.

Loads each real library in a separate process, runs shipped SPAN/RIFE models,
reuses input addresses, varies row padding and reconfigures sizes. Both pool
modes and profiling-off must match the immutable reference without tolerance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('reference', 'candidate', 'models', 'rife', 'report'):
        p.add_argument('--' + key, required=True, type=Path)
    p.add_argument('--case', action='append')
    args = p.parse_args()
    perf = '2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16'
    balanced = perf.replace('Performance', 'Balanced').replace('b5f48', 'b8f64')
    # name, model, before, factor, cut threshold, resize, chain length, reconfigure, RIFE code
    cases = [
        ('span-performance', perf, False, (1, 1), 0, 0, 1, True, 426),
        ('span-balanced', balanced, False, (1, 1), 0, 0, 1, False, 426),
        ('span-standard', perf.replace('V3.1Sharp1', 'V3.1'), False, (1, 1), 0, 0, 1, False, 426),
        ('span-standard-balanced', balanced.replace('V3.1Sharp1', 'V3.1'), False, (1, 1), 0, 0, 1, False, 426),
        ('rife-after-x4', perf, False, (4, 1), 0, 0, 1, True, 426),
        ('rife-before-x4', perf, True, (4, 1), 0, 0, 1, False, 426),
        ('rife-before-x2', perf, True, (2, 1), 0, 0, 1, False, 426),
        ('rife-resize-before', perf, True, (2, 1), 0, 48, 1, False, 426),
        ('rife-resize-after', perf, False, (2, 1), 0, 48, 1, False, 426),
        ('rife-rational', perf, True, (5, 2), 0, 0, 1, False, 426),
        ('rife-cuts-before', perf, True, (4, 1), .001, 0, 1, False, 426),
        ('rife-cuts-after', perf, False, (4, 1), .001, 0, 1, False, 426),
        ('two-models-before', perf, True, (2, 1), 0, 0, 2, False, 426),
        ('two-models-after', perf, False, (2, 1), 0, 0, 2, False, 426),
        ('rife-zero', perf, True, (2, 1), 0, 0, 1, False, 426),
        ('rife-425', perf, True, (2, 1), 0, 0, 1, False, 425),
        ('rife-422-lite', perf, True, (2, 1), 0, 0, 1, False, 4221),
    ]
    if args.case:
        requested = set(args.case)
        assert requested <= {case[0] for case in cases}, 'unknown case'
        cases = [case for case in cases if case[0] in requested]
    report = {'passed': False, 'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              'candidate_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
              'model_files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(args.models.glob('*SPANF3*.onnx'))},
              'rife_files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(args.rife.glob('*.onnx'))}, 'comparisons': []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='ajn-ort-parity-') as temporary:
        tmp = Path(temporary)
        for name, model, before, factor, cut, resize, length, reconfigure, code in cases:
            images, results = {}, {}
            for variant, library, pool, profile in [('reference', args.reference, '0', '0'),
                ('pool-off', args.candidate, '0', '1'), ('candidate', args.candidate, '1', '1'),
                ('profile-off', args.candidate, '1', '0')]:
                spec = {'conf': str(tmp / 'profile.conf'), 'stats': str(tmp / 'stats.txt'),
                        'models': str(args.models.resolve()), 'rife': str(args.rife.resolve()),
                        'model': model, 'device': '', 'before': before, 'factor': list(factor),
                        'rife_code': code, 'threshold': cut, 'resize': resize, 'chain_models': length,
                        'reconfigure': reconfigure, 'width': 128 if code == 4221 else 64,
                        'height': 128 if code == 4221 else 64, 'zero_endpoint': name == 'rife-zero',
                        'output': str(tmp / 'output.npz'), 'result': str(tmp / 'result.json')}
                spec_path = tmp / 'spec.json'
                spec_path.write_text(json.dumps(spec))
                env = dict(os.environ, AJI_ORT_PROVIDER='cpu', AJI_PIXEL_POOL=pool,
                           AJI_RIFE_PROFILE=profile, AJI_REUSE='off', AJI_REUSE_THRESHOLD='0')
                completed = subprocess.run([sys.executable, str(Path(__file__).with_name('vulkan_cache.py')),
                    '--worker', str(spec_path), '--library', str(library.resolve())],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                assert completed.returncode == 0, f'{name}/{variant}:\n{completed.stdout}'
                results[variant] = json.loads(Path(spec['result']).read_text())
                with np.load(spec['output']) as saved:
                    images[variant] = {key: saved[key].copy() for key in saved.files}
            for variant in ('pool-off', 'candidate', 'profile-off'):
                assert images[variant].keys() == images['reference'].keys()
                for key, reference in images['reference'].items():
                    assert np.array_equal(images[variant][key], reference), (
                        f'{name}/{variant}/{key}: {np.count_nonzero(images[variant][key] != reference)} changed bytes')
            stats = results['candidate']['stats']
            if factor != (1, 1):
                assert stats['RIFE'].startswith('rife_v4.'), f'{name}: interpolation not loaded'
                assert stats['RIFE profiling'] == 'on'
                runs = int(stats['RIFE measured runs'])
                assert runs > 0, f'{name}: real RIFE inference not exercised'
                assert float(stats['RIFE inference total ms']) > 0
                assert int(stats['RIFE source preparations']) < 2 * runs, f'{name}: source cache not exercised'
                if factor == (2, 1) and name != 'rife-zero':
                    assert int(stats['RIFE timestep updates']) == 0, f'{name}: warm timestep .5 was rewritten'
                assert results['profile-off']['stats']['RIFE profiling'] == 'off'
            item = {'case': name, 'frames_per_variant': results['candidate']['frames'],
                    'byte_identical': True, 'results': results}
            report['comparisons'].append(item)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
            print(f'PASS {name}: {item["frames_per_variant"]} images per variant, byte-identical', flush=True)
    report['passed'] = True
    args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
