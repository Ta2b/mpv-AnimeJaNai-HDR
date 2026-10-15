using System.Diagnostics;
using System.IO.Pipes;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AnimeJaNai.Platform;

// On demand only. No set_property, pause, reconfiguration or inference command.
public static class ReferenceExporter
{
    static readonly string[] Properties = [
        "path", "playlist-pos", "time-pos", "pause", "vf", "video-params", "video-dec-params",
        "video-out-params", "video-target-params", "container-fps", "estimated-vf-fps", "display-fps",
        "estimated-display-fps", "display-width", "display-height", "hwdec-current", "current-vo",
        "mpv-version", "ffmpeg-version", "working-directory", "frame-drop-count", "decoder-frame-drop-count",
        "user-data/animejanai-hardware", "user-data/animejanai-active-slot",
        "user-data/animejanai-interpolation", "user-data/animejanai-rife-sync",
        "user-data/animejanai-truehdr", "user-data/animejanai-linux-hdr"
    ];
    static readonly string[] Options = [
        "scale", "cscale", "dscale", "tscale", "correct-downscaling", "linear-downscaling",
        "sigmoid-upscaling", "glsl-shaders", "icc-profile", "target-colorspace-hint", "target-prim",
        "target-trc", "target-peak", "tone-mapping", "gamut-mapping-mode", "deband", "dither-depth",
        "video-sync", "interpolation", "hwdec", "gpu-api", "gpu-context", "video-unscaled"
    ];
    static readonly string[] State = ["path", "playlist-pos", "vf", "video-params", "video-out-params",
        "user-data/animejanai-active-slot", "user-data/animejanai-hardware"];

    public static async Task<object> Capture(string root, string endpoint)
    {
        DateTime started = DateTime.UtcNow;
        var watch = Stopwatch.StartNew();
        using var ipc = await Ipc.Connect(endpoint);
        var observed = new SortedDictionary<string, JsonElement>(StringComparer.Ordinal);
        var unavailable = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string property in Properties.Concat(Options.Select(o => "options/" + o)))
        {
            var response = await ipc.Command("get_property", property);
            if (response.error == "success") observed[property] = response.data;
            else unavailable[property] = response.error;
        }
        if (!observed.ContainsKey("path") || !observed.ContainsKey("video-params"))
            throw new InvalidOperationException("No loaded video: reference not exported");

