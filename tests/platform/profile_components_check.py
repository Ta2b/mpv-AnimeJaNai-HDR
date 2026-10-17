#!/usr/bin/env python3
"""Short CPU check of actual shared CLI: exact components, off profile, stage policy."""
import json,subprocess,sys,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="aji-profile-components-") as temp:
 root=Path(temp);data=root/"animejanai";inf=data/"inference";models=data/"onnx";rife=data/"rife"
 for folder in (inf,models,rife):folder.mkdir(parents=True)
 for name in ("libaji_trt.so","libaji_pipeline.so","aji_pipeline.fatbin","aji_dml.dll"):(inf/name).touch()
 (rife/"rife_v4.26.onnx").touch()
 conf=data/"animejanai.conf"
 stage="[slot_1]\nchain_1_pipeline_version=1\nchain_1_stage_count=1\nchain_1_stage_1_id=r\nchain_1_stage_1_kind=interpolate\nchain_1_stage_1_method=rife\nchain_1_stage_1_runtime={runtime}\nchain_1_stage_1_model=426\nchain_1_stage_1_factor_numerator=4\nchain_1_stage_1_policy=quality\n"
 def put(backend="TensorRT",slot=1,runtime="tensorrt",extra=""):
  conf.write_text(f"[global]\n backend = {backend}\n default_slot = {slot}\n rife_engine = fast\n"+stage.format(runtime=runtime)+extra)
 def cli(mode,platform="linux"):
  return subprocess.check_output([sys.argv[1],sys.argv[2],mode,"--root",str(root),"--platform",platform,"--pipeline-features","15"],text=True)
 checks=[]
 put();output=cli("--profile-components");assert "trt-runtime:missing" in output and "rife:present" in output;checks.append("exact active runtime missing, exact RIFE present")
 put(extra="chain_1_stage_1_ensemble=yes\n");assert "rife:missing" in cli("--profile-components");checks.append("another RIFE file does not satisfy ensemble")
 put(slot=0);assert not cli("--profile-components").strip();checks.append("off profile downloads no inference packs")
 put(backend="DirectML",runtime="directml");result=json.loads(cli("--profile-plan","windows"));assert result["plan"]["legacy_compatible"] and result["plan"]["can_execute"];checks.append("Quality stage projects with historical global Fast on Windows")
 put(backend="OpenVINO",runtime="openvino");assert "onnxruntime:missing" in cli("--profile-components");checks.append("active OpenVINO identifies missing runtime pack")
 result={"passed":True,"checks":checks,"scope":"Actual shared CLI with simulated files/platforms; no GPU execution"}
 print(json.dumps(result,indent=2))
 if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+"\n")
