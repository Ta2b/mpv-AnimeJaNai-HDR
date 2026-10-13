#!/usr/bin/env python3
"""Compare real Vulkan outputs against an immutable pre-change library.

Each library runs in a separate process. No mock kernels and no tolerance: every
active output byte must match. Inputs reuse their addresses, with varying row
padding, so a pointer-based cache cannot pass. --benchmark adds alternating
reference/candidate trials at the requested size, without changing the models.
"""
import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

import numpy as np


class Plan(ct.Structure):
    _fields_ = [(name, ct.c_int) for name in
                ('width', 'height', 'numerator', 'denominator', 'active')]


def profile(model, before, factor, threshold, resize, chain_models, ensemble=False):
    text = ('[global]\nbackend=Vulkan\n[slot_1]\n'
            'chain_1_min_resolution=0x0\nchain_1_max_resolution=16384x16384\n'
            f'chain_1_rife={"yes" if factor != (1, 1) else "no"}\n'
            f'chain_1_rife_factor_numerator={factor[0]}\nchain_1_rife_factor_denominator={factor[1]}\n'
            'chain_1_rife_model=46\n'
            f'chain_1_rife_ensemble={"yes" if ensemble else "no"}\n'
            f'chain_1_rife_before_upscale={"yes" if before else "no"}\n'
            f'chain_1_rife_scene_detect_threshold={threshold}\n')
    for i in range(chain_models):
        text += f'chain_1_model_{i+1}_name={model}\n'
        if i == 0 and resize:
            text += f'chain_1_model_{i+1}_resize_height_before_upscale={resize}\n'
    return text


