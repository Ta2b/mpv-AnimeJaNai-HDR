#!/usr/bin/env python3
"""Renders test charts through the real HDR shaders (mpv gpu-next / libplacebo, Vulkan) and
checks the output luminance. Needs mpv, a Vulkan driver (lavapipe works), xvfb-run, numpy, Pillow.

usage: tests/hdr/shader_check.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SHADERS = os.path.join(HERE, '..', '..', 'BuildMpvUpscale2xAnimeJaNai', 'mpv-upscale-2x_animejanai',
                       'portable_config', 'user-shaders')
GRADE = os.path.join(SHADERS, 'anime-hdr-grade.hook')
CALIBRATION = os.path.join(SHADERS, 'anime-hdr-calibration.hook')
W, H = 960, 544

# Shader options the controller sends for the mpv backend at highlights=0.85 on a 1000-nit display
# (hdr-grade.lua plan), vibrance off to read luminance only.
MPV_BACKEND = {'spec_gain': 4.337, 'area_gain': 1.425, 'vibrance': 0, 'abl': 0}

failures = []


def check(name, cond, value=None):
    print(('ok    ' if cond else 'FAIL  ') + name + ('' if value is None else '  (%s)' % value))
    if not cond:
        failures.append(name)


def pq_to_nits(e):
    m1 = 2610 / 16384; m2 = 2523 / 4096 * 128
    c1 = 3424 / 4096; c2 = 2413 / 4096 * 32; c3 = 2392 / 4096 * 32
    p = np.power(np.clip(e, 0, 1), 1 / m2)
    return 10000 * np.power(np.maximum(p - c1, 0) / (c2 - c3 * p), 1 / m1)


def chart(path):
    img = np.zeros((H, W, 3), np.uint8)
    img[0:64, :, :] = np.linspace(0, 255, W).astype(np.uint8)[None, :, None]
    img[64:320, 0:320] = 255                                  # large white area
    for y in range(84, 320, 40):                              # small white dots on black
        for x in range(340, 640, 40):
            img[y:y + 6, x:x + 6] = 255
    img[64:320, 640:960] = 60                                 # dots on a grey field
    for y in range(84, 320, 40):
        for x in range(660, 960, 40):
            img[y:y + 6, x:x + 6] = 255
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (230, 180, 150), (200, 90, 90),
              (90, 160, 200), (255, 200, 0), (128, 128, 128)]
    for i, c in enumerate(colors):
        img[320:H, i * 120:(i + 1) * 120] = c
    Image.fromarray(img).save(path)


def flat(path, value, dot=False):
    img = np.full((H, W, 3), value, np.uint8)
    if dot:
        img[260:284, 468:492] = 255
    Image.fromarray(img).save(path)


SNAP = r'''
local out = mp.get_opt('snap-out')
local n = 0
mp.register_event('playback-restart', function()
    n = n + 1
    local i = n
    mp.add_timeout(1.0, function()
        mp.commandv('screenshot-to-file', out .. '-' .. i .. '.png', 'window')
        if i >= mp.get_property_number('playlist-count', 1) then mp.command('quit')
        else mp.command('playlist-next') end
    end)
end)
'''


def vulkan_device():
    """The first Vulkan device mpv lists (lavapipe on CI runners is not picked automatically)."""
    if os.environ.get('AJ_VULKAN_DEVICE'):
        return os.environ['AJ_VULKAN_DEVICE']
    r = subprocess.run(['mpv', '--no-config', '--vulkan-device=help'], capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        line = line.strip()
        if line.startswith("'") and "'" in line[1:]:
            return line[1:line.index("'", 1)]
    return None


DEVICE = vulkan_device()


def render(tmp, images, shaders=(), opts=None, peak=1000):
    """Renders each image in turn (one player, in order) and returns the outputs in nits."""
    snap = os.path.join(tmp, 'snap.lua')
    with open(snap, 'w') as f:
        f.write(SNAP)
    out = os.path.join(tmp, 'shot%d' % len(os.listdir(tmp)))
    cmd = ['xvfb-run', '-a', '-s', '-screen 0 1280x720x24', 'mpv', '--no-config',
           '--msg-level=all=warn', '--vo=gpu-next', '--gpu-api=vulkan', '--gpu-context=x11vk',
           '--geometry=%dx%d' % (W, H), '--no-border', '--keepaspect=no', '--video-unscaled=yes',
           '--target-trc=pq', '--target-prim=bt.2020', '--target-peak=%d' % peak,
           '--target-contrast=inf', '--dither-depth=no', '--deband=no',
           '--screenshot-format=png', '--screenshot-high-bit-depth=yes', '--screenshot-png-compression=1',
           '--image-display-duration=inf', '--pause', '--script=' + snap, '--script-opts=snap-out=' + out]
    if DEVICE:
        cmd.append('--vulkan-device=' + DEVICE)
    for s in shaders:
        cmd.append('--glsl-shader=' + s)
    if opts:
        cmd.append('--glsl-shader-opts=' + ','.join('anime-hdr-grade/%s=%s' % kv for kv in opts.items()))
    cmd += images
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    log = r.stdout + r.stderr
    bad = [l for l in log.splitlines() if 'shader' in l.lower() and ('error' in l.lower() or 'fail' in l.lower())]
    if bad:
        print('\n'.join(bad))
    check('shaders compile (%s)' % (', '.join(os.path.basename(s) for s in shaders) or 'none'), not bad)
    shots = []
    for i in range(1, len(images) + 1):
        p = '%s-%d.png' % (out, i)
        if not os.path.exists(p):
            print(log)
            check('screenshot %d written' % i, False)
            sys.exit(1)
        a = np.array(Image.open(p)).astype(float)
        scale = 65535.0 if a.max() > 255 else 255.0
        shots.append(pq_to_nits(a[..., :3] / scale))
    return shots


def main():
    with tempfile.TemporaryDirectory() as tmp:
        c = os.path.join(tmp, 'chart.png'); chart(c)
        bright = os.path.join(tmp, 'bright.png'); flat(bright, 235, dot=True)
        dark = os.path.join(tmp, 'dark.png'); flat(dark, 20, dot=True)

        (base,) = render(tmp, [c])
        (grade,) = render(tmp, [c], [GRADE], MPV_BACKEND)
        finite = bool(np.isfinite(grade).all())
        check('output finite', finite)

        area, dot_black = grade[190, 160].max(), grade[86, 342].max()
        check('isolated highlight near the peak', 700 <= dot_black <= 1010, '%.0f nits' % dot_black)
        check('large white area kept moderate', 230 <= area <= 360, '%.0f nits' % area)
        check('highlight stands out of the area', dot_black > 2.5 * area)
        check('never above the display peak', grade.max() <= 1020, '%.0f nits' % grade.max())
        shadow_base, shadow = base[32, 30].max(), grade[32, 30].max()
        check('deep shadows darker', shadow <= shadow_base + 1e-3, '%.3f -> %.3f nits' % (shadow_base, shadow))
        skin_base, skin = base[430, 3 * 120 + 60], grade[430, 3 * 120 + 60]
        check('skin hue kept', abs(skin[0] / skin[1] - skin_base[0] / skin_base[1]) < 0.08,
              'R/G %.3f -> %.3f' % (skin_base[0] / skin_base[1], skin[0] / skin[1]))

        # OLED ABL: a bright scene gets less gain, a dark scene keeps its highlights.
        (b0,) = render(tmp, [bright], [GRADE], MPV_BACKEND)
        (b1,) = render(tmp, [bright], [GRADE], dict(MPV_BACKEND, abl=0.6))
        check('ABL lowers a bright scene', b1[100, 100].max() < b0[100, 100].max() - 5,
              '%.0f -> %.0f nits' % (b0[100, 100].max(), b1[100, 100].max()))
        (d1,) = render(tmp, [dark], [GRADE], dict(MPV_BACKEND, abl=0.6))
        (d0,) = render(tmp, [dark], [GRADE], MPV_BACKEND)
        check('ABL leaves a dark scene', abs(d1[272, 480].max() - d0[272, 480].max()) < 5,
              '%.0f / %.0f nits' % (d0[272, 480].max(), d1[272, 480].max()))

        # Scene cut: after a bright image, a dark one renders as if it were alone (no smearing).
        seq = render(tmp, [bright, dark], [GRADE], MPV_BACKEND)
        diff = float(np.abs(seq[1] - d0).max())
        check('scene cut resets the temporal state', diff < 2.0, 'max diff %.2f nits' % diff)

        # Calibration pattern: absolute patches.
        (cal,) = render(tmp, [c], [CALIBRATION])
        def patch(y, i):
            return float(np.median(cal[int(y * H), int((i + 0.5) * W / 8)]))
        for i, nits in enumerate([400, 600, 800, 1000]):
            v = patch(0.80, i)
            check('calibration peak patch %d nits' % nits, abs(v - nits) / nits < 0.03, '%.1f' % v)
        for i, nits in enumerate([5, 10, 20, 50, 100, 150, 203, 300]):
            v = patch(0.55, i)
            check('calibration grey patch %d nits' % nits, abs(v - nits) / nits < 0.03, '%.2f' % v)

    print('%d failure(s)' % len(failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
