#!/usr/bin/env python3
"""Targeted real mpv/NVDEC checks. SPEC.json {mpv,input,conf,models,lib,out};
run with case paused|sequence|seek. Successful receipts are reused, never rerun.
CUDA/TensorRT runtime libraries must already be available to the subprocess.
"""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

spec = json.loads(Path(sys.argv[1]).read_text())
case = sys.argv[2]
assert case in ('paused', 'sequence', 'seek')
out = Path(spec['out']); out.mkdir(parents=True, exist_ok=True)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def arguments(capacity, name):
    vf = (f"@aji:animejanai=conf={spec['conf']}:model-dir={spec['models']}:"
          f"lib={spec['lib']}:trtexec=/bin/false:slot=1:queue-depth=1:"
          f"output-444=no:passthrough=no:prefetch={capacity}")
    return [spec['mpv'], '--no-config', '--load-scripts=no', '--ao=null',
            '--audio=no', '--hwdec=nvdec', '--hwdec-codecs=all',
            '--stop-screensaver=no', f'--log-file={out}/{name}.log', f'--vf={vf}']

def sequence(capacity, name):
    video = out / (name + '.nut')
    args = arguments(capacity, name) + [f'--o={video}', '--of=nut',
                                      '--ovc=rawvideo', spec['input']]
    started = time.monotonic()
    with (out / (name + '-stdout.log')).open('wb') as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                       timeout=20, check=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
        '-select_streams', 'v:0', '-show_streams', '-show_frames', '-of', 'json', str(video)]))
    raw = out / (name + '.nv12')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video),
                    '-pix_fmt', 'nv12', '-f', 'rawvideo', str(raw)], check=True)
    stream = probe['streams'][0]
    assert (stream['width'], stream['height']) == (256, 144)
    data = raw.read_bytes(); frame_size = 256 * 144 * 3 // 2
    assert len(data) == spec.get('frames', 12) * frame_size
    frames = [{'pts': f['pts'], 'time_base': stream['time_base'],
               'sha256': hashlib.sha256(data[i*frame_size:(i+1)*frame_size]).hexdigest()}
              for i, f in enumerate(probe['frames'])]
    assert len(frames) == spec.get('frames', 12)
    log = (out / (name + '.log')).read_text()
    assert 'cuda[nv12]' in log and 'backend: TensorRT' in log
    return {'frames': frames, 'raw_sha256': digest(raw),
            'duration_s': time.monotonic() - started, 'args': args}

def interactive(capacity, name, seek):
    endpoint = out / (name + '.sock')
    endpoint.unlink(missing_ok=True)
    args = arguments(capacity, name) + ['--vo=null', '--pause=yes',
        '--keep-open=yes', '--idle=yes', '--screenshot-sw=yes',
        f'--input-ipc-server={endpoint}', spec['input']]
    started = time.monotonic()
    with (out / (name + '-stdout.log')).open('wb') as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        connection = None
        try:
            deadline = time.monotonic() + 12
            while not endpoint.exists():
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(.02)
            connection = socket.socket(socket.AF_UNIX); connection.settimeout(5)
            connection.connect(str(endpoint)); reader = connection.makefile('rb')
            request_id = 0
            def command(command):
                nonlocal request_id
                request_id += 1
                connection.sendall((json.dumps({'command': command, 'request_id': request_id})+'\n').encode())
                while True:
                    line = reader.readline(); assert line, 'IPC disconnected'
                    response = json.loads(line)
                    if response.get('request_id') == request_id:
                        return response
            def prop(name):
                return command(['get_property', name]).get('data')
            def state():
                return {'pause': prop('pause'), 'time_pos': prop('time-pos'),
                        'meta': prop('vf-metadata/aji') or {},
                        'video_out': prop('video-out-params'), 'hwdec': prop('hwdec-current')}
            while True:
                before = state(); meta = before['meta']
                if (before['time_pos'] is not None and meta.get('prefetch-format') == 'cuda'
                        and int(meta.get('prefetch-ready', -1)) == capacity):
                    break
                assert time.monotonic() < deadline, before
                time.sleep(.02)
            assert before['pause'] is True and before['hwdec'] == 'nvdec'
            assert (before['video_out']['w'], before['video_out']['h']) == (256, 144)
            result = {'before': before}
            if seek:
                initial = out / (name + '-initial.png'); target = out / (name + '-target.png')
                assert command(['screenshot-to-file', str(initial), 'video'])['error'] == 'success'
                assert command(['seek', '0.3', 'absolute+exact'])['error'] == 'success'
                deadline = time.monotonic() + 5
                while True:
                    after = state(); meta = after['meta']; ready = int(meta.get('prefetch-ready', -1))
                    # Near EOF fewer than capacity pictures may remain. EOF is not a picture.
                    if (after['time_pos'] is not None and after['time_pos'] >= .3
                        and int(meta.get('prefetch-epoch', 0)) > int(before['meta']['prefetch-epoch'])
                        and ((capacity == 0 and ready == 0) or 0 < ready <= capacity)):
                        break
                    assert time.monotonic() < deadline, after
                    time.sleep(.02)
                assert after['pause'] is True
                assert command(['screenshot-to-file', str(target), 'video'])['error'] == 'success'
                assert digest(initial) != digest(target)
                result.update(after=after, initial_png_sha256=digest(initial), target_png_sha256=digest(target))
                if capacity:
                    response = command(['vf-command', 'aji', 'slot', '1'])
                    assert response['error'] != 'success', response
                    result['slot_command'] = response
            command(['quit'])
            process.wait(timeout=5)
            assert process.returncode == 0
            result.update(duration_s=time.monotonic()-started, args=args)
            return result
        finally:
            if connection:
                connection.close()
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)

identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode() + b''.join(
    Path(spec[key]).read_bytes() for key in ('mpv', 'input', 'conf', 'lib'))).hexdigest()
results = []
for capacity in (0, 3):
    name = f'{case}-{capacity}'
    receipt = out / (name + '-receipt.json')
    if receipt.exists():
        result = json.loads(receipt.read_text())
        assert result.get('_identity') == identity, 'Inputs changed: use a fresh output directory'
    else:
        result = sequence(capacity, name) if case == 'sequence' else interactive(capacity, name, case == 'seek')
        result['_identity'] = identity
        receipt.write_text(json.dumps(result, indent=2)+'\n')
    results.append(result)
if case == 'sequence':
    assert results[0]['frames'] == results[1]['frames'], 'Pixels or PTS changed'
elif case == 'seek':
    assert results[0]['target_png_sha256'] == results[1]['target_png_sha256'], 'Different/stale target picture'
print(json.dumps({'case': case, 'passed': True, 'results': results}, indent=2))
