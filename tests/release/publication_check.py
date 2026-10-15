#!/usr/bin/env python3
"""Targeted publication regression: run the actual scripts against a fake gh."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="aji-release-") as temp:
    base = Path(temp)
    state = base / "state.json"
    gh = base / "gh"
    gh.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ['RELEASE_TEST_STATE']);s=json.loads(p.read_text());a=sys.argv[1:]
s['calls'].append(a)
command=a[1];tag=a[2] if len(a)>2 else None
if command=='view':
    code=0 if tag in s['releases'] else 1
elif command=='create':
    s['releases'][tag]={'tagName':tag,'isLatest':False,'isDraft':False,'isPrerelease':False};code=0
elif command=='upload':
    code=1 if s.get('upload_fail') else 0
elif command=='list':
    print(json.dumps(list(s['releases'].values())));code=0
elif command=='edit':
    for r in s['releases'].values():r['isLatest']=r['tagName']==tag
    code=0
else:raise AssertionError(a)
p.write_text(json.dumps(s));sys.exit(code)
''')
    gh.chmod(0o755)
    env = dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'],
               RELEASE_TEST_STATE=str(state), GITHUB_REPOSITORY='test/player', GITHUB_SHA='abc')

    def reset(latest='3.8.0.31'):
        state.write_text(json.dumps({'calls': [], 'releases': {
            latest: dict(tagName=latest, isLatest=True, isDraft=False, isPrerelease=False)}}))

    def run(*args, ok=True):
        result = subprocess.run(args, env=env, text=True, capture_output=True)
        assert (result.returncode == 0) == ok, result.stderr
        return json.loads(state.read_text())

    def latest(s):
        return [r['tagName'] for r in s['releases'].values() if r['isLatest']]

    # Same completion sequence on the reference and candidate scripts.
    reset()
    old = base / 'publish-reference.sh'
    old.write_bytes(subprocess.check_output(['git', 'show', '55bbc85:.github/scripts/publish.sh'], cwd=ROOT))
    for tag in ['3.8.0.33', '3.8.0.32']:
        before = run('bash', str(old), tag, 'manifest.json', '--', 'player.zip')
    assert latest(before) == ['3.8.0.32']  # reproduced regression

    reset()
    for tag in ['3.8.0.33', '3.8.0.32']:
        uploaded = run('bash', str(ROOT / '.github/scripts/publish.sh'), tag, 'manifest.json', '--', 'player.zip')
        if tag.endswith('33'):
            assert not any(c[1] == 'edit' for c in uploaded['calls'])
        after = run('python3', str(ROOT / '.github/scripts/promote-latest.py'), tag)
    assert latest(after) == ['3.8.0.33']
    uploads = [c for c in after['calls'] if c[1] == 'upload']
    assert [c[-1] for c in uploads] == ['manifest.json', 'player.zip'] * 2
    # Idempotent calls by the other platforms do not change latest.
    edits = len([c for c in after['calls'] if c[1] == 'edit'])
    after = run('python3', str(ROOT / '.github/scripts/promote-latest.py'), '3.8.0.33')
    assert len([c for c in after['calls'] if c[1] == 'edit']) == edits
    # A failed upload fails the build, leaving the dependent promotion job skipped.
    after['upload_fail'] = True; state.write_text(json.dumps(after))
    failed = run('bash', str(ROOT / '.github/scripts/publish.sh'), '3.8.0.34', '--', 'player.zip', ok=False)
    assert latest(failed) == ['3.8.0.33']
    run('python3', str(ROOT / '.github/scripts/promote-latest.py'), '3.8.0.99', ok=False)
    print(json.dumps({'passed': True, 'before_latest': latest(before), 'after_latest': latest(after),
                      'asset_order_preserved': True, 'duplicate_promotion_ignored': True,
                      'failed_upload_preserves_latest': True}, indent=2))
