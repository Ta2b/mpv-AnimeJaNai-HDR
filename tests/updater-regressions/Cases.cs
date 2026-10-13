using System.Net;
using System.Text.Json;

try
{
    Environment.SetEnvironmentVariable("ANIMEJANAI_PACKS_DIR", null);
    string root = Path.Combine(AppContext.BaseDirectory, "fixtures", Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(root);
    int passed = 0;
    void Check(bool ok, string message) { if (!ok) throw new Exception(message); }
    void Pass(string name) { passed++; Console.WriteLine("PASS " + name); }
    foreach (string mode in new[] { "normal", "replace-fails", "retire-fails", "crlf", "empty-legacy", "no-legacy" })
    {
        // Linux permits unlinking open files; Windows sharing-violation fixtures are platform-specific.
        if (!OperatingSystem.IsWindows() && (mode is "replace-fails" or "retire-fails")) continue;
        string dir = Path.Combine(root, mode), pc = Path.Combine(dir, "portable_config");
        Directory.CreateDirectory(Path.Combine(pc, "scripts"));
        string target = Path.Combine(pc, "input.conf"), legacy = Path.Combine(pc, "input-user.conf");
        string loader = Path.Combine(pc, "scripts", "animejanai_userinput.lua");
        string nl = mode == "crlf" ? "\r\n" : "\n";
        string original = string.Join(nl, new[] { "# header", "#@ANIMEJANAI-MANAGED-BEGIN",
            "SPACE cycle pause", "#@ANIMEJANAI-MANAGED-END", "q quit", "" });
        File.WriteAllText(target, original);
        if (mode != "no-legacy")
            File.WriteAllText(legacy, mode == "empty-legacy" ? "# no bindings\n" : "F11 cycle fullscreen\n");
        File.WriteAllText(loader, "-- legacy fixture");
        File.WriteAllText(Path.Combine(pc, "input-animejanai.conf"),
            "SPACE cycle pause\n" + (mode == "normal" ? "F10 cycle mute\n" : ""));
        var app = new Production(dir, new FixtureHttp());
        string? locked = mode == "replace-fails" ? target : mode == "retire-fails" ? legacy : null;
        if (locked != null)
        {
            using var held = new FileStream(locked, FileMode.Open, FileAccess.Read, FileShare.Read);
            app.Sync();
        }
        else app.Sync();
        if (mode == "replace-fails")
        {
            Check(File.ReadAllText(target) == original, "Failed replacement changed original");
            Check(File.Exists(legacy) && File.Exists(loader), "Failed replacement retired legacy files");
            Check(!Directory.EnumerateFiles(pc, "*.tmp").Any(), "Failed replacement left temporary output");
        }
        if (mode == "retire-fails") Check(File.Exists(legacy), "Fixture failed to hold legacy file");
        app.Sync();
        string saved = File.ReadAllText(target);
        int count = saved.Split("F11 cycle fullscreen").Length - 1;
        Check(count == (mode is "empty-legacy" or "no-legacy" ? 0 : 1), "Lost or duplicated migrated binding");
        Check(saved.Contains("q quit") && saved.Contains("SPACE cycle pause"), "Lost existing bindings");
        if (mode == "normal") Check(saved.Contains("F10 cycle mute"), "Did not refresh managed bindings");
        if (mode == "no-legacy") Check(saved == original, "Changed already current input.conf");
        Check(!File.Exists(legacy) && !File.Exists(loader), "Successful retry did not retire legacy files");
        if (mode == "crlf") Check(!saved.Replace("\r\n", "").Contains('\n'), "Changed line endings");
        app.Sync(); Check(File.ReadAllText(target) == saved, "Migration is not idempotent");
        Pass("migration-" + mode);
    }

    string copyRoot = Path.Combine(root, "preserve-copy");
    string copySource = Path.Combine(root, "copy-source");
    foreach (string dir in new[] {copyRoot, copySource}) Directory.CreateDirectory(Path.Combine(dir, "portable_config", "profiles", "linux-amd"));
    string bankRel = Path.Combine("portable_config", "profiles", "linux-amd", "animejanai.conf");
    File.WriteAllText(Path.Combine(copyRoot, bankRel), "user bank");
    File.WriteAllText(Path.Combine(copySource, bankRel), "default bank");
    Directory.CreateDirectory(Path.Combine(copySource, "portable_config", "profiles", "linux-nvidia"));
    File.WriteAllText(Path.Combine(copySource, "portable_config", "profiles", "linux-nvidia", "animejanai.conf"), "new NVIDIA bank");
    var copier = new Production(copyRoot, new FixtureHttp(), windows: false);
    copier.Copy(copySource, new HashSet<string> {"portable_config/profiles"});
    Check(File.ReadAllText(Path.Combine(copyRoot, bankRel)) == "user bank", "Update replaced user bank");
    Check(File.ReadAllText(Path.Combine(copyRoot, "portable_config", "profiles", "linux-nvidia", "animejanai.conf")) == "new NVIDIA bank", "Update did not seed missing bank");
    Pass("Linux update preserves existing banks and seeds missing banks");

    foreach (string version in new[] { "3.5.0", "3.6.0" })
    {
        var http = new FixtureHttp();
        string dir = Path.Combine(root, version); Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "version.txt"), version + "\n");
        var index = await new Production(dir, http).Packs();
        Check(index.PackageVersion == version, "Selected another release's packs");
        Check(http.Urls[0].EndsWith("/releases/tags/" + version), "Did not request exact installed tag");
        Check(!http.Urls.Any(u => u.EndsWith("/latest")), "Component lookup requested latest");
        Pass("installed-tag-" + version);
    }
    {
        var http = new FixtureHttp();
        var release = await new Production(root, http).Latest();
        Check(release.Tag == "3.5.0" && http.Urls.Single().EndsWith("/latest"), "Changed application-update selection");
        Pass("application-latest-control");
    }
    {
        var http = new FixtureHttp();
        bool failed = false;
        try { await new Production(root, http).Packs(); }
        catch (InvalidOperationException) { failed = true; }
        Check(failed && http.Urls.Count == 0, "Missing installed version selected network packs");
        Pass("missing-version");
    }
    {
        var http = new FixtureHttp();
        string dir = Path.Combine(root, "unpublished"); Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "version.txt"), "3.7.0");
        bool failed = false;
        try { await new Production(dir, http).Packs(); }
        catch (HttpRequestException) { failed = true; }
        Check(failed && http.Urls.Count == 1, "Missing tag silently fell back to another release");
        Pass("missing-release");
    }
    {
        var http = new FixtureHttp();
        var index = await new Production(Path.Combine(root, "3.6.0"), http, false).Packs();
        Check(index.PackageVersion == "3.6.0" && http.Urls[1].EndsWith("packs-linux-x64.json"), "Wrong platform index");
        Pass("linux-index-control");
    }
    {
        var http = new FixtureHttp(); string packs = Path.Combine(root, "local-packs"); Directory.CreateDirectory(packs);
        File.WriteAllText(Path.Combine(packs, "packs.json"), FixtureHttp.Index("3.6.0"));
        Environment.SetEnvironmentVariable("ANIMEJANAI_PACKS_DIR", packs);
        var index = await new Production(root, http).Packs();
        Environment.SetEnvironmentVariable("ANIMEJANAI_PACKS_DIR", null);
        Check(index.PackageVersion == "3.6.0" && http.Urls.Count == 0, "Local pack override used network");
        Pass("local-pack-control");
    }
    {
        var http = new FixtureHttp();
        string dir = Path.Combine(root, "pinned-components"); Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "version.txt"), "3.6.1-test.1");
        File.WriteAllText(Path.Combine(dir, "manifest.json"),
            "{\"package_version\":\"3.6.1-test.1\",\"component_package_version\":\"3.6.0\"}");
        var app = new Production(dir, http);
        var index = await app.Packs();
        Check(index.PackageVersion == "3.6.0" && http.Urls[0].EndsWith("/tags/3.6.0"),
            "Test package did not select its explicit component release");
        Check(app.Mismatch(index) == null, "Rejected explicitly selected matching packs");
        Check(app.Mismatch(index with { PackageVersion = "3.5.0" }) != null,
            "Explicit pin allowed a different component release");
        Pass("explicit-component-release");
    }
    {
        var app = new Production(Path.Combine(root, "3.6.0"), new FixtureHttp());
        var index = await app.Packs();
        Check(app.Mismatch(index) == null, "Rejected normal matching release");
        Check(app.Mismatch(index with { PackageVersion = "3.5.0" }) != null,
            "Normal package accepted a different release");
        Pass("normal-version-validation");
    }
    // ---- macOS: the application is replaced as a whole ----
    // POSIX paths: these cases run where the application can exist.
    if (!OperatingSystem.IsWindows())
    {
    {
        Check(Production.Bundle("/Applications/mpv AnimeJaNai.app/Contents/Resources/") == "/Applications/mpv AnimeJaNai.app", "Did not find the application of its Resources folder");
        Check(Production.Bundle("/Users/a/Apps/X.app/Contents/Resources/Manager.app/Contents/MacOS") == "/Users/a/Apps/X.app/Contents/Resources/Manager.app", "Did not pick the innermost application");
        Check(Production.Bundle("/opt/animejanai") == null && Production.Bundle("/tmp/X.app/ContentsOther") == null, "Took a plain folder for an application");
        Pass("mac-bundle-of-a-path");
    }
    {
        var release = new Release("3.8.0.20", new List<Asset> {
            new("AnimeJaNai-mac-bench.zip", "bench"), new("mpv-AnimeJaNai-HDR-v3.8.0.20-linux-x64.AppImage", "linux"),
            new("mpv-AnimeJaNai-HDR-v3.8.0.20-macos-arm64.zip.sha256", "sum"),
            new("mpv-AnimeJaNai-HDR-v3.8.0.20-macos-arm64.zip", "mac") });
        Check(Production.MacApplication(release, "-macos-arm64.zip")?.Url == "mac", "Wrong macOS asset");
        // A release that Deploy just created: the macOS workflow has not added its application yet.
        var early = new Release("3.8.0.21", release.Assets.Where(a => !a.Name.Contains("macos")).ToList());
        Check(Production.MacApplication(early, "-macos-arm64.zip") == null, "Offered a release without a macOS application");
        // An application of another version left on a release is not this release's.
        Check(Production.MacApplication(new Release("3.8.0.21", release.Assets), "-macos-arm64.zip") == null, "Took another version's application");
        Pass("mac-release-asset");
    }
    {
        string dir = Path.Combine(root, "mac-sum"); Directory.CreateDirectory(dir);
        string file = Path.Combine(dir, "a.zip"); File.WriteAllText(file, "abc");
        const string sum = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        Check(Production.Checksum(file, sum + "  a.zip\n") && Production.Checksum(file, sum.ToUpperInvariant()), "Rejected the right checksum");
        Check(!Production.Checksum(file, sum.Replace('b', 'c')) && !Production.Checksum(file, "") && !Production.Checksum(file, "a.zip"), "Accepted a wrong checksum");
        Pass("mac-checksum");
    }
    {
        string dir = Path.Combine(root, "mac-swap"), app = Path.Combine(dir, "mpv AnimeJaNai.app");
        string staging = Path.Combine(dir, ".AnimeJaNai-update");
        void Make(string at, string version)
        {
            Directory.CreateDirectory(Path.Combine(at, "Contents", "MacOS"));
            Directory.CreateDirectory(Path.Combine(at, "Contents", "Resources"));
            File.WriteAllText(Path.Combine(at, "Contents", "MacOS", "mpv-animejanai"), "#!/bin/sh\n");
            File.WriteAllText(Path.Combine(at, "Contents", "Resources", "version.txt"), version);
        }
        string Version() => File.ReadAllText(Path.Combine(app, "Contents", "Resources", "version.txt"));
        Make(app, "1"); File.WriteAllText(Path.Combine(app, "Contents", "Resources", "only-in-old"), "x");
        Check(Production.Blocked(app) == null, "A writable folder was reported read-only");
        Check(Production.Blocked("/private/var/folders/x/T/AppTranslocation/ABCD/d/mpv AnimeJaNai.app") == "translocated", "Did not see a translocated application");
        Check(!Directory.EnumerateFileSystemEntries(dir).Any(e => Path.GetFileName(e).StartsWith(".AnimeJaNai-write")), "The write test left a folder");

        // An archive without an application, then one whose application has no launcher.
        Directory.CreateDirectory(staging);
        bool refused = false;
        try { Production.Staged(staging, "mpv-animejanai"); } catch (InvalidOperationException) { refused = true; }
        Check(refused, "Accepted an archive without an application");
        Directory.CreateDirectory(Path.Combine(staging, "mpv AnimeJaNai.app", "Contents", "MacOS"));
        refused = false;
        try { Production.Staged(staging, "mpv-animejanai"); } catch (InvalidOperationException) { refused = true; }
        Check(refused && Version() == "1", "Accepted an application without its launcher");
        Directory.Delete(staging, true);

        // A complete one replaces the installed application; nothing of the old one remains.
        Make(Path.Combine(staging, "mpv AnimeJaNai.app"), "2");
        string staged = Production.Staged(staging, "mpv-animejanai");
        // A leftover of an interrupted update does not stop the next one.
        Directory.CreateDirectory(Path.Combine(dir, ".mpv AnimeJaNai.app.previous", "junk"));
        Production.Replace(staged, app);
        Check(Version() == "2", "The application was not replaced");
        Check(!File.Exists(Path.Combine(app, "Contents", "Resources", "only-in-old")), "Files of the old application remain");
        Check(Directory.GetFileSystemEntries(dir).Select(Path.GetFileName).OrderBy(n => n).SequenceEqual(new[] { ".AnimeJaNai-update", "mpv AnimeJaNai.app" }),
            "The update left something next to the application");
        Check(!Directory.EnumerateFileSystemEntries(staging).Any(), "The staged application was copied, not moved");

        // The new application cannot be moved in: the installed one is put back untouched.
        bool failed = false;
        try { Production.Replace(Path.Combine(staging, "missing.app"), app); } catch (Exception) { failed = true; }
        Check(failed && Version() == "2" && !Directory.Exists(Path.Combine(dir, ".mpv AnimeJaNai.app.previous")), "A failed replacement lost the installed application");
        Pass("mac-application-replaced-or-kept");
    }
    }
    // Releases are read from GitHub's pages; the API is only the second way.
    {
        string dir = Path.Combine(root, "pages"); Directory.CreateDirectory(dir);
        var pages = new PagesHttp("3.9.0", "manifest.json", "mpv-AnimeJaNai-HDR-v3.9.0-macos-arm64.zip", "mpv-AnimeJaNai-HDR-v3.9.0-linux-x64.AppImage", "SHA256SUMS");
        var latest = await new Production(dir, pages).Latest();
        Check(latest.Tag == "3.9.0" && latest.Assets.Count == 4
            && latest.Assets.Any(a => a.Url == "https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/download/3.9.0/mpv-AnimeJaNai-HDR-v3.9.0-macos-arm64.zip"),
            "Latest release not read from its pages");
        Check(!pages.Urls.Any(u => u.Contains("api.github.com")), "The API was used although the pages answered");
        Check(Production.MacApplication(latest, "-macos-arm64.zip") != null && Production.AppImage(latest, "linux-x64") != null, "Files of the platforms not found in the page");
        // The pages do not answer: the API.
        var api = new FixtureHttp();
        var fallback = await new Production(dir, api).Latest();
        Check(fallback.Tag == "3.5.0" && api.Urls.Single().Contains("api.github.com"), "No second way when the pages fail");
        Pass("releases-read-from-pages");
    }
    // Linux AppImage: which file of the release, where it goes, and its checksum.
    {
        var release = new Release("3.9.0", new List<Asset> { new("mpv-upscale-2x_animejanai-v3.9.0-linux-x64.tar.zst", "tar"),
            new("mpv-AnimeJaNai-HDR-v3.9.0-linux-x64.AppImage", "image"), new("mpv-AnimeJaNai-HDR-v3.9.0-macos-arm64.zip", "mac") });
        Check(Production.AppImage(release, "linux-x64")?.Url == "image", "Wrong AppImage asset");
        Check(Production.AppImage(new Release("3.9.1", release.Assets), "linux-x64") == null, "Took another version's AppImage");
        Check(Production.Target("/home/a/Apps/mpv-AnimeJaNai-HDR-v3.8.0.20-linux-x64.AppImage", "3.8.0.20", "3.9.0") == "/home/a/Apps/mpv-AnimeJaNai-HDR-v3.9.0-linux-x64.AppImage",
            "A name that carries its version must follow the new one");
        Check(Production.Target("/home/a/Apps/mpv.AppImage", "3.8.0.20", "3.9.0") == "/home/a/Apps/mpv.AppImage", "A name without version must be kept");
        const string listing = "aaaa  manifest.json\n51678e8a2f74a2db2092c5f0e387a72fa31e531e513036898366adcf07998dca  mpv-AnimeJaNai-HDR-v3.9.0-linux-x64.AppImage\nbbbb *other.bin\n";
        Check(Production.Listed(listing, "mpv-AnimeJaNai-HDR-v3.9.0-linux-x64.AppImage") == "51678e8a2f74a2db2092c5f0e387a72fa31e531e513036898366adcf07998dca"
            && Production.Listed(listing, "other.bin") == "bbbb" && Production.Listed(listing, "absent") == null, "Checksum listing misread");
        Pass("appimage-asset-target-checksum");
    }
    Console.WriteLine($"Completed {passed} updater regression cases.");
    return 0;
}
catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }

