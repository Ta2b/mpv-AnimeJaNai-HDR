#!/usr/bin/env python3
"""FP32 reference of the ordered Quality chain (AH-370).

Replays, in float32 with ONNX Runtime, the exact non-network steps of the
native CUDA pipeline (canonical YUV444P16 input, RIFE pre/post with the pair's
matrix and padding, the intermediate YUV16 quantization, SPAN pre/post) and runs
the networks from FP16 models promoted to FP32 copies (tests/inference/
ort_fp32_fixture.py logic). Outputs use the probe layout: one `NNN.npy`
(3, H, W) uint16 YUV444P16 per output plus `receipt.json`.

Installed models are never modified; promoted copies live in --work.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MATRICES = {'601': (0.299, 0.114), '709': (0.2126, 0.0722), '2020': (0.2627, 0.0593)}


def csp(matrix, rng):
    kr, kb = MATRICES[matrix]
    if rng == 'full':
        return dict(kr=np.float32(kr), kb=np.float32(kb), yoff=np.float32(0), yscale=np.float32(65535),
                    coff=np.float32(32768), cscale=np.float32(65535))
    return dict(kr=np.float32(kr), kb=np.float32(kb), yoff=np.float32(16 * 256), yscale=np.float32(219 * 256),
                coff=np.float32(128 * 256), cscale=np.float32(224 * 256))


def rgb_to_yuv16(rgb):
    """Probe input conversion: canonical RGB24 -> 16-bit full-range BT.709 (vfi_candidate_probe)."""
    r, g, b = [rgb[..., i].astype(np.float64) for i in range(3)]
    y = .2126 * r + .7152 * g + .0722 * b
    cb = (b - y) / (2 * (1 - .0722))
    cr = (r - y) / (2 * (1 - .2126))
    return np.stack([np.clip(np.rint(x * 65535 + offset), 0, 65535).astype(np.uint16)
                     for x, offset in ((y, 0), (cb, 32768), (cr, 32768))])


def pre444(planes, c):
    """k_pre444 / k_pre444_pad: YUV16 planes (3,H,W) -> RGB float32 (3,H,W), no FP16 rounding."""
    y = (planes[0].astype(np.float32) - c['yoff']) / c['yscale']
    u = (planes[1].astype(np.float32) - c['coff']) / c['cscale']
    v = (planes[2].astype(np.float32) - c['coff']) / c['cscale']
    kr, kb = c['kr'], c['kb']
    kg = np.float32(1) - kr - kb
    r = y + np.float32(2) * (np.float32(1) - kr) * v
    b = y + np.float32(2) * (np.float32(1) - kb) * u
    g = y - (np.float32(2) * kb * (np.float32(1) - kb) * u + np.float32(2) * kr * (np.float32(1) - kr) * v) / kg
    return np.stack([r, g, b]).astype(np.float32)


def post444(rgb, c):
    """k_post444 with 16-bit quantization: RGB float32 (3,H,W) -> YUV16 planes."""
    r, g, b = rgb[0], rgb[1], rgb[2]
    kr, kb = c['kr'], c['kb']
    y = kr * r + (np.float32(1) - kr - kb) * g + kb * b
    u = (b - y) / (np.float32(2) * (np.float32(1) - kb))
    v = (r - y) / (np.float32(2) * (np.float32(1) - kr))
    def quant(x):
        return np.clip(np.rint(x), 0, 65535).astype(np.uint16)
    return np.stack([quant(y * c['yscale'] + c['yoff']), quant(u * c['cscale'] + c['coff']), quant(v * c['cscale'] + c['coff'])])


def studio_black(c):
    y = (np.float32(16 * 256) - c['yoff']) / c['yscale']
    return np.array([y, y, y], dtype=np.float32)  # U=V=0 -> R=G=B=Y


def rife_input(a_rgb, b_rgb, t, pw, ph, pad_l, pad_t, c):
    """11-channel RIFE tensor on the padded geometry: a, b, timestep, meshx, meshy, mulw, mulh."""
    _, h, w = a_rgb.shape
    x = np.zeros((1, 11, ph, pw), dtype=np.float32)
    black = studio_black(c)
    for ch in range(3):
        x[0, ch, :, :] = black[ch]
        x[0, 3 + ch, :, :] = black[ch]
    x[0, 0:3, pad_t:pad_t + h, pad_l:pad_l + w] = a_rgb
    x[0, 3:6, pad_t:pad_t + h, pad_l:pad_l + w] = b_rgb
    x[0, 6] = np.float32(t)
    xs = np.arange(pw, dtype=np.float32)
    ys = np.arange(ph, dtype=np.float32)
    x[0, 7] = (np.float32(2) * xs / np.float32(pw - 1) - np.float32(1))[None, :]
    x[0, 8] = (np.float32(2) * ys / np.float32(ph - 1) - np.float32(1))[:, None]
    x[0, 9] = np.float32(2) / np.float32(pw - 1)
    x[0, 10] = np.float32(2) / np.float32(ph - 1)
    return x


def promote(source, work):
    """FP16 -> FP32 copy of an ONNX model, as tests/inference/ort_fp32_fixture.py does."""
    import onnx
    from onnx import TensorProto, AttributeProto, numpy_helper
    # Keyed by the source digest so a re-exported model of the same name is promoted again;
    # written atomically so an interrupted run never leaves a truncated copy behind.
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    destination = work / f'{source.stem}.{digest}.fp32.onnx'
    if destination.exists():
        return destination
    model = onnx.load(str(source))

    def promote_tensor(t):
        if t.data_type == TensorProto.FLOAT16:
            t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))

    def promote_graph(g):
        for v in list(g.input) + list(g.output) + list(g.value_info):
            if v.type.tensor_type.elem_type == TensorProto.FLOAT16:
                v.type.tensor_type.elem_type = TensorProto.FLOAT
        for t in g.initializer:
            promote_tensor(t)
        for node in g.node:
            for a in node.attribute:
                if node.op_type == 'Cast' and a.name == 'to' and a.i == TensorProto.FLOAT16:
                    a.i = TensorProto.FLOAT
                if a.type == AttributeProto.TENSOR:
                    promote_tensor(a.t)
                elif a.type == AttributeProto.TENSORS:
                    for t in a.tensors:
                        promote_tensor(t)
                elif a.type == AttributeProto.GRAPH:
                    promote_graph(a.g)
                elif a.type == AttributeProto.GRAPHS:
                    for graph in a.graphs:
                        promote_graph(graph)
    promote_graph(model.graph)
    onnx.checker.check_model(model)
    partial = destination.with_suffix('.tmp')
    onnx.save(model, str(partial))
    partial.replace(destination)
    return destination


class Session:
    """ONNX Runtime session that falls back to the CPU provider when the CUDA
    provider cannot execute (missing cuDNN, unsupported operator)."""

    def __init__(self, path, provider):
        import onnxruntime as ort
        self.ort, self.path, self.provider = ort, str(path), provider
        self.sess = self.open('cpu' if provider == 'cpu' else 'cuda')

    def open(self, provider):
        opts = self.ort.SessionOptions()
        opts.log_severity_level = 3
        # TF32 is on by default in the CUDA provider: Conv/MatMul inputs would be rounded to a
        # 10-bit mantissa on Ampere/Ada tensor cores, so the reference would not be float32.
        providers = ['CPUExecutionProvider'] if provider == 'cpu' else [('CUDAExecutionProvider', {'use_tf32': 0}), 'CPUExecutionProvider']
        sess = self.ort.InferenceSession(self.path, opts, providers=providers)
        active = sess.get_providers()[0]
        self.used = 'cuda' if active == 'CUDAExecutionProvider' else 'cpu'
        if provider == 'cuda' and self.used != 'cuda':
            print(f'CUDA provider unavailable for {self.path}; using CPU', file=sys.stderr)
        self.tf32 = False
        return sess

    def run(self, x):
        name = self.sess.get_inputs()[0].name
        try:
            return self.sess.run(None, {name: x})[0]
        except Exception as error:  # noqa: BLE001 - provider failure, retry on CPU once
            if self.used == 'cpu':
                raise
            print(f'CUDA provider failed ({str(error).splitlines()[0][:120]}); using CPU', file=sys.stderr)
            self.sess = self.open('cpu')
            return self.sess.run(None, {name: x})[0]


def session(path, provider):
    return Session(path, provider)


def run(sess, x):
    y = sess.run(x)
    if not np.isfinite(y).all():  # quant() would silently clamp NaN/inf to 0/65535
        raise RuntimeError(f'{sess.path}: {int((~np.isfinite(y)).sum())} non-finite output values; no reference written')
    return y


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--rife', type=Path, required=True, help='FP16 RIFE ONNX (11-channel input)')
    p.add_argument('--span', type=Path, required=True, help='FP16 SPAN ONNX (x2)')
    p.add_argument('--input', type=Path, required=True, help='raw RGB24 frames')
    p.add_argument('--width', type=int, required=True)
    p.add_argument('--height', type=int, required=True)
    p.add_argument('--frames', default='2,3,4,5', help='source frame indices, consecutive pairs')
    p.add_argument('--factor', type=int, default=4)
    p.add_argument('--pad', type=int, default=64, choices=(16, 32, 64), help='RIFE padding multiple of the compared engine')
    p.add_argument('--matrix', default='709', choices=sorted(MATRICES))
    p.add_argument('--range', dest='rng', default='full', choices=('full', 'limited'))
    p.add_argument('--intermediate', default='yuv16', choices=('yuv16', 'rgb'), help='RIFE->SPAN handoff of the compared engine')
    p.add_argument('--scene-threshold', type=float, default=0.15)
    p.add_argument('--provider', default='cuda', choices=('cuda', 'cpu'))
    p.add_argument('--work', type=Path, required=True, help='directory for promoted FP32 model copies')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):
        sys.exit(f'refusing to overwrite {a.output}')
    a.output.mkdir(parents=True, exist_ok=True)
    a.work.mkdir(parents=True, exist_ok=True)
    w, h = a.width, a.height
    frame_bytes = w * h * 3
    raw = np.fromfile(a.input, dtype=np.uint8)
    indices = [int(i) for i in a.frames.split(',')]
    sources = []
    for i in indices:  # same scaling as the probe: float32 RGB in [0, 1]
        sources.append(rgb_to_yuv16(raw[i * frame_bytes:(i + 1) * frame_bytes].reshape(h, w, 3).astype(np.float32) / 255))
    c = csp(a.matrix, a.rng)
    pw = (w + a.pad - 1) // a.pad * a.pad
    ph = (h + a.pad - 1) // a.pad * a.pad
    pad_l = ((pw - w) // 2) & ~1
    pad_t = ((ph - h) // 2) & ~1
    started = time.perf_counter()
    rife = session(promote(a.rife, a.work), a.provider)
    span = session(promote(a.span, a.work), a.provider)
    outputs, hashes, notes = [], [], []

    def upscale_from_yuv(planes):
        rgb = pre444(planes, c)
        y = run(span, rgb[None])[0]
        return post444(y.astype(np.float32), c)

    def upscale_from_rgb(rgb):
        y = run(span, rgb[None].astype(np.float32))[0]
        return post444(y.astype(np.float32), c)

    for pair in range(len(sources) - 1):
        sa, sb = sources[pair], sources[pair + 1]
        outputs.append(upscale_from_yuv(sa))
        a_rgb, b_rgb = pre444(sa, c), pre444(sb, c)
        score = float(np.abs(sa[0].astype(np.float32) - sb[0].astype(np.float32)).sum() / 65535.0 / (pw * ph))
        scene = score > a.scene_threshold
        notes.append({'pair': pair, 'scene_score': score, 'scene': scene})
        for j in range(1, a.factor):
            if scene:
                outputs.append(outputs[-1].copy() if j == 1 else outputs[-1].copy())
                continue
            t = j / a.factor
            y = run(rife, rife_input(a_rgb, b_rgb, t, pw, ph, pad_l, pad_t, c))[0]
            mid = y[:, pad_t:pad_t + h, pad_l:pad_l + w].astype(np.float32)
            if a.intermediate == 'yuv16':
                outputs.append(upscale_from_yuv(post444(mid, c)))
            else:
                outputs.append(upscale_from_rgb(mid))
    outputs.append(upscale_from_yuv(sources[-1]))
    for n, planes in enumerate(outputs):
        np.save(a.output / f'{n:03d}.npy', planes)
        hashes.append(hashlib.sha256(planes.tobytes()).hexdigest())
    receipt = {
        'schema': 'animejanai.fp32-reference.v1', 'ticket': 'AH-370',
        'rife': str(a.rife), 'rife_sha256': hashlib.sha256(a.rife.read_bytes()).hexdigest(),
        'span': str(a.span), 'span_sha256': hashlib.sha256(a.span.read_bytes()).hexdigest(),
        'input': str(a.input), 'input_sha256': hashlib.sha256(raw.tobytes()).hexdigest(),
        'frames': indices, 'width': w, 'height': h, 'factor': a.factor, 'pad': a.pad,
        'padded': [pw, ph], 'pad_offset': [pad_l, pad_t], 'matrix': a.matrix, 'range': a.rng,
        'intermediate': a.intermediate, 'provider': a.provider, 'provider_used': {'rife': rife.used, 'span': span.used}, 'tf32': False, 'promoted': {'rife': str(rife.path), 'span': str(span.path)}, 'scene': notes,
        'outputs': len(outputs), 'hashes': hashes, 'seconds': time.perf_counter() - started,
        'scope': 'FP32 ideal of the same algorithm (networks FP32, conversions float32, same quantizations); not a performance measure',
    }
    (a.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({k: receipt[k] for k in ('outputs', 'padded', 'seconds', 'scene')}, indent=None))


if __name__ == '__main__':
    main()
