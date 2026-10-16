using AnimeJaNaiConfEditor.ViewModels;
using ReactiveUI.Builder;
using System.Text.Json;

string root = Path.GetFullPath(args[0]); string data = Path.Combine(root, "settings");
Directory.CreateDirectory(data); Directory.CreateDirectory(Path.Combine(data,"onnx"));
Environment.SetEnvironmentVariable("ANIMEJANAI_ROOT",root);
Environment.SetEnvironmentVariable("ANIMEJANAI_DATA_DIR",data); // Not ROOT/animejanai: no player notification.
string Template(string mode) => "[global]\nconfig_version=3\nbackend=TensorRT\ndefault_slot=1\nrife_engine="+mode
    +"\nrife_drawings=yes\nquality_preset=sharp\ntrt_engine_settings=--stronglyTyped\n[slot_1]\nprofile_name=Quality custom spatial\nchain_1_model_1_name=2x_fixture_fp16\nchain_1_rife=yes\nchain_1_rife_model=426\nchain_1_rife_factor_numerator=5\nchain_1_rife_factor_denominator=2\nchain_1_rife_ensemble=yes\nchain_1_rife_before_upscale=yes\nchain_1_rife_scene_detect_threshold=0.150\n";
File.WriteAllText(Path.Combine(data,"animejanai.conf"),Template("old"));
RxAppBuilder.CreateReactiveUIBuilder().WithCoreServices().BuildApp();
MainWindowViewModel.Platform=MainWindowViewModel.Os.Linux;
var vm = new MainWindowViewModel();
var results = new List<object>();
foreach (string alias in new[] {"old","quality","new","fast"})
{
    string input=Path.Combine(root,alias+"-input.conf");File.WriteAllText(input,Template(alias));
    vm.AnimeJaNaiConf=vm.ReadAnimeJaNaiConf(input);
    string output=Path.Combine(root,alias+"-saved.conf");vm.WriteAnimeJaNaiConf(output);
    results.Add(new { alias, canonical=vm.AnimeJaNaiConf.RifeEngine,
        quality_checked=vm.AnimeJaNaiConf.RifeEngineQuality, fast_checked=vm.AnimeJaNaiConf.RifeEngineFast,
        drawings=vm.AnimeJaNaiConf.RifeDrawings, spatial_sharp=vm.AnimeJaNaiConf.QualitySharp, output });
}
// Same property setters as the real toggle bindings, followed by the production save method.
vm.AnimeJaNaiConf.RifeEngineQuality=true;vm.WriteAnimeJaNaiConf(Path.Combine(root,"toggle-quality.conf"));
vm.AnimeJaNaiConf.RifeEngineFast=true;vm.WriteAnimeJaNaiConf(Path.Combine(root,"toggle-fast.conf"));
var notices=new Dictionary<string,string?>();
foreach(string name in new[]{"SpatialQualityNotice","TemporalQualityNotice","GlobalFidelityNotice","RetimingNotice","EnsemblePrecisionNotice"})
    notices[name]=typeof(MainWindowViewModel).GetProperty(name)?.GetValue(vm)?.ToString();
Console.WriteLine(JsonSerializer.Serialize(new { results, notices, native_inference_repeated=false }));
