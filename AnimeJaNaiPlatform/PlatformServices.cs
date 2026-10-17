using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AnimeJaNai.Platform;

// Shared by the player CLI and the Manager through its pinned PlatformSource.
// Describes implemented paths, never a claim that a particular GPU was tested.
public static class QualitySemantics
{
    public const string Spatial = "Spatial preset Quality selects an upscaling model/chain. It does not select temporal RIFE policy or lock the entire playback chain.";
    public const string Temporal = "Full RIFE (Quality): a complete RIFE prediction per intermediate frame, with the configured upscale and cut rules. Fast: supported motion/source reuse and approximate shortcuts can change contours or motion. Both retain execution optimizations; availability depends on the backend.";
    public const string GlobalLock = "Global fidelity lock is not available yet. Temporal Quality alone does not freeze model selection, resolution, final scaler, interpolation factor, HDR or external frame generation.";
    public const string Retiming = "Held-drawing retiming spreads motion over the duration of a held drawing. It changes the chosen temporal rendering, is separate from ensemble, and is ignored by temporal Quality. Restart playback after changing it.";
    public const string EnsemblePrecision = "Ensemble selects a different RIFE model when supported; it is independent of temporal Quality/Fast. FP16 model weights do not establish operator or accumulator precision, nor equal output between backends. Temporal Quality does not change the model's precision policy.";
    public static string CanonicalTemporal(string? value) =>
        (value ?? "").Trim().ToLowerInvariant() switch {
            "old" or "quality" => "quality", "new" or "fast" => "fast",
            var unknown => throw new InvalidDataException("Unknown RIFE policy preserved: " + unknown)
        };
}

public static class BackendCapabilities
{
    public const string OpenVino = "Experimental OpenVINO / ONNX Runtime inference for Intel GPUs: spatial ONNX upscaling and the shared ONNX RIFE path. Requires a compatible OpenVINO provider, supported operators and ONNX RIFE models; SDR sources. Provider availability is checked during playback.";
    public const string NcnnVulkan = "NCNN / Vulkan inference on Linux: SPAN AnimeJaNai and RIFE 4.6 models. SDR sources, even dimensions; CPU/GPU transfers. Select the mpv display API separately.";
    public const string TensorRt = "TensorRT / CUDA inference on NVIDIA. Uses ONNX RIFE models. The mpv display API is a separate setting.";
    public const string VulkanPresentation = "Vulkan display API: mpv presents the finished pictures. These RTX Video controls apply to NVIDIA inference with Vulkan display; HDR contrast, saturation and middle grey are shared with the mpv conversion.";
    public static object Describe() => new {
        schema = "animejanai.capabilities.v1",
        source = "AnimeJaNaiPlatform/PlatformServices.cs:BackendCapabilities",
        openvino = OpenVino, ncnn_vulkan = NcnnVulkan, tensorrt = TensorRt,
        vulkan_presentation = VulkanPresentation,
        quality_semantics = new { spatial = QualitySemantics.Spatial, temporal = QualitySemantics.Temporal,
            global_lock = QualitySemantics.GlobalLock, retiming = QualitySemantics.Retiming,
            ensemble_precision = QualitySemantics.EnsemblePrecision, aliases = new { old = "quality", @new = "fast" } },
        qualification = "Implemented paths; library/provider/model availability and native hardware qualification are separate evidence."
    };
}

// Read-only, on-demand comparison. A package declaration is not runtime loading.
public static class PackageProvenance
{
    public static object Capture(string root, string? releaseManifest = null)
    {
        var errors = new List<string>();
        JsonElement? ReadJson(string path)
        {
            if (!File.Exists(path)) return null;
            try { using var doc = JsonDocument.Parse(File.ReadAllText(path)); return doc.RootElement.Clone(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException)
            { errors.Add($"{path}: {e.Message}"); return null; }
        }
        string? ReadText(string path)
        {
            if (!File.Exists(path)) return null;
            try { return File.ReadAllText(path).Trim(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            { errors.Add($"{path}: {e.Message}"); return null; }
        }
        var libraries = new List<object>();
        foreach (string directory in new[] { Path.Combine(root,"animejanai","inference"), Path.Combine(root,"inference") }.Distinct())
        {
            JsonElement? metadata = ReadJson(Path.Combine(directory,"GPU-SOURCE.json"));
            JsonElement hashes = default;
            if (metadata is { ValueKind: JsonValueKind.Object } m) m.TryGetProperty("sha256",out hashes);
            var names = new HashSet<string>(new[] { "libaji.so","libaji_trt.so","libaji_trt_rtx.so","libaji_ort.so","libaji_vulkan.so","libaji_migraphx_rgb.so",
                "aji.dll","aji_trt.dll","aji_trt_rtx.dll","aji_dml.dll","aji_migraphx.dll" },StringComparer.Ordinal);
            if (hashes.ValueKind == JsonValueKind.Object)
                foreach (var entry in hashes.EnumerateObject())
                    if (Path.GetFileName(entry.Name)==entry.Name) names.Add(entry.Name);
            foreach (string name in names.Order(StringComparer.Ordinal))
            {
                string path=Path.Combine(directory,name);
                if (!File.Exists(path)) continue;
                try {
                    using var file=File.OpenRead(path);
                    string actual=Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
                    string? expected=hashes.ValueKind==JsonValueKind.Object && hashes.TryGetProperty(name,out var h) && h.ValueKind==JsonValueKind.String ? h.GetString() : null;
                    bool? matches=expected is null ? null : string.Equals(actual,expected,StringComparison.OrdinalIgnoreCase);
                    libraries.Add(new { path, actual_sha256=actual, declared_sha256=expected,
                        matches_compiled_metadata=matches, compiled_library_metadata=metadata });
                } catch(Exception e) when(e is IOException or UnauthorizedAccessException)
                { errors.Add($"{path}: {e.Message}"); }
            }
        }
        var assembly=System.Reflection.Assembly.GetEntryAssembly();
        var info=assembly?.GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute),false)
            .OfType<System.Reflection.AssemblyInformationalVersionAttribute>().FirstOrDefault()?.InformationalVersion;
        return new {
            schema="animejanai.versions.v1",
            compiled_tool=new { assembly_version=assembly?.GetName().Version?.ToString(), informational_version=info },
            installed_package=new { root=Path.GetFullPath(root), version=ReadText(Path.Combine(root,"version.txt")), manifest=ReadJson(Path.Combine(root,"manifest.json")) },
            delivered_manifest=releaseManifest is null ? null : ReadJson(Path.GetFullPath(releaseManifest)),
            installed_libraries=libraries, errors,
            limitations=new[] { "Actual hashes describe files on disk, not libraries or models already loaded in a running process.",
                "Compiled source/build information is a separate declaration; a missing or mismatched hash does not identify the installed source revision.",
                "An explicitly supplied release manifest describes delivery; it is not inferred from the installed version or compile/link success." }
        };
    }
}

public static class PlatformServices
{
    public record Adapter(string vendor, string name, string pci, bool discrete);
    public record Hardware(string vendor, string name, string pci, string? vulkan_device,
        string platform, Adapter[] adapters, string[]? display_pci = null);
    public record BankState(string vendor, string hash, string? bank = null);

