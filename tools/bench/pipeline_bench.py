#!/usr/bin/env python3
"""Reliable offline bench for the ordered CUDA pipeline (AH-396).

Runs tests/inference/pipeline_fusion_probe.py as a subprocess, several times,
alternating variants (sets of environment variables) round-robin so that GPU
clocks, thermal state and desktop load affect every variant the same way.
GPU time per pair comes from the pipeline's own CUDA events
(`aji_pipeline_timing:` lines, AJI_PIPELINE_TIMING=1); wall time from the probe.
Reports min and median per variant and refuses to run when other processes keep
the GPU busy. Output directories are temporary: the probe never replays.
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent.parent / 'tests' / 'inference' / 'pipeline_fusion_probe.py'
TIMING = re.compile(r'^aji_pipeline_timing: ticket=(\d+) outputs=(\d+) total_gpu_ms=([0-9.]+)(.*)$')
STAGE = re.compile(r' ([0-9a-f-]+|legacy-model-\d+)=([0-9.]+)')


def gpu_utilisation():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        return max(int(x) for x in out) if out else None
    except Exception:  # noqa: BLE001 - no nvidia-smi: cannot check
        return None


def wait_idle(threshold, patience):
    deadline = time.monotonic() + patience
    while True:
        u = gpu_utilisation()
        if u is None or u <= threshold:
            return u
        if time.monotonic() > deadline:
            return u
        time.sleep(1.0)


def run_once(spec, env, python, keep):
    out = Path(tempfile.mkdtemp(prefix='bench-'))
    s = dict(spec)
    s['output'] = str(out / 'run')
    spec_path = out / 'spec.json'
    spec_path.write_text(json.dumps(s))
    full_env = dict(os.environ)
    full_env.update(env)
    full_env['AJI_PIPELINE_TIMING'] = '1'
    try:
        proc = subprocess.run([python, str(PROBE), str(spec_path)], capture_output=True, text=True,
                              env=full_env, cwd=str(PROBE.parent), timeout=600)
        pairs = []
        for line in proc.stderr.splitlines():
            m = TIMING.match(line)
            if m:
                pairs.append({'ticket': int(m.group(1)), 'outputs': int(m.group(2)), 'gpu_ms': float(m.group(3)),
                              'stages': {k: float(v) for k, v in STAGE.findall(m.group(4))}})
        wall = []
        for line in proc.stdout.splitlines():
            if line.startswith('{"pair"'):
                wall.append(json.loads(line)['complete_wall_ms'])
        return {'returncode': proc.returncode, 'pairs': pairs, 'wall_ms': wall,
                'stderr_tail': proc.stderr[-800:] if proc.returncode else ''}
    finally:
        if not keep:
            shutil.rmtree(out, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--spec', type=Path, required=True, help='probe spec JSON (its output path is replaced)')
    p.add_argument('--variant', action='append', default=[], metavar='NAME[=VAR=VALUE,...]',
                   help='named environment set; repeatable; e.g. shared=AJI_PIPELINE_SHARED_STREAM=1')
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--skip-pairs', type=int, default=1, help='pairs ignored at the start of each run (warm-up, graph capture)')
    p.add_argument('--idle-threshold', type=int, default=5, help='max GPU utilisation (%%) from other processes before a run')
    p.add_argument('--idle-patience', type=float, default=30.0, help='seconds to wait for an idle GPU before giving up')
    p.add_argument('--python', default=sys.executable)
    p.add_argument('--keep', action='store_true', help='keep the temporary output directories')
    p.add_argument('--output', type=Path, required=True, help='receipt JSON')
    a = p.parse_args()
    spec = json.loads(a.spec.read_text())
    variants = []
    for v in a.variant or ['default']:
        name, _, rest = v.partition('=')
        env = {}
        if rest:
            for item in rest.split(','):
                k, _, val = item.partition('=')
                env[k] = val
        variants.append((name, env))
    results = {name: [] for name, _ in variants}
    busy = []
    for r in range(a.runs):
        for name, env in variants:
            u = wait_idle(a.idle_threshold, a.idle_patience)
            if u is not None and u > a.idle_threshold:
                busy.append({'run': r, 'variant': name, 'utilisation': u})
            res = run_once(spec, env, a.python, a.keep)
            res['utilisation_before'] = u
            results[name].append(res)
            print(f'run {r} {name}: rc={res["returncode"]} gpu_ms={[round(x["gpu_ms"], 2) for x in res["pairs"]]} wall={[round(x, 1) for x in res["wall_ms"]]}', flush=True)

    def summary(runs):
        gpu = [pr['gpu_ms'] for res in runs if res['returncode'] == 0 for pr in res['pairs'][a.skip_pairs:] if pr['outputs'] > 1]
        wall = [w for res in runs if res['returncode'] == 0 for w in res['wall_ms'][a.skip_pairs:-1]]
        stages = {}
        for res in runs:
            if res['returncode']:
                continue
            for pr in res['pairs'][a.skip_pairs:]:
                if pr['outputs'] <= 1:
                    continue
                for k, v in pr['stages'].items():
                    stages.setdefault(k, []).append(v)
        return {'runs': len(runs), 'failed': sum(1 for r in runs if r['returncode']),
                'gpu_ms': {'min': min(gpu) if gpu else None, 'median': statistics.median(gpu) if gpu else None, 'n': len(gpu)},
                'wall_ms': {'min': min(wall) if wall else None, 'median': statistics.median(wall) if wall else None, 'n': len(wall)},
                'stages_gpu_ms_min': {k: min(v) for k, v in stages.items()}}
    receipt = {'schema': 'animejanai.pipeline-bench.v1', 'ticket': 'AH-396', 'spec': str(a.spec), 'runs': a.runs,
               'skip_pairs': a.skip_pairs, 'idle_threshold': a.idle_threshold, 'busy_runs': busy,
               'variants': {name: {'env': env, 'summary': summary(results[name]), 'runs': results[name]} for name, env in variants},
               'scope': 'warm pairs of a short offline chain on a shared desktop GPU; GPU ms from pipeline events; not display FPS'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2))
    for name, _ in variants:
        s = receipt['variants'][name]['summary']
        print(f'{name}: gpu min {s["gpu_ms"]["min"]} median {s["gpu_ms"]["median"]} (n={s["gpu_ms"]["n"]}) | wall min {s["wall_ms"]["min"]} median {s["wall_ms"]["median"]} | failed {s["failed"]}')
    if busy:
        print(f'WARNING: {len(busy)} runs started with GPU utilisation above {a.idle_threshold}%', file=sys.stderr)


if __name__ == '__main__':
    main()
