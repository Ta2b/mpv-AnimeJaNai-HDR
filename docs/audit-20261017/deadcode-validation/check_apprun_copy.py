#!/usr/bin/env python3
"""Compare the extracted managed-directory copies before/after removal of duplicates."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

repo = Path('/tmp/animejanai-audit-cleanup-20261017')
before = subprocess.check_output(['git', 'show', 'HEAD:installer/linux/AppRun'], cwd=repo, text=True)
after = (repo / 'installer/linux/AppRun').read_text()

def copies(source):
    start = source.index('for managed in scripts shaders user-scripts user-shaders hdr-tools; do')
    end = source.index('\ndone', start) + len('\ndone')
    extra = [line for line in source.splitlines() if line.startswith('cp -rf "$HERE/portable_config/scripts"') or line.startswith('cp -rf "$HERE/portable_config/shaders"')]
    return source[start:end] + '\n' + '\n'.join(extra) + '\n'

def tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        key = str(path.relative_to(root))
        metadata = path.lstat()
        row = {'mode': stat.S_IMODE(metadata.st_mode)}
        if path.is_symlink():
            row.update(type='symlink', target=os.readlink(path))
        elif path.is_dir():
            row.update(type='directory')
        else:
            row.update(type='file', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result[key] = row
    return result

with tempfile.TemporaryDirectory(prefix='aji copy check ') as temp:
    base = Path(temp)
    image = base / 'image with spaces'
    seed = base / 'initial user data'
    wrapper = base / 'bin'
    wrapper.mkdir()
    (wrapper / 'cp').write_text('#!/bin/sh\nprintf "copy\\n" >> "$COPY_LOG"\nexec /bin/cp "$@"\n')
    (wrapper / 'cp').chmod(0o755)
    for name in ('scripts', 'shaders', 'user-scripts', 'user-shaders', 'hdr-tools'):
        src = image / 'portable_config' / name
        dst = seed / 'portable_config' / name
        (src / 'nested').mkdir(parents=True)
        dst.mkdir(parents=True)
        (src / 'nested' / 'asset with spaces.dat').write_bytes(bytes(range(256)))
        (src / 'replace.lua').write_text('fresh managed file\n')
        (src / 'replace.lua').chmod(0o640)
        (src / 'local-link').symlink_to('replace.lua')
        (dst / 'replace.lua').write_text('old managed file\n')
        (dst / 'user-only.txt').write_text('preserved custom file\n')
    states = {}
    counts = {}
    for label, source in [('before', before), ('after', after)]:
        data = base / label
        shutil.copytree(seed, data)
        log = base / f'{label}.log'
        env = dict(os.environ, HERE=str(image), DATA=str(data), COPY_LOG=str(log), PATH=str(wrapper) + os.pathsep + os.environ['PATH'])
        subprocess.run(['sh', '-eu', '-c', copies(source)], env=env, check=True)
        states[label] = tree(data)
        counts[label] = len(log.read_text().splitlines())
    assert states['before'] == states['after'], 'Managed-copy final trees differ'
    assert counts == {'before': 7, 'after': 5}, counts
    print(json.dumps({'result': 'PASS', 'trees_equal_content_modes_symlinks': True, 'preserves_existing_user_only_files': True, 'copy_invocations': counts, 'entries_compared': len(states['after']), 'scope': 'extracted managed-directory copy block; no full AppImage launch, GPU or FPS measurement'}, indent=2))