// GitHub's pages: releases/latest leads to the tag, and a file of a release exists or not.
class PagesHttp : HttpMessageHandler
{
    public List<string> Urls = new();
    readonly string tag; readonly string[] files;
    public PagesHttp(string tag, params string[] files) { this.tag = tag; this.files = files; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        var url = request.RequestUri!; Urls.Add(url.ToString());
        if (url.Host != "github.com") return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Forbidden));
        if (url.AbsolutePath.EndsWith("/releases/latest"))
            // What a client that follows redirections ends on.
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                RequestMessage = new HttpRequestMessage(HttpMethod.Head, new Uri(url, "tag/" + tag)) });
        if (url.AbsolutePath.EndsWith("/releases/expanded_assets/" + tag))
        {
            // As GitHub writes it: one link per file, with other links around.
            string html = "<ul><li><a href=\"/Ta2b/mpv-AnimeJaNai-HDR/archive/refs/tags/" + tag + ".zip\">Source</a></li>"
                + string.Concat(files.Select(f => "<li><a href=\"/Ta2b/mpv-AnimeJaNai-HDR/releases/download/" + tag + "/" + f + "\" rel=\"nofollow\">" + f + "</a></li>")) + "</ul>";
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(html), RequestMessage = request });
        }
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound) { RequestMessage = request });
    }
}

class FixtureHttp : HttpMessageHandler
{
    public List<string> Urls = new();
    public static string Index(string version) => JsonSerializer.Serialize(new { package_version = version,
        packs = new[] { new { name = "rife", asset = "component-rife.7z", bytes = 1, files = new[] { "fixture" } } } });
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        var url = request.RequestUri!;
        // This fixture is the API: GitHub's pages do not answer, so every lookup falls back to it.
        if (url.Host == "github.com") return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound) { RequestMessage = request });
        Urls.Add(url.ToString());
        string path = url.AbsolutePath, version = path.Contains("3.6.0") ? "3.6.0" : "3.5.0";
        if (path.EndsWith("3.7.0")) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        string body = path.EndsWith(".json") ? Index(version) : JsonSerializer.Serialize(new {
            tag_name = version, assets = new[] {
                new { name = "packs.json", browser_download_url = $"https://fixture.invalid/{version}/packs.json" },
                new { name = "packs-linux-x64.json", browser_download_url = $"https://fixture.invalid/{version}/packs-linux-x64.json" }
            } });
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body) });
    }
}
