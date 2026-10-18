using AnimeJaNai.Platform;
using P=AnimeJaNai.Platform.InterpolationPipeline;
void Check(bool ok,string what) { if(!ok)throw new Exception(what); }
void Invalid(Action action) {
    try {action();throw new Exception("Invalid configuration accepted");}
    catch(InvalidDataException){}
}
var legacy=new Dictionary<string,string> {
    ["chain_1_rife"]="yes",["chain_1_rife_model"]="426",["chain_1_rife_ensemble"]="yes",
    ["chain_1_rife_factor_numerator"]="5",["chain_1_rife_factor_denominator"]="2",
    ["chain_1_rife_scene_detect_threshold"]="0.173",["chain_1_model_1_name"]="SPAN-one",
    ["chain_1_model_1_resize_height_before_upscale"]="720",["chain_1_model_2_name"]="SPAN-two",
    ["chain_1_model_2_temporal_scene_threshold"]="0.125"
};
var before=P.Read(legacy,1,temporalPolicy:"old");
// The first model's attached resize is its own exact-size step, hoisted before RIFE-before as the old reader did.
Check(before.MigratedLegacy&&before.Stages.Select(x=>x.Id).SequenceEqual(new[]{"legacy-model-1-resize","legacy-rife","legacy-model-1","legacy-model-2"}),"Legacy RIFE-before order");
Check(before.Stages[1].Policy=="quality"&&before.Stages[1].Model=="426"&&before.Stages[1].Options["ensemble"]=="yes","Legacy RIFE policy/model/ensemble");
Check(before.Stages[1].Options["scene_detect_threshold"]=="0.173"&&before.Stages[0].Options["target_height"]=="720"&&before.Stages[0].Options.ContainsKey("legacy_geometry")&&!before.Stages[2].Options.ContainsKey("resize_height_before_upscale"),"Legacy numerical settings");
legacy["chain_1_rife_before_upscale"]="no";
var after=P.Read(legacy,1,temporalPolicy:"quality");
Check(after.Stages.Select(x=>x.Id).SequenceEqual(new[]{"legacy-model-1-resize","legacy-model-1","legacy-model-2","legacy-rife"}),"Legacy RIFE-after order");
Check(after.OutputCadence(new P.Rational(24000,1001))==new P.Rational(60000,1001),"Legacy 5/2 cadence");
var plan=new P.Plan(false,new[]{
    before.Stages[1] with {Factor=new P.Rational(2,1)},
    new P.Stage("fruc-second","interpolate","nvidia-fruc","cuda",true,"",new P.Rational(2,1),"fast",new Dictionary<string,string>{{"sdk_library","/path with spaces/libNvOFFRUC.so"},{"future_option","keep-this"}}),
    before.Stages[2],
    new P.Stage("wan-disabled","preparation","wan2_2_fun_inp","external",false,"model",new P.Rational(1,1),"quality",new Dictionary<string,string>{{"workflow","my-workflow"}})
});
var saved=P.Write(plan,7);var loaded=P.Read(saved,7);
Check(!loaded.MigratedLegacy&&loaded.IsFast&&loaded.OutputCadence(new P.Rational(24000,1001))==new P.Rational(96000,1001),"RIFE2-FRUC2 cadence/policy");
Check(loaded.Stages.Select(x=>x.Id).SequenceEqual(plan.Stages.Select(x=>x.Id)),"Stable identity/order");
Check(loaded.Stages[1].Options["sdk_library"]=="/path with spaces/libNvOFFRUC.so"&&loaded.Stages[1].Options["future_option"]=="keep-this","External paths and extensions preserved");
Check(loaded.Stages[3].Method=="wan2_2_fun_inp"&&!loaded.Stages[3].Enabled,"Disabled unavailable workflow retained");
Check(P.Write(loaded,7).OrderBy(x=>x.Key).SequenceEqual(saved.OrderBy(x=>x.Key)),"Stable second save");
var unknown=saved.ToDictionary(x=>x.Key,x=>x.Value);unknown["chain_7_pipeline_version"]="2";
Invalid(()=>P.Read(unknown,7));unknown.Remove("chain_7_pipeline_version");Invalid(()=>P.Read(unknown,7));
Invalid(()=>P.Validate(plan with {Stages=new[]{plan.Stages[0],plan.Stages[0]}}));
Invalid(()=>new P.Rational(1,0));Invalid(()=>default(P.Rational).Multiply(new P.Rational(1,1)));
Console.WriteLine("PASS: legacy before/after, 5/2 and 2x2 exact cadence, stable ordered identity/options, disabled workflow and invalid-version guards. No GPU/video execution.");
