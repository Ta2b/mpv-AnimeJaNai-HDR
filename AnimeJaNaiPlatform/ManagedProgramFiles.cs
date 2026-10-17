using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace AnimeJaNai.Platform;

// Program assets only. Profiles, settings, SDKs, models and engine caches are
// deliberately outside this namespace, including when a manifest is malformed.
public static class ManagedProgramFiles
{
    public const string InventoryName = "managed-program-files.json";
    const string StateName = ".managed-program-files.json";
    const string LegacyName = "legacy-managed-program-files.json";
    const string Schema = "animejanai.managed-program-files.v1";
    public sealed record Inventory(string Schema, Dictionary<string, string> Files);
    public sealed record Legacy(string Schema, Dictionary<string, string[]> Files);
    public sealed record Report(string Schema, bool LegacyMigration, List<string> Installed,
        List<string> Removed, List<string> Preserved, List<string> Conflicts);

    public static bool IsManaged(string path)
    {
        if (string.IsNullOrEmpty(path) || path.Contains('\\') || path.Contains(':') || path.Any(char.IsControl)
            || path.Split('/').Any(p => p is "" or "." or "..")) return false;
        return new[] { "scripts", "shaders", "user-scripts", "user-shaders", "hdr-tools" }
            .Any(p => path.StartsWith("portable_config/" + p + "/", StringComparison.Ordinal))
            || path.StartsWith("animejanai/preparation/", StringComparison.Ordinal)
                && Path.GetExtension(path) is ".py" or ".json";
    }
    public static bool IsManagedDirectory(string path) =>
        new[] { "portable_config/scripts", "portable_config/shaders", "portable_config/user-scripts",
            "portable_config/user-shaders", "portable_config/hdr-tools", "animejanai/preparation" }
        .Any(p => path == p || path.StartsWith(p + "/", StringComparison.Ordinal));
    static string Hash(string path)
    {
        using var file = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
    }
    static bool Digest(string value) => value is { Length: 64 } && value.All(Uri.IsHexDigit);
    static void Validate(IEnumerable<KeyValuePair<string, string>> files)
    {
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (path, digest) in files)
            if (!IsManaged(path) || !Digest(digest) || !names.Add(path))
                throw new InvalidDataException("Invalid managed program inventory: " + path);
    }
    // Refuse symlinked program files and parents rather than following a user
    // link outside (or inside) the installation. An explicitly chosen root may
    // itself be a mount/link; descendants must be ordinary files/directories.
    static bool Linked(string root, string path)
    {
        for (string? part = Path.Combine(root, path); part != root && part != null; part = Path.GetDirectoryName(part))
            if ((new FileInfo(part).LinkTarget != null) || (new DirectoryInfo(part).LinkTarget != null)) return true;
        return false;
    }
    static Inventory Read(string path)
    {
        var result = JsonSerializer.Deserialize(File.ReadAllText(path), ManagedProgramFilesJsonContext.Default.Inventory)
            ?? throw new InvalidDataException("Empty managed inventory");
        if (result.Schema != Schema || result.Files == null) throw new InvalidDataException("Unsupported managed inventory");
        Validate(result.Files); return result;
    }
    static void AtomicJson<T>(string path, T value, JsonTypeInfo<T> type)
    {
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temporary, JsonSerializer.Serialize(value, type) + "\n"); File.Move(temporary, path, true); }
        finally { File.Delete(temporary); }
    }
    public static void WriteInventory(string root)
    {
        root = Path.GetFullPath(root);
        var files = new Dictionary<string, string>(StringComparer.Ordinal);
        void Visit(string directory)
        {
            foreach (var entry in Directory.EnumerateFileSystemEntries(directory).Order(StringComparer.Ordinal))
            {
                string relative = Path.GetRelativePath(root, entry).Replace('\\', '/');
                if (Linked(root, relative)) throw new InvalidDataException("Linked package program: " + relative);
                if (Directory.Exists(entry)) Visit(entry);
                else if (IsManaged(relative)) files.Add(relative, Hash(entry));
            }
        }
        foreach (string directory in new[] { "portable_config/scripts", "portable_config/shaders", "portable_config/user-scripts",
            "portable_config/user-shaders", "portable_config/hdr-tools", "animejanai/preparation" })
            if (Directory.Exists(Path.Combine(root, directory))) Visit(Path.Combine(root, directory));
        Validate(files); AtomicJson(Path.Combine(root, InventoryName), new Inventory(Schema, files), ManagedProgramFilesJsonContext.Default.Inventory);
    }
    public static Report Sync(string packageRoot, string targetRoot, IEnumerable<string>? preservedPaths = null)
    {
        packageRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(packageRoot));
        targetRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(targetRoot));
        if (packageRoot.Equals(targetRoot, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal)) throw new ArgumentException("Package and writable roots must differ");
        var preserved = preservedPaths?.ToArray() ?? [];
        var wanted = Read(Path.Combine(packageRoot, InventoryName));
        // Validate every source before touching any target program.
        foreach (var (relative, digest) in wanted.Files)
            if (Linked(packageRoot, relative) || !File.Exists(Path.Combine(packageRoot, relative))
                || Hash(Path.Combine(packageRoot, relative)) != digest)
                throw new InvalidDataException("Package program hash/link mismatch: " + relative);
        Directory.CreateDirectory(targetRoot);
        string state = Path.Combine(targetRoot, StateName);
        if (new FileInfo(state).LinkTarget != null || new FileInfo(state + ".lock").LinkTarget != null
            || new FileInfo(Path.Combine(targetRoot, ".managed-program-files-report.json")).LinkTarget != null)
            throw new InvalidDataException("Linked managed inventory state");
        using var exclusive = new FileStream(state + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        bool migration = !File.Exists(state);
        var previous = migration ? new Inventory(Schema, new(StringComparer.Ordinal)) : Read(state);
        var known = new Dictionary<string, string[]>(StringComparer.Ordinal);
        string legacyPath = Path.Combine(packageRoot, LegacyName);
        if (File.Exists(legacyPath))
        {
            var legacy = JsonSerializer.Deserialize(File.ReadAllText(legacyPath), ManagedProgramFilesJsonContext.Default.Legacy)
                ?? throw new InvalidDataException("Empty legacy program inventory");
            if (legacy.Schema != Schema || legacy.Files == null) throw new InvalidDataException("Unsupported legacy program inventory");
            foreach (var (path, hashes) in legacy.Files)
            {
                if (hashes == null || hashes.Length == 0) throw new InvalidDataException("Missing legacy hashes");
                Validate(new[] { new KeyValuePair<string, string>(path, hashes[0]) });
                if (hashes.Any(h => !Digest(h))) throw new InvalidDataException("Invalid legacy hash");
                known.Add(path, hashes);
            }
        }
        var next = new Dictionary<string, string>(previous.Files, StringComparer.Ordinal);
        var report = new Report(Schema, migration, new(), new(), new(), new());
        foreach (string relative in wanted.Files.Keys.Concat(previous.Files.Keys).Concat(migration ? known.Keys : [])
            .Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal))
        {
            if (preserved.Any(p => relative.Equals(p, StringComparison.OrdinalIgnoreCase)
                || relative.StartsWith(p.TrimEnd('/') + "/", StringComparison.OrdinalIgnoreCase)))
            { report.Preserved.Add(relative); continue; }
            string destination = Path.Combine(targetRoot, relative);
            if (Linked(targetRoot, relative) || Directory.Exists(destination))
            { report.Conflicts.Add(relative + ": link or directory preserved"); continue; }
            bool exists = File.Exists(destination);
            string? actual = exists ? Hash(destination) : null;
            wanted.Files.TryGetValue(relative, out string? desired);
            previous.Files.TryGetValue(relative, out string? owned);
            bool recognized = actual != null && (actual == owned || migration && known.TryGetValue(relative, out var hashes) && hashes.Contains(actual));
            if (desired == null)
            {
                if (!exists) { next.Remove(relative); continue; }
                if (!recognized) { report.Preserved.Add(relative); continue; }
                // If interrupted here, next launch observes the absent file and
                // converges. A modified file never becomes newly owned.
                File.Delete(destination); next.Remove(relative); report.Removed.Add(relative); continue;
            }
            if (actual == desired) { next[relative] = desired; continue; }
            if (exists && !recognized)
            { report.Conflicts.Add(relative + ": local modification/unattributed file preserved"); continue; }
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            string temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.Copy(Path.Combine(packageRoot, relative), temporary);
                if (Hash(temporary) != desired || Linked(targetRoot, relative)
                    || (exists ? !File.Exists(destination) || Hash(destination) != actual : File.Exists(destination)))
                    throw new IOException("Program changed during sync: " + relative);
                if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(temporary, File.GetUnixFileMode(Path.Combine(packageRoot, relative)));
                File.Move(temporary, destination, true);
            }
            finally { File.Delete(temporary); }
            next[relative] = desired; report.Installed.Add(relative);
        }
        // Atomic receipt publication: partially completed copies/removals are
        // recognized by old/new hashes on the next run after interruption.
        AtomicJson(state, new Inventory(Schema, next), ManagedProgramFilesJsonContext.Default.Inventory);
        AtomicJson(Path.Combine(targetRoot, ".managed-program-files-report.json"), report, ManagedProgramFilesJsonContext.Default.Report);
        return report;
    }
}

// The updater is trimmed: use generated metadata rather than runtime reflection.
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    PropertyNameCaseInsensitive = true, WriteIndented = true)]
[JsonSerializable(typeof(ManagedProgramFiles.Inventory))]
[JsonSerializable(typeof(ManagedProgramFiles.Legacy))]
[JsonSerializable(typeof(ManagedProgramFiles.Report))]
internal partial class ManagedProgramFilesJsonContext : JsonSerializerContext { }