        var warnings = new List<string>();
        var files = new SortedDictionary<string, Artifact>(StringComparer.Ordinal);
        async Task<string> Resolve(string path)
        {
            var expanded = await ipc.Command("expand-path", path);
            if (expanded.error != "success" || expanded.data.ValueKind != JsonValueKind.String)
                throw new IOException($"Cannot resolve mpv path {path}: {expanded.error}");
            string value = expanded.data.GetString()!;
            string cwd = observed.TryGetValue("working-directory", out var wd) ? wd.GetString()! : root;
            return Path.GetFullPath(value, cwd);
        }
        void Add(string path, string role, bool text = false)
        {
            if (files.ContainsKey(path)) return;
            try { files[path] = Fingerprint(path, role, text); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            { warnings.Add($"{role}: {path}: {e.Message}"); }
        }
        void Inventory(string directory, string role, HashSet<string> ancestors)
        {
            // Follow model-package symlinks on macOS, but never recurse through a cycle.
            string real = new DirectoryInfo(directory).ResolveLinkTarget(true)?.FullName ?? Path.GetFullPath(directory);
            if (!ancestors.Add(real)) { warnings.Add($"Directory cycle: {directory}"); return; }
            try
            {
                foreach (string item in Directory.EnumerateFileSystemEntries(directory).Order(StringComparer.Ordinal))
                {
                    if (files.Count >= 10000) { warnings.Add("Artifact inventory exceeds 10000 files; incomplete"); break; }
                    if (Directory.Exists(item)) Inventory(item, role, ancestors);
                    else Add(item, role);
                }
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            { warnings.Add($"Inventory: {directory}: {e.Message}"); }
            finally { ancestors.Remove(real); }
        }
        var filters = new List<object>();
        if (observed.TryGetValue("vf", out var vf) && vf.ValueKind == JsonValueKind.Array)
            foreach (var filter in vf.EnumerateArray())
            {
                if (!filter.TryGetProperty("name", out var name) || !name.GetString()!.StartsWith("animejanai", StringComparison.Ordinal)) continue;
                bool enabled = !filter.TryGetProperty("enabled", out var en) || en.ValueKind != JsonValueKind.False;
                if (!enabled) continue;
                var paths = new SortedDictionary<string, string>(StringComparer.Ordinal);
                if (filter.TryGetProperty("params", out var parameters))
                    foreach (string key in new[] { "conf", "lib", "stats", "model-dir", "rife-model-dir" })
                    {
                        if (!parameters.TryGetProperty(key, out var value) || value.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(value.GetString())) continue;
                        string path = await Resolve(value.GetString()!);
                        paths[key] = path;
                        if (key.EndsWith("-dir", StringComparison.Ordinal))
                            Inventory(path, "model_and_export_inventory", new HashSet<string>(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal));
                        else Add(path, key, key is "conf" or "stats");
                    }
                filters.Add(new { observed_filter = filter.Clone(), resolved_paths = paths });
            }

        if (observed.TryGetValue("options/glsl-shaders", out var shaders) && shaders.ValueKind == JsonValueKind.Array)
            foreach (var shader in shaders.EnumerateArray())
                if (shader.ValueKind == JsonValueKind.String) Add(await Resolve(shader.GetString()!), "shader");
        if (observed.TryGetValue("options/icc-profile", out var icc) && icc.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(icc.GetString()) && icc.GetString() != "auto")
            Add(await Resolve(icc.GetString()!), "icc_profile");
        foreach (string file in new[] { "version.txt", "manifest.json", "animejanai/version.txt", "animejanai/inference/GPU-SOURCE.json" })
            if (File.Exists(Path.Combine(root, file))) Add(Path.Combine(root, file), "package_provenance", true);

        var changed = new List<string>();
        foreach (string property in State.Concat(Options.Select(o => "options/" + o)))
        {
            var end = await ipc.Command("get_property", property);
            if (observed.TryGetValue(property, out var before))
            {
                if (end.error != "success" || before.GetRawText() != end.data.GetRawText()) changed.Add(property);
            }
            else if (end.error == "success") changed.Add(property);
        }
        foreach (var file in files.Values.Where(f => f.role != "stats"))
        {
            var info = new FileInfo(file.path);
            if (!info.Exists || info.Length != file.size || info.LastWriteTimeUtc != file.modified_utc)
                changed.Add(file.path);
        }
        return new {
            schema = "animejanai.reference.v1", captured_utc = started, duration_ms = watch.Elapsed.TotalMilliseconds,
            qualification = "partial", consistent_observed_state = changed.Count == 0 && files.Values.All(f => f.stable),
            changed_during_capture = changed, warnings,
            machine = new { os = RuntimeInformation.OSDescription, architecture = RuntimeInformation.OSArchitecture.ToString(),
                logical_processors = Environment.ProcessorCount },
            observed_properties = observed, unavailable_properties = unavailable, filters, artifacts = files.Values,
            limitations = new[] {
                "Read-only sequential snapshot, not an atomic per-output trace; changes away and back may escape detection.",
                "File hashes identify bytes on disk at capture time, not proof of the weights already loaded in a session.",
                "Model/export directories are an inventory, not proof that each artifact was executed; engine selection needs backend telemetry.",
                "Configured precision/ensemble/cut/order are in the captured config; effective operator precision, placement and intermediate dimensions may be unreported.",
                "Stats are an unverified sample: they may predate this media or profile. Missing properties are recorded, never inferred from a preset name.",
                "Media is identified by mpv path and parameters, not hashed. No FPS or perceptual-quality conclusion follows from this report."
            }
        };
    }

    public sealed record Artifact(string role, string path, long size, DateTime modified_utc, string sha256, bool stable, string? text);
    public static Artifact Fingerprint(string path, string role, bool text = false)
    {
        var before = new FileInfo(path);
        long size = before.Length; DateTime modified = before.LastWriteTimeUtc;
        using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        byte[] hash; string? content = null;
        if (text && size <= 1024 * 1024)
        {
            using var memory = new MemoryStream(); input.CopyTo(memory);
            byte[] bytes = memory.ToArray(); hash = SHA256.HashData(bytes); content = Encoding.UTF8.GetString(bytes);
        }
        else hash = SHA256.HashData(input);
        before.Refresh();
        return new Artifact(role, path, size, modified, Convert.ToHexString(hash).ToLowerInvariant(),
            before.Exists && before.Length == size && before.LastWriteTimeUtc == modified, content);
    }

    public static void WriteNew(string output, string json)
    {
        string path = Path.GetFullPath(output);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temp, json + "\n", new UTF8Encoding(false)); File.Move(temp, path, false); }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    sealed class Ipc : IDisposable
    {
        readonly Stream stream;
        readonly StreamReader reader;
        readonly StreamWriter writer;
        int id;
        Ipc(Stream stream)
        {
            this.stream = stream;
            reader = new StreamReader(stream, Encoding.UTF8, leaveOpen: true);
            writer = new StreamWriter(stream, new UTF8Encoding(false), leaveOpen: true) { AutoFlush = true };
        }
        public static async Task<Ipc> Connect(string endpoint)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            if (OperatingSystem.IsWindows())
            {
                const string prefix = @"\\.\pipe\";
                if (endpoint.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) endpoint = endpoint[prefix.Length..];
                var pipe = new NamedPipeClientStream(".", endpoint, PipeDirection.InOut, PipeOptions.Asynchronous);
                try { await pipe.ConnectAsync(timeout.Token); return new Ipc(pipe); }
                catch { pipe.Dispose(); throw; }
            }
            var socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            try { await socket.ConnectAsync(new UnixDomainSocketEndPoint(endpoint), timeout.Token); return new Ipc(new NetworkStream(socket, true)); }
            catch { socket.Dispose(); throw; }
        }
        public async Task<(string error, JsonElement data)> Command(params string[] command)
        {
            int request = ++id;
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            await writer.WriteLineAsync(JsonSerializer.Serialize(new { command, request_id = request }).AsMemory(), timeout.Token);
            while (true)
            {
                string line = await reader.ReadLineAsync(timeout.Token) ?? throw new IOException("mpv IPC closed");
                using var json = JsonDocument.Parse(line);
                var result = json.RootElement;
                if (!result.TryGetProperty("request_id", out var response) || response.GetInt32() != request) continue;
                return (result.GetProperty("error").GetString()!, result.TryGetProperty("data", out var data) ? data.Clone() : default);
            }
        }
        public void Dispose() { writer.Dispose(); reader.Dispose(); stream.Dispose(); }
    }
}
