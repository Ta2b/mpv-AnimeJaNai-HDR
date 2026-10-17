#!/usr/bin/env python3
"""Quality equivalence rule (AH-370): bounded error against an FP32 reference.

A candidate keeps the Quality label when, on the same inputs, its error against
the FP32 reference is not larger than the delivered engine's own error:
    MSE(candidate, fp32)  <= mse_ratio  * MSE(delivered, fp32)   per channel
    MAX(candidate, fp32)  <= MAX(delivered, fp32) + max_slack    per channel (16-bit units)
with no non-finite value and the same output count. Outputs are the probe's
`NNN.npy` (3, H, W) uint16 YUV444P16 files. Exit 0 = equivalent, 2 = not.
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


def error(a, b):
    d = a.astype(np.int64) - b.astype(np.int64)
    return {'mse': [float((d[c] ** 2).mean()) for c in range(3)],
            'max': [int(np.abs(d[c]).max()) for c in range(3)],
            'mean_abs': [float(np.abs(d[c]).mean()) for c in range(3)]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--fp32', type=Path, required=True)
    p.add_argument('--delivered', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--count', type=int, default=0, help='outputs to compare (default: all fp32 outputs)')
    p.add_argument('--mse-ratio', type=float, default=1.1)
    p.add_argument('--max-slack', type=int, default=16, help='allowed extra max error in 16-bit units (1/16 of a 12-bit step)')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    counts = {k: len(sorted(getattr(a, k).glob('[0-9][0-9][0-9].npy'))) for k in ('fp32', 'delivered', 'candidate')}
    count = a.count or counts['fp32']
    frames, failures = [], []
    if not a.count and len(set(counts.values())) != 1:
        failures.append(f'output count differs: {counts}')
    agg = {'delivered': {'mse': np.zeros(3), 'max': [0, 0, 0]}, 'candidate': {'mse': np.zeros(3), 'max': [0, 0, 0]}}
    for n in range(count if not failures else 0):
        ref, dlv, cnd = load(a.fp32, n), load(a.delivered, n), load(a.candidate, n)
        if ref is None or dlv is None or cnd is None:
            failures.append(f'output {n} missing in one directory')
            break
        if ref.shape != dlv.shape or ref.shape != cnd.shape:
            failures.append(f'output {n} shape mismatch {ref.shape} {dlv.shape} {cnd.shape}')
            break
        ed, ec = error(dlv, ref), error(cnd, ref)
        frames.append({'output': n, 'delivered': ed, 'candidate': ec})
        for k, e in (('delivered', ed), ('candidate', ec)):
            agg[k]['mse'] += np.array(e['mse'])
            agg[k]['max'] = [max(x, y) for x, y in zip(agg[k]['max'], e['max'])]
    verdict = {}
    if not frames and not failures:
        failures.append('no outputs to compare')
    for k in agg:
        agg[k]['mse'] = (agg[k]['mse'] / max(len(frames), 1)).tolist()
    if frames and not failures:
        for ch, name in enumerate(('Y', 'U', 'V')):
            mse_ok = agg['candidate']['mse'][ch] <= a.mse_ratio * agg['delivered']['mse'][ch] + 1e-9
            max_ok = agg['candidate']['max'][ch] <= agg['delivered']['max'][ch] + a.max_slack
            verdict[name] = {'mse_ok': bool(mse_ok), 'max_ok': bool(max_ok)}
            if not (mse_ok and max_ok):
                failures.append(f'{name}: candidate mse {agg["candidate"]["mse"][ch]:.4g} max {agg["candidate"]["max"][ch]} '
                                f'vs delivered mse {agg["delivered"]["mse"][ch]:.4g} max {agg["delivered"]["max"][ch]}')
    equivalent = bool(frames) and not failures

    def psnr(mse):  # None (JSON null) for an identical channel: Infinity is not valid JSON
        return [float(10 * np.log10(65535.0 ** 2 / m)) if m > 0 else None for m in mse]
    receipt = {
        'schema': 'animejanai.quality-equivalence.v1', 'ticket': 'AH-370',
        'fp32': str(a.fp32), 'delivered': str(a.delivered), 'candidate': str(a.candidate),
        'outputs_compared': len(frames), 'output_counts': counts, 'rule': {'mse_ratio': a.mse_ratio, 'max_slack_16bit': a.max_slack},
        'aggregate': {k: {'mse': v['mse'], 'max': v['max'], 'psnr_db': psnr(v['mse'])} for k, v in agg.items()},
        'verdict': verdict, 'failures': failures, 'equivalent': equivalent, 'frames': frames,
        'scope': 'numerical equivalence against FP32 on the given inputs only; no temporal, visual or performance claim',
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2))
    print('EQUIVALENT' if equivalent else 'NOT EQUIVALENT', json.dumps({'aggregate': receipt['aggregate'], 'failures': failures}, indent=None))
    sys.exit(0 if equivalent else 2)


if __name__ == '__main__':
    main()
