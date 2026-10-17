using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

// One producer builds both entry points. A pinned package never silently falls
// back to the older Windows filter, which cannot announce exact DML pairs.
internal sealed class WindowsMpvBundle
{
    internal const string Source = "19c0fcf89595e6ab33908299207c555b67e81558";
    internal const string Patch = "526303a3a596436acc7cc339e400f3f4adc0a40c7680573d8bc7e329e9b03095";
    internal const string Filter = "7ecbb7e76d4f5a05f8933b5bbdf10a075541de23617112730af9ced51e2e8bba";
    internal static readonly string[] Binaries = ["mpv.exe", "mpv.com", "libmpv-2.dll"];
    readonly string directory;
    internal string Identity { get; }
    WindowsMpvBundle(string directory, string producer) =>
        (this.directory, Identity) = (directory, $"windows-{producer}-exact-dml-pair1");

    internal static WindowsMpvBundle? Load(string baseDirectory)
    {
        string pin = Path.Combine(baseDirectory, "windows-mpv-source-ref.txt");
        string? local = Environment.GetEnvironmentVariable("MPV_WINDOWS_LOCAL");
        if (!File.Exists(pin))
        {
            if (!string.IsNullOrWhiteSpace(local))
                throw new InvalidDataException("MPV_WINDOWS_LOCAL requires windows-mpv-source-ref.txt.");
            return null;
        }
        string producer = File.ReadAllText(pin).Trim();
        if (!Regex.IsMatch(producer, "\\A[0-9a-f]{40}\\z"))
            throw new InvalidDataException("Invalid Windows mpv producer pin.");
        if (string.IsNullOrWhiteSpace(local))
            throw new InvalidDataException("The pinned Windows mpv bundle was not staged (MPV_WINDOWS_LOCAL).");
        string directory = Path.GetFullPath(local);
        using var json = JsonDocument.Parse(File.ReadAllText(Path.Combine(directory, "aji-dml-pair-provenance.json")));
        var root = json.RootElement;
        Require(root, "schema", "animejanai.windows-mpv-bundle.v1");
        Require(root, "player_source", producer);
        Require(root, "mpv_source", Source);
        Require(root, "patch_sha256", Patch);
        Require(root, "filter_sha256", Filter);
        if (root.GetProperty("dml_exact_pair").GetInt32() != 1 || root.GetProperty("abi").GetInt32() != 9)
            throw new InvalidDataException("Windows mpv bundle lacks the reviewed DML pair contract.");
        foreach (string name in Binaries)
        {
            string path = Path.Combine(directory, name);
            using var file = File.OpenRead(path);
            string actual = Convert.ToHexStringLower(SHA256.HashData(file));
            Require(root.GetProperty("files"), name, actual);
        }
        return new WindowsMpvBundle(directory, producer);
    }
    static void Require(JsonElement root, string key, string expected)
    {
        if (!root.TryGetProperty(key, out var value) || value.GetString() != expected)
            throw new InvalidDataException($"Windows mpv provenance mismatch: {key}.");
    }
    internal void Install(string destination, params string[] names)
    {
        foreach (string name in names) File.Copy(Path.Combine(directory, name), Path.Combine(destination, name), true);
        File.Copy(Path.Combine(directory, "aji-dml-pair-provenance.json"), Path.Combine(destination, "aji-dml-pair-provenance.json"), true);
    }
}
