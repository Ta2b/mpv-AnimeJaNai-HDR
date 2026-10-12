using System.Text.Json;
using AnimeJaNai.Platform;

try
{
    string root = AppContext.BaseDirectory;
    int ri = Array.IndexOf(args, "--root");
    if (ri >= 0 && ri + 1 < args.Length) root = Path.GetFullPath(args[ri + 1]);
    string? Get(string key) { int i = Array.IndexOf(args, key); return i >= 0 && i+1 < args.Length ? args[i+1] : null; }
    if (args.FirstOrDefault() == "--save-bank")
    {
        PlatformServices.SaveActiveConfig(root, Get("--expected-hash") ?? "", File.ReadAllBytes(args[1]), Get("--expected-bank"));
        Console.WriteLine("{\"saved\":true}"); return 0;
    }
    object result = args.FirstOrDefault() switch
    {
        "--probe" => PlatformServices.Probe(root, Get("--vendor") ?? "auto"),
        "--activate-bank" when args.Length > 1 => PlatformServices.ActivateBank(root, args[1]),
        _ => throw new ArgumentException("Usage: AnimeJaNaiPlatform --probe | --activate-bank BANK [--root DIR]")
    };
    Console.WriteLine(JsonSerializer.Serialize(result));
    return 0;
}
catch (Exception e)
{
    Console.Error.WriteLine(e.Message);
    return 1;
}
