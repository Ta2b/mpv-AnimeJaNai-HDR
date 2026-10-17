#!/usr/bin/env python3
"""Actual mpv hook, fake delayed read-only canonical CLI, HDR-only profile.
Proves first playback waits for profile activation; no engine, GPU or FPS trial.
"""
from pathlib import Path
import json,os,shutil,subprocess,sys
repo=Path(__file__).resolve().parents[2];out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
before=out/'before.lua';before.write_bytes(subprocess.check_output(['git','show','5ff6137878cc4f3616ee9740fb7495fc9a2c46f0:installer/macos/config/scripts/animejanai_mac.lua'],cwd=repo))
results={}
for label,controller,fail in [('before',before,False),('after',repo/'installer/macos/config/scripts/animejanai_mac.lua',False),('error',repo/'installer/macos/config/scripts/animejanai_mac.lua',True)]:
 root=out/label;conf=root/'portable_config';data=root/'animejanai';bundle=root/'bundle'
 for d in (conf/'hdr-tools',data,bundle,root/'cache'):d.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(repo/'BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config/hdr-tools/interpolation-stages.lua',conf/'hdr-tools/interpolation-stages.lua')
 source='[global]\nbackend=CoreMLNative\ndefault_slot=1\napple_auto_profile=no\n[slot_1]\nprofile_name=HDR\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=h\nchain_1_stage_1_kind=hdr\nchain_1_stage_1_method=mpv\nchain_1_stage_1_runtime=gpu-next\nchain_1_stage_1_policy=quality\n'
 (data/'animejanai.conf').write_text(source)
 helper=bundle/'AnimeJaNaiPlatform'
 helper.write_text('#!'+sys.executable+'\nimport json,sys,time\ntime.sleep(.3)\n'+('sys.exit(1)\n' if fail else 'args=sys.argv[1:]\nrule=int(args[args.index("--rule")+1])\nprint(json.dumps({"schema":"animejanai.profile-plan.v1","slot":1,"rule":rule,"issues":[],"plan":{"schema":"animejanai.profile-plan.v1","can_execute":True,"legacy_compatible":True},"profile_hdr":{"schema":"animejanai.profile-plan.v1","can_execute":True,"legacy_compatible":True}}))\n'))
 helper.chmod(0o755)
 result=root/'playback.json';observer=root/'observe.lua'
 observer.write_text("local mp=require'mp';local u=require'mp.utils';local first\nmp.register_event('playback-restart',function() if first==nil then first={slot=mp.get_property_native('user-data/animejanai-active-slot') or 0};local f=assert(io.open("+json.dumps(str(result)) +",'w'));f:write(u.format_json(first));f:close() end end)\n")
 env=dict(os.environ,ANIMEJANAI_BUNDLE=str(bundle),ANIMEJANAI_DATA_DIR=str(data),ANIMEJANAI_CACHE=str(root/'cache'))
 cmd=['mpv','--no-config','--load-scripts=no','--config-dir='+str(conf),'--vo=null','--ao=null','--hwdec=no','--untimed','--frames=3','--script='+str(controller),'--script='+str(observer),'av://lavfi:testsrc2=size=64x64:rate=24']
 p=subprocess.run(cmd,env=env,cwd=conf,text=True,capture_output=True,timeout=8);(root/'mpv.log').write_text(p.stdout+p.stderr)
 assert p.returncode==0 and result.exists() and 'Lua error:' not in p.stdout+p.stderr,(label,p.returncode,p.stdout+p.stderr)
 r=json.loads(result.read_text());assert (data/'animejanai.conf').read_text()==source
 if label=='before':assert r['slot']==0,'Baseline ambiguity: helper finished before first output; no conclusion'
 if label=='after':assert r['slot']==1,'Profile not applied before actual playback'
 if label=='error':assert r['slot']==0,'Resolver failure must release preload to normal playback'
 results[label]=r
receipt={'passed':True,'cases':results,'scope':'Actual Linux mpv Lua hooks with macOS controller and 300ms fake resolver; no engine/native GPU call, no FPS claim'}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