    public static Adapter[] LinuxAdapters(string sysfs = "/sys/bus/pci/devices")
    {
        var result = new List<Adapter>();
        foreach (var dir in Directory.GetDirectories(sysfs).Order())
        {
            string Read(string file) => File.Exists(Path.Combine(dir, file))
                ? File.ReadAllText(Path.Combine(dir, file)).Trim() : "";
            if (!Read("class").StartsWith("0x03")) continue;
            string vendor = Read("vendor") switch
            { "0x10de" => "nvidia", "0x1002" => "amd", "0x8086" => "intel", _ => "unknown" };
            string pci = Path.GetFileName(dir);
            string label = vendor switch { "amd" => "AMD Radeon", "nvidia" => "NVIDIA", "intel" => "Intel", _ => "GPU" };
            // Prefer the dedicated NVIDIA/AMD adapter on the initial Intel hybrid targets.
            bool discrete = vendor is "nvidia" or "amd";
            result.Add(new(vendor, $"{label} ({Read("device")}, PCI {pci})", pci, discrete));
        }
        return result.ToArray();
    }

    public static string[] DisplayAdapters(string drm = "/sys/class/drm") => !Directory.Exists(drm) ? [] :
        Directory.GetDirectories(drm).Where(d => File.Exists(Path.Combine(d, "status")) &&
            File.ReadAllText(Path.Combine(d, "status")).Trim() == "connected" &&
            (!File.Exists(Path.Combine(d, "enabled")) || File.ReadAllText(Path.Combine(d, "enabled")).Trim() == "enabled"))
        .Select(d => Directory.ResolveLinkTarget(d, true)?.FullName ?? "")
        .Select(d => Regex.Matches(d, @"\d{4}:\d{2}:\d{2}\.\d").LastOrDefault()?.Value)
        .OfType<string>().Distinct().ToArray();

    public static Adapter SelectAdapter(IEnumerable<Adapter> adapters, string requested = "auto") =>
        adapters.Where(a => requested == "auto" || a.vendor == requested)
            .OrderByDescending(a => (a.discrete ? 100 : 0) + (a.vendor == "nvidia" ? 1 : 0))
            .FirstOrDefault() ?? new("unknown", "GPU unavailable", "", false);

