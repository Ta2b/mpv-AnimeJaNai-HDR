#!/usr/bin/env python3
"""Exercise the real Vulkan drawing cache, including its approximation limits.

The default and forced-exact modes must match a committed reference byte for
byte. The opt-in similar mode must keep its original anchor, reject a fade or
high-contrast movement, and reuse the anchor for compression noise. A genuine
low-contrast movement is deliberately included: approximation can discard it.
Libraries run in separate processes; no mock inference or numerical tolerance.
"""
import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

from vulkan_cache import Plan, profile


MODEL = '2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16'
CASES = ('span', 'rife-before', 'rife-after')


def pictures(width, height):
    y, x, k = np.indices((height, width, 3))
    anchor = (48 + (x * 3 + y * 2 + k * 17) % 112).astype(np.uint8)
    noise = (anchor.astype(np.int16) + np.random.default_rng(13).integers(
        -1, 2, anchor.shape, dtype=np.int16)).astype(np.uint8)
    chroma = anchor.copy()
    chroma[height//2, width//2, 2] += 1
    low_contrast = anchor.copy()
    low_contrast[height//3:height//3+3, width//3:width//3+3] += 16
    moving_object = anchor.copy()
    moving_object[height//3:height//3+3, width//3:width//3+3] += 64
    return [('anchor', anchor), ('compression-noise', noise), ('chroma-byte', chroma),
            ('low-contrast-movement', low_contrast), ('return-to-anchor', anchor),
            ('fade-one', anchor + np.uint8(1)), ('fade-two', anchor + np.uint8(2)),
            ('moving-object', moving_object), ('scene-cut', 255 - anchor)]


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
    contexts, outputs, results = [], {}, {}
    try:
        # Keep the GPU instance alive across cases. Every context owns its model and cache.
        for case in CASES:
            conf = Path(spec['directory']) / f'{case}.conf'
            stats = Path(spec['directory']) / f'{case}.stats'
            factor = (1, 1) if case == 'span' else (4, 1)
            conf.write_text(profile(MODEL, case == 'rife-before', factor, .15, 0, 1))
            context = lib.aji_vk_create(os.fsencode(conf), os.fsencode(spec['models']),
                                       os.fsencode(spec['rife']), spec['device'].encode(),
                                       os.fsencode(stats), 1)
            if not context:
                raise RuntimeError(lib.aji_vk_error(None).decode())
            contexts.append((case, context, factor, stats))
        for case, context, factor, stats in contexts:
            results[case] = []
            # Reconfigure at a new size and then return: no picture from the previous
            # configuration may survive. Input buffers keep the same addresses per size.
            width, height = spec['width'], spec['height']
            sizes = ((width, height), (width + 16, height + 8), (width, height))
            for size_index, (width, height) in enumerate(sizes):
                plan = Plan()
                assert lib.aji_vk_configure(context, width, height, 24, ct.byref(plan)) == 0, (
                    lib.aji_vk_error(context).decode())
                assert (plan.numerator, plan.denominator) == factor
                stride = width * 3 + 17
                previous = np.zeros((height, stride), np.uint8)
                current = np.zeros_like(previous)
                observations = []
                for index, (label, image) in enumerate(pictures(width, height)):
                    if index:
                        previous[:] = current
                        previous[:, width*3:] = index * 19
                    current.fill(index * 23)
                    current[:, :width*3] = image.reshape(height, width*3)
                    before_previous, before_current = previous.copy(), current.copy()
                    steps = [1.] if not index else [step / factor[0] for step in range(1, factor[0]+1)]
                    for step_index, instant in enumerate(steps):
                        out_stride = plan.width * 3 + 11 + step_index
                        output = np.full((plan.height, out_stride), 123, np.uint8)
                        status = lib.aji_vk_process(context,
                            previous.ctypes.data_as(bytep) if index else None, stride,
                            current.ctypes.data_as(bytep), stride, instant,
                            output.ctypes.data_as(bytep), out_stride)
                        assert status == 0, lib.aji_vk_error(context).decode()
                        assert np.array_equal(previous, before_previous), 'previous input mutated'
                        assert np.array_equal(current, before_current), 'current input mutated'
                        assert np.all(output[:, plan.width*3:] == 123), 'output padding overwritten'
                        key = f'{case}/{size_index}/{label}/{step_index}'
                        outputs[key] = output[:, :plan.width*3].copy()
                    values = dict(line.split(': ', 1) for line in stats.read_text().splitlines() if ': ' in line)
                    observations.append({'label': label, 'stats': values})
                results[case].append(observations)
        np.savez(spec['outputs'], **outputs)
        Path(spec['results']).write_text(json.dumps(results, indent=2) + '\n')
    finally:
        for _, context, _, _ in reversed(contexts):
            lib.aji_vk_destroy(context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('reference', 'candidate', 'models', 'rife', 'report'):
        parser.add_argument('--' + key, type=Path)
    parser.add_argument('--device', default='')
    parser.add_argument('--width', type=int, default=128)
    parser.add_argument('--height', type=int, default=96)
    parser.add_argument('--worker')
    parser.add_argument('--library')
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    for key in ('reference', 'candidate', 'models', 'rife', 'report'):
        if getattr(args, key) is None:
            parser.error('--' + key + ' is required')
    if args.width < 64 or args.height < 64 or args.width % 2 or args.height % 2:
        parser.error('source dimensions must be even and at least 64')
    report = {'passed': False, 'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              'candidate_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
              'input_size': [args.width, args.height], 'checks': []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='ajn-sameness-') as temporary:
        outputs, statistics = {}, {}
        for variant in ('reference', 'default', 'exact-overrides-thresholds', 'similar'):
            directory = Path(temporary) / variant
            directory.mkdir()
            env = dict(os.environ)
            # Parent shell settings must never silently change the default-mode test.
            for key in ('AJI_VK_SAME', 'AJI_REUSE_THRESHOLD', 'AJI_REUSE_PEAK'):
                env.pop(key, None)
            env.update(AJI_VK_CACHE='1', AJI_VK_RIFE_GPU_CACHE='1')
            if variant == 'exact-overrides-thresholds':
                env.update(AJI_VK_SAME='exact', AJI_REUSE_THRESHOLD='8', AJI_REUSE_PEAK='255')
            elif variant == 'similar':
                env['AJI_VK_SAME'] = 'similar'
            spec = {'directory': str(directory), 'models': str(args.models.resolve()),
                    'rife': str(args.rife.resolve()), 'device': args.device,
                    'width': args.width, 'height': args.height,
                    'outputs': str(directory / 'outputs.npz'), 'results': str(directory / 'results.json')}
            spec_path = directory / 'spec.json'
            spec_path.write_text(json.dumps(spec))
            library = args.reference if variant == 'reference' else args.candidate
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                '--worker', str(spec_path), '--library', str(library.resolve())],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert completed.returncode == 0, f'{variant}:\n{completed.stdout}'
            with np.load(spec['outputs']) as saved:
                outputs[variant] = {key: saved[key].copy() for key in saved.files}
            statistics[variant] = json.loads(Path(spec['results']).read_text())
            print(f'Finished {variant}: {len(outputs[variant])} real output images', flush=True)
        for variant in ('default', 'exact-overrides-thresholds'):
            assert outputs[variant].keys() == outputs['reference'].keys()
            for key, reference in outputs['reference'].items():
                assert np.array_equal(reference, outputs[variant][key]), f'{variant}: changed pixels in {key}'
            for case in CASES:
                for observations in statistics[variant][case]:
                    stats = observations[-1]['stats']
                    assert 'identical bytes only' in stats['Source cache']
                    assert int(stats['Held RIFE outputs reused']) == 0
            report['checks'].append({'mode': variant, 'byte_identical': True,
                                     'images': len(outputs[variant])})
        for case in CASES:
            for size_index, observations in enumerate(statistics['similar'][case]):
                initial = int(observations[0]['stats']['Source preparations'])
                # These five later sources must stay on the original anchor, not update it.
                for observation in observations[1:6]:
                    assert int(observation['stats']['Source preparations']) == initial, (case, observation)
                    label = observation['label']
                    keys = [key for key in outputs['similar'] if key.startswith(f'{case}/{size_index}/{label}/')]
                    anchor = outputs['reference'][f'{case}/{size_index}/anchor/0']
                    assert all(np.array_equal(outputs['similar'][key], anchor) for key in keys), (case, label)
                # Fade +2 differs enough from the original anchor; accepting +1 must not
                # replace that anchor and allow a gradual fade to freeze indefinitely.
                assert int(observations[6]['stats']['Source preparations']) == initial + 1
                assert int(observations[7]['stats']['Source preparations']) == initial + 2
                assert int(observations[8]['stats']['Source preparations']) == initial + 3
                for label in ('fade-two', 'moving-object', 'scene-cut'):
                    step = 0 if case == 'span' else 3
                    key = f'{case}/{size_index}/{label}/{step}'
                    assert np.array_equal(outputs['similar'][key], outputs['reference'][key]), (case, label)
                held = int(observations[-1]['stats']['Held RIFE outputs reused'])
                assert held == (0 if case == 'span' else 15 * (size_index + 1)), (case, held)
        low_contrast_key = 'span/0/low-contrast-movement/0'
        changed = int(np.count_nonzero(outputs['similar'][low_contrast_key] != outputs['reference'][low_contrast_key]))
        assert changed > 0, 'low-contrast quality limitation must be observable in real model output'
        report['checks'].append({'mode': 'similar', 'anchor_preserved': True,
            'fade_and_peak_rejected': True, 'reconfiguration_clears_cache': True,
            'low_contrast_movement_discarded': True, 'changed_output_bytes': changed,
            'quality_equivalence': False})
        report['statistics'] = statistics
    report['passed'] = True
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS exact default, threshold precedence, anchor, stride, reconfiguration and opt-in limits', flush=True)


if __name__ == '__main__':
    main()
