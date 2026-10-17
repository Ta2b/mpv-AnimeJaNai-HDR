#!/usr/bin/env python3
"""Synthetic reference clip for the equivalence rule (AH-370): raw RGB24 frames.

Gradients (banding), thin lines, flat anime-like areas, a hard edge and a
moving disc give the FP32 comparison borders, smooth ramps and motion. The
pattern is deterministic; its SHA-256 identifies the input in receipts.
"""
import argparse
import hashlib
from pathlib import Path

import numpy as np


def frame(w, h, index):
    y, x = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), dtype=np.float32)
    # Slow horizontal luma ramp (banding test) on the top third.
    img[: h // 3, :, :] = (x[: h // 3] / (w - 1))[..., None] * 255
    # Colour ramps on the middle third: hue sweep with mid saturation.
    t = x[h // 3: 2 * h // 3] / (w - 1)
    img[h // 3: 2 * h // 3, :, 0] = 128 + 100 * np.sin(2 * np.pi * t)
    img[h // 3: 2 * h // 3, :, 1] = 128 + 100 * np.sin(2 * np.pi * t + 2.1)
    img[h // 3: 2 * h // 3, :, 2] = 128 + 100 * np.sin(2 * np.pi * t + 4.2)
    # Flat anime-like areas with thin dark lines on the bottom third.
    bottom = slice(2 * h // 3, h)
    img[bottom, :, :] = np.array([230, 205, 180], dtype=np.float32)
    img[bottom, :, :][(y[bottom] % 48 == 0) | (x[bottom] % 64 == 0)] = np.array([30, 25, 40], dtype=np.float32)
    # Hard vertical edge that moves 6 px per frame and a moving disc (occlusion).
    edge = w // 2 + 6 * index
    img[bottom, edge: edge + 40, :] = np.array([40, 60, 160], dtype=np.float32)
    cx, cy, r = w // 4 + 10 * index, h // 2, min(w, h) // 9
    disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    img[disc] = np.array([250, 90, 60], dtype=np.float32)
    # Text-like high-frequency block.
    block = (slice(h // 6, h // 6 + 40), slice(w - 360, w - 40))
    noise = ((x[block] * 7 + y[block] * 13 + index) % 11 < 4)
    img[block][noise] = 0
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--width', type=int, default=1280)
    p.add_argument('--height', type=int, default=720)
    p.add_argument('--frames', type=int, default=4)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    data = b''.join(frame(a.width, a.height, i).tobytes() for i in range(a.frames))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(data)
    print(a.output, len(data), hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
