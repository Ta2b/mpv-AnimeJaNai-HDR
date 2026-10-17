#!/usr/bin/env python3
"""Bounded native CoreML CPU transaction cases; reference pixels reused from AH240.
No timing/FPS benchmark. Each successful case is recorded immediately.
"""
from pathlib import Path
import hashlib,json,os,shutil,signal,subprocess,sys,time
probe,models,model,output=map(str,sys.argv[1:]);probe=str(Path(probe).resolve());out=Path(output).resolve();out.mkdir(exist_ok=True)
reference='18dfcc6c44d5a6abeeeb97c2c9e393c9126762ddc34e9da1e72fd806f8843f63'
env=dict(os.environ,AJI_COREML_NO_PLAN='1');evidence={'source':os.environ.get('GITHUB_SHA'),'scope':'Native CoreML CPU256 transaction protocol, no FPS/GPU/ANE claim','reference_reused':'AH240/.91 native output','cases':{}}
handles=[]
def record(name,details):
 evidence['cases'][name]=details;(out/'receipt.json').write_text(json.dumps(evidence,indent=2)+'\n')
def start(name,cache):
 log=(out/(name+'.log')).open('w');handles.append(log)
 return subprocess.Popen([probe,str(Path(models).resolve()),model,str(cache),str(out/(name+'.rgb'))],stdout=log,stderr=subprocess.STDOUT,env=env)
def finish(process,name,ok=True):
 code=process.wait(timeout=120);assert (code==0)==ok,(name,code,(out/(name+'.log')).read_text())
 if ok:assert hashlib.sha256((out/(name+'.rgb')).read_bytes()).hexdigest()==reference,name
 return (out/(name+'.log')).read_text()
def owned_stage(process,cache):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  matches=list(cache.glob('native/coreml-tx1/*/.stage-*/.aji-stage-owner'))
  if matches:return matches[0].parent
  assert process.poll() is None,'builder exited before an owned stage was observed'
  time.sleep(.005)
 raise AssertionError('owned stage not observed')
def entry(cache):
 pointers=list(cache.glob('native/coreml-tx1/*/current'));assert len(pointers)==1
 pointer=pointers[0];lines=pointer.read_text().splitlines();assert len(lines)==3
 return pointer,pointer.parent/lines[2]
try:
 cache=out/'concurrent-cache';cache.mkdir()
 # Old namespace is never a migration/deletion target.
 old=cache/'native/old-p3-entry';old.mkdir(parents=True);(old/'user-data').write_text('preserve')
 first=start('concurrent-1',cache);stage=owned_stage(first,cache)
 assert first.poll() is None
 second=start('concurrent-2',cache)
 assert first.poll() is None,'requests did not genuinely overlap; no dedup conclusion'
 log1=finish(first,'concurrent-1');log2=finish(second,'concurrent-2')
 assert (log1+log2).count('compiled cache miss:')==1
 pointer,generation=entry(cache);assert len(list(pointer.parent.glob('data-*')))==1
 assert (old/'user-data').read_text()=='preserve'
 record('concurrent_cold_and_hit',{'overlap':True,'native_compilations':1,'two_outputs_exact':True,'generation':generation.name,'old_namespace_preserved':True})
 # Genuine process death with a marked stage, not a simulated timeout.
 cache=out/'recovery-cache';cache.mkdir();victim=start('killed-builder',cache);stage=owned_stage(victim,cache)
 victim.kill();assert victim.wait(timeout=10)==-signal.SIGKILL
 assert stage.exists();keydir=stage.parent
 foreign=keydir/'.stage-user';foreign.mkdir();(foreign/'keep').write_text('user')
 other=keydir/'.stage-other-key';other.mkdir();(other/'.aji-stage-owner').write_text('aji-stage-owner-v1\np3-other\n')
 log=finish(start('recovery',cache),'recovery');assert log.count('compiled cache miss:')==1
 assert not stage.exists() and (foreign/'keep').read_text()=='user' and other.exists()
 pointer,generation=entry(cache)
 record('killed_builder_recovery',{'native_output_exact':True,'owned_orphan_removed':True,'unowned_and_other_key_preserved':True})
 # Corruption is injected in private fixture data; all retired files remain.
 compiled=generation/'model.mlmodelc'
 for p in compiled.iterdir():
  if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
  else:p.unlink()
 failed=finish(start('invalid-artifact',cache),'invalid-artifact',ok=False)
 assert 'invalid commit retired, data preserved' in failed
 assert not pointer.exists() and generation.exists() and compiled.exists()
 finish(start('repair',cache),'repair');_,repaired=entry(cache)
 assert repaired!=generation and generation.exists()
 record('invalid_artifact_repair',{'native_failure_detected':True,'old_generation_preserved':True,'new_generation':repaired.name,'new_output_exact':True})
 for p in sorted(cache.rglob('*'),key=lambda p:len(p.parts),reverse=True):p.chmod(0o555 if p.is_dir() else 0o444)
 cache.chmod(0o555)
 log=finish(start('readonly-hit',cache),'readonly-hit');assert 'compiled cache miss:' not in log
 assert entry(cache)[1]==repaired
 record('readonly_complete_hit',{'native_output_exact':True,'no_compilation':True,'same_generation':True})
 evidence['passed']=True
finally:
 (out/'receipt.json').write_text(json.dumps(evidence,indent=2)+'\n')
 for h in handles:h.close()
print(json.dumps(evidence,indent=2))