def worker(args):
    spec = json.loads(Path(args.worker).read_text())
    lib = ct.CDLL(str(Path(args.library).resolve()))
    bytep = ct.POINTER(ct.c_ubyte)
    lib.aji_vk_create.argtypes = [ct.c_char_p] * 5 + [ct.c_int]
    lib.aji_vk_create.restype = ct.c_void_p
    lib.aji_vk_configure.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_double, ct.POINTER(Plan)]
    lib.aji_vk_process.argtypes = [ct.c_void_p, bytep, ct.c_ssize_t, bytep, ct.c_ssize_t,
                                  ct.c_double, bytep, ct.c_ssize_t]
    lib.aji_vk_error.argtypes = [ct.c_void_p]
    lib.aji_vk_error.restype = ct.c_char_p
    lib.aji_vk_destroy.argtypes = [ct.c_void_p]
    conf, stats = Path(spec['conf']), Path(spec['stats'])
    conf.write_text(profile(spec['model'], spec['before'], tuple(spec['factor']),
                            spec['threshold'], spec['resize'], spec['chain_models'],
                            spec.get('ensemble', False)))
    context = lib.aji_vk_create(os.fsencode(conf), os.fsencode(spec['models']),
                               os.fsencode(spec['rife']), spec['device'].encode(),
                               os.fsencode(stats), 1)
    if not context:
        raise RuntimeError(lib.aji_vk_error(None).decode())
    outputs, times, intervals = {}, [], []
    completed = 0
    zero_calls = 0
    try:
        sizes = [(spec['width'], spec['height'])]
        if spec.get('reconfigure'):
            sizes += [(spec['width'] + 16, spec['height'] + 8), sizes[0]]
        for w, h in sizes:
            plan = Plan()
            if lib.aji_vk_configure(context, w, h, 24, ct.byref(plan)):
                raise RuntimeError(lib.aji_vk_error(context).decode())
            assert (plan.numerator, plan.denominator) == tuple(spec['factor']), (
                f'RIFE factor not active: {plan.numerator}/{plan.denominator}, expected {spec["factor"]}')
            stride, out_stride = w * 3 + 17, plan.width * 3 + 19
            previous = np.zeros((h, stride), np.uint8)
            current = np.zeros_like(previous)
            out = np.zeros((plan.height, out_stride), np.uint8)
            y, x, k = np.indices((h, w, 3))

            def picture(identity):
                image = ((x * 3 + y * 2 + k * 30) % 256).astype(np.uint8)
                # Most changes are local; one identity changes a single RGB byte.
                if identity:
                    image[h//4:h//2, w//4:w//2] ^= np.uint8(identity * 17 % 256)
                if identity == 5:
                    image = ((x * 3 + y * 2 + k * 30) % 256).astype(np.uint8)
                    image[h//2, w//2, 2] ^= np.uint8(1)
                return image

            sequence = ([i % 5 for i in range(spec['pairs'] + 1)] if spec.get('benchmark')
                        else [0, 1, 2, 2, 2, 5, 0, 3, 4, 1, 0])
            if spec.get('held'):
                sequence = [0] * len(sequence)
            if spec['factor'] == [1, 1]:
                steps = [1.0]
            elif spec['factor'][1] == 1:
                steps = [i/spec['factor'][0] for i in range(1, spec['factor'][0] + 1)]
                if spec.get('zero_endpoint'):
                    steps.insert(0, 0.0)
            else:
                # Same rational accumulator as the mpv bridge, updated below per pair.
                steps = None
            acc = spec['factor'][1]
            for index, identity in enumerate(sequence):
                current.fill((index * 31) % 256)
                current[:, :w*3] = picture(identity).reshape(h, w*3)
                if index:
                    previous.fill((index * 23) % 256)
                    previous[:, :w*3] = picture(sequence[index-1]).reshape(h, w*3)
                expected_current, expected_previous = current.copy(), previous.copy()
                instants = [1.0] if not index else steps
                if instants is None:
                    instants = []
                    while acc <= spec['factor'][0]:
                        instants.append(acc / spec['factor'][0])
                        acc += spec['factor'][1]
                    acc -= spec['factor'][0]
                interval_start = time.perf_counter()
                for t in instants:
                    if not spec.get('benchmark'):
                        # A packed endpoint must remain independent of the caller's output pitch.
                        out_stride = plan.width * 3 + 19 + completed % 3
                        out = np.empty((plan.height, out_stride), np.uint8)
                    out.fill(123)
                    start = time.perf_counter()
                    status = lib.aji_vk_process(context, previous.ctypes.data_as(bytep) if index else None,
                                               stride, current.ctypes.data_as(bytep), stride, t,
                                               out.ctypes.data_as(bytep), out_stride)
                    elapsed = (time.perf_counter() - start) * 1000
                    if status:
                        raise RuntimeError(lib.aji_vk_error(context).decode())
                    assert np.array_equal(current, expected_current), 'current input mutated'
                    assert np.array_equal(previous, expected_previous), 'previous input mutated'
                    assert np.all(out[:, plan.width*3:] == 123), 'output row padding overwritten'
                    if not spec.get('benchmark'):
                        outputs[f'frame_{completed}'] = out[:, :plan.width*3].copy()
                    if index >= spec.get('warmup', 0):
                        times.append(elapsed)
                    completed += 1
                    zero_calls += int(index > 0 and t == 0)
                if index >= spec.get('warmup', 0):
                    intervals.append((time.perf_counter() - interval_start) * 1000)
        values = {}
        for line in stats.read_text().splitlines():
            if ': ' in line:
                key, value = line.split(': ', 1)
                values[key] = value
        if not spec.get('benchmark'):
            np.savez(spec['output'], **outputs)
        result = {'frames': completed, 'stats': values, 'zero_calls': zero_calls,
                  'median_frame_ms': statistics.median(times),
                  'median_interval_ms': statistics.median(intervals),
                  'p95_frame_ms': float(np.percentile(times, 95)),
                  'mean_frame_ms': statistics.mean(times)}
        Path(spec['result']).write_text(json.dumps(result, indent=2) + '\n')
    finally:
        lib.aji_vk_destroy(context)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--models', type=Path)
    p.add_argument('--rife', type=Path)
    p.add_argument('--device', default='')
    p.add_argument('--report', type=Path)
    p.add_argument('--benchmark', action='store_true')
    p.add_argument('--width', type=int)
    p.add_argument('--height', type=int)
    p.add_argument('--case', action='append', help='run only named cases (repeatable)')
    p.add_argument('--candidate-models', type=Path, help='experimental converted graph variants')
    p.add_argument('--candidate-cache', choices=('0', '1'), default='1',
                   help='isolate graph changes in benchmarks; parity always checks both cache modes')
    p.add_argument('--reference-cache', choices=('0', '1'), default='0',
                   help='benchmark against an already optimized reference')
    p.add_argument('--reference-rife-cache', choices=('0', '1'), default='0',
                   help='keep resident RIFE inputs enabled in an optimized reference')
    p.add_argument('--candidate-rife-cache', choices=('0', '1'), default='1',
                   help='isolate resident RIFE inputs in benchmarks; parity checks both modes')
    p.add_argument('--pairs', type=int, default=12)
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--worker')
    p.add_argument('--library')
    args = p.parse_args()
    if args.worker:
        worker(args)
        return
    args.width = args.width or (1280 if args.benchmark else 64)
    args.height = args.height or (720 if args.benchmark else 64)
    for key in ('reference', 'candidate', 'models', 'rife', 'report'):
        if getattr(args, key) is None:
            p.error('--' + key + ' is required')
    perf = '2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16'
    balanced = '2x_AnimeJaNai_HD_V3.1Sharp1_Balanced_SPANF3_b8f64_unshuffle_fp16'
    cases = [
        ('span-held-and-changing', perf, False, (1, 1), 0, 0, 1, True),
        ('balanced-held-and-changing', balanced, False, (1, 1), 0, 0, 1, False),
        ('performance-standard', perf.replace('V3.1Sharp1', 'V3.1'), False, (1, 1), 0, 0, 1, False),
        ('balanced-standard', balanced.replace('V3.1Sharp1', 'V3.1'), False, (1, 1), 0, 0, 1, False),
        ('rife-only', perf, False, (4, 1), 0, 0, 0, False),
        ('rife-after-x4', perf, False, (4, 1), 0, 0, 1, True),
        ('rife-before-x4', perf, True, (4, 1), 0, 0, 1, False),
        ('rife-before-resize', perf, True, (4, 1), 0, 48, 1, False),
        ('rife-after-resize', perf, False, (2, 1), 0, 48, 1, False),
        ('rife-rational', perf, True, (5, 2), 0, 0, 1, False),
        ('scene-cut-after', perf, False, (4, 1), .001, 0, 1, False),
        ('scene-cut-before', perf, True, (4, 1), .001, 0, 1, False),
        ('two-models-after', perf, False, (2, 1), 0, 0, 2, False),
        ('two-models-before', perf, True, (2, 1), 0, 0, 2, False),
        ('rife-ensemble-after', perf, False, (4, 1), 0, 0, 1, False),
        ('rife-ensemble-before', perf, True, (2, 1), 0, 0, 1, False),
        ('rife-only-x8', perf, False, (8, 1), 0, 0, 0, False),
        ('rife-zero-endpoint', perf, False, (2, 1), 0, 0, 1, False),
    ]
    if args.benchmark:
        cases = [(name, perf, before, factor, 0, 0, 1, False) for name, before, factor in
                 [('span-changing', False, (1, 1)), ('span-held', False, (1, 1)),
                  ('rife-after-x4', False, (4, 1)), ('rife-before-x4', True, (4, 1))]]
    if args.case:
        requested = set(args.case)
        assert requested <= {case[0] for case in cases}, 'unknown case name'
        cases = [case for case in cases if case[0] in requested]
    report = {'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              'candidate_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
              'input_size': [args.width, args.height],
              'reference_cache': args.reference_cache,
              'reference_rife_cache': args.reference_rife_cache,
              'candidate_cache': args.candidate_cache,
              'candidate_rife_cache': args.candidate_rife_cache,
              'benchmark': args.benchmark, 'comparisons': []}
    report['model_files'] = {
        mode: {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(folder.glob('*.ncnn.*')) if path.suffix in ('.param', '.bin')}
        for mode, folder in [('reference', args.models),
                             ('candidate', args.candidate_models or args.models)]}
    report['rife_files'] = {str(path.relative_to(args.rife)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(args.rife.rglob('*'))
                            if path.is_file() and path.suffix in ('.param', '.bin')}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report['passed'] = False
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='ajn-cache-') as temporary:
        tmp = Path(temporary)
        for name, model, before, factor, threshold, resize, chain_models, reconfigure in cases:
            trials = args.trials if args.benchmark else 1
            for trial in range(trials):
                variants = [('reference', args.reference, args.reference_cache, args.reference_rife_cache),
                            ('candidate-off', args.candidate, '0', '0'),
                            ('candidate-gpu-off', args.candidate, '1', '0'),
                            ('candidate', args.candidate,
                             args.candidate_cache if args.benchmark else '1',
                             args.candidate_rife_cache if args.benchmark else '1')]
                if args.benchmark:
                    variants = [variants[0], variants[3]]
                    if trial % 2:
                        variants.reverse()
                results, images = {}, {}
                for variant, library, cache, rife_cache in variants:
                    spec = {'conf': str(tmp/'profile.conf'), 'stats': str(tmp/'stats.txt'),
                            'models': str((args.candidate_models if variant != 'reference' and
                                           args.candidate_models else args.models).resolve()),
                            'rife': str(args.rife.resolve()),
                            'device': args.device, 'model': model, 'before': before, 'factor': factor,
                            'ensemble': name.startswith('rife-ensemble-'),
                            'zero_endpoint': name == 'rife-zero-endpoint',
                            'threshold': threshold, 'resize': resize, 'chain_models': chain_models,
                            'reconfigure': reconfigure, 'width': args.width, 'height': args.height,
                            'output': str(tmp/f'{variant}.npz'), 'result': str(tmp/f'{variant}.json'),
                            'benchmark': args.benchmark, 'pairs': args.pairs,
                            'warmup': 3 if args.benchmark else 0, 'held': name == 'span-held'}
                    spec_path = tmp/'spec.json'
                    spec_path.write_text(json.dumps(spec))
                    result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                             '--worker', str(spec_path), '--library', str(library.resolve())],
                                            env=dict(os.environ, AJI_VK_CACHE=cache,
                                                     AJI_VK_RIFE_GPU_CACHE=rife_cache),
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    assert result.returncode == 0, f'{name}/{variant}:\n{result.stdout}'
                    results[variant] = json.loads(Path(spec['result']).read_text())
                    if not args.benchmark:
                        with np.load(spec['output']) as output:
                            images[variant] = {key: output[key].copy() for key in output.files}
                if images:
                    for variant in ('candidate-off', 'candidate-gpu-off', 'candidate'):
                        assert images['reference'].keys() == images[variant].keys()
                        for key in images['reference']:
                            a, b = images['reference'][key], images[variant][key]
                            assert np.array_equal(a, b), (
                                f'{name}/{variant}/{key}: changed {np.count_nonzero(a != b)} output bytes')
                    candidate_stats = results['candidate']['stats']
                    multiplier = 3 if reconfigure else 1
                    assert int(candidate_stats['Source preparations']) == 9 * multiplier, (
                        f'{name}: wrong exact source cache misses, {candidate_stats}')
                    if factor != (1, 1):
                        assert candidate_stats['RIFE'] == '4.6', f'{name}: RIFE not loaded'
                        assert int(candidate_stats['Pair preparations']) == 9 * multiplier
                        assert int(candidate_stats['RIFE inferences']) > 0, f'{name}: no interpolation computed'
                        uploads = int(candidate_stats['RIFE cached uploads'])
                        hits = int(candidate_stats['RIFE GPU input hits'])
                        calls = int(candidate_stats['RIFE inferences'])
                        assert uploads > 0 and hits > 0, f'{name}: GPU cache not exercised'
                        assert uploads + hits == 2 * (calls - results['candidate']['zero_calls']), (
                            f'{name}: wrong GPU input accounting')
                        assert int(candidate_stats['RIFE cached tensor bytes']) > 0
                        rgb_preparations = int(candidate_stats['RIFE RGB preparations'])
                        assert 0 < rgb_preparations <= int(candidate_stats['Source preparations'])
                        if not threshold:
                            assert rgb_preparations == 9 * multiplier, (
                                f'{name}: RGB inputs must be packed exactly once per source')
                        assert int(candidate_stats['RIFE direct RGB outputs']) == (0 if before else calls), (
                            f'{name}: wrong final RIFE output path')
                        for variant in ('candidate-off', 'candidate-gpu-off'):
                            assert int(results[variant]['stats']['RIFE cached uploads']) == 0
                            assert int(results[variant]['stats']['RIFE GPU input hits']) == 0
                    if not before or factor == (1, 1):
                        assert int(candidate_stats['SPAN inferences']) == 9 * multiplier * chain_models
                item = {'case': name, 'trial': trial, 'results': results,
                        'byte_identical': True if images else None}
                report['comparisons'].append(item)
                args.report.write_text(json.dumps(report, indent=2) + '\n')
                reference, candidate = results['reference'], results['candidate']
                speedup = reference['median_interval_ms']/candidate['median_interval_ms']
                print(f'PASS {name} trial={trial} frames={candidate["frames"]} '
                      f'byte_identical={True if images else "not_compared"} interval_speedup={speedup:.3f} '
                      f'SPAN={candidate["stats"].get("SPAN inferences", "?")}', flush=True)
    report['passed'] = True
    args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
