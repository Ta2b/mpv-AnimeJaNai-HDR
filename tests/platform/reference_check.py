#!/usr/bin/env python3
"""Observed-reference contract against an independent, read-only mpv IPC fixture.

Usage: reference_check.py PLATFORM_EXECUTABLE
Linux/macOS Unix socket transport; Windows transport is qualified on Windows.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading

helper = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='aji-ref-') as temp:
    root = Path(temp)
    models = root / 'models'; models.mkdir()
    model = models / 'same.onnx'; model.write_bytes(b'graph')
    weights = models / 'same.onnx.data'; weights.write_bytes(b'AAAA')
    config = root / 'effective.conf'; config.write_text('[slot_1]\nchain_1_rife_engine=quality\n')
    library = root / 'aji.so'; library.write_bytes(b'engine')
    # A directory link used by the Mac model installer, including a loop.
    package = root / 'package.mlpackage'; package.mkdir()
    (package / 'weights.bin').write_bytes(b'package weights')
    (models / 'linked.mlpackage').symlink_to(package, target_is_directory=True)
    (package / 'cycle').symlink_to(package, target_is_directory=True)
    vf = [{'name':'animejanai', 'enabled':True, 'params':{
        'lib':str(library), 'conf':str(config), 'model-dir':str(models), 'slot':'1'}}]
    props = {'path':'test.mp4', 'playlist-pos':0, 'time-pos':1.0, 'pause':True, 'vf':vf,
        'video-params':{'w':16,'h':16}, 'video-out-params':{'w':32,'h':32},
        'working-directory':str(root), 'options/scale':'ewa_lanczossharp'}

    def capture(label, change=False, loaded=True):
        endpoint = root / 'mpv.sock'
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(endpoint)); server.listen(1)
        calls, errors = [], []
        def serve():
            try:
                connection, _ = server.accept()
                with connection, connection.makefile('rwb', buffering=0) as stream:
                    counts = {}
                    for line in stream:
                        request = json.loads(line); command = request['command']; calls.append(command)
                        assert command[0] in ['get_property','expand-path'], command
                        response = dict(request_id=request['request_id'], error='success')
                        if command[0] == 'expand-path': response['data'] = command[1]
                        else:
                            key = command[1]; counts[key] = counts.get(key,0) + 1
                            if key not in props or (not loaded and key == 'path'):
                                response['error'] = 'property unavailable'
                            else:
                                response['data'] = props[key]
                                if key == 'vf' and change and counts[key] > 1: response['data'] = []
                        # An unrelated event precedes responses, just as with the real mpv.
                        stream.write(b'{"event":"idle"}\n')
                        stream.write((json.dumps(response)+'\n').encode())
            except Exception as error: errors.append(error)
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        output = root / (label+'.json')
        result = subprocess.run([str(helper),'--export-reference','--root',str(root),
            '--mpv-ipc',str(endpoint),'--output',str(output)], text=True, capture_output=True, timeout=10)
        thread.join(3); server.close(); endpoint.unlink()
        assert not thread.is_alive() and not errors, errors
        return result, json.loads(output.read_text()) if output.exists() else None

    result, first = capture('first')
    assert result.returncode == 0, result.stderr
    assert first['consistent_observed_state'] and first['qualification'] == 'partial'
    assert first['observed_properties']['options/scale'] == 'ewa_lanczossharp'
    assert first['unavailable_properties']['hwdec-current'] == 'property unavailable'
    assert any('cycle' in warning.lower() for warning in first['warnings'])
    bypath = {a['path']:a for a in first['artifacts']}
    assert bypath[str(weights)]['sha256'] == hashlib.sha256(b'AAAA').hexdigest()
    assert bypath[str(models/'linked.mlpackage/weights.bin')]['sha256'] == hashlib.sha256(b'package weights').hexdigest()
    assert bypath[str(config)]['text'] == config.read_text()
    # Same name, same size, restored mtime: content hash must still change.
    stamp = weights.stat(); weights.write_bytes(b'BBBB'); os.utime(weights, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    result, changed = capture('changed', change=True)
    assert result.returncode == 0, result.stderr
    assert not changed['consistent_observed_state'] and 'vf' in changed['changed_during_capture']
    assert next(a['sha256'] for a in changed['artifacts'] if a['path']==str(weights)) == hashlib.sha256(b'BBBB').hexdigest()
    # Export to an existing report must fail without changing its bytes.
    protected = (root/'first.json').read_bytes()
    result, _ = capture('first')
    assert result.returncode != 0 and (root/'first.json').read_bytes() == protected
    assert not list(root.glob('*.tmp'))
    result, absent = capture('absent', loaded=False)
    assert result.returncode != 0 and absent is None
    print(json.dumps({'passed':True, 'read_only_ipc':True, 'same_name_changed_weights_detected':True,
        'state_change_detected':True, 'symlink_package_hashed':True, 'loop_bounded':True,
        'existing_report_preserved':True, 'idle_player_rejected':True}, indent=2))
