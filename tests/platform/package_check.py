#!/usr/bin/env python3
"""Offline AppRun/update fixtures: managed refresh, user preservation and private IPC.
Uses the real launchers with a fake mpv process; hardware playback is runtime_check.py.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / 'BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/hdr-tools/launch-linux.sh'
passed = 0
def check(name, condition):
    global passed
    assert condition, name
    print('PASS ' + name); passed += 1

with tempfile.TemporaryDirectory(prefix='ajn-package-') as tmp:
    base = Path(tmp)
    image = base / 'image1'; data_home = base / 'data'; runtime = base / 'runtime'; runtime.mkdir()
    def write(relative, content):
        target = image / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
    for folder in ('scripts', 'shaders', 'user-scripts', 'user-shaders', 'hdr-tools'):
        write('portable_config/' + folder + '/managed', 'v1')
    for path, value in {
        'version.txt': 'test-1', 'manifest.json': '{"platform":"linux-x64"}', '7zz': 'tool', 'portable_config/mpv.conf': 'user defaults',
        'portable_config/mpv-animejanai.conf': '# managed default',
        'portable_config/input-animejanai.conf': '# managed input',
        'portable_config/script-opts/animejanai_hdr_auto.conf': 'linux_hdr_output=sdr\n',
        'portable_config/profiles/linux-amd/animejanai.conf': 'AMD bank',
        'animejanai/animejanai.conf': '[global]\ndefault_slot=0\n',
        'animejanai/onnx/model.onnx': 'model', 'animejanai/onnx/model.ncnn.bin': 'vulkan-v1',
        'animejanai/rife-vulkan/rife-v4.6/flownet.bin': 'rife-v1', 'animejanai/inference/libaji_vulkan.so': 'library-v1', 'AnimeJaNaiManager-HDR': 'manager',
        'AnimeJaNaiPlatform': 'helper', 'libSkiaSharp.so': 'native library',
    }.items(): write(path, value)
    write('mpv/mpv', '''#!/bin/sh
printf '%s\n' "$ANIMEJANAI_ROOT" "$ANIMEJANAI_IPC_PATH" "$ANIMEJANAI_INFERENCE_DIR" > "$AJ_CAPTURE"
printf '%s\n' "$@" > "$AJ_CAPTURE.args"
stat -c '%a' "$(dirname "$ANIMEJANAI_IPC_PATH")" >> "$AJ_CAPTURE"
''')
    (image / 'mpv/mpv').chmod(0o755)
    shutil.copy2(LAUNCHER, image / 'mpv-animejanai'); (image / 'mpv-animejanai').chmod(0o755)
    shutil.copy2(REPO / 'installer/linux/AppRun', image / 'AppRun'); (image / 'AppRun').chmod(0o755)
    upstream = data_home / 'AnimeJaNai'; upstream.mkdir(parents=True); (upstream / 'sentinel').write_text('keep')
    env = os.environ.copy()
    for name in ('ANIMEJANAI_ROOT', 'ANIMEJANAI_MPV', 'ANIMEJANAI_INFERENCE_DIR'): env.pop(name, None)
    env.update(XDG_DATA_HOME=str(data_home), XDG_RUNTIME_DIR=str(runtime),
        ANIMEJANAI_OFFLINE='1', AJ_CAPTURE=str(base / 'capture'))
    def launch(): subprocess.run([str(image / 'AppRun')], env=env, check=True, capture_output=True)
    launch()
    data = data_home / 'AnimeJaNai-HDR-linux'
    capture = (base / 'capture').read_text().splitlines()
    check('AppImage uses fork-specific data directory', capture[0] == str(data))
    check('IPC parent private', capture[3] == '700')
    check('IPC directory removed after exit', not Path(capture[1]).parent.exists())
    check('upstream data untouched', (upstream / 'sentinel').read_text() == 'keep')
    check('HDR Manager and helper linked', (data / 'AnimeJaNaiManager-HDR').is_symlink() and (data / 'AnimeJaNaiPlatform').is_symlink())
    preserved = {
        'portable_config/mpv.conf': '# personal player settings',
        'portable_config/script-opts/animejanai_hdr_auto.conf': '# comment\nlinux_hdr_output=sdr\npaper_white=280\n',
        'portable_config/profiles/linux-amd/animejanai.conf': '# user bank',
        'animejanai/animejanai.conf': '[global]\ndefault_slot=1\nchain_1_rife=yes\n',
        'animejanai/onnx/model.engine': 'cached engine',
    }
    for relative, content in preserved.items(): (data / relative).write_text(content)
    old_image = image
    image = base / 'image2'; shutil.copytree(old_image, image)
    write('version.txt', 'test-2')
    write('animejanai/onnx/model.ncnn.bin', 'vulkan-v2')
    write('animejanai/rife-vulkan/rife-v4.6/flownet.bin', 'rife-v2')
    write('portable_config/profiles/linux-nvidia/animejanai.conf', 'new bank')
    for folder in ('scripts', 'shaders', 'user-scripts', 'user-shaders', 'hdr-tools'):
        write('portable_config/' + folder + '/managed', 'v2')
    launch()
    for relative, content in preserved.items(): check('preserve ' + relative, (data / relative).read_text() == content)
    for folder in ('scripts', 'shaders', 'user-scripts', 'user-shaders', 'hdr-tools'):
        check('refresh ' + folder, (data / 'portable_config' / folder / 'managed').read_text() == 'v2')
    check('new bank seeded during upgrade', (data / 'portable_config/profiles/linux-nvidia/animejanai.conf').read_text() == 'new bank')
    check('updater receives current Linux manifest and version', (data / 'version.txt').read_text() == 'test-2' and 'linux-x64' in (data / 'manifest.json').read_text())
    check('archive tool linked for writable component installation', (data / '7zz').is_symlink())
    check('Manager relinked for new mount path', (data / 'AnimeJaNaiManager-HDR').resolve() == image / 'AnimeJaNaiManager-HDR')
    check('Vulkan weights refreshed', (data / 'animejanai/onnx/model.ncnn.bin').read_text() == 'vulkan-v2')
    check('RIFE Vulkan refreshed', (data / 'animejanai/rife-vulkan/rife-v4.6/flownet.bin').read_text() == 'rife-v2')
    check('Vulkan library relinked even while old image remains mounted', (data / 'animejanai/inference/libaji_vulkan.so').resolve() == image / 'animejanai/inference/libaji_vulkan.so')
    write('portable_config/hdr-tools/managed', 'v3-same-version'); launch()
    check('HDR tools refreshed even for reused version', (data / 'portable_config/hdr-tools/managed').read_text() == 'v3-same-version')
    # Desktop integration: only a real AppImage registers itself, the entry follows the file.
    apps = data_home / 'applications/mpv-animejanai-hdr.desktop'
    def player_args(): return [l for l in (base / 'capture.args').read_text().splitlines() if not l.startswith(('--config-dir=', '--input-ipc-server='))]
    check('no menu entry without an AppImage path', not apps.exists())
    check('no file given opens the player window', player_args() == ['--player-operation-mode=pseudo-gui'])
    env['APPIMAGE'] = str(base / 'player v1.AppImage'); launch()
    entry = apps.read_text()
    check('menu entry registered on launch', f'TryExec={env["APPIMAGE"]}' in entry and f'Exec="{env["APPIMAGE"]}" %U' in entry and 'video/x-matroska' in entry)
    subprocess.run([str(image / 'AppRun'), str(base / 'a b.mkv')], env=env, check=True, capture_output=True)
    check('file from Open With reaches the player', player_args() == [str(base / 'a b.mkv')])
    env['APPIMAGE'] = str(base / 'player v2.AppImage'); launch()
    check('menu entry follows a renamed AppImage', f'TryExec={env["APPIMAGE"]}' in apps.read_text())
    subprocess.run([str(image / 'AppRun'), '--uninstall'], env=env, check=True, capture_output=True); launch()
    check('uninstall is respected on later launches', not apps.exists())
    subprocess.run([str(image / 'AppRun'), '--install'], env=env, check=True, capture_output=True)
    check('install registers again', apps.exists())
    print(f'{passed} offline package regressions passed')
