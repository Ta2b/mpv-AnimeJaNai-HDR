using AnimeJaNaiConfEditor.ViewModels;
using ReactiveUI.Builder;
using System.Text.Json;

// UI metadata fixture, not a fake native-provider qualification.
string data=Path.GetFullPath(args[0]);Directory.CreateDirectory(Path.Combine(data,"onnx"));
Directory.CreateDirectory(Path.Combine(data,"inference"));
Environment.SetEnvironmentVariable("ANIMEJANAI_DATA_DIR",data);
Environment.SetEnvironmentVariable("ANIMEJANAI_INFERENCE_DIR",Path.Combine(data,"inference"));
foreach(var file in new[]{"libaji_ort.so","libaji_vulkan.so","libnvinfer.so.11"})
    File.WriteAllText(Path.Combine(data,"inference",file),"presence-only fixture");
File.WriteAllText(Path.Combine(data,"animejanai.conf"),"[global]\nconfig_version=3\nbackend=OpenVINO\ndefault_slot=0\n");
RxAppBuilder.CreateReactiveUIBuilder().WithCoreServices().BuildApp();
MainWindowViewModel.Platform=MainWindowViewModel.Os.Linux;
var vm=new MainWindowViewModel();
vm.AnimeJaNaiConf.UserSelectOpenVino();string openvino=vm.BackendNotice;
vm.AnimeJaNaiConf.UserSelectVulkan();string vulkan=vm.BackendNotice;
vm.AnimeJaNaiConf.UserSelectTensorRt();string tensorrt=vm.BackendNotice;
var display=typeof(MainWindowViewModel).GetProperty("VulkanPresentationNotice")?.GetValue(vm);
Console.WriteLine(JsonSerializer.Serialize(new{openvino,ncnn_vulkan=vulkan,tensorrt,vulkan_display=display,
    native_provider_qualification=false}));
