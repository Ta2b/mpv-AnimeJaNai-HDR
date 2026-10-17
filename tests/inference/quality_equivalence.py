#!/usr/bin/env python3
"""Quality equivalence rule (AH-370): bounded error against an FP32 reference.

A candidate keeps the Quality label when, on the same inputs, its error against
the FP32 reference is not larger than the delivered engine's own error:
    MSE(candidate, fp32)  <= mse_ratio * MSE(delivered, fp32)                  per channel
    P99.9(candidate, fp32) <= tail_ratio * P99.9(delivered, fp32) + max_slack   per channel
    MAX(candidate, fp32)  <= (1 + max_ratio) * MAX(delivered, fp32) + max_slack per channel
in 16-bit units, with no non-finite value and the same output count. Outputs are
the probe's `NNN.npy` (3, H, W) uint16 YUV444P16 files. Exit 0 = equivalent, 2 = not.

Rule v3 (AH-399, 18 October 2026): the slack is relative. Two TensorRT builds of
the same FP16 program pick different kernels and round differently; one FP16
step at values in [0.5, 1) is 32 units of 16 bits, so the former absolute slack
of 16 units sat below the delivered program's own build-to-build variance, and
the worst pixel (several thousand units on the fixed inputs) swings by a few per
cent between builds. The 99.9th percentile of |error| guards against new
localized artefacts that the mean would hide; the max keeps a proportional cap.

Rule v2 (AH-399): when the probe's `summary.json` is present next to the
delivered and candidate outputs, their timelines (PTS, durations) and output
flags must be identical, and when the FP32 receipt is present, every pair the
reference judged a scene cut must be repeated (flag REPEATED) by the candidate
and no other pair may be.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np


def load(directory, n):
    path = directory / f'{n:03d}.npy'
    if not path.exists():
        return None
    return np.load(path)


def error(a, b, hist=None):
    d = a.astype(np.int64) - b.astype(np.int64)
    if hist is not None:  # exact |error| histogram per channel, for the tail percentile over all outputs
        for c in range(3):
            hist[c] += np.bincount(np.abs(d[c]).ravel(), minlength=65536)
    return {'mse': [float((d[c] ** 2).mean()) for c in range(3)],
            'max': [int(np.abs(d[c]).max()) for c in range(3)],
            'mean_abs': [float(np.abs(d[c]).mean()) for c in range(3)]}


def percentile(hist, q):
    """Value of |error| below which q of all pixels fall, from an exact histogram."""
    total = int(hist.sum())
    if total == 0:
        return 0
    return int(np.searchsorted(np.cumsum(hist), q * total))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--fp32', type=Path, required=True)
    p.add_argument('--delivered', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--count', type=int, default=0, help='outputs to compare (default: all fp32 outputs)')
    p.add_argument('--mse-ratio', type=float, default=1.1)
    p.add_argument('--tail-ratio', type=float, default=1.1, help='allowed ratio on the 99.9th percentile of |error| (0 disables the tail check)')
    p.add_argument('--max-ratio', type=float, default=0.02, help='allowed relative growth of the max error (0 = absolute slack only, rule v2)')
    p.add_argument('--max-slack', type=int, default=32, help='allowed extra error in 16-bit units on top of the ratios (one FP16 step in [0.5, 1))')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    counts = {k: len(sorted(getattr(a, k).glob('[0-9][0-9][0-9].npy'))) for k in ('fp32', 'delivered', 'candidate')}
    count = a.count or counts['fp32']
    frames, failures = [], []
    if not a.count and len(set(counts.values())) != 1:
        failures.append(f'output count differs: {counts}')
    agg = {'delivered': {'mse': np.zeros(3), 'max': [0, 0, 0]}, 'candidate': {'mse': np.zeros(3), 'max': [0, 0, 0]}}
    hist = {k: np.zeros((3, 65536), dtype=np.int64) for k in agg}
    for n in range(count if not failures else 0):
        ref, dlv, cnd = load(a.fp32, n), load(a.delivered, n), load(a.candidate, n)
        if ref is None or dlv is None or cnd is None:
            failures.append(f'output {n} missing in one directory')
            break
        if ref.shape != dlv.shape or ref.shape != cnd.shape:
            failures.append(f'output {n} shape mismatch {ref.shape} {dlv.shape} {cnd.shape}')
            break
        ed, ec = error(dlv, ref, hist['delivered']), error(cnd, ref, hist['candidate'])
        frames.append({'output': n, 'delivered': ed, 'candidate': ec})
        for k, e in (('delivered', ed), ('candidate', ec)):
            agg[k]['mse'] += np.array(e['mse'])
            agg[k]['max'] = [max(x, y) for x, y in zip(agg[k]['max'], e['max'])]
    verdict = {}
    # Rule v2: timeline, flags and scene decisions from the probe summaries and the FP32 receipt.
    REPEATED = 8
    structure = {'timeline_ok': None, 'flags_ok': None, 'scene_ok': None}
    summaries = {}
    for k in ('delivered', 'candidate'):
        path = getattr(a, k) / 'summary.json'
        if path.exists():
            summaries[k] = json.loads(path.read_text())
    if len(summaries) == 2:
        structure['timeline_ok'] = summaries['delivered'].get('timeline') == summaries['candidate'].get('timeline')
        structure['flags_ok'] = summaries['delivered'].get('flags') == summaries['candidate'].get('flags')
        for key in ('timeline_ok', 'flags_ok'):
            if structure[key] is False:
                failures.append(f'{key.split("_")[0]} differs between delivered and candidate')
    receipt_path = a.fp32 / 'receipt.json'
    if receipt_path.exists() and 'candidate' in summaries:
        ref = json.loads(receipt_path.read_text())
        factor, scenes, flags = int(ref.get('factor', 0)), ref.get('scene', []), summaries['candidate'].get('flags', [])
        if factor > 1 and scenes and flags:
            ok = True
            for entry in scenes:
                pair = int(entry['pair'])
                for j in range(1, factor):
                    index = pair * factor + j
                    if index < len(flags):
                        repeated = bool(flags[index] & REPEATED)
                        if repeated != bool(entry['scene']):
                            ok = False
            structure['scene_ok'] = ok
            if not ok:
                failures.append('scene-cut decisions differ from the FP32 reference')
    if not frames and not failures:
        failures.append('no outputs to compare')
    for k in agg:
        agg[k]['mse'] = (agg[k]['mse'] / max(len(frames), 1)).tolist()
        agg[k]['p999'] = [percentile(hist[k][c], 0.999) for c in range(3)]
    if frames and not failures:
        for ch, name in enumerate(('Y', 'U', 'V')):
            mse_ok = agg['candidate']['mse'][ch] <= a.mse_ratio * agg['delivered']['mse'][ch] + 1e-9
            tail_ok = a.tail_ratio <= 0 or agg['candidate']['p999'][ch] <= a.tail_ratio * agg['delivered']['p999'][ch] + a.max_slack
            max_ok = agg['candidate']['max'][ch] <= (1 + a.max_ratio) * agg['delivered']['max'][ch] + a.max_slack
            verdict[name] = {'mse_ok': bool(mse_ok), 'tail_ok': bool(tail_ok), 'max_ok': bool(max_ok)}
            if not (mse_ok and tail_ok and max_ok):
                failures.append(f'{name}: candidate mse {agg["candidate"]["mse"][ch]:.4g} p99.9 {agg["candidate"]["p999"][ch]} max {agg["candidate"]["max"][ch]} '
                                f'vs delivered mse {agg["delivered"]["mse"][ch]:.4g} p99.9 {agg["delivered"]["p999"][ch]} max {agg["delivered"]["max"][ch]}')
    equivalent = bool(frames) and not failures

    def psnr(mse):  # None (JSON null) for an identical channel: Infinity is not valid JSON
        return [float(10 * np.log10(65535.0 ** 2 / m)) if m > 0 else None for m in mse]
    receipt = {
        'schema': 'animejanai.quality-equivalence.v3', 'ticket': 'AH-370/AH-399', 'structure': structure,
        'fp32': str(a.fp32), 'delivered': str(a.delivered), 'candidate': str(a.candidate),
        'outputs_compared': len(frames), 'output_counts': counts,
        'rule': {'mse_ratio': a.mse_ratio, 'tail_ratio': a.tail_ratio, 'tail_percentile': 99.9, 'max_ratio': a.max_ratio, 'max_slack_16bit': a.max_slack},
        'aggregate': {k: {'mse': v['mse'], 'p999': v['p999'], 'max': v['max'], 'psnr_db': psnr(v['mse'])} for k, v in agg.items()},
        'verdict': verdict, 'failures': failures, 'equivalent': equivalent, 'frames': frames,
        'scope': 'numerical equivalence against FP32 on the given inputs only; no temporal, visual or performance claim',
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2))
    print('EQUIVALENT' if equivalent else 'NOT EQUIVALENT', json.dumps({'aggregate': receipt['aggregate'], 'failures': failures}, indent=None))
    sys.exit(0 if equivalent else 2)


if __name__ == '__main__':
    main()
