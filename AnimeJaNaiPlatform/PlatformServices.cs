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
        (value ?? "").Trim().ToLowerInvariant() is "old" or "quality" ? "quality" : "fast";
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
    public static Plan Read(IReadOnlyDictionary<string,string> section,int chain,string backend="tensorrt",string temporalPolicy="fast")
    {
        var values=new Dictionary<string,string>(StringComparer.Ordinal);
        foreach(var kv in section)values[kv.Key.ToLowerInvariant()]=kv.Value;
        string prefix=Key(chain),version=Value(values,prefix+"pipeline_version");
        if(version.Length==0)
        {
            if(values.Keys.Any(k=>k.StartsWith(prefix+"stage_",StringComparison.Ordinal)))
                throw new InvalidDataException("Stage keys require an explicit pipeline_version");
            return Migrate(values,chain,backend,temporalPolicy);
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
        var plan=new Plan(false,stages);Validate(plan);return plan;
    }
    private static Plan Migrate(IReadOnlyDictionary<string,string> values,int chain,string backend,string policy)
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
        var plan=new Plan(true,stages);Validate(plan);return plan;
    }
    public static void Validate(Plan plan)
    {
        if(plan.Stages.Count>MaxStages)throw new InvalidDataException("Too many pipeline stages");
        var ids=new HashSet<string>(StringComparer.Ordinal);
        foreach(var s in plan.Stages)
        {
            if(!Regex.IsMatch(s.Id,@"^[A-Za-z0-9_-]{1,64}$")||!ids.Add(s.Id))throw new InvalidDataException("Stage IDs must be stable, distinct identifiers");
            foreach(string token in new[] {s.Kind,s.Method,s.Runtime})
                if(!Regex.IsMatch(token,@"^[a-z0-9_-]{1,64}$"))throw new InvalidDataException("Stage kind/method/runtime must be explicit identifiers");
            if(s.Factor.Numerator<=0||s.Factor.Denominator<=0)throw new InvalidDataException("Invalid stage factor");
            if(s.Kind!="interpolate"&&s.Factor!=new Rational(1,1))throw new InvalidDataException("Only interpolation stages multiply cadence");
            if(s.Kind=="interpolate"&&s.Factor.Numerator<s.Factor.Denominator)throw new InvalidDataException("Interpolation factor cannot reduce cadence");
            if(s.Policy is not ("quality" or "fast"))throw new InvalidDataException("Explicit quality/fast policy required");
            if(s.Model.Contains('\n')||s.Model.Contains('\r'))throw new InvalidDataException("Invalid model name");
            foreach(var pair in s.Options)
                if(Fields.Contains(pair.Key)||!Regex.IsMatch(pair.Key,@"^[a-z0-9_]{1,80}$")||pair.Value.Contains('\n')||pair.Value.Contains('\r'))
                    throw new InvalidDataException("Invalid stage option");
        }
        // Verify cumulative arithmetic without imposing a model/hardware speed claim.
        plan.OutputCadence(new Rational(1,1));
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