    public static Hardware Probe(string root, string requested = "auto")
    {
        if (OperatingSystem.IsWindows())
        {
            string json = Run("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                Path.Combine(root, "portable_config", "hdr-tools", "detect-gpu.ps1"));
            using var doc = JsonDocument.Parse(json);
            var list = doc.RootElement.EnumerateArray().Select(a =>
            {
                string name = a.GetProperty("Name").GetString() ?? "GPU";
                string id = a.GetProperty("PNPDeviceID").GetString() ?? "";
                string vendor = id.Contains("VEN_10DE") ? "nvidia" : id.Contains("VEN_1002") ? "amd" : id.Contains("VEN_8086") ? "intel" : "unknown";
                return new Adapter(vendor, name, id, Regex.IsMatch(name, "GeForce|Radeon RX|Arc|Quadro", RegexOptions.IgnoreCase));
            }).ToArray();
            var chosen = SelectAdapter(list, requested);
            return new(chosen.vendor, chosen.name, chosen.pci, null, "windows", list);
        }
        var adapters = LinuxAdapters();
        var selected = SelectAdapter(adapters, requested);
        string player = Environment.GetEnvironmentVariable("ANIMEJANAI_MPV") ?? Path.Combine(root, "mpv", "mpv");
        string? device = null;
        if (File.Exists(player))
        {
            string output = Run(player, "--no-config", "--vulkan-device=help");
            var names = Regex.Matches(output, "(?m)^\\s*'([^']+)'").Select(m => m.Groups[1].Value);
            device = names.FirstOrDefault(n => selected.vendor switch
            {
                "nvidia" => n.Contains("NVIDIA", StringComparison.OrdinalIgnoreCase),
                "amd" => Regex.IsMatch(n, "AMD|Radeon", RegexOptions.IgnoreCase),
                "intel" => n.Contains("Intel", StringComparison.OrdinalIgnoreCase), _ => false
            });
        }
        return new(selected.vendor, device ?? selected.name, selected.pci, device, "linux", adapters, DisplayAdapters());
    }

    static string Run(string command, params string[] args)
    {
        var si = new ProcessStartInfo(command) { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        foreach (var arg in args) si.ArgumentList.Add(arg);
        try
        {
            using var p = Process.Start(si)!;
            var stdout = p.StandardOutput.ReadToEndAsync();
            var stderr = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(15000)) { p.Kill(true); return ""; }
            return stdout.GetAwaiter().GetResult() + stderr.GetAwaiter().GetResult();
        }
        catch (System.ComponentModel.Win32Exception) { return ""; }
    }

    public static object ActivateBank(string root, string bank)
    {
        string[] allowed = ["nvidia", "amd", "linux-nvidia", "linux-amd"];
        if (!allowed.Contains(bank)) throw new ArgumentException("Unknown profile bank");
        string profiles = Path.Combine(root, "portable_config", "profiles");
        Directory.CreateDirectory(profiles);
        string selected = Path.Combine(profiles, bank, "animejanai.conf");
        string active = Path.Combine(root, "animejanai", "animejanai.conf");
        string statePath = Path.Combine(profiles, "active-bank.json");
        using var guard = Lock(Path.Combine(profiles, ".bank.lock"));
        if (!File.Exists(selected)) throw new FileNotFoundException("Missing profile bank", selected);
        var state = File.Exists(statePath) ? JsonSerializer.Deserialize<BankState>(File.ReadAllText(statePath)) : null;
        string? oldBank = state?.bank ?? state?.vendor;
        if (state is not null && (!allowed.Contains(oldBank) || string.IsNullOrEmpty(state.hash)))
            throw new InvalidDataException("Invalid profile bank state");
        string? Hash(string p) => File.Exists(p) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))) : null;
        string? activeHash = Hash(active);
        // Preserve a pre-bank installation verbatim before its first explicit selection.
        if (state is null && activeHash is not null && activeHash != Hash(selected))
            AtomicWrite(Path.Combine(profiles, "untracked-" + activeHash + ".conf"), File.ReadAllBytes(active));
        if (state is not null && activeHash is not null && !string.Equals(activeHash, state.hash, StringComparison.OrdinalIgnoreCase))
        {
            string previous = Path.Combine(profiles, oldBank!, "animejanai.conf");
            string? previousHash = Hash(previous);
            if (!string.Equals(previousHash, state.hash, StringComparison.OrdinalIgnoreCase) && previousHash != activeHash)
                throw new IOException($"Conflicting edits: {active} and {previous}. Both files were preserved.");
            if (previousHash != activeHash) AtomicWrite(previous, File.ReadAllBytes(active));
        }
        string hash = Hash(selected)!;
        if (activeHash != hash) AtomicWrite(active, File.ReadAllBytes(selected));
        string vendor = bank.EndsWith("nvidia") ? "nvidia" : "amd";
        AtomicWrite(statePath, JsonSerializer.SerializeToUtf8Bytes(new BankState(vendor, hash, bank)));
        return new { conf = active, bank = selected, vendor };
    }

    public static string CurrentBank(string root)
    {
        var path = Path.Combine(root, "portable_config", "profiles", "active-bank.json");
        var state = File.Exists(path) ? JsonSerializer.Deserialize<BankState>(File.ReadAllText(path)) : null;
        return state?.bank ?? state?.vendor ?? "";
    }

    public static string FileHash(string path) => File.Exists(path)
        ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))) : "";

    // The Manager uses the same transaction and lock as bank activation.
    public static void SaveActiveConfig(string root, string expectedHash, byte[] content, string? expectedBank = null)
    {
        string active = Path.Combine(root, "animejanai", "animejanai.conf");
        string profiles = Path.Combine(root, "portable_config", "profiles");
        Directory.CreateDirectory(profiles);
        using var guard = Lock(Path.Combine(profiles, ".bank.lock"));
        if (!string.Equals(FileHash(active), expectedHash, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Profile changed since the Manager opened it. Reload before saving; files were preserved.");
        var statePath = Path.Combine(profiles, "active-bank.json");
        var state = File.Exists(statePath) ? JsonSerializer.Deserialize<BankState>(File.ReadAllText(statePath)) : null;
        string? bank = state?.bank ?? state?.vendor;
        if (expectedBank is not null && (bank ?? "") != expectedBank)
            throw new IOException("Active profile bank changed. Reopen the Manager before saving; files were preserved.");
        string? bankPath = bank is null ? null : Path.Combine(profiles, bank, "animejanai.conf");
        if (bank is not null && !new[] {"nvidia", "amd", "linux-nvidia", "linux-amd"}.Contains(bank))
            throw new IOException("Invalid profile bank state");
        if (bankPath is not null && !string.Equals(FileHash(bankPath), state!.hash, StringComparison.OrdinalIgnoreCase) && FileHash(bankPath) != expectedHash)
            throw new IOException("Profile bank changed concurrently. Files were preserved.");
        // Recoverable if interrupted: activation reconciles content hashes on next start.
        AtomicWrite(active, content);
        if (bankPath is not null)
        {
            AtomicWrite(bankPath, content);
            AtomicWrite(statePath, JsonSerializer.SerializeToUtf8Bytes(state! with {bank = bank, hash = FileHash(active)}));
        }
    }

    static FileStream Lock(string path)
    {
        var timer = Stopwatch.StartNew();
        while (true)
        {
            try { return new(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException) when (timer.Elapsed < TimeSpan.FromSeconds(10)) { Thread.Sleep(50); }
        }
    }

    static void AtomicWrite(string path, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string tmp = path + ".tmp-" + Guid.NewGuid().ToString("N");
        try { File.WriteAllBytes(tmp, bytes); File.Move(tmp, path, true); }
        finally { if (File.Exists(tmp)) File.Delete(tmp); }
    }
}

// Ordered data contract shared with the Manager. Execution availability is
// checked separately by the selected runtime; reading a method never claims it
// is installed. An explicit pipeline is authoritative, never silently flattened
// back into the historical single-RIFE settings.
public static class InterpolationPipeline
{
    public const int Version = 1;
    public const int MaxStages = 16;
    public readonly record struct Rational
    {
        public long Numerator { get; }
        public long Denominator { get; }
        public Rational(long numerator, long denominator)
        {
            if (numerator <= 0 || denominator <= 0) throw new InvalidDataException("Cadence/factors must be positive fractions");
            long a=numerator,b=denominator;
            while(b!=0) { long r=a%b; a=b; b=r; }
            Numerator=numerator/a; Denominator=denominator/a;
        }
        public Rational Multiply(Rational other)
        {
            if(Numerator<=0||Denominator<=0||other.Numerator<=0||other.Denominator<=0)
                throw new InvalidDataException("Invalid cadence fraction");
            var n=(System.Numerics.BigInteger)Numerator*other.Numerator;
            var d=(System.Numerics.BigInteger)Denominator*other.Denominator;
            var gcd=System.Numerics.BigInteger.GreatestCommonDivisor(n,d);n/=gcd;d/=gcd;
            if(n>long.MaxValue || d>long.MaxValue)throw new InvalidDataException("Cumulative cadence exceeds the rational timestamp range");
            return new Rational((long)n,(long)d);
        }
        public override string ToString() => $"{Numerator}/{Denominator}";
    }
    public sealed record Stage(string Id,string Kind,string Method,string Runtime,bool Enabled,
        string Model,Rational Factor,string Policy,IReadOnlyDictionary<string,string> Options);
    public sealed record Plan(bool MigratedLegacy,IReadOnlyList<Stage> Stages)
    {
        public Rational OutputCadence(Rational source) => Stages.Where(s=>s.Enabled&&s.Kind=="interpolate")
            .Aggregate(source,(f,s)=>f.Multiply(s.Factor));
        public bool IsFast => Stages.Any(s=>s.Enabled&&s.Kind=="interpolate"&&s.Policy=="fast");
    }
    private static readonly HashSet<string> Fields = new(StringComparer.OrdinalIgnoreCase) {
        "id","kind","method","runtime","enabled","model","factor_numerator","factor_denominator","policy"
    };
    private static string Key(int chain) => chain>0 ? $"chain_{chain}_" : throw new InvalidDataException("Chain number must be positive");
    private static string Value(IReadOnlyDictionary<string,string> values,string key,string fallback="") =>
        values.TryGetValue(key,out var v) ? v.Trim() : fallback;
    private static long Integer(string value,string key)
    {
        if(!long.TryParse(value,System.Globalization.NumberStyles.None,System.Globalization.CultureInfo.InvariantCulture,out long n))
            throw new InvalidDataException($"Invalid integer: {key}");
        return n;
    }
    private static bool Yes(string value,string key)
    {
        return value.ToLowerInvariant() switch { "yes" => true,"no" => false,_=>throw new InvalidDataException($"Expected yes/no: {key}") };
    }
    public static Plan Read(IReadOnlyDictionary<string,string> section,int chain,string backend="tensorrt",string temporalPolicy="fast",Func<string,int>? modelFrames=null,string? platform=null)
    {
        var values=new Dictionary<string,string>(StringComparer.Ordinal);
        foreach(var kv in section)values[kv.Key.ToLowerInvariant()]=kv.Value;
        string prefix=Key(chain),version=Value(values,prefix+"pipeline_version");
        if(version.Length==0)
        {
            if(values.Keys.Any(k=>k.StartsWith(prefix+"stage_",StringComparison.Ordinal)))
                throw new InvalidDataException("Stage keys require an explicit pipeline_version");
            return Migrate(values,chain,backend,temporalPolicy,modelFrames,platform);
        }
        if(Integer(version,"pipeline_version")!=Version)throw new InvalidDataException("Unsupported interpolation pipeline version; preserve the original profile");
        long count=Integer(Value(values,prefix+"stage_count"),"stage_count");
        if(count<0||count>MaxStages)throw new InvalidDataException($"Pipeline supports at most {MaxStages} ordered stages");
        var stages=new List<Stage>();
        for(int i=1;i<=count;i++)
        {
            string p=$"{prefix}stage_{i}_";
            var options=values.Where(k=>k.Key.StartsWith(p,StringComparison.Ordinal)&&!Fields.Contains(k.Key[p.Length..]))
                .ToDictionary(k=>k.Key[p.Length..],k=>k.Value,StringComparer.Ordinal);
            stages.Add(new Stage(Value(values,p+"id"),Value(values,p+"kind").ToLowerInvariant(),
                Value(values,p+"method").ToLowerInvariant(),Value(values,p+"runtime").ToLowerInvariant(),
                Yes(Value(values,p+"enabled","yes"),p+"enabled"),Value(values,p+"model"),
                new Rational(Integer(Value(values,p+"factor_numerator","1"),p+"factor_numerator"),
                    Integer(Value(values,p+"factor_denominator","1"),p+"factor_denominator")),
                Value(values,p+"policy","quality").ToLowerInvariant(),options));
        }
        var plan=Normalize(new Plan(false,stages),platform);Validate(plan);return plan;
    }
    private static Plan Migrate(IReadOnlyDictionary<string,string> values,int chain,string backend,string policy,Func<string,int>? modelFrames,string? platform)
    {
        string prefix=Key(chain);var stages=new List<Stage>();
        string modelPrefix=prefix+"model_";
        var indices=values.Keys.Select(k=>Regex.Match(k,"^"+Regex.Escape(modelPrefix)+@"([1-9][0-9]*)_name$"))
            .Where(m=>m.Success).Select(m=>int.Parse(m.Groups[1].Value,System.Globalization.CultureInfo.InvariantCulture)).Order().ToArray();
        foreach(int i in indices)
        {
            string p=$"{modelPrefix}{i}_",name=Value(values,p+"name");if(name.Length==0)continue;
            var options=values.Where(k=>k.Key.StartsWith(p,StringComparison.Ordinal)&&k.Key!=p+"name")
                .ToDictionary(k=>k.Key[p.Length..],k=>k.Value,StringComparer.Ordinal);
            if(modelFrames!=null&&Value(options,"frames","0")=="0") {int frames=modelFrames(name);if(frames>1)options["frames"]=frames.ToString(System.Globalization.CultureInfo.InvariantCulture);}
            stages.Add(new Stage($"legacy-model-{i}","upscale","onnx",backend.ToLowerInvariant(),true,name,new Rational(1,1),"quality",options));
        }
        if(Yes(Value(values,prefix+"rife","no"),prefix+"rife"))
        {
            var options=new Dictionary<string,string>(StringComparer.Ordinal) {
                ["ensemble"]=Value(values,prefix+"rife_ensemble","no"),
                ["scene_detect_threshold"]=Value(values,prefix+"rife_scene_detect_threshold","0.150")
            };
            var rife=new Stage("legacy-rife","interpolate","rife",backend.ToLowerInvariant(),true,
                Value(values,prefix+"rife_model","414"),
                new Rational(Integer(Value(values,prefix+"rife_factor_numerator","1"),prefix+"rife_factor_numerator"),
                    Integer(Value(values,prefix+"rife_factor_denominator","1"),prefix+"rife_factor_denominator")),
                QualitySemantics.CanonicalTemporal(policy),options);
            if(Yes(Value(values,prefix+"rife_before_upscale","yes"),prefix+"rife_before_upscale"))stages.Insert(0,rife);
            else stages.Add(rife);
        }
        var plan=Normalize(new Plan(true,stages),platform);Validate(plan);return plan;
    }
    // Split the old attached resize without changing its filter or position.
    // The old NVIDIA reader hoists the FIRST model's Spline36 resize before
    // RIFE-before, except for temporal models (which force RIFE-after).
    public static string HistoricalResizeMethod(string runtime,string? platform=null) =>
        runtime is "tensorrt" or "directml" || runtime=="migraphx"&&(platform??(OperatingSystem.IsWindows()?"windows":"linux"))=="windows" ? "spline36" : "bilinear";
    public static Plan Normalize(Plan plan,string? platform=null)
    {
        var stages=plan.Stages.ToList();
        int firstModel=stages.FindIndex(s=>s.Kind=="upscale");
        int rife=stages.FindIndex(s=>s.Kind=="interpolate"&&s.Method=="rife");
        bool temporal=stages.Any(s=>s.Kind=="upscale"&&
            Value(s.Options,"frames","0") is not ("0" or "1"));
        if(plan.MigratedLegacy&&temporal&&rife>=0&&rife<firstModel)
        {
            var stage=stages[rife];stages.RemoveAt(rife);stages.Add(stage);
            firstModel=stages.FindIndex(s=>s.Kind=="upscale");rife=stages.Count-1;
        }
        var output=new List<Stage>();
        for(int i=0;i<stages.Count;i++)
        {
            var stage=stages[i];
            if(stage.Kind!="upscale"||stage.Method!="onnx") {output.Add(stage);continue;}
            var options=new Dictionary<string,string>(stage.Options);
            string height=Value(options,"resize_height_before_upscale","0"),percent=Value(options,"resize_factor_before_upscale","100");
            bool validHeight=double.TryParse(height,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out double hv)&&double.IsFinite(hv);
            bool validPercent=double.TryParse(percent,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out double pv)&&double.IsFinite(pv);
            if(!validHeight||!validPercent)throw new InvalidDataException("Invalid legacy resize settings; original profile preserved.");
            if(hv>0||pv!=100)
            {
                string id=stage.Id.Length<=57?stage.Id+"-resize":"resize-"+Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(stage.Id))).ToLowerInvariant()[..32];
                string origin=(platform??(OperatingSystem.IsWindows()?"windows":OperatingSystem.IsMacOS()?"macos":"linux"))+":"+stage.Runtime;
                var size=new Dictionary<string,string>{{hv>0?"target_height":"target_percent",hv>0?height:percent},{"legacy_geometry",origin}};
                var resize=new Stage(id,"resize",HistoricalResizeMethod(stage.Runtime,platform),stage.Runtime,stage.Enabled,"",new(1,1),"quality",size);
                if(plan.MigratedLegacy&&i==firstModel&&rife>=0&&rife<i&&!temporal)
                    output.Insert(output.FindIndex(s=>s.Id==stages[rife].Id),resize);
                else output.Add(resize);
            }
            options.Remove("resize_height_before_upscale");options.Remove("resize_factor_before_upscale");
            output.Add(stage with {Options=options});
        }
        return plan with {Stages=output};
    }
    // Lossless legacy projection, only where the native reader places resize
    // exactly here. Other ordered graphs retain independent resize steps.
    public static Plan InferencePlan(Plan plan)
    {
        Validate(plan);
        var active=plan.Stages.Where(s=>s.Enabled&&!(s.Kind=="hdr"&&
            (s.Method=="mpv"&&s.Runtime=="gpu-next"||s.Method=="nvidia-truehdr"&&s.Runtime=="rtx-video"))).ToList();
        var output=new List<Stage>();
        for(int i=0;i<active.Count;i++)
        {
            var stage=active[i];
            if(stage.Kind=="resize"&&stage.Method is "spline36" or "bilinear"&&stage.Options.TryGetValue("legacy_geometry",out string? geometry)&&
                stage.Method==HistoricalResizeMethod(stage.Runtime,geometry.Split(':')[0]))
            {
                int model=i+1;
                bool beforeRife=model<active.Count&&active[model].Kind=="interpolate"&&active[model].Method=="rife";
                if(beforeRife)model++;
                if(model>=active.Count||active[model].Kind!="upscale"||active[model].Method!="onnx"||active[model].Runtime!=stage.Runtime||
                    beforeRife&&(i!=0||active[i+1].Runtime!=stage.Runtime||Value(active[model].Options,"frames","0") is not ("0" or "1")))
                {output.Add(stage);continue;}
                // An upscaler following RIFE cannot retain its attached resize:
                // the legacy reader would move it before RIFE.
                if(!beforeRife&&output.Count==1&&output[0].Kind=="interpolate") {output.Add(stage);continue;}
                var up=active[model];var options=new Dictionary<string,string>(up.Options);
                if(stage.Options.TryGetValue("target_height",out string? h))options["resize_height_before_upscale"]=h;
                else options["resize_factor_before_upscale"]=Value(stage.Options,"target_percent","100");
                if(beforeRife)output.Add(active[i+1]);
                output.Add(up with {Options=options});i=model;
            }
            else output.Add(stage);
        }
        return new(false,output);
    }
    public static void ValidateStageOptions(Stage stage)
    {
        void Number(string key,double minimum,double maximum,bool integer=false)
        {
            if(!stage.Options.TryGetValue(key,out var raw))return;
            if(!double.TryParse(raw,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out var n)||
                !double.IsFinite(n)||n<minimum||n>maximum||integer&&n!=Math.Truncate(n))
                throw new InvalidDataException($"{key} must be {(integer?"an integer":"a number")} from {minimum} to {maximum}.");
        }
        void Flag(string key) {if(stage.Options.TryGetValue(key,out var value)&&value is not ("yes" or "no"))throw new InvalidDataException(key+" must be yes or no.");}
        if(stage.Method=="rife") {Flag("ensemble");Number("scene_detect_threshold",0,1);}
        if(stage.Kind=="upscale") {Number("frames",0,64,true);Number("temporal_scene_threshold",0,1);}
        if(stage.Kind=="resize")
        {
            if(stage.Options.ContainsKey("target_height")==stage.Options.ContainsKey("target_percent"))throw new InvalidDataException("Downscale requires one target: height or percentage.");
            if(stage.Options.TryGetValue("legacy_geometry",out var legacy))
            {
                if(!Regex.IsMatch(legacy,@"^(linux|windows|macos):[a-z0-9_-]+$"))throw new InvalidDataException("Invalid legacy sizing identity.");
                Number("target_height",0.001,double.MaxValue);Number("target_percent",0.001,double.MaxValue);
            }
            else {Number("target_height",32,8192,true);Number("target_percent",1,100,true);}
        }
        if(stage.Kind=="hdr")
        {
            Number("contrast",0,200,true);Number("saturation",0,200,true);Number("middle_gray",10,100,true);
            if(stage.Method=="mpv") {Flag("mpv_truehdr_look");Number("paper_white",80,400,true);Number("highlights",0,100,true);Number("vibrance",0,80,true);}
            if(stage.Method=="nvidia-truehdr")Number("peak",400,2000,true);
        }
    }
    public static void Validate(Plan plan)
    {
        if(plan.Stages.Count>MaxStages)throw new InvalidDataException("Too many pipeline stages");
        if(plan.Stages.Count(s=>s.Kind=="hdr")>1)throw new InvalidDataException("Only one HDR conversion stage is allowed per profile.");
        bool afterHdr=false;
        var ids=new HashSet<string>(StringComparer.Ordinal);
        foreach(var s in plan.Stages)
        {
            if(s.Enabled&&afterHdr)throw new InvalidDataException("HDR must be the last active stage; the following providers currently require SDR.");
            if(s.Enabled&&s.Kind=="hdr")afterHdr=true;
            if(!Regex.IsMatch(s.Id,@"^[A-Za-z0-9_-]{1,64}$")||!ids.Add(s.Id))throw new InvalidDataException("Stage IDs must be stable, distinct identifiers");
            foreach(string token in new[] {s.Kind,s.Method,s.Runtime})
                if(!Regex.IsMatch(token,@"^[a-z0-9_-]{1,64}$"))throw new InvalidDataException("Stage kind/method/runtime must be explicit identifiers");
            if(s.Factor.Numerator<=0||s.Factor.Denominator<=0)throw new InvalidDataException("Invalid stage factor");
            if(s.Kind!="interpolate"&&s.Factor!=new Rational(1,1))throw new InvalidDataException("Only interpolation stages multiply cadence");
            if(s.Kind=="interpolate"&&s.Factor.Numerator<s.Factor.Denominator)throw new InvalidDataException("Interpolation factor cannot reduce cadence");
            if(s.Policy is not ("quality" or "fast"))throw new InvalidDataException("Explicit quality/fast policy required");
            ValidateStageOptions(s);
            if(s.Model.Contains('\n')||s.Model.Contains('\r'))throw new InvalidDataException("Invalid model name");
            foreach(var pair in s.Options)
                if(Fields.Contains(pair.Key)||!Regex.IsMatch(pair.Key,@"^[a-z0-9_]{1,80}$")||pair.Value.Contains('\n')||pair.Value.Contains('\r'))
                    throw new InvalidDataException("Invalid stage option");
        }
        // Verify cumulative arithmetic without imposing a model/hardware speed claim.
        plan.OutputCadence(new Rational(1,1));
    }
    public static void ValidateProfile(IEnumerable<Plan> chains)
    {
        int hdr=0;
        foreach(var chain in chains) {Validate(chain);hdr+=chain.Stages.Count(s=>s.Kind=="hdr");}
        if(hdr>1)throw new InvalidDataException("Only one HDR conversion stage is allowed per profile, across all its chains.");
    }
    public static IReadOnlyDictionary<string,string> Write(Plan plan,int chain)
    {
        Validate(plan);string prefix=Key(chain);var result=new Dictionary<string,string>(StringComparer.Ordinal) {
            [prefix+"pipeline_version"]=Version.ToString(System.Globalization.CultureInfo.InvariantCulture),
            [prefix+"stage_count"]=plan.Stages.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)
        };
        for(int i=0;i<plan.Stages.Count;i++)
        {
            var s=plan.Stages[i];string p=$"{prefix}stage_{i+1}_";
            foreach(var kv in new Dictionary<string,string> {
                ["id"]=s.Id,["kind"]=s.Kind,["method"]=s.Method,["runtime"]=s.Runtime,["enabled"]=s.Enabled?"yes":"no",
                ["model"]=s.Model,["factor_numerator"]=s.Factor.Numerator.ToString(System.Globalization.CultureInfo.InvariantCulture),
                ["factor_denominator"]=s.Factor.Denominator.ToString(System.Globalization.CultureInfo.InvariantCulture),["policy"]=s.Policy
            })result[p+kv.Key]=kv.Value;
            foreach(var kv in s.Options.OrderBy(k=>k.Key,StringComparer.Ordinal))result[p+kv.Key]=kv.Value;
        }
        return result;
    }
}

