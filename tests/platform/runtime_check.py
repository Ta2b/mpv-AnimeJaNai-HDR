#!/usr/bin/env python3
"""Exercise an isolated portable package on a real Wayland session via mpv IPC.
Usage: runtime_check.py PACKAGE --report REPORT [--manager-writer DLL --dotnet DOTNET]
The source package is never edited. This checks playback/IPC, not physical HDR accuracy.
"""
import argparse
import glob
import json
import os
import re
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('package', type=Path)
p.add_argument('--report', type=Path, required=True)
p.add_argument('--manager-writer', type=Path)
p.add_argument('--dotnet', default='dotnet')
p.add_argument('--appimage', type=Path)
p.add_argument('--inference', action='store_true', help='Exercise Vulkan profiles on the selected real GPU')
args = p.parse_args()
runtime = os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir())
before = set(glob.glob(runtime + '/animejanai-hdr.*/mpv.sock'))
manager_pid = None
report = {'physical_hdr_verified': False, 'test_conditions': {
    'performance_reference': False, 'load_controlled': False,
    'purpose': 'functional validation; no Windows/Linux performance comparison'}}
args.report.parent.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='ajn-runtime-') as tmp:
    tree = Path(tmp) / 'player'
    shutil.copytree(args.package, tree, symlinks=True)
    log = args.report.with_suffix('.mpv.log').resolve()
    console_path = args.report.with_suffix('.console.log').resolve()
    clips = sorted((tree / 'animejanai/benchmarks').glob('*.mp4'))
    assert clips, 'No bundled test clips'
    console = console_path.open('w')
    launcher = tree / 'mpv-animejanai'
    env = os.environ.copy()
    if args.appimage:
        launcher = args.appimage.resolve()
        env.update(APPIMAGE_EXTRACT_AND_RUN='1', XDG_DATA_HOME=str(Path(tmp) / 'data'), ANIMEJANAI_OFFLINE='1')
        tree = Path(tmp) / 'data/AnimeJaNai-HDR-linux'
    player = subprocess.Popen([str(launcher), '--idle=yes', '--keep-open=yes',
        '--pause=yes', '--ao=null', '--force-window=yes', '--no-terminal', '--log-file=' + str(log), str(clips[0])],
        stdout=console, stderr=console, env=env)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(15)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            paths = set(glob.glob(runtime + '/animejanai-hdr.*/mpv.sock')) - before
            if paths: break
            if player.poll() is not None: raise RuntimeError('Player stopped: ' + console_path.read_text())
            time.sleep(.1)
        assert paths, 'IPC socket not created'
        ipc = paths.pop()
        assert stat.S_IMODE(Path(ipc).parent.stat().st_mode) == 0o700, 'IPC directory not private'
        client.connect(ipc)
        stream = client.makefile('rwb', buffering=0)
        sequence = 0
        def command(*cmd):
            global sequence
            sequence += 1
            stream.write((json.dumps({'command': cmd, 'request_id': sequence}) + '\n').encode())
            while True:
                line = stream.readline()
                if not line: raise RuntimeError('IPC closed')
                result = json.loads(line)
                if result.get('request_id') == sequence:
                    if result['error'] != 'success': raise RuntimeError(str(cmd) + ': ' + result['error'])
                    return result.get('data')
        def get(name): return command('get_property', name)
        for _ in range(100):
            try:
                if get('video-params').get('w'): break
            except (RuntimeError, AttributeError): pass
            time.sleep(.1)
        context = get('gpu-context')
        if isinstance(context, list):
            context = context[0]['name'] if isinstance(context[0], dict) else context[0]
        assert context == 'waylandvk', repr(context)
        hardware = get('user-data/animejanai-hardware')
        assert hardware['vulkan_device'], 'Vulkan adapter not selected explicitly'
        if args.inference:
            bank = 'linux-nvidia' if hardware['vendor'] == 'nvidia' else 'linux-amd'
            bank_conf = (tree / 'portable_config/profiles' / bank / 'animejanai.conf').read_text()
            expected = int(re.search(r'^default_slot=(\d+)', bank_conf, re.M)[1])
            for _ in range(100):
                if get('user-data/animejanai-active-slot') == expected: break
                time.sleep(.1)
            assert get('user-data/animejanai-active-slot') == expected, 'Packaged startup profile was not activated'
            if expected:
                assert any(f.get('name') == 'animejanai-vulkan' for f in get('vf'))
                assert re.search(r'\[slot_' + str(expected) + r'\][\s\S]*?chain_1_rife=no', bank_conf)
            report['startup_profile'] = {'slot': expected, 'rife': False, 'activated': True}
            report['startup_output'] = get('user-data/animejanai-linux-hdr')
            expected_output = re.search(r'^linux_hdr_output=(\w+)',
                (tree / 'portable_config/script-opts/animejanai_hdr_auto.conf').read_text(), re.M)[1]
            assert report['startup_output']['requested'] == expected_output, 'Startup output did not respect the saved mode'
            command('keypress', 'Ctrl+0')
            for _ in range(100):
                if get('user-data/animejanai-active-slot') == 0: break
                time.sleep(.1)
        assert get('user-data/animejanai-active-slot') == 0
        assert not any(f.get('label') == 'aji' for f in get('vf'))
        loaded = get('user-data/animejanai-user-runtime')
        assert loaded['started'] and not any(n.endswith('.dll') for n in loaded['loaded'])
        report.update(hardware=hardware, loaded=loaded, ipc_private=True)
        command('keypress', 'Ctrl+e')
        for _ in range(100):
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit(): continue
                try:
                    cmdline = (proc / 'cmdline').read_bytes().split(b'\0')
                    if cmdline and Path(cmdline[0].decode()).resolve() == (tree / 'AnimeJaNaiManager-HDR').resolve():
                        manager_pid = int(proc.name); break
                except (OSError, UnicodeError): pass
            if manager_pid: break
            time.sleep(.1)
        assert manager_pid, 'Ctrl+E handler did not launch Manager'
        time.sleep(1)
        os.kill(manager_pid, 0)
        report['manager_opened'] = True
        if args.manager_writer:
            env = os.environ.copy(); env['ANIMEJANAI_IPC_PATH'] = ipc
            hdr = tree / 'portable_config/script-opts/animejanai_hdr_auto.conf'
            hdr.write_text(hdr.read_text() + '\n# smoke test comment\nunknown_smoke=keep\n')
            for output in ('pq', 'sdr'):
                subprocess.run([args.dotnet, str(args.manager_writer), '--save-hdr', str(hdr), output], env=env, check=True)
                time.sleep(.5)
                state = get('user-data/animejanai-linux-hdr')
                assert state['requested'] == output, 'Manager save did not reload via IPC'
                assert state['display'] == 'not-physically-verified'
                if output == 'pq' and state['negotiated'] == 'pq':
                    command('keypress', 'Ctrl+Alt+p'); time.sleep(.2)
                    assert any('calibration' in s for s in get('glsl-shaders')), 'Calibration shortcut failed'
                    command('keypress', 'Ctrl+Alt+p'); time.sleep(.2)
                    command('keypress', 'Ctrl+g'); command('keypress', 'Ctrl+g'); time.sleep(.2)
                    assert not any('anime-hdr-' in s for s in get('glsl-shaders')), 'Grade off shortcut failed'
                    command('keypress', 'Ctrl+g'); time.sleep(.2)
                    report['hdr_shortcuts_negotiated_pq'] = True
                if output == 'sdr': assert not any('anime-hdr-' in s for s in get('glsl-shaders')), 'HDR shaders left active in SDR'
                assert 'unknown_smoke=keep' in hdr.read_text() and '# smoke test comment' in hdr.read_text()
            report['manager_save_reload_comments'] = True
        results = []
        for clip in clips:
            command('loadfile', str(clip), 'replace')
            command('set_property', 'pause', False)
            for _ in range(100):
                try:
                    if get('path') == str(clip) and get('time-pos') >= .75: break
                except RuntimeError: pass
                time.sleep(.1)
            params = get('video-params')
            expected_w, expected_h = map(int, clip.stem.split('x'))
            assert (params['w'], params['h']) == (expected_w, expected_h), 'Wrong decoded clip dimensions'
            results.append({'clip': clip.name, 'width': params['w'], 'height': params['h'],
                'hwdec': get('hwdec-current'), 'dropped_frames': get('frame-drop-count')})
        if args.inference:
            # Keep tests SDR; inference must not depend on negotiated HDR output.
            command('loadfile', str(clips[0]), 'replace')
            command('set_property', 'pause', False)
            time.sleep(.5)
            inference = []
            for slot, height, rife in ((1, 720, False), (2, 720, True), (3, int(clips[0].stem.split('x')[1]), True), (5, 480, False), (6, 360, True), (1, 720, False)):
                command('keypress', 'Ctrl+' + str(slot))
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        video = get('video-out-params')
                        stats_path = tree / 'animejanai/currentanimejanai.log'
                        stats = stats_path.read_text() if stats_path.exists() else ''
                        if get('user-data/animejanai-active-slot') == slot and video.get('h') == height and ('RIFE: 4.6' if rife else 'RIFE: off') in stats: break
                    except (RuntimeError, AttributeError): pass
                    time.sleep(.1)
                assert get('user-data/animejanai-active-slot') == slot
                assert video['h'] == height, repr(video)
                assert ('RIFE: 4.6' if rife else 'RIFE: off') in stats, stats
                assert 'GPU: ' + hardware['vulkan_device'] in stats, 'Wrong inference GPU'
                assert any(f.get('name') == 'animejanai-vulkan' for f in get('vf'))
                before_pos = get('time-pos')
                before_dropped = get('frame-drop-count')
                vram_peak = None
                memory_file = Path('/sys/bus/pci/devices') / hardware['pci'] / 'mem_info_vram_used'
                for _ in range(50):
                    if memory_file.exists():
                        try: vram_peak = max(vram_peak or 0, int(memory_file.read_text()))
                        except OSError: pass
                    time.sleep(.1)
                assert get('time-pos') > before_pos, 'Inference playback stalled'
                inference.append({'slot': slot, 'output': video,
                    'dropped_frames': get('frame-drop-count') - before_dropped,
                    'stats': stats_path.read_text(), 'vram_device_peak_bytes': vram_peak, 'decoder': get('hwdec-current')})
                command('seek', '10', 'absolute+exact')
                time.sleep(.3)
            command('script-message', 'animejanai-select', '0')
            time.sleep(.5)
            assert not any(f.get('label') == 'aji' for f in get('vf')), 'Inference filter was not removed'
            # Reload a different resolution and enable again: flush/reconfigure.
            command('loadfile', str(clips[-1]), 'replace')
            time.sleep(.5)
            command('script-message', 'animejanai-select', '1')
            time.sleep(2)
            assert get('video-out-params')['h'] == 720
            command('script-message', 'animejanai-select', '0')
            for _ in range(100):
                if get('user-data/animejanai-active-slot') == 0: break
                time.sleep(.1)
            assert get('user-data/animejanai-active-slot') == 0
            report['inference'] = inference
            report['inference_switch_seek_reload_disable'] = True
        command('keypress', 'Ctrl+Alt+h')
        time.sleep(.2)
        report['clips'] = results
        report['output'] = get('user-data/animejanai-linux-hdr')
        report['diagnostic'] = (tree / 'animejanai/diagnostic-hdr.txt').read_text()
        assert 'powershell.exe' not in log.read_text().lower()
        assert 'display-info.dll' not in log.read_text().lower()
        command('quit')
        player.wait(timeout=10)
        assert not Path(ipc).exists(), 'IPC socket left behind'
        report['socket_cleanup'] = True
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        client.close()
        if manager_pid:
            try: os.kill(manager_pid, signal.SIGTERM)
            except ProcessLookupError: pass
        if player.poll() is None:
            player.terminate()
            try: player.wait(timeout=5)
            except subprocess.TimeoutExpired: player.kill()
        console.close()
