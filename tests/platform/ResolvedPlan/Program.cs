using AnimeJaNai.Platform;
using System.Text.Json;
using P=AnimeJaNai.Platform.InterpolationPipeline;
string root=Path.Combine(Path.GetTempPath(),"aji-resolved-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
var checks=new List<string>();void Check(string name,bool condition){if(!condition)throw new Exception(name);checks.Add(name);}
void Refused(string name,Action action){try{action();}catch(InvalidDataException){checks.Add(name);return;}throw new Exception(name);}
try {
    string models=Path.Combine(root,"onnx"),rife=Path.Combine(root,"rife"),inference=Path.Combine(root,"inference");
    foreach(var dir in new[]{models,rife,inference})Directory.CreateDirectory(dir);
    foreach(var name in new[]{"libnvinfer.so.11","libaji_trt.so","libaji_pipeline.so","aji_pipeline.fatbin","aji_dml.dll","libaji_ort.dylib"})File.WriteAllText(Path.Combine(inference,name),"");
    File.WriteAllText(Path.Combine(models,"SPAN.onnx"),"");File.WriteAllText(Path.Combine(rife,"rife_v4.26.onnx"),"");
    var context=new ProfileResolver.Context("linux","tensorrt",inference,models,rife,15,"quality");
    var legacy=new Dictionary<string,string>{{"chain_1_rife","yes"},{"chain_1_rife_model","426"},{"chain_1_rife_factor_numerator","4"},{"chain_1_model_1_name","SPAN"},{"chain_1_model_1_resize_height_before_upscale","720"}};
    var migrated=P.Read(legacy,1,"tensorrt","quality");
    Check("NVIDIA legacy migration keeps Spline36 before RIFE",string.Join(",",migrated.Stages.Select(s=>s.Method))=="spline36,rife,onnx");
    var projected=P.InferencePlan(migrated);Check("legacy projection preserves original resize and order",projected.Stages.Count==2&&projected.Stages[0].Method=="rife"&&projected.Stages[1].Options["resize_height_before_upscale"]=="720");
    var temporal=P.Read(legacy,1,"tensorrt","quality",_=>3);Check("detected temporal model preserves legacy RIFE-after",string.Join(",",temporal.Stages.Select(s=>s.Method))=="spline36,onnx,rife");
    var ort=P.Read(legacy,1,"openvino","quality");Check("non-CUDA legacy filter retains Bilinear name",ort.Stages[0].Method=="bilinear");
    Check("plan explains exact files without hardware claim",ProfileResolver.Resolve(migrated,context).CanExecute);
    var ensemble=migrated with{Stages=migrated.Stages.Select(s=>s.Method=="rife"?s with{Options=new Dictionary<string,string>{{"ensemble","yes"}}}:s).ToArray()};
    var missing=ProfileResolver.Resolve(ensemble,context);Check("ordinary RIFE file cannot hide missing exact ensemble",!missing.CanExecute&&missing.Stages.SelectMany(s=>s.Requirements).Any(r=>r.Identity=="rife_v4.26_ensemble.onnx"&&!r.Present));
    Refused("unknown temporal alias is refused, never Fast",()=>QualitySemantics.CanonicalTemporal("future-mode"));
    Refused("invalid RIFE threshold rejected by shared save validator",()=>P.Validate(new(false,[new("r","interpolate","rife","tensorrt",true,"426",new(2,1),"quality",new Dictionary<string,string>{{"scene_detect_threshold","NaN"}})])));
    var old=new P.Stage("old","interpolate","nvidia-fruc","cuda",true,"",new(2,1),"fast",new Dictionary<string,string>{{"sdk_library","preserve-me"}});
    Check("active FRUC refused explicitly",ProfileResolver.Resolve(new(false,[old]),context).Issues.Any(x=>x.Contains("FRUC has been removed")));
    Check("disabled imported FRUC preserved without dependency",ProfileResolver.Resolve(new(false,[old with{Enabled=false}]),context).CanExecute&&P.Write(new(false,[old with{Enabled=false}]),1)["chain_1_stage_1_sdk_library"]=="preserve-me");
    var area=new P.Stage("small","resize","area","cuda",true,"",new(1,1),"quality",new Dictionary<string,string>{{"target_height","720"}});
    var absent=ProfileResolver.Resolve(new(false,[area]),context with{PipelineFeatures=0});Check("missing feature gives structured installation action",absent.Stages[0].Requirements.Any(r=>r.Kind=="capability"&&!r.Present));
    var dml=new P.Stage("dml","interpolate","rife","directml",true,"426",new(2,1),"quality",new Dictionary<string,string>());
    Check("Windows DirectML simple projection remains available",ProfileResolver.Resolve(new(false,[dml]),context with{Platform="windows",Backend="directml"}).CanExecute);
    Check("Windows DirectML mixed CUDA graph refused",!ProfileResolver.Resolve(new(false,[area,dml]),context with{Platform="windows",Backend="directml"}).CanExecute);
    string ini="[global]\n backend = TensorRT\n default_slot = 2\n rife_engine = quality\n[slot_2]\n"+string.Join("\n",P.Write(ensemble,1).Select(k=>$" {k.Key} = {k.Value}"));
    Check("launcher handles whitespace and ordered-only profiles",ProfileResolver.ResolveConfiguration(ini,context).Requirements.Any(r=>r.Pack=="rife"&&!r.Present));
    string receipt=JsonSerializer.Serialize(new{passed=true,checks,scope="CPU exact model dependencies, preservation and migration contracts; simulated OS/library fixtures, no hardware qualification"},new JsonSerializerOptions{WriteIndented=true});
    if(args.Length>0){if(File.Exists(args[0]))throw new Exception("Existing conclusive receipt");Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0]))!);File.WriteAllText(args[0],receipt);}Console.WriteLine(receipt);
}finally {Directory.Delete(root,true);}
