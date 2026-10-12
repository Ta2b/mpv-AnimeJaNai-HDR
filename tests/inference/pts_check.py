#!/usr/bin/env python3
"""Check RIFE cadence, rational factors and EOF drain through the actual mpv filter."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('package', type=Path)
p.add_argument('--device', required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
root = a.package.resolve()
env = dict(os.environ, LD_LIBRARY_PATH=str(root / 'mpv') + ':' + str(root / 'animejanai/inference'))
results = []
with tempfile.TemporaryDirectory(prefix='ajn-pts-') as tmp:
    tmp = Path(tmp)
    source = tmp / 'source.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(root / 'animejanai/benchmarks/480x360.mp4'),
        '-frames:v', '12', '-an', '-c:v', 'ffv1', str(source)], check=True)
    for numerator, denominator in ((2, 1), (3, 2)):
        conf = tmp / 'profile.conf'
        conf.write_text('[global]\nbackend=Vulkan\n[slot_1]\nchain_1_min_resolution=0x0\n'
            'chain_1_max_resolution=1920x1080\nchain_1_rife=yes\nchain_1_rife_model=46\n'
            f'chain_1_rife_factor_numerator={numerator}\nchain_1_rife_factor_denominator={denominator}\n')
        output = tmp / 'output.mkv'
        vf = 'animejanai-vulkan:' + ':'.join(f'{key}={value}' for key, value in {
            'lib': root / 'animejanai/inference/libaji_vulkan.so', 'conf': conf,
            'model-dir': root / 'animejanai/onnx', 'rife-model-dir': root / 'animejanai/rife-vulkan',
            'device': a.device, 'slot': 1}.items())
        run = subprocess.run([str(root / 'mpv/mpv'), '--no-config', '--hwdec=no', '--vf=' + vf,
            '--o=' + str(output), '--ovc=ffv1', '--of=matroska', '--ofopts=allow_raw_vfw=1', str(source)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert run.returncode == 0, run.stdout
        report = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'frame=pts_time', '-show_entries', 'stream=avg_frame_rate', '-of', 'json', str(output)], text=True))
        pts = [float(frame['pts_time']) for frame in report['frames']]
        expected_frames = 1 + 11 * numerator // denominator
        expected_step = 1001 / 24000 * denominator / numerator
        assert len(pts) == expected_frames, (numerator, denominator, len(pts), pts)
        assert all(abs(y - x - expected_step) < .0011 for x, y in zip(pts, pts[1:])), pts
        results.append({'factor': [numerator, denominator], 'input_frames': 12,
            'output_frames': len(pts), 'pts': pts, 'stream': report['streams'][0]})
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps({'device': a.device, 'cadence_eof': results}, indent=2) + '\n')
print('PASS RIFE factors 2 and 3/2: monotonic PTS, correct counts, EOF drained')