// Shared resolution evidence for the Manager and launchers. File checks never
// establish GPU/driver support: the native reader still negotiates execution.
public static class ProfileResolver
{
    public const string Schema = "animejanai.profile-plan.v1";
    public sealed record Context(string Platform,string Backend,string InferenceDirectory,string ModelsDirectory,
        string? RifeDirectory=null,ulong PipelineFeatures=0,string TemporalPolicy="fast",string AppleDevice="AUTO");
    public sealed record Requirement(string Kind,string Identity,string Path,bool Present,string? Pack=null);
    public sealed record ResolvedStage(string Id,string Kind,string Method,string Runtime,string Model,bool Enabled,
        string Status,string Reason,IReadOnlyList<Requirement> Requirements,int Group,string CadenceMultiplier);
    public sealed record Result(string Schema,IReadOnlyList<ResolvedStage> Stages,IReadOnlyList<string> Issues,
        string CadenceMultiplier,bool LegacyCompatible,bool CanExecute,string Qualification);
    public sealed record Configuration(string Schema,string Backend,int Slot,int? Rule,Result? Plan,
        IReadOnlyList<Requirement> Requirements,IReadOnlyList<string> Issues,Result? ProfileHdr=null);
    static string Opt(InterpolationPipeline.Stage s,string key,string fallback="")=>s.Options.TryGetValue(key,out var value)?value:fallback;
    public static bool LegacyCompatible(InterpolationPipeline.Plan plan,Context context)
    {
        if(plan.Stages.Any(s=>s.Enabled&&s.Kind=="resize"&&s.Options.ContainsKey("legacy_geometry")&&s.Method!=InterpolationPipeline.HistoricalResizeMethod(s.Runtime,context.Platform)))return false;
        var stages=InterpolationPipeline.InferencePlan(plan).Stages.ToArray();
        if(stages.Any(s=>s.Runtime!=context.Backend||s.Kind is not ("upscale" or "interpolate")))return false;
        var rife=stages.Where(s=>s.Kind=="interpolate").ToArray();
        if(rife.Length>1||rife.Any(s=>s.Method!="rife"))return false;
        if(stages.Any(s=>s.Kind=="upscale"&&s.Method!="onnx"))return false;
        if(rife.Length==1)
        {
            int index=Array.IndexOf(stages,rife[0]);
            if(index!=0&&index!=stages.Length-1)return false;
        }
        return true;
    }
    [System.Runtime.InteropServices.UnmanagedFunctionPointer(System.Runtime.InteropServices.CallingConvention.Cdecl)]
    delegate ulong NativeFeatures();
    public static ulong ReadPipelineFeatures(string directory)
    {
        IntPtr handle=IntPtr.Zero;
        try
        {
            handle=System.Runtime.InteropServices.NativeLibrary.Load(Path.Combine(directory,"libaji_pipeline.so"));
            return System.Runtime.InteropServices.NativeLibrary.TryGetExport(handle,"aji_pipeline_features_v1",out var symbol)
                ?System.Runtime.InteropServices.Marshal.GetDelegateForFunctionPointer<NativeFeatures>(symbol)():0;
        }
        catch(Exception e) when(e is DllNotFoundException or BadImageFormatException or EntryPointNotFoundException){return 0;}
        finally {if(handle!=IntPtr.Zero)System.Runtime.InteropServices.NativeLibrary.Free(handle);}
    }
    public static string RifeFile(string code,bool ensemble)
    {
        if(!Regex.IsMatch(code,@"^[0-9]{2,4}$"))return "";
        return "rife_v"+code[..1]+"."+(code.Length==2?code.Substring(1,1):code.Substring(1,2))+
            (code.Length==4&&code.EndsWith('1')?"_lite":"")+(ensemble?"_ensemble":"")+".onnx";
    }
    public static Result Resolve(InterpolationPipeline.Plan plan,Context context)
    {
        var issues=new List<string>();var output=new List<ResolvedStage>();
        bool legacy=false;
        try {InterpolationPipeline.Validate(plan);legacy=LegacyCompatible(plan,context);}
        catch(InvalidDataException e){issues.Add(e.Message);}
        var cadence=new InterpolationPipeline.Rational(1,1);int group=0;bool previousInference=false;
        foreach(var s in plan.Stages)
        {
            var requirements=new List<Requirement>();var reasons=new List<string>();
            void Require(string kind,string name,string path,string? pack=null,bool directory=false)
            {var r=new Requirement(kind,name,path,directory?Directory.Exists(path):File.Exists(path),pack);requirements.Add(r);if(!r.Present)reasons.Add("Missing "+kind+": "+name);}
            bool inference=s.Kind is "interpolate" or "upscale";
            if(s.Enabled)
            {
                if(!inference||!previousInference)group++;
                previousInference=inference;
                try {if(s.Kind=="interpolate")cadence=cadence.Multiply(s.Factor);}
                catch(InvalidDataException e){reasons.Add(e.Message);}
                if(s.Method=="nvidia-fruc")reasons.Add("FRUC has been removed. This imported step is preserved; disable or remove it explicitly.");
                else if(s.Method=="mpv"&&s.Kind=="hdr"&&s.Runtime=="gpu-next") { }
                else if(s.Method=="nvidia-truehdr"&&s.Kind=="hdr"&&s.Runtime=="rtx-video"&&context.Platform=="windows") { }
                else
                {
                    bool ordered=!legacy;
                    if(s.Kind=="resize"&&s.Options.ContainsKey("legacy_geometry")&&ordered)
                        reasons.Add("Legacy sizing must keep its original compatible order and backend. Choose downscale-only sizing explicitly before using an independent step.");
                    if(ordered&&(context.Platform!="linux"||context.Backend!="tensorrt"))reasons.Add("This ordered combination requires the Linux NVIDIA reader; the imported choices are preserved.");
                    bool runtime=s.Runtime==context.Backend||s.Runtime=="cuda"&&context.Backend=="tensorrt";
                    if(!runtime)reasons.Add("Step runtime "+s.Runtime+" differs from selected backend "+context.Backend+".");
                    string suffix=context.Platform=="windows"?".dll":context.Platform=="macos"?".dylib":".so";
                    string prefix=context.Platform=="windows"?"":"lib";
                    string? module=context.Backend switch {"tensorrt"=>"aji_trt","directml"=>"aji_dml","openvino" or "onnxruntime"=>"aji_ort","migraphx"=>context.Platform=="windows"?"aji_migraphx":File.Exists(Path.Combine(context.InferenceDirectory,"libaji_migraphx_rgb.so"))?"aji_migraphx_rgb":"aji_ort","vulkan"=>"aji_vulkan","coreml" or "coremlnative" or "metal"=>"aji_ort",_=>null};
                    if(module==null)reasons.Add("No declared reader for backend "+context.Backend+".");
                    else Require("reader",prefix+module+suffix,Path.Combine(context.InferenceDirectory,prefix+module+suffix),
                        module=="aji_ort"&&context.Platform=="linux"?"onnxruntime":null);
                    if(context.Platform=="macos"&&module=="aji_ort")
                        Require("runtime","libonnxruntime.1.dylib",Path.Combine(context.InferenceDirectory,"libonnxruntime.1.dylib"));
                    if(context.Backend=="tensorrt")
                    {
                        string runtimeFile=context.Platform=="windows"?"nvinfer_11.dll":"libnvinfer.so.11";
                        Require("runtime",runtimeFile,Path.Combine(context.InferenceDirectory,runtimeFile),"trt-runtime");
                    }
                    if(ordered&&context.Platform=="linux"&&context.Backend=="tensorrt")
                        foreach(var file in new[]{"libaji_pipeline.so","aji_pipeline.fatbin"})Require("reader",file,Path.Combine(context.InferenceDirectory,file));
                    if(s.Kind=="interpolate"&&s.Method=="rife")
                    {
                        if(context.Backend=="vulkan")
                        {
                            string root=Path.Combine(Path.GetDirectoryName(context.ModelsDirectory)!,"rife-vulkan","rife-v4.6");
                            if(s.Model!="46")reasons.Add("The Vulkan reader currently requires RIFE4.6.");
                            foreach(var name in new[]{"flownet.param","flownet.bin"})Require("model",name,Path.Combine(root,name),"rife-vulkan");
                        }
                        else
                        {
                            string name=RifeFile(s.Model,Opt(s,"ensemble","no")=="yes");
                            if(name.Length==0)reasons.Add("Invalid RIFE model identifier.");
                            else Require("model",name,Path.Combine(context.RifeDirectory??Path.Combine(Path.GetDirectoryName(context.ModelsDirectory)!,"rife"),name),"rife");
                        }
                        if(ordered&&(s.Factor.Denominator!=1||s.Factor.Numerator<2||s.Factor.Numerator>8))reasons.Add("Ordered RIFE requires an integer multiplier2–8.");
                    }
                    else if(s.Kind=="upscale"&&s.Method=="onnx")
                    {
                        if(string.IsNullOrWhiteSpace(s.Model))reasons.Add("Choose an upscaling model.");
                        else if(context.Backend=="vulkan")
                            foreach(var extension in new[]{".ncnn.param",".ncnn.bin"})Require("model",s.Model+extension,Path.Combine(context.ModelsDirectory,s.Model+extension));
                        else if(context.Platform=="macos"&&context.Backend is "metal" or "coremlnative")
                        {
                            var devices=context.AppleDevice.ToLowerInvariant().Split('+',StringSplitOptions.TrimEntries);
                            bool templated=context.Backend=="coremlnative"||devices.Any(d=>d is "cpu" or "ane" or "npu");
                            bool metal=context.Backend=="metal"&&devices.Any(d=>d is not ("cpu" or "ane" or "npu"));
                            if(metal)
                                foreach(string extension in new[]{".ajm",".ajw"})Require("model",s.Model+extension,Path.Combine(context.ModelsDirectory,s.Model+extension));
                            if(templated)
                            {
                                Require("model",s.Model+".mlpatch",Path.Combine(context.ModelsDirectory,s.Model+".mlpatch"));
                                Require("model-package",s.Model+".mlpackage",Path.Combine(context.ModelsDirectory,s.Model+".mlpackage"),directory:true);
                            }
                        }
                        else Require("model",s.Model+".onnx",Path.Combine(context.ModelsDirectory,s.Model+".onnx"));
                        int frames=int.TryParse(Opt(s,"frames","0"),out int configured)&&configured>0?configured:OnnxModelShape.TemporalFrames(Path.Combine(context.ModelsDirectory,s.Model+".onnx"));
                        if(ordered&&frames>1)reasons.Add("Temporal upscaling is unavailable in the ordered reader.");
                    }
                    else if(s.Kind=="resize"&&s.Method is "area" or "spline36" or "bilinear")
                    {
                        ulong bit=s.Method=="area"?1UL:s.Method=="spline36"?4UL:0UL;
                        if(ordered&&(context.PipelineFeatures&bit)==0) {reasons.Add("Update the reader to use independent "+s.Method+" downscale.");requirements.Add(new("capability","independent-"+s.Method,"",false,"reader"));}
                    }
                    else if(s.Kind=="hdr"&&s.Method=="nvidia-truehdr"&&s.Runtime=="cuda")
                    {
                        if((context.PipelineFeatures&2)==0) {reasons.Add("Update the reader to use TrueHDR.");requirements.Add(new("capability","truehdr","",false,"reader"));}
                        string root=Opt(s,"sdk_root","/usr/local/VideoFX");
                        foreach(var file in new[]{"lib/libVideoFX.so","lib/libNVCVImage.so","features/nvvfxtruehdr/lib/libnvVFXTrueHDR.so"})Require("SDK",Path.GetFileName(file),Path.Combine(root,file));
                    }
                    else reasons.Add("No provider delivered for "+s.Kind+" / "+s.Method+".");
                }
            }
            string status=!s.Enabled?"disabled":reasons.Count==0?"files-present":"unavailable";
            string reason=!s.Enabled?"Disabled; settings preserved.":reasons.Count==0?"Required files present; GPU, driver and source support are checked during playback.":string.Join(" ",reasons);
            output.Add(new(s.Id,s.Kind,s.Method,s.Runtime,s.Model,s.Enabled,status,reason,requirements,s.Enabled?group:0,cadence.ToString()));
            if(s.Enabled)issues.AddRange(reasons.Select(r=>s.Id+": "+r));
        }
        if(!legacy&&(cadence.Denominator!=1||cadence.Numerator>16))issues.Add("Ordered cumulative interpolation must be an integer multiplier ≤16.");
        return new(Schema,output,issues.Distinct().ToArray(),cadence.ToString(),legacy,issues.Count==0,
            "Static plan and exact required files only. Groups describe consecutive inference; native fusion remains backend-dependent. No hardware execution or measured FPS is implied.");
    }
    public static Dictionary<string,Dictionary<string,string>> Parse(string text)
    {
        var sections=new Dictionary<string,Dictionary<string,string>>(StringComparer.OrdinalIgnoreCase);Dictionary<string,string>? section=null;
        foreach(string line in text.Split('\n'))
        {
            string s=line.Trim();if(s.Length==0||s.StartsWith('#')||s.StartsWith(';'))continue;
            if(s.StartsWith('[')&&s.EndsWith(']')) {string name=s[1..^1].Trim();if(!sections.TryGetValue(name,out section))sections[name]=section=new(StringComparer.OrdinalIgnoreCase);continue;}
            int equals=s.IndexOf('=');if(section!=null&&equals>0)section[s[..equals].Trim().ToLowerInvariant()]=s[(equals+1)..].Trim();
        }
        return sections;
    }
    public static Configuration ResolveConfiguration(string text,Context context,int? slot=null,int? rule=null)
    {
        var sections=Parse(text);var global=sections.GetValueOrDefault("global")??new();
        string backend=global.GetValueOrDefault("backend",context.Backend).ToLowerInvariant();
        int selected=slot??(int.TryParse(global.GetValueOrDefault("default_slot","0"),out int n)?n:0);
        var requirements=new List<Requirement>();var issues=new List<string>();Result? selectedPlan=null,profileHdr=null;
        context=context with {Backend=backend,TemporalPolicy=global.GetValueOrDefault("rife_engine","fast"),AppleDevice=global.GetValueOrDefault("apple_device",context.AppleDevice)};
        if(selected>0&&sections.TryGetValue("slot_"+selected,out var section))
        {
            var chains=section.Keys.Select(k=>Regex.Match(k,@"^chain_([1-9][0-9]*)_")).Where(m=>m.Success).Select(m=>int.Parse(m.Groups[1].Value)).Distinct().Order();
            // macOS applies its unique HDR request at profile scope, even when
            // no inference rule matches. Resolve that independently rather than
            // requiring every inactive rule's models or moving native stages.
            if(context.Platform=="macos")
            {
                var hdrPlans=new List<InterpolationPipeline.Plan>();
                foreach(var field in section.Where(k=>Regex.IsMatch(k.Key,@"^chain_[1-9][0-9]*_stage_[1-9][0-9]*_kind$")&&k.Value=="hdr"))
                {
                    string prefix=field.Key[..^4];
                    string chainPrefix=field.Key[..field.Key.IndexOf("_stage_",StringComparison.Ordinal)];
                    if(section.GetValueOrDefault(chainPrefix+"_pipeline_version")!="1")
                    {issues.Add("Profile HDR: unsupported or missing pipeline version.");continue;}
                    var single=section.Where(k=>k.Key.StartsWith(prefix,StringComparison.Ordinal))
                        .ToDictionary(k=>"chain_1_stage_1_"+k.Key[prefix.Length..],k=>k.Value);
                    single["chain_1_pipeline_version"]="1";single["chain_1_stage_count"]="1";
                    try {hdrPlans.Add(InterpolationPipeline.Read(single,1,backend,context.TemporalPolicy,platform:context.Platform));}
                    catch(InvalidDataException e){issues.Add("Profile HDR: "+e.Message);}
                }
                try
                {
                    InterpolationPipeline.ValidateProfile(hdrPlans);
                    if(hdrPlans.Count>0)
                    {
                        profileHdr=Resolve(new(false,hdrPlans.SelectMany(p=>p.Stages).ToArray()),context);
                        issues.AddRange(profileHdr.Issues);requirements.AddRange(profileHdr.Stages.SelectMany(s=>s.Requirements));
                    }
                }
                catch(InvalidDataException e){issues.Add("Profile HDR: "+e.Message);}
            }
            foreach(int chain in chains)
            {
                if(rule!=null&&rule!=chain)continue;
                try
                {
                    var plan=InterpolationPipeline.Read(section,chain,backend,context.TemporalPolicy,name=>OnnxModelShape.TemporalFrames(Path.Combine(context.ModelsDirectory,name+".onnx")),context.Platform);
                    var resolved=Resolve(plan,context);selectedPlan??=resolved;
                    requirements.AddRange(resolved.Stages.SelectMany(s=>s.Requirements));issues.AddRange(resolved.Issues);
                }
                catch(InvalidDataException e){issues.Add("Rule "+chain+": "+e.Message);}
            }
        }
        return new(Schema,backend,selected,rule,selectedPlan,requirements.DistinctBy(r=>r.Path).ToArray(),issues.Distinct().ToArray(),profileHdr);
    }
}


    // Reads an ONNX model's graph input shape without an onnx dependency: a
    // minimal protobuf walk (ModelProto.graph -> GraphProto.input /
    // initializer -> ValueInfoProto.type -> tensor_type.shape.dim), mirroring
    // the engine's onnx_shape.cpp. Used to tell temporal (multi-frame) models
    // apart, which take T frames as [N, T*3, H, W] or [N, T, 3, H, W].
    public static class OnnxModelShape
    {
        private static readonly Dictionary<string, (DateTime, long, int)> _cache = [];

        // Frames per inference of the model (1 for single-frame models or an
        // unreadable file), cached while the file is unchanged.
        public static int TemporalFrames(string onnxPath)
        {
            try
            {
                var info = new FileInfo(onnxPath);
                if (!info.Exists)
                    return 1;
                if (_cache.TryGetValue(onnxPath, out var c) && c.Item1 == info.LastWriteTimeUtc && c.Item2 == info.Length)
                    return c.Item3;
                var dims = InputDims(File.ReadAllBytes(onnxPath));
                var frames = 1;
                if (dims is { Count: 5 } && dims[1] > 1 && dims[2] == 3)
                    frames = (int)dims[1];
                else if (dims is { Count: 4 } && dims[1] > 3 && dims[1] % 3 == 0)
                    frames = (int)(dims[1] / 3);
                _cache[onnxPath] = (info.LastWriteTimeUtc, info.Length, frames);
                return frames;
            }
            catch (Exception)
            {
                return 1;
            }
        }

        // Dims of the first graph input that is not an initializer (-1 for
        // symbolic dims), or null.
        public static List<long>? InputDims(byte[] data)
        {
            var m = new Reader(data, 0, data.Length);
            while (m.More)
            {
                var f = m.Tag(out var wire);
                if (f != 7 || wire != 2)
                {
                    m.Skip(wire);
                    continue;
                }
                var g = m.Sub();
                var inits = new HashSet<string>();
                var inputs = new List<(string, List<long>)>();
                while (g.More)
                {
                    var gf = g.Tag(out var gw);
                    if (gf == 5 && gw == 2)
                        inits.Add(TensorName(g.Sub()));
                    else if (gf == 11 && gw == 2)
                    {
                        var vi = ValueInfo(g.Sub());
                        if (vi is { } v)
                            inputs.Add(v);
                    }
                    else
                        g.Skip(gw);
                }
                foreach (var (name, dims) in inputs)
                {
                    if (!inits.Contains(name))
                        return dims;
                }
                return null;
            }
            return null;
        }

        private static string TensorName(Reader r)
        {
            while (r.More)
            {
                var f = r.Tag(out var wire);
                if (f == 8 && wire == 2)
                    return r.String();
                r.Skip(wire);
            }
            return string.Empty;
        }

        private static (string, List<long>)? ValueInfo(Reader r)
        {
            var name = string.Empty;
            List<long>? dims = null;
            while (r.More)
            {
                var f = r.Tag(out var wire);
                if (f == 1 && wire == 2)
                    name = r.String();
                else if (f == 2 && wire == 2)
                {
                    var tp = r.Sub();
                    while (tp.More)
                    {
                        var tf = tp.Tag(out var tw);
                        if (tf != 1 || tw != 2)
                        {
                            tp.Skip(tw);
                            continue;
                        }
                        var tt = tp.Sub();
                        while (tt.More)
                        {
                            var ff = tt.Tag(out var w);
                            if (ff == 2 && w == 2)
                                dims = Shape(tt.Sub());
                            else
                                tt.Skip(w);
                        }
                    }
                }
                else
                    r.Skip(wire);
            }
            return dims == null ? null : (name, dims);
        }

        private static List<long> Shape(Reader r)
        {
            var dims = new List<long>();
            while (r.More)
            {
                var f = r.Tag(out var wire);
                if (f == 1 && wire == 2)
                {
                    var d = r.Sub();
                    long v = -1;
                    while (d.More)
                    {
                        var df = d.Tag(out var dw);
                        if (df == 1 && dw == 0)
                            v = (long)d.Varint();
                        else
                            d.Skip(dw);
                    }
                    dims.Add(v);
                }
                else
                    r.Skip(wire);
            }
            return dims;
        }

        private sealed class Reader(byte[] data, int pos, int end)
        {
            private int _pos = pos;

            public bool More => _pos < end;

            public ulong Varint()
            {
                ulong v = 0;
                for (var shift = 0; shift < 64; shift += 7)
                {
                    if (_pos >= end)
                        throw new InvalidDataException("truncated varint");
                    var b = data[_pos++];
                    v |= (ulong)(b & 0x7f) << shift;
                    if ((b & 0x80) == 0)
                        return v;
                }
                throw new InvalidDataException("varint too long");
            }

            public uint Tag(out int wire)
            {
                var t = Varint();
                wire = (int)(t & 7);
                return (uint)(t >> 3);
            }

            public Reader Sub()
            {
                var n = Varint();
                if (n > (ulong)(end - _pos))
                    throw new InvalidDataException("truncated field");
                var r = new Reader(data, _pos, _pos + (int)n);
                _pos += (int)n;
                return r;
            }

            public string String()
            {
                var s = Sub();
                return System.Text.Encoding.UTF8.GetString(data, s._pos, s.Length);
            }

            private int Length => end - _pos;

            public void Skip(int wire)
            {
                switch (wire)
                {
                    case 0: Varint(); break;
                    case 1: _pos += 8; break;
                    case 2: Sub(); break;
                    case 5: _pos += 4; break;
                    default: throw new InvalidDataException($"wire type {wire}");
                }
                if (_pos > end)
                    throw new InvalidDataException("truncated field");
            }
        }
    }
