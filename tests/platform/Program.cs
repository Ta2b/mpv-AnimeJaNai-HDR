using System.Text;
using System.Text.Json;
using AnimeJaNai.Platform;

int passed = 0;
void Check(string name, bool result) { if (!result) throw new Exception(name); Console.WriteLine("PASS " + name); passed++; }
void Conflict(Action action, string name) { try { action(); } catch (IOException) { Check(name, true); return; } throw new Exception(name); }
string root = Path.Combine(Path.GetTempPath(), "ajn-platform-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    string profiles = Path.Combine(root, "portable_config", "profiles");
    string active = Path.Combine(root, "animejanai", "animejanai.conf");
    string Bank(string bank) => Path.Combine(profiles, bank, "animejanai.conf");
    void Write(string path, string text) { Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, text); }
    foreach (var bank in new[] { "nvidia", "amd", "linux-nvidia", "linux-amd" }) Write(Bank(bank), bank + "\n# comment\n");
    PlatformServices.ActivateBank(root, "nvidia");
    string hash = PlatformServices.FileHash(active);
    // Migrate the previous two-field format, preserving a Manager edit.
    Write(Path.Combine(profiles, "active-bank.json"), JsonSerializer.Serialize(new {vendor="nvidia", hash}));
    Write(active, "user edit\n# preserved\n");
    PlatformServices.ActivateBank(root, "linux-amd");
    Check("legacy state migration preserves Windows edits", File.ReadAllText(Bank("nvidia")).Contains("user edit"));
    Check("Linux state has bank identity", File.ReadAllText(Path.Combine(profiles, "active-bank.json")).Contains("linux-amd"));
    Check("Linux and Windows banks remain separate", File.ReadAllText(Bank("amd")) == "amd\n# comment\n");
    string before = PlatformServices.FileHash(active);
    PlatformServices.SaveActiveConfig(root, before, Encoding.UTF8.GetBytes("Linux user setting\n# comment\n"));
    Check("Manager transaction mirrors active bank", File.ReadAllText(active) == File.ReadAllText(Bank("linux-amd")));
    Conflict(() => PlatformServices.SaveActiveConfig(root, before, Encoding.UTF8.GetBytes("stale edit")), "stale Manager rejected");
    Check("stale save preserves content", File.ReadAllText(active).Contains("Linux user setting"));
    Write(active, "active edit"); Write(Bank("linux-amd"), "bank edit");
    Conflict(() => PlatformServices.ActivateBank(root, "linux-nvidia"), "concurrent active and bank edits rejected");
    Check("both conflicting files preserved", File.ReadAllText(active) == "active edit" && File.ReadAllText(Bank("linux-amd")) == "bank edit");
    try { PlatformServices.ActivateBank(root, "../../escape"); throw new Exception("bank traversal accepted"); } catch (ArgumentException) { Check("bank name allowlist", true); }
    string sysfs = Path.Combine(root, "pci");
    void Gpu(string pci, string vendor) { var d = Path.Combine(sysfs, pci); Write(Path.Combine(d, "vendor"), vendor); Write(Path.Combine(d, "class"), "0x030000"); Write(Path.Combine(d, "device"), "0x1234"); }
    Gpu("0000:00:02.0", "0x8086"); Gpu("0000:01:00.0", "0x10de");
    var adapters = PlatformServices.LinuxAdapters(sysfs);
    Check("Intel/NVIDIA hybrid selects NVIDIA for inference", PlatformServices.SelectAdapter(adapters).vendor == "nvidia");
    Check("explicit Intel selection respected", PlatformServices.SelectAdapter(adapters, "intel").pci == "0000:00:02.0");
    Check("no NVIDIA device remains non-NVIDIA", PlatformServices.SelectAdapter(adapters.Where(a => a.vendor == "intel")).vendor == "intel");
    string concurrent = Path.Combine(root, "concurrent");
    foreach (var bank in new[] { "linux-amd", "linux-nvidia" })
        Write(Path.Combine(concurrent, "portable_config", "profiles", bank, "animejanai.conf"), "identical content");
    PlatformServices.ActivateBank(concurrent, "linux-amd");
    var expected = PlatformServices.FileHash(Path.Combine(concurrent, "animejanai", "animejanai.conf"));
    PlatformServices.ActivateBank(concurrent, "linux-nvidia");
    Conflict(() => PlatformServices.SaveActiveConfig(concurrent, expected, Encoding.UTF8.GetBytes("stale bank"), "linux-amd"),
        "bank identity conflict rejected even with identical content");
    int saved = 0, rejected = 0;
    using var start = new ManualResetEventSlim();
    var writers = Enumerable.Range(1, 2).Select(i => Task.Run(() =>
    {
        start.Wait();
        try { PlatformServices.SaveActiveConfig(concurrent, expected, Encoding.UTF8.GetBytes("writer " + i), "linux-nvidia"); Interlocked.Increment(ref saved); }
        catch (IOException) { Interlocked.Increment(ref rejected); }
    })).ToArray();
    start.Set(); Task.WaitAll(writers);
    Check("concurrent writers serialize and reject stale write", saved == 1 && rejected == 1);
    Console.WriteLine($"{passed} platform regressions passed");
}
finally { Directory.Delete(root, true); }
