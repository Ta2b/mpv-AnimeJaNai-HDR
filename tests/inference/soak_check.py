#!/usr/bin/env python3
"""Process a longer clip segment with Vulkan and record device VRAM usage.
Runs without a display to isolate inference stability; does not certify realtime rendering.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('package', type=Path)
p.add_argument('--device', required=True)
p.add_argument('--pci', required=True)
p.add_argument('--slot', type=int, default=6)
p.add_argument('--seconds', type=int, default=60)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
root = a.package.resolve()
env = dict(os.environ, LD_LIBRARY_PATH=str(root / 'mpv') + ':' + str(root / 'animejanai/inference'))
a.report.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ajn-soak-') as tmp:
    stats = Path(tmp) / 'stats.txt'
    vf = 'animejanai-vulkan:' + ':'.join(f'{key}={value}' for key, value in {
        'lib': root / 'animejanai/inference/libaji_vulkan.so',
        'conf': root / 'portable_config/profiles/linux-amd/animejanai.conf',
        'model-dir': root / 'animejanai/onnx', 'rife-model-dir': root / 'animejanai/rife-vulkan',
        'device': a.device, 'slot': a.slot, 'stats': stats}.items())
    log = a.report.with_suffix('.log').open('w')
    started = time.monotonic()
    proc = subprocess.Popen([str(root / 'mpv/mpv'), '--no-config', '--vo=null', '--ao=null',
        '--hwdec=no', '--untimed', '--end=' + str(a.seconds), '--vf=' + vf,
        str(root / 'animejanai/benchmarks/1280x720.mp4')], env=env, stdout=log, stderr=log)
    samples = []
    vram = Path('/sys/bus/pci/devices') / a.pci / 'mem_info_vram_used'
    try:
        while proc.poll() is None:
            if time.monotonic() - started > max(120, a.seconds * 10):
                raise TimeoutError('Inference soak stalled')
            try: memory = int(vram.read_text())
            except OSError: memory = None
            samples.append({'wall_seconds': time.monotonic() - started, 'device_vram_bytes': memory})
            time.sleep(1)
        assert proc.returncode == 0, 'Inference failed; inspect ' + str(a.report.with_suffix('.log'))
        text = stats.read_text()
        frames = int(next(line.split(': ')[1] for line in text.splitlines() if line.startswith('Frames: ')))
        assert frames >= a.seconds * 23, 'Clip did not complete the requested segment'
        report = {'device': a.device, 'pci': a.pci, 'slot': a.slot, 'clip_seconds': a.seconds,
            'wall_seconds': time.monotonic() - started, 'frames': frames, 'stats': text,
            'vram_samples': samples, 'rendering_realtime_verified': False}
        a.report.write_text(json.dumps(report, indent=2) + '\n')
        print('PASS Vulkan soak:', frames, 'output frames;', report['wall_seconds'], 'wall seconds')
    finally:
        if proc.poll() is None: proc.terminate(); proc.wait(timeout=10)
        log.close()
