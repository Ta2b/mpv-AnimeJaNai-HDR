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
