#!/usr/bin/env python3
"""Exercise the Manager's export action against two owned real mpv/ORT CPU sessions."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

s = json.loads(Path(sys.argv[1]).read_text())
out = Path(s['output']); out.mkdir(parents=True, exist_ok=True)
receipt = out / 'summary.json'
if receipt.exists():
    assert json.loads(receipt.read_text())['passed']
    print('Conclusive receipt exists; no repeat.'); sys.exit()
models = out / 'models'; models.mkdir(exist_ok=True)
model = Path(s['model']); shutil.copyfile(model, models / model.name)
conf = out / 'test.conf'
conf.write_text('[global]\nbackend=CPU\nlogging=yes\n' + ''.join(
    f'[slot_{i}]\nchain_1_model_1_name={model.stem}\nchain_1_rife=no\n' for i in (1, 2)))
(out / 'version.txt').write_text('manager-reference-qualification\n')
commands, players, logs, sockets, proxies = [], [], [], [], []

class Control:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(5); self.socket.connect(str(path))
        self.stream = self.socket.makefile('rwb', buffering=0); self.request = 0
    def command(self, *args):
        self.request += 1
        self.stream.write((json.dumps(dict(command=args, request_id=self.request))+'\n').encode())
        while True:
            result = json.loads(self.stream.readline())
            if result.get('request_id') == self.request:
                if result['error'] != 'success': raise RuntimeError(result)
                return result.get('data')
    def state(self):
        return {p: self.command('get_property', p) for p in
                ('path', 'vf', 'pause', 'time-pos', 'video-out-params', 'user-data/animejanai-active-slot')}
    def close(self): self.stream.close(); self.socket.close()

class Proxy:
    def __init__(self, path, target):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path)); self.listener.listen(); self.listener.settimeout(.2)
        self.stopped = False; self.target = target
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()
    def run(self):
        while not self.stopped:
            try: client, _ = self.listener.accept()
            except socket.timeout: continue
            except OSError: break
            with client, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                try: upstream.connect(str(self.target))
                except OSError: continue  # Deliberately disconnected owned player; close the client normally.
                upstream.settimeout(5)
                with client.makefile('rwb', buffering=0) as front, upstream.makefile('rwb', buffering=0) as back:
                    while line := front.readline():
                        request = json.loads(line); commands.append(request['command']); back.write(line)
                        while reply := back.readline():
                            front.write(reply)
                            if json.loads(reply).get('request_id') == request['request_id']: break
    def close(self): self.stopped = True; self.listener.close(); self.thread.join(timeout=1)

with tempfile.TemporaryDirectory(prefix='aji-ref16-') as temp:
    runtime = Path(temp)
    env = dict(os.environ, LD_LIBRARY_PATH=s['runtime'], AJI_ORT_PROVIDER='cpu', OMP_NUM_THREADS='2',
               XDG_RUNTIME_DIR=temp, TMPDIR=temp)
    env.pop('ANIMEJANAI_IPC_PATH', None)
    try:
        endpoints = []
        for i in (1, 2):
            folder = runtime / f'animejanai-hdr.test{i}'; folder.mkdir(mode=0o700)
            real = folder / 'real.sock'; endpoint = folder / 'mpv.sock'; endpoints.append(str(endpoint))
            clip = out / f'session-{i}.mp4'; shutil.copyfile(s['clip'], clip)
            vf = f'animejanai-vulkan:lib={s["library"]}:conf={conf}:model-dir={models}:slot={i}:device=cpu:ahead=1'
            command = [s['player'], '--no-config', '--load-scripts=no', '--hwdec=no', '--vo=null',
                       '--pause=yes', '--keep-open=yes', '--idle=yes', '--audio=no', '--sub=no',
                       '--osd-level=0', '--input-ipc-server='+str(real), '--vf='+vf, str(clip)]
            commands_file = out / f'player-{i}-command.json'; commands_file.write_text(json.dumps(command, indent=2)+'\n')
            log = (out / f'player-{i}.log').open('w'); logs.append(log)
            player = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT); players.append(player)
            deadline = time.monotonic()+15
            while not real.exists():
                assert player.poll() is None, (out / f'player-{i}.log').read_text()
                if time.monotonic() > deadline: raise RuntimeError('No player IPC')
                time.sleep(.02)
            control = Control(real); sockets.append(control)
            while True:
                try:
                    if control.command('get_property', 'video-out-params'): break
                except RuntimeError: pass
                if time.monotonic() > deadline: raise RuntimeError('No decoded frame')
                time.sleep(.02)
            control.command('set_property', 'user-data/animejanai-active-slot', i)
            proxies.append(Proxy(endpoint, real))
        probe = subprocess.Popen([s['probe'], str(out)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=(out/'probe-stderr.log').open('w'), text=True, bufsize=1)
        transcript = []
        def act(action, **args):
            start = time.monotonic(); request = dict(action=action, **args)
            probe.stdin.write(json.dumps(request)+'\n'); probe.stdin.flush()
            selector = selectors.DefaultSelector(); selector.register(probe.stdout, selectors.EVENT_READ)
            try:
                if not selector.select(25): raise RuntimeError('Manager probe timed out')
                line = probe.stdout.readline(); assert line, (out/'probe-stderr.log').read_text()
            finally: selector.close()
            result = json.loads(line); transcript.append(dict(request=request, response=result, seconds=time.monotonic()-start))
            assert not result['IsBusy']; return result
        try:
            found = act('refresh')  # Production endpoint discovery, only this private runtime directory.
            assert len(found['sessions']) == 2 and found['selected'] is None and not found['CanExport'], found
            act('select', endpoint=endpoints[1])
            before = [c.state() for c in sockets]
            output = out/'selected-session.json'; result = act('export', output=str(output))
            assert result['exported'] and str(output) in result['Status'], result
            report = json.loads(output.read_text())
            assert report['consistent_observed_state'] and report['qualification'] == 'partial'
            assert report['observed_properties']['path'] == str(out/'session-2.mp4')
            assert report['observed_properties']['user-data/animejanai-active-slot'] == 2
            assert report['filters'][0]['observed_filter']['params']['slot'] == '2'
            assert report['manager_selection']['endpoint'] == endpoints[1]
            for artifact in report['artifacts']:
                assert hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest() == artifact['sha256']
            after = [c.state() for c in sockets]; assert before == after
            original = output.read_bytes(); count = len(commands)
            existing = act('export', output=str(output))
            assert not existing['exported'] and 'already exists' in existing['Status']
            assert output.read_bytes() == original and len(commands) == count
            sockets[1].command('set_property', 'user-data/animejanai-active-slot', 3)
            stale_file = out/'stale.json'; stale = act('export', output=str(stale_file))
            assert not stale['exported'] and 'changed' in stale['Status'] and not stale_file.exists(), stale
            act('refresh'); assert act('select', endpoint=endpoints[1])['CanExport']
            sockets[1].command('quit'); players[1].wait(timeout=5); sockets[1].close(); sockets.pop()
            gone_file = out/'gone.json'; gone = act('export', output=str(gone_file))
            assert not gone['exported'] and 'failed' in gone['Status'] and not gone_file.exists(), gone
            assert commands and all(c[0] in ('get_property', 'expand-path') for c in commands), commands
            summary = dict(passed=True, two_real_sessions=True, selected_media='session-2.mp4', selected_slot=2,
                report_artifacts=len(report['artifacts']), unchanged_player_state=True, read_only_commands=len(commands),
                existing_destination_preserved=True, stale_selection_refused=True, disconnected_session_refused=True,
                export_seconds=transcript[2]['seconds'], fps_claimed=False, qualification='Manager Linux action; Windows/macOS runtime in AH-237')
            (out/'transcript.json').write_text(json.dumps(transcript, indent=2)+'\n')
            (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
            receipt.write_text(json.dumps(summary, indent=2)+'\n'); print(json.dumps(summary, indent=2))
        finally:
            probe.stdin.close(); probe.wait(timeout=5)
    finally:
        for control in sockets:
            try: control.command('quit')
            except (OSError, RuntimeError, ValueError): pass
            control.close()
        for player in players:
            if player.poll() is None:
                player.terminate(); player.wait(timeout=5)
        for proxy in proxies: proxy.close()
        for log in logs: log.close()
