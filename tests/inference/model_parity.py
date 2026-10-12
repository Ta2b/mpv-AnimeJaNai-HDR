#!/usr/bin/env python3
"""Compare converted SPAN GPU outputs with the original FP16 ONNX models.
Requires the built native smoke tool, ONNX Runtime and an explicit Vulkan GPU.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import numpy as np
import onnxruntime as ort

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('bundle', type=Path)
p.add_argument('original_models', type=Path)
p.add_argument('--device', required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
a.bundle = a.bundle.resolve()
env = dict(os.environ, LD_LIBRARY_PATH=str(a.bundle / 'inference') + ':' + os.environ.get('LD_LIBRARY_PATH', ''))
results = []
with tempfile.TemporaryDirectory(prefix='ajn-parity-') as tmp:
    tmp = Path(tmp)
    def run(model, size, device=a.device):
        conf = tmp / 'profile.conf'
        conf.write_text('[global]\nbackend=Vulkan\n[slot_1]\nchain_1_min_resolution=0x0\n'
            'chain_1_max_resolution=4096x4096\nchain_1_model_1_name=' + model + '\nchain_1_rife=no\n')
        return subprocess.run([str(a.bundle / 'inference/animejanai-vulkan-test'), str(conf),
            str(a.bundle / 'onnx'), str(a.bundle / 'rife-vulkan'), device, '1', str(size), str(tmp / 'out.rgb')],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for model in sorted(a.original_models.glob('*SPANF3*.onnx')):
        session = ort.InferenceSession(str(model), providers=['CPUExecutionProvider'])
        for size in (64, 96):
            result = run(model.stem, size)
            assert result.returncode == 0, result.stdout
            y, x, channel = np.indices((size, size, 3))
            rgb = ((x * 3 + y * 2 + channel * 30 + 12) % 256).astype(np.uint8)
            input_image = (rgb.astype(np.float32) / 255).transpose(2, 0, 1)[None].astype(np.float16)
            expected = session.run(None, {session.get_inputs()[0].name: input_image})[0][0].transpose(1, 2, 0)
            expected = np.clip(expected.astype(np.float32) * 255, 0, 255)
            actual = np.frombuffer((tmp / 'out.rgb').read_bytes(), dtype=np.uint8).reshape(expected.shape)
            diff = np.abs(expected - actual)
            item = {'model': model.name, 'input': [size, size], 'mean_rgb8_error': float(diff.mean()), 'max_rgb8_error': float(diff.max())}
            results.append(item)
            assert item['mean_rgb8_error'] < 1.5 and item['max_rgb8_error'] < 8, item
    assert results, 'No original SPAN models'
    assert run('missing-model', 64).returncode != 0, 'Missing model silently substituted'
    assert run(results[0]['model'][:-5], 65).returncode != 0, 'Odd source dimensions accepted'
    assert run(results[0]['model'][:-5], 64, 'nonexistent-test-gpu').returncode != 0, 'Requested GPU silently substituted'
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps({'device': a.device, 'comparisons': results,
    'missing_model_refused': True, 'odd_dimensions_refused': True, 'wrong_gpu_refused': True}, indent=2) + '\n')
print(json.dumps(results, indent=2))
