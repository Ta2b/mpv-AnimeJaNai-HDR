// AnimeJaNaiUpdater — keeps an installed mpv-upscale-2x_animejanai folder up to date in place,
// preserving user files, and manages hardware-specific component packs ("AnimeJaNai Manager").
// Ships at the install root next to mpvnet.exe.
//
//   AnimeJaNaiUpdater.exe --check        prints UPDATE_AVAILABLE <ver> | UP_TO_DATE <ver> (for the lua)
//   AnimeJaNaiUpdater.exe --apply        waits for mpv to close, downloads + applies, relaunches mpv
//   macOS (the install is an application, replaced as a whole; see "macOS" below) and Linux
//   AppImage (the file is replaced by the release's AppImage; see "Linux AppImage" below):
//   AnimeJaNaiUpdater --apply [--wait-pid PID] [--status FILE] [--reopen PATH] [--no-relaunch]
//   AnimeJaNaiUpdater.exe --components   detect GPU, list installed/available packs + recommendation
//   AnimeJaNaiUpdater.exe --install X    download + install component pack X
//   AnimeJaNaiUpdater.exe --remove X     delete component pack X's files
//   AnimeJaNaiUpdater.exe --auto         install everything the detected hardware recommends
//
// Update size is tiered: if the latest release's heavy deps match what's installed (compared via
// manifest.json) only the small overlay archive is fetched; otherwise the full package.
//
// Component packs are subsets of the install (TensorRT runtime, per-GPU-generation builder
// resources, RIFE models), emitted by the package builder as component-<name>.7z + packs.json
// release assets. Archives are rooted at the install dir, so extraction is installation;
// packs.json carries each pack's file list, so removal is deletion. Installed state lives in
// components.json at the install root (inferred from disk for installs that predate it).
// Dev override: set ANIMEJANAI_PACKS_DIR to a local directory with packs.json + archives.

using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using static Downloader;

// HDR fork: updates, component packs and manifests come from the fork's releases.
const string Repo = "Ta2b/mpv-AnimeJaNai-HDR";
string apiLatest = $"https://api.github.com/repos/{Repo}/releases/latest";

// macOS: the install is an application ("mpv AnimeJaNai.app") and the updater sits in its
// Contents/Resources, next to manifest.json. ANIMEJANAI_ROOT is the user's folder there, not
// the install.
string? macApp = OperatingSystem.IsMacOS() ? BundleOf(AppContext.BaseDirectory) : null;

// Single-file exe: BaseDirectory is the folder the exe runs from = the install root.
string installDir = macApp is not null ? Path.Combine(macApp, "Contents", "Resources")
    : Path.GetFullPath(Environment.GetEnvironmentVariable("ANIMEJANAI_ROOT") ?? AppContext.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar, '/');

// Platform-specific names come from the install's manifest.json so this same code works on Windows
// and (later) Linux. Fallbacks keep older installs (no manifest fields) working on Windows.
string localManifest = Path.Combine(installDir, "manifest.json");
string playerExe = ReadManifestString(localManifest, "player_executable", "mpvnet.exe");
string archiveTool = ReadManifestString(localManifest, "archive_tool", "7z.exe");
// The thing to *launch* (vs. the process name to wait on). On Windows the
// player exe is both; on Linux the launcher (mpv-animejanai) wraps the mpv
// binary to set --config-dir + the bundled library path. Falls back to the
// player exe for older installs / Windows.
string playerLauncher = ReadManifestString(localManifest, "player_launcher", playerExe);
// Release assets are shared across platforms on one tag, suffixed by RID
// (…-linux-x64.tar.zst / overlay-…-linux-x64.7z / manifest-linux-x64.json).
// Windows keeps its legacy unsuffixed names. This RID selects our platform's
// assets from a release that may carry both.
string platformRid = ReadManifestString(localManifest, "platform", "win-x64");
bool isWinRid = platformRid == "win-x64";
// True if an asset belongs to our platform: Windows = anything not tagged
// "linux"; otherwise the name must carry our RID.
bool RidMatch(string name) => isWinRid ? !name.Contains("linux") : name.Contains(platformRid);

// NVML ships in the NVIDIA driver as nvml.dll on Windows and libnvidia-ml.so.1
// on Linux; remap the DllImport library name on non-Windows so GPU detection
// (DetectGpu) works cross-platform without per-OS P/Invoke declarations.
if (!OperatingSystem.IsWindows())
{
    NativeLibrary.SetDllImportResolver(typeof(Nvml).Assembly, (name, asm, search) =>
        name == "nvml.dll" ? NativeLibrary.Load("libnvidia-ml.so.1", asm, search)
                           : IntPtr.Zero);
}

string mode = args.Length > 0 ? args[0].ToLowerInvariant() : "--check";

try
{
    switch (mode)
    {
        case "--check":
            if (macApp is not null)
            {
                await MacCheckAsync();
                return 0;
            }
            await CheckAsync();
            return 0;
        case "--apply":
            if (macApp is not null)
            {
                return await MacApplyAsync();
            }
            if (Environment.GetEnvironmentVariable("ANIMEJANAI_APPIMAGE") == "1")
            {
                return await AppImageApplyAsync();
            }
            return await ApplyAsync();
        case "--components" or "--install" or "--remove" or "--auto" or "--recommend" when macApp is not null:
            Console.WriteLine("No component packs on macOS: everything is in the application.");
            return 2;
        case "--components":
            await ComponentsAsync(null, args.Contains("--json"));
            return 0;
        case "--install":
            return await InstallComponentAsync(args.Length > 1 ? args[1] : "");
        case "--remove":
            return RemoveComponent(args.Length > 1 ? args[1] : "");
        case "--auto":
            return await AutoComponentsAsync();
        case "--recommend":
            return await RecommendAsync();
        default:
            Console.WriteLine("Usage: AnimeJaNaiUpdater.exe [--check|--apply|--components|--install <pack>|--remove <pack>|--auto|--recommend]");
            return 2;
    }
}
catch (Exception ex)
{
    Console.WriteLine($"Updater error: {ex.Message}");
    return 1;
}

// ---- modes ---------------------------------------------------------------------------------

async Task CheckAsync()
{
    // Before the network call, so post-update housekeeping happens even offline.
    CleanupLegacy();
    MigrateUserConf();
    SyncInputConf();
    MigrateAnimeJaNaiConf();
    MigrateMpvConfProfile();
    var release = await GetLatestReleaseAsync();
    string local = ReadLocalVersion();
    // Platforms are released independently: a release that does not have this platform's files
    // (yet) is not an update. An AppImage is replaced by the AppImage of the release, a folder
    // install by its overlay or full package; the overlay is the last file a platform uploads.
    bool appImage = Environment.GetEnvironmentVariable("ANIMEJANAI_APPIMAGE") == "1";
    bool published = appImage
        ? AppImageAsset(release, platformRid) is not null
        : release.Assets.Any(a => Regex.IsMatch(a.Name, @"overlay-.*\.7z$") && RidMatch(a.Name));
    if (IsNewer(release.Tag, local) && published)
    {
        Console.WriteLine($"UPDATE_AVAILABLE {release.Tag}");
        // UPDATE_PACKS name:bytes,... - the components this update downloads again.
        try
        {
            var changed = await ChangedPacksAsync(release);
            if (changed.Count > 0)
            {
                Console.WriteLine("UPDATE_PACKS " + string.Join(",", changed.Select(c => $"{c.Pack.Name}:{c.Pack.Bytes}")));
            }
        }
        catch { /* the offer stands without the details */ }
        string? file = appImage ? Environment.GetEnvironmentVariable("APPIMAGE") : null;
        if (appImage && (string.IsNullOrEmpty(file) || !File.Exists(file)))
        {
            Console.WriteLine("UPDATE_BLOCKED extracted");
        }
        else if (file is not null && MacBlocked(file) is string reason)
        {
            Console.WriteLine($"UPDATE_BLOCKED {reason}");
        }
    }
    else
    {
        Console.WriteLine($"UP_TO_DATE {local}");
    }
}

// ---- Linux AppImage ----------------------------------------------------------------------------
// An AppImage is one read-only file: it cannot be updated piece by piece, so the AppImage of the
// release replaces it. As on macOS, the new file is downloaded and verified next to the old
// one while the player keeps playing; once the player has closed it takes its place (under the
// new version's name when the old name carried its version) and the player comes back. The
// user's settings are outside the file and are not touched.

static Asset? AppImageAsset(Release release, string rid) =>
    release.Assets.FirstOrDefault(a => a.Name.EndsWith(rid + ".AppImage", StringComparison.Ordinal) &&
                                       a.Name.Contains(release.Tag, StringComparison.Ordinal));

// Where the new AppImage goes: the same file, renamed to the new version when its name carries
// the version it replaces.
static string AppImageTarget(string current, string oldVersion, string newVersion)
{
    string name = Path.GetFileName(current);
    return oldVersion.Length > 0 && name.Contains(oldVersion, StringComparison.Ordinal)
        ? Path.Combine(Path.GetDirectoryName(current)!, name.Replace(oldVersion, newVersion))
        : current;
}

// The SHA-256 of `name` in a SHA256SUMS listing ("<hex>  <name>" a line), or null.
static string? ListedChecksum(string listing, string name)
{
    foreach (string line in listing.Split('\n'))
    {
        string[] parts = line.Split((char[]?)null, 2, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 2 && parts[1].Trim().TrimStart('*') == name)
        {
            return parts[0];
        }
    }
    return null;
}

async Task<int> AppImageApplyAsync()
{
    string? statusPath = Option("--status");
    string? reopen = Option("--reopen");
    int playerPid = int.TryParse(Option("--wait-pid"), out int parsed) ? parsed : 0;
    void Status(string line)
    {
        Console.WriteLine(line);
        if (statusPath is not null)
        {
            TryDelete(() => File.WriteAllText(statusPath, line + "\n"));
        }
    }

    string current = Environment.GetEnvironmentVariable("APPIMAGE") ?? "";
    string part = "";
    try
    {
        Status("CHECK");
        if (current.Length == 0 || !File.Exists(current))
        {
            Status($"FAILED This copy does not run from an AppImage file. Download the new one from https://github.com/{Repo}/releases");
            return 3;
        }
        if (MacBlocked(current) is not null)
        {
            Status("FAILED The folder that holds the AppImage cannot be written to. Move the AppImage to a folder of yours, then update.");
            return 3;
        }
        var release = await GetLatestReleaseAsync();
        string local = ReadLocalVersion();
        var asset = AppImageAsset(release, platformRid);
        if (!IsNewer(release.Tag, local) || asset is null)
        {
            Status($"UP_TO_DATE {local}");
            return 0;
        }

        string target = AppImageTarget(current, local, release.Tag);
        part = Path.Combine(Path.GetDirectoryName(current)!, "." + Path.GetFileName(target) + ".part");
        double shown = -1;
        Status("DOWNLOAD 0");
        await DownloadFileAsync(asset.Url, part, p =>
        {
            if (p != shown)
            {
                shown = p;
                Status($"DOWNLOAD {p:0}");
            }
        });
        Status("EXTRACT");
        // The checksums published with the release, when it has them.
        var sums = release.Assets.FirstOrDefault(a => a.Name == "SHA256SUMS");
        if (sums is not null)
        {
            using var client = NewClient();
            string? expected = ListedChecksum(await client.GetStringAsync(sums.Url), asset.Name);
            if (expected is not null && !ChecksumMatches(part, expected))
            {
                throw new IOException("The download is damaged (checksum mismatch). Nothing was changed.");
            }
        }
        // An AppImage starts with an ELF header: a page of error text saved as a file does not.
        using (var head = File.OpenRead(part))
        {
            var magic = new byte[4];
            if (head.Read(magic, 0, 4) != 4 || magic[0] != 0x7f || magic[1] != (byte)'E' || magic[2] != (byte)'L' || magic[3] != (byte)'F')
            {
                throw new IOException("The download is not an AppImage. Nothing was changed.");
            }
        }
        File.SetUnixFileMode(part, File.GetUnixFileMode(current) | UnixFileMode.UserExecute | UnixFileMode.UserRead | UnixFileMode.UserWrite);

        bool playerOpen = playerPid > 0 && IsRunning(playerPid);
        Status($"READY {release.Tag}");
        if (playerPid > 0 && !WaitForPid(playerPid, TimeSpan.FromSeconds(90)))
        {
            Status("FAILED The player did not close. Nothing was changed.");
            return 1;
        }
        if (statusPath is not null && File.Exists(statusPath + ".reopen"))
        {
            reopen = File.ReadAllText(statusPath + ".reopen").Trim();
        }
        // One rename puts the new file in place. This program runs from the old file, which Linux
        // keeps readable until its last user closes, even once it has no name.
        File.Move(part, target, true);
        part = "";
        if (target != current)
        {
            TryDelete(() => File.Delete(current));
        }
        Status($"DONE {release.Tag}");
        if (!args.Contains("--no-relaunch") && (playerOpen || playerPid == 0))
        {
            var start = new ProcessStartInfo { FileName = target, UseShellExecute = false };
            // What the old AppImage put in the environment points into its own mount.
            foreach (string name in new[] { "APPIMAGE", "APPDIR", "ARGV0", "OWD", "LD_LIBRARY_PATH", "MPV_HOME",
                         "ANIMEJANAI_APPIMAGE", "ANIMEJANAI_ROOT", "ANIMEJANAI_DATA_DIR", "ANIMEJANAI_MPV", "ANIMEJANAI_INFERENCE_DIR", "ANIMEJANAI_IPC_PATH" })
            {
                start.Environment.Remove(name);
            }
            if (!string.IsNullOrEmpty(reopen))
            {
                start.ArgumentList.Add(reopen);
            }
            try { Process.Start(start)?.Dispose(); }
            catch (Exception e) { Console.WriteLine($"Could not relaunch the player: {e.Message}"); }
        }
        return 0;
    }
    catch (Exception e)
    {
        Status("FAILED " + e.Message.Replace('\n', ' '));
        return 1;
    }
    finally
    {
        if (part.Length > 0)
        {
            TryDelete(() => File.Delete(part));
        }
        if (statusPath is not null)
        {
            TryDelete(() => File.Delete(statusPath + ".reopen"));
        }
    }
}

// 3.3.x -> 3.4.x leftovers: a full update copies the new package over the install but never
// deletes, so the retired VapourSynth/Python runtime (~5.5 GB, mostly vs-plugins) and the old
// in-folder ConfEditor survive the upgrade. The launcher lua runs --check on every mpv start,
// so this fires right after the post-update relaunch and is a cheap no-op afterwards. The gate
// is structural rather than a version compare: a legacy marker AND a 3.4-era marker must both
// exist, which is never true on a real 3.3.x install (no Manager / inference dir) nor on a
// fresh 3.4 one (no VSPipe).
void CleanupLegacy()
{
    try
    {
        bool legacy = File.Exists(Path.Combine(installDir, "VSPipe.exe"));
        bool current = File.Exists(Path.Combine(installDir, "AnimeJaNaiManager.exe")) ||
                       Directory.Exists(Path.Combine(installDir, "animejanai", "inference"));
        if (!legacy || !current)
        {
            return;
        }

        string[] dirs =
        {
            "vs-plugins", "vs-coreplugins", "vs-scripts", "vsgenstubs4", "Lib",
            "__pycache__", Path.Combine("animejanai", "core"),
        };
        // Only files 3.4.0 no longer ships. The mpv.net runtime (Locale/, *_cor3.dll, the
        // msvcp/vcruntime family, MediaInfo.dll), 7z.dll and yt-dlp.exe stay.
        string[] files =
        {
            "VSPipe.exe", "VSScript.dll", "VSVFW.dll", "AVFS.exe",
            "pfm-192-vapoursynth-win.exe", "portable.vs", "vsmlrt.py", "vsrepo.py",
            "vsgenstubs.py", "vspackages3.json", "MANIFEST.in", "7z.exe",
            "python.exe", "pythonw.exe", "python.cat", "python3.dll",
            "python313.dll", "python313._pth", "python313.zip", "sqlite3.dll",
            "libcrypto-3.dll", "libssl-3.dll", "libffi-8.dll",
            Path.Combine("animejanai", "AnimeJaNaiConfEditor.exe"),
            Path.Combine("animejanai", "av_libglesv2.dll"),
            Path.Combine("animejanai", "libHarfBuzzSharp.dll"),
            Path.Combine("animejanai", "libSkiaSharp.dll"),
        };

        long freed = 0;
        foreach (var rel in dirs)
        {
            string p = Path.Combine(installDir, rel);
            if (!Directory.Exists(p))
            {
                continue;
            }
            try
            {
                freed += new DirectoryInfo(p).EnumerateFiles("*", SearchOption.AllDirectories)
                                             .Sum(f => f.Length);
                Directory.Delete(p, true);
            }
            catch { /* locked file etc. - retried on a later start */ }
        }
        var pyds = Directory.EnumerateFiles(installDir, "*.pyd")
                            .Select(p => Path.GetFileName(p)!);
        foreach (var rel in files.Concat(pyds))
        {
            string p = Path.Combine(installDir, rel);
            if (!File.Exists(p))
            {
                continue;
            }
            try
            {
                long len = new FileInfo(p).Length;
                File.SetAttributes(p, FileAttributes.Normal);
                File.Delete(p);
                freed += len;
            }
            catch { /* retried on a later start */ }
        }
        if (freed > 0)
        {
            string amount = freed >= 1073741824
                ? $"{freed / 1073741824.0:F1} GB"
                : $"{freed / 1048576} MB";
            Console.WriteLine(
                $"LEGACY_CLEANUP freed {amount} of retired VapourSynth/Python files");
        }
    }
    catch { /* cleanup must never break --check */ }
}

// One-time retirement of mpv-user.conf. Since 3.4.0 mpv.conf is the user's own
// file (it includes the managed mpv-animejanai.conf), so the old separate
// mpv-user.conf is deprecated and confusing - it could still hold settings
// carried from 3.3.x. Fold its real settings into mpv.conf under the
// "Your settings below" marker, then delete it. Gated on mpv.conf being the
// new include-style file, so a pre-upgrade 3.3.x mpv.conf is left alone; once
// mpv-user.conf is gone this is a no-op. Fresh installs never ship it.
void MigrateUserConf()
{
    try
    {
        string pc = Path.Combine(installDir, "portable_config");
        string userConf = Path.Combine(pc, "mpv-user.conf");
        string mpvConf = Path.Combine(pc, "mpv.conf");
        if (!File.Exists(userConf) || !File.Exists(mpvConf))
        {
            return;
        }
        string mpv = File.ReadAllText(mpvConf);
        // Only fold into the new-style (include-based) mpv.conf; never touch a
        // legacy managed mpv.conf that an update is about to overwrite anyway.
        if (!mpv.Contains("mpv-animejanai.conf"))
        {
            return;
        }
        string nl = mpv.Contains("\r\n") ? "\r\n" : "\n";
        var keepLines = mpv.Replace("\r\n", "\n").Split('\n').ToList();
        // Drop any lingering include of mpv-user.conf (older 3.4.0 builds shipped one).
        keepLines.RemoveAll(l => l.TrimStart().StartsWith("include") &&
                                 l.Contains("mpv-user"));
        // Real settings = non-blank, non-comment lines the user actually added.
        var settings = File.ReadAllLines(userConf)
            .Where(l => l.Trim().Length > 0 && !l.TrimStart().StartsWith("#"))
            .ToList();
        if (settings.Count > 0)
        {
            keepLines.Add("");
            keepLines.Add("# Migrated from mpv-user.conf (retired in 3.4.0):");
            keepLines.AddRange(settings);
        }
        File.WriteAllText(mpvConf, string.Join(nl, keepLines));
        File.Delete(userConf);
        Console.WriteLine(settings.Count > 0
            ? $"USER_CONF_MIGRATED {settings.Count} setting(s) into mpv.conf"
            : "USER_CONF_RETIRED (no custom settings to migrate)");
    }
    catch { /* migration must never break --check */ }
}

// 3.5.x: the managed mpv-animejanai.conf moved its defaults out of top-level
// options into a named [animejanai] profile. Top-level options in an included
// file are appended to mpv's "default" profile and applied last, which silently
// beat the user's own top-level line in mpv.conf (e.g. volume-max). With the new
// layout mpv.conf must apply the profile itself, so inject `profile = animejanai`
// right after the include and BEFORE the user's own lines, so their overrides
// win. Gated on the new managed file (never fires against the old top-level
// layout), idempotent, and a no-op on fresh installs (they already ship the line).
void MigrateMpvConfProfile()
{
    try
    {
        string pc = Path.Combine(installDir, "portable_config");
        string mpvConf = Path.Combine(pc, "mpv.conf");
        string managed = Path.Combine(pc, "mpv-animejanai.conf");
        if (!File.Exists(mpvConf) || !File.Exists(managed))
        {
            return;
        }
        string mpv = File.ReadAllText(mpvConf);
        // Only the include-based mpv.conf; never a legacy managed mpv.conf.
        if (!mpv.Contains("mpv-animejanai.conf"))
        {
            return;
        }
        // Only once the installed managed file uses the new [animejanai] layout,
        // so we never apply a profile that isn't defined yet.
        if (!File.ReadAllText(managed).Contains("[animejanai]"))
        {
            return;
        }
        string nl = mpv.Contains("\r\n") ? "\r\n" : "\n";
        var lines = mpv.Replace("\r\n", "\n").Split('\n').ToList();
        // Idempotent: leave it alone if a profile=animejanai line already exists.
        if (lines.Any(l => Regex.IsMatch(l, @"^\s*profile\s*=\s*animejanai\s*(#.*)?$")))
        {
            return;
        }
        int inc = lines.FindIndex(l => l.TrimStart().StartsWith("include") &&
                                       l.Contains("mpv-animejanai.conf"));
        if (inc < 0)
        {
            return;  // unexpected layout; leave it alone
        }
        lines.Insert(inc + 1, "profile = animejanai");
        File.WriteAllText(mpvConf, string.Join(nl, lines));
        Console.WriteLine("MPV_CONF_MIGRATED (profile = animejanai applied; your mpv.conf overrides now win)");
    }
    catch { /* migration must never break --check */ }
}

// input.conf is the user's own file, but mpv's input.conf has no include and
// mpv.net builds its menu from input.conf's #menu: annotations - so the managed
// AnimeJaNai keybindings live inside input.conf as a marked block. This refreshes
// that block from input-animejanai.conf (overwritten on update) while preserving
// the user's section below the END marker, and one-time migrates the retired
// input-user.conf into that section. Mirrors the mpv-user.conf retirement.
void SyncInputConf()
{
    try
    {
        string pc = Path.Combine(installDir, "portable_config");
        string inputConf = Path.Combine(pc, "input.conf");
        string managedSrc = Path.Combine(pc, "input-animejanai.conf");
        if (!File.Exists(inputConf) || !File.Exists(managedSrc))
        {
            return;
        }
        string raw = File.ReadAllText(inputConf);
        string nl = raw.Contains("\r\n") ? "\r\n" : "\n";
        var lines = raw.Replace("\r\n", "\n").Split('\n').ToList();
        int begin = lines.FindIndex(l => l.StartsWith("#@ANIMEJANAI-MANAGED-BEGIN"));
        int end = lines.FindIndex(l => l.StartsWith("#@ANIMEJANAI-MANAGED-END"));
        if (begin < 0 || end < 0 || end <= begin)
        {
            return;  // not the managed-block layout (e.g. a pre-3.4 input.conf); leave it
        }

        string currentBlock = string.Join("\n", lines.GetRange(begin + 1, end - begin - 1)).Trim('\n');
        string newBlock = File.ReadAllText(managedSrc).Replace("\r\n", "\n").Trim('\n');
        var userSection = lines.GetRange(end + 1, lines.Count - end - 1);  // after END marker

        // One-time fold of the retired input-user.conf into the user section.
        string userConf = Path.Combine(pc, "input-user.conf");
        bool migrated = false;
        if (File.Exists(userConf))
        {
            var binds = File.ReadAllLines(userConf)
                .Where(l => l.Trim().Length > 0 && !l.TrimStart().StartsWith("#")).ToList();
            const string migrationMarker = "# Migrated from input-user.conf (retired in 3.4.0):";
            int previous = userSection.LastIndexOf(migrationMarker);
            bool alreadyMigrated = previous >= 0 &&
                userSection.Skip(previous + 1).Take(binds.Count).SequenceEqual(binds);
            if (binds.Count > 0 && !alreadyMigrated)
            {
                userSection.Add("");
                userSection.Add(migrationMarker);
                userSection.AddRange(binds);
            }
            migrated = true;
        }

        if (currentBlock == newBlock && !migrated)
        {
            try { File.Delete(Path.Combine(pc, "scripts", "animejanai_userinput.lua")); } catch { }
            return;  // block already current and nothing to migrate
        }

        var rebuilt = new List<string>();
        rebuilt.AddRange(lines.GetRange(0, begin + 1));  // header through the BEGIN marker
        rebuilt.AddRange(newBlock.Split('\n'));
        rebuilt.Add(lines[end]);                         // the END marker line
        rebuilt.AddRange(userSection);
        // Keep the old bindings and loader until the replacement is on disk.
        // Writing beside the destination also avoids truncating it on failure.
        string pending = inputConf + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(pending, string.Join(nl, rebuilt));
            File.Move(pending, inputConf, overwrite: true);
        }
        finally
        {
            try { File.Delete(pending); } catch { }
        }
        if (migrated)
        {
            try { File.Delete(userConf); } catch { }
        }
        try { File.Delete(Path.Combine(pc, "scripts", "animejanai_userinput.lua")); } catch { }
        Console.WriteLine(migrated
            ? File.Exists(userConf)
                ? "INPUT_CONF_SYNCED (bindings migrated; input-user.conf retirement will be retried)"
                : "INPUT_CONF_SYNCED (managed block refreshed; input-user.conf folded in and retired)"
            : "INPUT_CONF_SYNCED (managed keybindings block refreshed)");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"INPUT_CONF_SYNC_FAILED (original bindings retained): {ex.Message}");
    }
}

// The SD model was re-exported at ONNX opset 21 (the op23 build fell back to the
// CPU on the DirectML backend); the op23 .onnx no longer ships. Two post-update
// chores, both on --check (every start), so they fire on the post-update relaunch
// - with the new binary, since the updater ships in overlay_paths - before play:
//  1. animejanai.conf is user-preserved, so a custom profile that named the old
//     model by hand would error "model not found". Idempotent name rewrite.
//  2. The additive update copies the new op21 .onnx in but never deletes the old
//     op23 one (or its TensorRT engines - clean_stale_engines only prunes other
//     GPU/TRT versions, so same-machine op23 engines, tens of MB each, linger).
//     Remove op23's .onnx + derived engine/timing-cache files, gated on op21
//     being present so the last copy of the SD model is never deleted.
void MigrateAnimeJaNaiConf()
{
    const string oldName =
        "2x_AnimeJaNai_SD_V1beta34_Compact_1x3xHxW_dyn-HW_strong_fp16_op23_dynamo";
    const string newName =
        "2x_AnimeJaNai_SD_V1beta34_Compact_1x3xHxW_dyn-HW_strong_fp16_op21_dynamo";

    try
    {
        string conf = Path.Combine(installDir, "animejanai", "animejanai.conf");
        if (File.Exists(conf))
        {
            string text = File.ReadAllText(conf);
            if (text.Contains(oldName))
            {
                File.WriteAllText(conf, text.Replace(oldName, newName));
                Console.WriteLine("ANIMEJANAI_CONF_MIGRATED (SD model op23 -> op21)");
            }
        }
    }
    catch { /* migration must never break --check */ }

    try
    {
        string onnx = Path.Combine(installDir, "animejanai", "onnx");
        if (Directory.Exists(onnx) &&
            File.Exists(Path.Combine(onnx, newName + ".onnx")))
        {
            int removed = 0;
            foreach (var f in Directory.EnumerateFiles(onnx))
            {
                if (!Path.GetFileName(f).StartsWith(oldName + ".", StringComparison.Ordinal))
                {
                    continue;
                }
                try
                {
                    File.SetAttributes(f, FileAttributes.Normal);
                    File.Delete(f);
                    removed++;
                }
                catch { /* locked etc. - retried on a later start */ }
            }
            if (removed > 0)
            {
                Console.WriteLine($"ANIMEJANAI_ORPHAN_REMOVED ({removed} op23 SD file(s))");
            }
        }
    }
    catch { /* cleanup must never break --check */ }
}

// ---- macOS -----------------------------------------------------------------------------------
// The install is one application. Its files cannot be updated one by one (the signature of the
// application covers them), so the release's application replaces it as a whole. Nothing of the
// user's is inside: profiles and settings are in ~/Library/Application Support/AnimeJaNai.
// The new application is downloaded, unpacked and verified next to the old one while the player
// keeps playing; the swap itself is two renames once the player has closed.

string? Option(string name)
{
    int i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}

async Task MacCheckAsync()
{
    var release = await GetLatestReleaseAsync();
    string local = ReadLocalVersion();
    // The macOS application is added to a release some time after the release is created: a
    // release without it is not an update yet.
    if (!IsNewer(release.Tag, local) || MacAsset(release, MacAssetSuffix()) is null)
    {
        Console.WriteLine($"UP_TO_DATE {local}");
        return;
    }
    Console.WriteLine($"UPDATE_AVAILABLE {release.Tag}");
    if (MacBlocked(macApp!) is string reason)
    {
        Console.WriteLine($"UPDATE_BLOCKED {reason}");
    }
}

string MacAssetSuffix() => ReadManifestString(localManifest, "update_asset_suffix", "-macos-arm64.zip");

async Task<int> MacApplyAsync()
{
    string app = macApp!;
    string? statusPath = Option("--status");
    string? reopen = Option("--reopen");
    int playerPid = int.TryParse(Option("--wait-pid"), out int parsed) ? parsed : 0;
    // One line: the state the player's script shows (CHECK, DOWNLOAD n, EXTRACT, READY v,
    // DONE v, UP_TO_DATE v, FAILED text).
    void Status(string line)
    {
        Console.WriteLine(line);
        if (statusPath is not null)
        {
            TryDelete(() => File.WriteAllText(statusPath, line + "\n"));
        }
    }

    string staging = Path.Combine(Path.GetDirectoryName(app)!, ".AnimeJaNai-update");
    string work = Path.Combine(Path.GetTempPath(), $"animejanai-update-{Environment.ProcessId}");
    try
    {
        Status("CHECK");
        if (MacBlocked(app) is string reason)
        {
            Status("FAILED " + MacBlockedText(reason));
            return 3;
        }
        var release = await GetLatestReleaseAsync();
        string local = ReadLocalVersion();
        var asset = MacAsset(release, MacAssetSuffix());
        if (!IsNewer(release.Tag, local) || asset is null)
        {
            Status($"UP_TO_DATE {local}");
            return 0;
        }

        Directory.CreateDirectory(work);
        string zip = Path.Combine(work, asset.Name);
        double shown = -1;
        Status("DOWNLOAD 0");
        await DownloadFileAsync(asset.Url, zip, p =>
        {
            if (p != shown)
            {
                shown = p;
                Status($"DOWNLOAD {p:0}");
            }
        });
        // The checksum published next to the application, when the release has one.
        var sum = release.Assets.FirstOrDefault(a => a.Name == asset.Name + ".sha256");
        if (sum is not null)
        {
            string sumPath = zip + ".sha256";
            await DownloadFileAsync(sum.Url, sumPath, _ => { });
            if (!ChecksumMatches(zip, File.ReadAllText(sumPath)))
            {
                throw new IOException("The download is damaged (checksum mismatch). Nothing was changed.");
            }
        }

        Status("EXTRACT");
        TryDelete(() => Directory.Delete(staging, true));
        Directory.CreateDirectory(staging);
        // ditto keeps what an application needs: links, permissions, signatures.
        RunTool("/usr/bin/ditto", "-x", "-k", zip, staging);
        string staged = StagedApp(staging, ReadManifestString(localManifest, "player_launcher", "mpv-animejanai"));
        RunTool("/usr/bin/codesign", "--verify", "--deep", staged);
        // Downloaded by this program, not by a browser: no quarantine expected; removed if any.
        TryDelete(() => RunTool("/usr/bin/xattr", "-dr", "com.apple.quarantine", staged));

        bool playerOpen = playerPid > 0 && IsRunning(playerPid);
        Status($"READY {release.Tag}");
        if (playerPid > 0 && !WaitForPid(playerPid, TimeSpan.FromSeconds(90)))
        {
            Status("FAILED The player did not close. Nothing was changed.");
            return 1;
        }
        // The file the player was on when it closed, left by its script next to the status.
        if (statusPath is not null && File.Exists(statusPath + ".reopen"))
        {
            reopen = File.ReadAllText(statusPath + ".reopen").Trim();
        }
        ReplaceBundle(staged, app);
        Status($"DONE {release.Tag}");
        // A player closed by the user during the download is not opened again.
        if (!args.Contains("--no-relaunch") && (playerOpen || playerPid == 0))
        {
            var open = new ProcessStartInfo { FileName = "/usr/bin/open", UseShellExecute = false };
            open.ArgumentList.Add("-n");
            open.ArgumentList.Add(app);
            if (!string.IsNullOrEmpty(reopen))
            {
                open.ArgumentList.Add("--args");
                open.ArgumentList.Add(reopen);
            }
            try { Process.Start(open)?.Dispose(); }
            catch (Exception e) { Console.WriteLine($"Could not relaunch the player: {e.Message}"); }
        }
        return 0;
    }
    catch (Exception e)
    {
        Status("FAILED " + e.Message.Replace('\n', ' '));
        return 1;
    }
    finally
    {
        TryDelete(() => Directory.Delete(work, true));
        TryDelete(() => Directory.Delete(staging, true));
        if (statusPath is not null)
        {
            TryDelete(() => File.Delete(statusPath + ".reopen"));
        }
    }
}

static void RunTool(string tool, params string[] arguments)
{
    var psi = new ProcessStartInfo
    {
        FileName = tool,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    foreach (var a in arguments)
    {
        psi.ArgumentList.Add(a);
    }
    using var p = Process.Start(psi) ?? throw new InvalidOperationException($"Failed to start {tool}");
    var output = p.StandardOutput.ReadToEndAsync();
    string err = p.StandardError.ReadToEnd();
    output.Wait();
    p.WaitForExit();
    if (p.ExitCode != 0)
    {
        throw new InvalidOperationException($"{Path.GetFileName(tool)} failed (exit {p.ExitCode}): {err.Trim()}");
    }
}

static bool IsRunning(int pid)
{
    try
    {
        using var p = Process.GetProcessById(pid);
        return !p.HasExited;
    }
    catch (ArgumentException) { return false; }
    catch (InvalidOperationException) { return false; }
}

static bool WaitForPid(int pid, TimeSpan timeout)
{
    var sw = Stopwatch.StartNew();
    while (IsRunning(pid))
    {
        if (sw.Elapsed > timeout) return false;
        Thread.Sleep(200);
    }
    return true;
}

// The application a path is inside ("…/X.app/Contents/…"), or null.
static string? BundleOf(string path)
{
    string full = Path.GetFullPath(path).TrimEnd('/');
    int at = full.LastIndexOf(".app/Contents", StringComparison.Ordinal);
    if (at < 0) return null;
    string rest = full[(at + ".app/Contents".Length)..];
    return rest.Length == 0 || rest[0] == '/' ? full[..(at + ".app".Length)] : null;
}

// The release's application for this platform, or null when it is not published (yet).
static Asset? MacAsset(Release release, string suffix) =>
    release.Assets.FirstOrDefault(a => a.Name.EndsWith(suffix, StringComparison.Ordinal) &&
                                       a.Name.Contains(release.Tag, StringComparison.Ordinal));

// Why the application (macOS) or the AppImage (Linux) cannot be replaced where it is, or null.
//   translocated: opened from the downloads folder before being moved, macOS runs a read-only
//                 copy from a temporary place; the real application is somewhere else.
//   readonly:     the folder that holds it cannot be written to.
static string? MacBlocked(string app)
{
    if (app.Contains("/AppTranslocation/", StringComparison.Ordinal)) return "translocated";
    string probe = Path.Combine(Path.GetDirectoryName(app)!, ".AnimeJaNai-write-" + Guid.NewGuid().ToString("N"));
    try
    {
        Directory.CreateDirectory(probe);
        Directory.Delete(probe);
        return null;
    }
    catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return "readonly"; }
}

static string MacBlockedText(string reason) => reason == "translocated"
    ? "macOS is running a temporary copy of the application. Move it to the Applications folder with the Finder, open it from there, then update."
    : "The folder that holds the application cannot be written to. Move the application to the Applications folder, then update.";

// "<hex>  name" or "<hex>": the first word is the SHA-256 of the file.
static bool ChecksumMatches(string file, string published)
{
    string expected = published.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";
    using var input = File.OpenRead(file);
    string actual = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(input));
    return expected.Length == 64 && actual.Equals(expected, StringComparison.OrdinalIgnoreCase);
}

// The application an archive unpacked into `staging`: exactly one, with its launcher.
static string StagedApp(string staging, string launcher)
{
    var apps = Directory.GetDirectories(staging, "*.app");
    if (apps.Length != 1)
    {
        throw new InvalidOperationException("The downloaded archive does not hold one application. Nothing was changed.");
    }
    if (!File.Exists(Path.Combine(apps[0], "Contents", "MacOS", launcher)))
    {
        throw new InvalidOperationException("The downloaded application is incomplete. Nothing was changed.");
    }
    return apps[0];
}

// Puts `staged` in the place of `app` (same folder, so two renames). The old application is
// only removed once the new one is in place; if the new one cannot be moved in, the old one
// is put back.
static void ReplaceBundle(string staged, string app)
{
    string previous = Path.Combine(Path.GetDirectoryName(app)!, "." + Path.GetFileName(app) + ".previous");
    if (Directory.Exists(previous))
    {
        Directory.Delete(previous, true);
    }
    Directory.Move(app, previous);
    try
    {
        Directory.Move(staged, app);
    }
    catch
    {
        Directory.Move(previous, app);
        throw;
    }
    // This program is inside the old application: removed while it runs, which macOS allows.
    TryDelete(() => Directory.Delete(previous, true));
}

async Task<int> ApplyAsync()
{
    // The launching lua quits mpv right after starting us; wait for it to release file locks.
    WaitForProcessExit(Path.GetFileNameWithoutExtension(playerExe), TimeSpan.FromSeconds(30));

    var release = await GetLatestReleaseAsync();
    string local = ReadLocalVersion();
    if (!IsNewer(release.Tag, local))
    {
        Console.WriteLine($"Already up to date (v{local}). Relaunching mpv.");
        RelaunchMpv();
        return 0;
    }

    Console.WriteLine($"Updating from v{local} to v{release.Tag}...");
    string work = Path.Combine(Path.GetTempPath(), $"animejanai-update-{release.Tag}");
    Directory.CreateDirectory(work);
    string staging = Path.Combine(work, "staging");

    try
    {
        bool overlay = await IsOverlaySufficientAsync(release, work);
        Console.WriteLine(overlay
            ? "Heavy dependencies unchanged — downloading lightweight overlay update."
            : "Dependencies changed — downloading full package (this is large).");

        string archiveEntry = overlay
            ? await DownloadOverlayAsync(release, work)
            : await DownloadFullAsync(release, work);

        Console.WriteLine("Extracting...");
        Extract(archiveEntry, staging);

        // For the full package the archive root is the versioned folder; the overlay is flat.
        string sourceRoot = overlay ? staging : FindVersionedRoot(staging);

        BackupInputConf(local);
        // The versions of the packs before the update: InstallComponentAsync compares with them to
        // skip the packs that did not change.
        if (File.Exists(localManifest))
        {
            File.Copy(localManifest, Path.Combine(installDir, "manifest.prev.json"), true);
        }
        Console.WriteLine("Applying update (your animejanai.conf, mpv-user.conf and added models are kept)...");
        ApplyOver(sourceRoot, installDir, overlay);
        Console.WriteLine("Updating the components that changed...");
        await RefreshPacksAsync();

        Console.WriteLine($"Update to v{release.Tag} complete.");
    }
    finally
    {
        TryDelete(() => Directory.Delete(work, true));
    }

    // Migrate the user-preserved mpv.conf now that the new managed file is in
    // place (ApplyOver above copied it), BEFORE the relaunch reads config, so a
    // config-layout migration never waits for the next --check. Idempotent.
    MigrateMpvConfProfile();
    RelaunchMpv();
    return 0;
}

// ---- update decision -----------------------------------------------------------------------

// Overlay is enough when the latest release's heavy deps match the installed manifest's deps.
async Task<bool> IsOverlaySufficientAsync(Release release, string work)
{
    string manifestName = isWinRid ? "manifest.json" : $"manifest-{platformRid}.json";
    var asset = release.Assets.FirstOrDefault(a => a.Name == manifestName)
                ?? release.Assets.FirstOrDefault(a => a.Name == "manifest.json");
    if (asset is null)
    {
        return false; // no manifest published -> play safe with a full update
    }

    string remotePath = Path.Combine(work, "manifest.remote.json");
    await DownloadFileAsync(asset.Url, remotePath, _ => { });

    string? localDeps = ReadDepsRaw(Path.Combine(installDir, "manifest.json"));
    string? remoteDeps = ReadDepsRaw(remotePath);
    if (localDeps != null && remoteDeps != null && localDeps == remoteDeps)
    {
        return true;
    }
    // What a pack delivers (TensorRT, RIFE, the models, the Manager...) is brought up to date by
    // the pack itself after the overlay (RefreshPacksAsync): only the other dependencies call for
    // the full package.
    PackIndex? index = null;
    try { index = await ReleasePackIndexAsync(release); } catch { /* no index: compare everything */ }
    if (index is null)
    {
        return false;
    }
    var byPacks = index.Packs.Where(p => p.Dep is not null).Select(p => p.Dep!).ToHashSet();
    var local = ManifestDeps(Path.Combine(installDir, "manifest.json"));
    var remote = ManifestDeps(remotePath);
    if (local.Count == 0 || remote.Count == 0)
    {
        return false;
    }
    bool Same(Dictionary<string, string> a, Dictionary<string, string> b) =>
        a.Where(kv => !byPacks.Contains(kv.Key)).All(kv => b.TryGetValue(kv.Key, out var v) && v == kv.Value);
    return Same(local, remote) && Same(remote, local);
}

static Dictionary<string, string> ManifestDeps(string manifestPath)
{
    var deps = new Dictionary<string, string>();
    try
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (doc.RootElement.TryGetProperty("deps", out var node) && node.ValueKind == JsonValueKind.Object)
        {
            foreach (var p in node.EnumerateObject())
            {
                deps[p.Name] = p.Value.ValueKind == JsonValueKind.String ? p.Value.GetString() ?? "" : p.Value.GetRawText();
            }
        }
    }
    catch { /* missing/unreadable manifest -> empty */ }
    return deps;
}

// After an update: the packs of this installation whose content changed are downloaded again -
// the core packs (Manager, models) and the components the user installed (TensorRT, RIFE...).
// Unchanged ones are skipped by InstallComponentAsync. A failure leaves the previous version of
// that pack in place and does not undo the update.
async Task RefreshPacksAsync()
{
    PackIndex index;
    try { index = await GetPackIndexAsync(); }
    catch (Exception e)
    {
        Console.WriteLine($"Components not checked: {e.Message}");
        return;
    }
    var installed = ReadInstalledComponents(index);
    foreach (var pack in index.Packs.Where(p => p.Core || installed.ContainsKey(p.Name)))
    {
        try
        {
            await InstallComponentAsync(pack.Name);
        }
        catch (Exception e)
        {
            Console.WriteLine($"{pack.Name} not updated: {e.Message}");
        }
    }
}

// The packs an update to this release would download again, with their size: the core packs and
// the installed components whose version changes. Shown by the player with the update offer.
async Task<List<(Pack Pack, string From, string To)>> ChangedPacksAsync(Release release)
{
    var changed = new List<(Pack, string, string)>();
    string manifestName = isWinRid ? "manifest.json" : $"manifest-{platformRid}.json";
    var asset = release.Assets.FirstOrDefault(a => a.Name == manifestName);
    var index = await ReleasePackIndexAsync(release);
    if (asset is null || index is null)
    {
        return changed;
    }
    string remotePath = Path.Combine(Path.GetTempPath(), $"animejanai-manifest-{release.Tag}.json");
    await DownloadFileAsync(asset.Url, remotePath, _ => { });
    var local = ManifestDeps(localManifest);
    var remote = ManifestDeps(remotePath);
    TryDelete(() => File.Delete(remotePath));
    var installed = ReadInstalledComponents(index);
    // An AppImage brings its core packs inside the new AppImage.
    bool appImage = Environment.GetEnvironmentVariable("ANIMEJANAI_APPIMAGE") == "1";
    foreach (var pack in index.Packs.Where(p => p.Dep is not null && (p.Core ? !appImage : installed.ContainsKey(p.Name))))
    {
        local.TryGetValue(pack.Dep!, out var from);
        remote.TryGetValue(pack.Dep!, out var to);
        if ((from ?? "") != (to ?? ""))
        {
            changed.Add((pack, from ?? "", to ?? ""));
        }
    }
    return changed;
}

static string ReadManifestString(string manifestPath, string key, string fallback)
{
    try
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (doc.RootElement.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String)
        {
            var s = v.GetString();
            if (!string.IsNullOrEmpty(s)) return s;
        }
    }
    catch { /* missing/unreadable manifest -> fallback */ }
    return fallback;
}

static string? ReadDepsRaw(string manifestPath)
{
    try
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(manifestPath));
        return doc.RootElement.TryGetProperty("deps", out var deps) ? deps.GetRawText() : null;
    }
    catch
    {
        return null;
    }
}

// One heavy-dependency version out of a manifest's deps (e.g. "inference_runtime", "rife").
// "" if the manifest/key is missing - used to decide whether an already-present component pack's
// content is unchanged and the download can be skipped.
static string ReadManifestDep(string manifestPath, string depKey)
{
    try
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (doc.RootElement.TryGetProperty("deps", out var deps) &&
            deps.TryGetProperty(depKey, out var v) && v.ValueKind == JsonValueKind.String)
        {
            return v.GetString() ?? "";
        }
    }
    catch { /* missing/unreadable manifest -> "" */ }
    return "";
}

// ---- downloads -----------------------------------------------------------------------------

async Task<string> DownloadOverlayAsync(Release release, string work)
{
    // The overlay archive is a .7z on both platforms (extracted with the
    // manifest's archive_tool: 7za.exe / 7zz). Pick our platform's asset.
    var asset = release.Assets.FirstOrDefault(a => Regex.IsMatch(a.Name, @"overlay-.*\.7z$") && RidMatch(a.Name))
        ?? throw new InvalidOperationException("No overlay asset found on the latest release.");
    string dest = Path.Combine(work, asset.Name);
    await DownloadWithProgress(asset, dest);
    return dest;
}

async Task<string> DownloadFullAsync(Release release, string work)
{
    if (!isWinRid)
    {
        // Linux full package is a single zstd tarball (…-<rid>.tar.zst).
        var tar = release.Assets.FirstOrDefault(a =>
                Regex.IsMatch(a.Name, $@"{Regex.Escape(platformRid)}\.tar\.zst$"))
            ?? throw new InvalidOperationException("No full-package tarball found on the latest release.");
        string tarDest = Path.Combine(work, tar.Name);
        await DownloadWithProgress(tar, tarDest);
        return tarDest;
    }

    // Windows full package is a multi-volume .7z (full-package-*.7z.001/.002/...).
    var parts = release.Assets
        .Where(a => a.Name.Contains("full-package-") && Regex.IsMatch(a.Name, @"\.7z\.\d+$"))
        .OrderBy(a => a.Name)
        .ToList();
    if (parts.Count == 0)
    {
        throw new InvalidOperationException("No full-package assets found on the latest release.");
    }

    foreach (var part in parts)
    {
        await DownloadWithProgress(part, Path.Combine(work, part.Name));
    }
    // 7z auto-discovers the remaining volumes from the first part.
    return Path.Combine(work, parts[0].Name);
}

async Task DownloadWithProgress(Asset asset, string dest)
{
    double last = -10;
    Console.WriteLine($"Downloading {asset.Name}...");
    await DownloadFileAsync(asset.Url, dest, p =>
    {
        if (p >= last + 5)
        {
            Console.WriteLine($"  {asset.Name}: {p}%");
            last = p;
        }
    });
}

// ---- extraction / apply --------------------------------------------------------------------

void Extract(string archiveEntry, string outDir)
{
    Directory.CreateDirectory(outDir);
    // The Linux full package is a zstd tarball; the overlay (.7z) and the
    // Windows archives extract with the manifest's archive_tool.
    bool isTar = archiveEntry.EndsWith(".tar.zst", StringComparison.OrdinalIgnoreCase);
    string tool = isTar ? "tar" : Path.Combine(installDir, archiveTool);
    string toolArgs = isTar
        ? $"--zstd -xf \"{archiveEntry}\" -C \"{outDir}\""
        : $"x \"{archiveEntry}\" -o\"{outDir}\" -snl -y";   // -snl: restore symlinks as links
    var psi = new ProcessStartInfo
    {
        FileName = tool,
        Arguments = toolArgs,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true,
    };
    using var p = Process.Start(psi) ?? throw new InvalidOperationException($"Failed to start {tool}");
    string err = p.StandardError.ReadToEnd();
    p.StandardOutput.ReadToEnd();
    p.WaitForExit();
    if (p.ExitCode != 0)
    {
        throw new InvalidOperationException($"7z extraction failed (exit {p.ExitCode}): {err}");
    }
}

string FindVersionedRoot(string staging)
{
    var dir = Directory.GetDirectories(staging)
        .FirstOrDefault(d => Path.GetFileName(d).StartsWith("mpv-upscale-2x_animejanai-v"));
    return dir ?? staging;
}

// Copy the freshly-extracted tree over the install. user_preserve paths from the local manifest are
// never overwritten (relevant only to a full update — the overlay archive doesn't contain them).
void ApplyOver(string sourceRoot, string targetRoot, bool overlay)
{
    var preserve = ReadUserPreserve(Path.Combine(targetRoot, "manifest.json"));

    // Self-update: a running exe can't be overwritten, but it can be renamed out of the way first.
    // Derive the name from the running process so this works whether it's AnimeJaNaiUpdater.exe
    // (Windows) or AnimeJaNaiUpdater (Linux).
    string ownExe = Environment.ProcessPath ?? "";
    string ownName = string.IsNullOrEmpty(ownExe) ? "" : Path.GetFileName(ownExe);
    string newUpdater = Path.Combine(sourceRoot, ownName);
    if (!string.IsNullOrEmpty(ownExe) && File.Exists(newUpdater) &&
        Path.GetFullPath(ownExe).Equals(Path.GetFullPath(Path.Combine(targetRoot, ownName)), StringComparison.OrdinalIgnoreCase))
    {
        string old = ownExe + ".old";
        TryDelete(() => File.Delete(old));
        TryDelete(() => File.Move(ownExe, old));
    }

    CopyTree(sourceRoot, targetRoot, sourceRoot, preserve);
}

void CopyTree(string srcDir, string dstDir, string sourceRoot, HashSet<string> preserve)
{
    Directory.CreateDirectory(dstDir);

    foreach (var file in Directory.GetFiles(srcDir))
    {
        string rel = NormalizeRel(Path.GetRelativePath(sourceRoot, file));
        if (IsPreserved(rel, preserve) && File.Exists(Path.Combine(dstDir, Path.GetFileName(file))))
        {
            continue;
        }
        string dst = Path.Combine(dstDir, Path.GetFileName(file));
        TryDelete(() => { if (File.Exists(dst)) File.SetAttributes(dst, FileAttributes.Normal); });
        File.Copy(file, dst, true);
    }

    foreach (var sub in Directory.GetDirectories(srcDir))
    {
        string rel = NormalizeRel(Path.GetRelativePath(sourceRoot, sub));
        // Profile banks are seeded only when missing, including in preserved older trees.
        if (IsPreserved(rel, preserve) && !rel.StartsWith("portable_config/profiles", StringComparison.OrdinalIgnoreCase))
        {
            continue;
        }
        CopyTree(sub, Path.Combine(dstDir, Path.GetFileName(sub)), sourceRoot, preserve);
    }
}

static bool IsPreserved(string rel, HashSet<string> preserve)
{
    foreach (var p in preserve)
    {
        if (rel == p || rel.StartsWith(p + "/", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }
    }
    return false;
}

static string NormalizeRel(string rel) => rel.Replace('\\', '/');

static HashSet<string> ReadUserPreserve(string manifestPath)
{
    var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    try
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (doc.RootElement.TryGetProperty("user_preserve", out var arr))
        {
            foreach (var e in arr.EnumerateArray())
            {
                var v = e.GetString();
                if (!string.IsNullOrEmpty(v)) set.Add(NormalizeRel(v));
            }
        }
    }
    catch { /* if unreadable, preserve nothing extra — overlay path is unaffected */ }
    return set;
}

void BackupInputConf(string oldVersion)
{
    string input = Path.Combine(installDir, "portable_config", "input.conf");
    if (File.Exists(input))
    {
        string bak = Path.Combine(installDir, "portable_config", $"input.conf.bak-{oldVersion}");
        TryDelete(() => File.Delete(bak));
        try { File.Copy(input, bak, true); }
        catch (Exception e) { Console.WriteLine($"  (could not back up input.conf: {e.Message})"); }
    }
}

// ---- helpers -------------------------------------------------------------------------------

string ReadLocalVersion()
{
    string path = Path.Combine(installDir, "version.txt");
    return File.Exists(path) ? File.ReadAllText(path).Trim() : "0.0.0";
}

Task<Release> GetLatestReleaseAsync() => GetReleaseAsync(apiLatest);

// A test/core-only package may reuse an explicitly pinned component release
// when its inference/runtime/model dependencies are unchanged. Normal packages
// omit this field and resolve components against their own installed version.
string ReadComponentVersion() => ReadManifestString(
    localManifest, "component_package_version", ReadLocalVersion()).Trim();

Task<Release> GetInstalledReleaseAsync()
{
    string tag = ReadComponentVersion();
    if (string.IsNullOrWhiteSpace(tag) || tag == "0.0.0")
    {
        throw new InvalidOperationException(
            "Cannot select component packs: the installed component version is missing or empty.");
    }
    return GetReleaseAsync($"https://api.github.com/repos/{Repo}/releases/tags/{Uri.EscapeDataString(tag)}");
}

// A release and its files, read from GitHub's pages. The API gives one internet address sixty
// anonymous requests an hour, shared by everything behind that address (other computers of
// the house, other customers of a provider that shares its addresses): once they are spent
// every check fails. The page of the latest release redirects to its tag, and the list of a
// release's files is a page too. tag: null for the latest release.
async Task<Release> PagesReleaseAsync(string? tag)
{
    using var client = NewClient();
    if (tag is null)
    {
        using var page = await client.SendAsync(new HttpRequestMessage(HttpMethod.Head, $"https://github.com/{Repo}/releases/latest"));
        string address = page.RequestMessage?.RequestUri?.AbsolutePath ?? "";
        const string marker = "/releases/tag/";
        int at = address.IndexOf(marker, StringComparison.Ordinal);
        if (!page.IsSuccessStatusCode || at < 0)
        {
            throw new InvalidOperationException("The page of the latest release did not lead to a release.");
        }
        tag = Uri.UnescapeDataString(address[(at + marker.Length)..].Trim('/'));
    }
    using var listing = await client.GetAsync($"https://github.com/{Repo}/releases/expanded_assets/{Uri.EscapeDataString(tag)}");
    if (!listing.IsSuccessStatusCode)
    {
        throw new InvalidOperationException($"The files of release {tag} could not be listed.");
    }
    string html = await listing.Content.ReadAsStringAsync();
    var assets = new List<Asset>();
    foreach (Match m in Regex.Matches(html, "href=\"(/" + Regex.Escape(Repo) + "/releases/download/[^\"]+)\""))
    {
        string path = System.Net.WebUtility.HtmlDecode(m.Groups[1].Value);
        string name = Uri.UnescapeDataString(path[(path.LastIndexOf('/') + 1)..]);
        if (!assets.Any(a => a.Name == name))
        {
            assets.Add(new Asset(name, "https://github.com" + path));
        }
    }
    if (assets.Count == 0)
    {
        throw new InvalidOperationException($"Release {tag} lists no file.");
    }
    return new Release(tag, assets);
}

// url: the API address of the release (.../releases/latest or .../releases/tags/TAG). The pages
// are asked first; the API is the second way, where the pages are filtered and it is not.
async Task<Release> GetReleaseAsync(string url)
{
    try
    {
        const string byTag = "/releases/tags/";
        int at = url.IndexOf(byTag, StringComparison.Ordinal);
        return await PagesReleaseAsync(at < 0 ? null : Uri.UnescapeDataString(url[(at + byTag.Length)..]));
    }
    catch (Exception e) when (e is HttpRequestException or InvalidOperationException or TaskCanceledException)
    {
    }
    using var client = NewClient();
    using var request = new HttpRequestMessage(HttpMethod.Get, url);
    // Unauthenticated requests are limited per address; a test machine that shares its address
    // (continuous integration) gives a token. Sent to the GitHub API only, never with a download.
    if (Environment.GetEnvironmentVariable("ANIMEJANAI_GITHUB_TOKEN") is { Length: > 0 } token &&
        url.StartsWith("https://api.github.com/", StringComparison.Ordinal))
    {
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);
    }
    using var response = await client.SendAsync(request);
    response.EnsureSuccessStatusCode();
    string json = await response.Content.ReadAsStringAsync();
    using var doc = JsonDocument.Parse(json);
    var root = doc.RootElement;
    string tag = root.GetProperty("tag_name").GetString() ?? "";
    var assets = new List<Asset>();
    if (root.TryGetProperty("assets", out var arr))
    {
        foreach (var a in arr.EnumerateArray())
        {
            assets.Add(new Asset(
                a.GetProperty("name").GetString() ?? "",
                a.GetProperty("browser_download_url").GetString() ?? ""));
        }
    }
    return new Release(tag, assets);
}

void RelaunchMpv()
{
    // Launch through the platform launcher: mpvnet.exe on Windows (shell-exec
    // so file associations/working dir resolve), the mpv-animejanai shell
    // launcher on Linux (sets --config-dir + the bundled library path).
    string launcher = Path.Combine(installDir, playerLauncher);
    if (!File.Exists(launcher))
    {
        return;
    }
    try
    {
        if (OperatingSystem.IsWindows())
        {
            Process.Start(new ProcessStartInfo { FileName = launcher, UseShellExecute = true });
        }
        else
        {
            // ensure the launcher is executable (overlay extraction may have
            // dropped the bit), then start it directly with an absolute path.
            try
            {
                File.SetUnixFileMode(launcher, File.GetUnixFileMode(launcher)
                    | UnixFileMode.UserExecute | UnixFileMode.GroupExecute | UnixFileMode.OtherExecute);
            }
            catch { /* best effort */ }
            Process.Start(new ProcessStartInfo
            {
                FileName = launcher,
                UseShellExecute = false,
                WorkingDirectory = installDir,
            });
        }
    }
    catch (Exception e) { Console.WriteLine($"Could not relaunch mpv: {e.Message}"); }
}

static void WaitForProcessExit(string name, TimeSpan timeout)
{
    var sw = Stopwatch.StartNew();
    while (sw.Elapsed < timeout && Process.GetProcessesByName(name).Length > 0)
    {
        Thread.Sleep(500);
    }
}

static void TryDelete(Action action)
{
    try { action(); } catch { /* best effort */ }
}

// Numeric-dotted semver compare; "3.2.10" > "3.2.9". Falls back to ordinal on non-numeric parts.
static bool IsNewer(string remote, string local)
{
    int[] R = Parse(remote), L = Parse(local);
    for (int i = 0; i < Math.Max(R.Length, L.Length); i++)
    {
        int r = i < R.Length ? R[i] : 0;
        int l = i < L.Length ? L[i] : 0;
        if (r != l) return r > l;
    }
    return false;

    static int[] Parse(string v)
    {
        var parts = v.TrimStart('v', 'V').Split('.');
        var nums = new int[parts.Length];
        for (int i = 0; i < parts.Length; i++)
        {
            nums[i] = int.TryParse(new string(parts[i].TakeWhile(char.IsDigit).ToArray()), out var n) ? n : 0;
        }
        return nums;
    }
}

// ---- component manager ----------------------------------------------------------------------

async Task<PackIndex> GetPackIndexAsync()
{
    string? local = Environment.GetEnvironmentVariable("ANIMEJANAI_PACKS_DIR");
    string json;
    List<Asset> assets;
    if (!string.IsNullOrEmpty(local))
    {
        json = File.ReadAllText(Path.Combine(local, "packs.json"));
        assets = Directory.GetFiles(local, "component-*.7z")
            .Select(f => new Asset(Path.GetFileName(f), f)).ToList();
    }
    else
    {
        // Packs must match this installation, including prereleases and older
        // versions. The latest endpoint is only for updating the application.
        var release = await GetInstalledReleaseAsync();
        return await ReleasePackIndexAsync(release)
            ?? throw new InvalidOperationException(
                $"Release {release.Tag} publishes no component packs (packs.json missing).");
    }
    return ParsePackIndex(json, assets);
}

// The pack index of a release, null when it publishes none.
async Task<PackIndex?> ReleasePackIndexAsync(Release release)
{
    // packs index is RID-suffixed on Linux (packs-linux-x64.json) so it can
    // coexist with the Windows packs.json on a shared release; its "asset"
    // fields already carry the matching component-*-<rid>.7z names.
    string packsName = isWinRid ? "packs.json" : $"packs-{platformRid}.json";
    var idx = release.Assets.FirstOrDefault(a => a.Name == packsName)
        ?? release.Assets.FirstOrDefault(a => a.Name == "packs.json");
    if (idx is null)
    {
        return null;
    }
    using var client = NewClient();
    return ParsePackIndex(await client.GetStringAsync(idx.Url), release.Assets);
}

PackIndex ParsePackIndex(string json, List<Asset> assets)
{

    var packs = new List<Pack>();
    using var doc = JsonDocument.Parse(json);
    foreach (var e in doc.RootElement.GetProperty("packs").EnumerateArray())
    {
        var files = e.GetProperty("files").EnumerateArray()
            .Select(f => f.GetString() ?? "").Where(f => f.Length > 0).ToList();
        string asset = e.GetProperty("asset").GetString() ?? "";
        packs.Add(new Pack(
            e.GetProperty("name").GetString() ?? "",
            asset,
            // A pack unchanged since an earlier release is not published again: its index entry
            // then carries the address of the asset in that earlier release.
            e.TryGetProperty("url", out var reused) && !string.IsNullOrEmpty(reused.GetString())
                ? reused.GetString()
                : assets.FirstOrDefault(a => a.Name == asset)?.Url,
            e.GetProperty("bytes").GetInt64(),
            files,
            e.TryGetProperty("dep", out var d) ? d.GetString() : null,
            e.TryGetProperty("installed_bytes", out var ib) ? ib.GetInt64() : 0,
            e.TryGetProperty("core", out var core) && core.ValueKind == JsonValueKind.True));
    }
    return new PackIndex(
        doc.RootElement.TryGetProperty("package_version", out var v)
            ? v.GetString() ?? "" : "", packs);
}

// Does the pack's content on disk actually match the published pack? components.json records only
// what the updater BELIEVES it installed, and that record can be wrong - e.g. a component whose
// download was skipped or failed while the record was still written, leaving the previous release's
// files in place. That state is self-perpetuating: the record then says "current" forever and the
// real files are never refreshed (this is how a TensorRT 11.0 runtime survived an upgrade to a
// package built for 11.1). Comparing the total extracted size against the index catches it - a
// different upstream build is a different size - and costs only a directory stat.
// Older indexes carry no installed_bytes; there is nothing to verify against, so trust the record.
bool PackContentMatches(Pack pack)
{
    if (pack.InstalledBytes <= 0)
    {
        return true;
    }
    long actual = 0;
    foreach (var f in pack.Files)
    {
        var fi = new FileInfo(Path.Combine(installDir, f));
        if (!fi.Exists)
        {
            return false;
        }
        actual += fi.Length;
    }
    if (actual != pack.InstalledBytes)
    {
        Console.WriteLine($"{pack.Name}: on-disk content does not match the published pack " +
                          $"({actual:N0} vs {pack.InstalledBytes:N0} bytes); reinstalling.");
        return false;
    }
    return true;
}

// Installed state: components.json, else inferred from what's on disk so
// full installs that predate the manager work out of the box.
Dictionary<string, string> ReadInstalledComponents(PackIndex index)
{
    string path = Path.Combine(installDir, "components.json");
    var installed = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    if (File.Exists(path))
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            foreach (var e in doc.RootElement.GetProperty("installed").EnumerateObject())
            {
                installed[e.Name] = e.Value.GetString() ?? "";
            }
            return installed;
        }
        catch { /* fall through to inference */ }
    }
    foreach (var pack in index.Packs.Where(p => !p.Core))
    {
        // a pack counts as installed when all its files exist
        if (pack.Files.Count > 0 &&
            pack.Files.All(f => File.Exists(Path.Combine(installDir, f))))
        {
            installed[pack.Name] = "(pre-manager install)";
        }
    }
    return installed;
}

// JSON written through JsonNode, not reflection: the updater is published trimmed.
void WriteInstalledComponents(Dictionary<string, string> installed)
{
    var list = new JsonObject();
    foreach (var (name, version) in installed)
        list[name] = version;
    File.WriteAllText(Path.Combine(installDir, "components.json"),
        new JsonObject { ["installed"] = list }.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
}

string? PackVersionMismatch(PackIndex index)
{
    string localVersion = ReadComponentVersion();
    return localVersion != "" && index.PackageVersion != "" && localVersion != index.PackageVersion
        ? $"This installation selects component release v{localVersion} but the published packs are for v{index.PackageVersion}."
        : null;
}

// NVIDIA detection via NVML (ships with the driver); its absence means a
// non-NVIDIA GPU, which is exactly the DirectML recommendation.
static (bool HasNvidia, string Sm, string GpuName) DetectGpu()
{
    try
    {
        if (Nvml.nvmlInit_v2() != 0)
        {
            return (false, "", "");
        }
        try
        {
            if (Nvml.nvmlDeviceGetHandleByIndex_v2(0, out var dev) != 0)
            {
                return (false, "", "");
            }
            Nvml.nvmlDeviceGetCudaComputeCapability(dev, out int major, out int minor);
            var name = new byte[96];
            Nvml.nvmlDeviceGetName(dev, name, (uint)name.Length);
            string gpu = System.Text.Encoding.ASCII.GetString(name).TrimEnd('\0');
            return (true, $"sm{major}{minor}", gpu);
        }
        finally { Nvml.nvmlShutdown(); }
    }
    catch
    {
        return (false, "", "");
    }
}

// Hardware-matched packs only. RIFE is a user choice, not a recommendation:
// it is preselected on installs that have never managed components (fresh or
// legacy-full), and once the user has made any component decision their
// choice stands - no nagging after a deliberate removal.
List<string> RecommendedPacks(PackIndex index, bool hasNvidia, string sm)
{
    var rec = new List<string>();
    if (hasNvidia)
    {
        rec.Add("trt-runtime");
        // exact generation pack if published, else the PTX fallback pack
        // (JIT-compiles for newer GPUs than this TensorRT knows)
        rec.Add(index.Packs.Any(p => p.Name == $"trt-{sm}") ? $"trt-{sm}" : "trt-ptx");
    }
    else if (OperatingSystem.IsLinux() && index.Packs.Any(p => p.Name == "onnxruntime") && HasIntelGpu())
    {
        // OpenVINO, through the ONNX Runtime engine, is the engine of Intel GPUs on Linux.
        rec.Add("onnxruntime");
    }
    return rec;
}

static bool HasIntelGpu()
{
    try
    {
        return Directory.GetDirectories("/sys/class/drm", "card*")
            .Select(d => Path.Combine(d, "device", "vendor"))
            .Any(f => File.Exists(f) && File.ReadAllText(f).Trim().Equals("0x8086", StringComparison.OrdinalIgnoreCase));
    }
    catch
    {
        return false;
    }
}

bool ComponentsNeverManaged() => !File.Exists(Path.Combine(installDir, "components.json"));

bool PreselectPack(Pack pack, Dictionary<string, string> installed, List<string> rec) =>
    installed.ContainsKey(pack.Name) || rec.Contains(pack.Name) ||
    (pack.Name == "rife" && ComponentsNeverManaged());

async Task ComponentsAsync(PackIndex? prefetched, bool json = false)
{
    var index = prefetched ?? await GetPackIndexAsync();
    var installed = ReadInstalledComponents(index);
    var (hasNvidia, sm, gpu) = DetectGpu();
    var rec = RecommendedPacks(index, hasNvidia, sm);
    if (json)
    {
        // consumed by the AnimeJaNai Manager GUI; keep keys stable
        var packs = new JsonArray();
        foreach (var p in index.Packs.Where(p => !p.Core))
        {
            packs.Add((JsonNode)new JsonObject
            {
                ["name"] = p.Name,
                ["bytes"] = p.Bytes,
                ["installed"] = installed.ContainsKey(p.Name),
                ["recommended"] = rec.Contains(p.Name),
                ["preselect"] = PreselectPack(p, installed, rec),
            });
        }
        Console.WriteLine(new JsonObject
        {
            ["package_version"] = index.PackageVersion,
            ["version_mismatch"] = PackVersionMismatch(index),
            ["gpu"] = new JsonObject { ["nvidia"] = hasNvidia, ["sm"] = sm, ["name"] = gpu },
            ["packs"] = packs,
        }.ToJsonString());
        return;
    }
    if (PackVersionMismatch(index) is string warn)
    {
        Console.WriteLine(warn);
        Console.WriteLine();
    }
    Console.WriteLine(hasNvidia
        ? $"GPU: {gpu} ({sm}) - TensorRT recommended"
        : "GPU: no NVIDIA device detected - DirectML (in the core install) covers AMD/Intel");
    Console.WriteLine($"Recommended packs: {string.Join(", ", rec)}");
    Console.WriteLine();
    foreach (var pack in index.Packs.Where(p => !p.Core))
    {
        string state = installed.ContainsKey(pack.Name) ? "installed" :
                       rec.Contains(pack.Name) ? "RECOMMENDED" :
                       PreselectPack(pack, installed, rec) ? "default on new installs" :
                       "available";
        Console.WriteLine($"  {pack.Name,-14} {pack.Bytes / 1048576,6} MB  {state}");
    }
}

async Task<int> InstallComponentAsync(string name)
{
    if (string.IsNullOrEmpty(name))
    {
        Console.WriteLine("--install needs a pack name (see --components)");
        return 2;
    }
    var index = await GetPackIndexAsync();
    var pack = index.Packs.FirstOrDefault(p => p.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
    if (pack is null)
    {
        Console.WriteLine($"Unknown pack '{name}'. Available: {string.Join(", ", index.Packs.Select(p => p.Name))}");
        return 2;
    }
    if (pack.Url is null)
    {
        Console.WriteLine($"Pack '{name}' has no downloadable asset on the selected release.");
        return 1;
    }
    if (PackVersionMismatch(index) is string warn)
    {
        // a pack from a different release can mismatch the installed aji/TensorRT builds
        Console.WriteLine(warn);
        Console.WriteLine("Update first (AnimeJaNaiUpdater.exe --apply), then install components.");
        return 1;
    }

    // Skip the (large) download when the identical content is already on disk: every file the pack
    // ships is present AND the upstream version that governs it is unchanged. That version is the
    // manifest dep the build tagged the pack with (inference_runtime for TensorRT, rife for RIFE).
    // We treat it as unchanged when the just-installed core's manifest (target) matches either the
    // snapshot the setup installer leaves of the pre-upgrade manifest (manifest.prev.json - the
    // bootstrap for the first upgrade off an install that recorded only the package version) or the
    // dep version components.json recorded on a prior managed install. A future TensorRT/RIFE bump
    // changes the dep, so this correctly re-downloads then; a different GPU's builder-resource pack
    // has files that aren't present, so it isn't skipped either.
    string target = pack.Dep is null ? "" : ReadManifestDep(localManifest, pack.Dep);
    bool filesPresent = pack.Files.Count > 0 &&
        pack.Files.All(f => File.Exists(Path.Combine(installDir, f)));
    if (filesPresent && target != "" && PackContentMatches(pack))
    {
        string prev = pack.Dep is null ? "" :
            ReadManifestDep(Path.Combine(installDir, "manifest.prev.json"), pack.Dep);
        var current = ReadInstalledComponents(index);
        current.TryGetValue(pack.Name, out var recorded);
        if (prev == target || recorded == target)
        {
            if (!pack.Core)
            {
                current[pack.Name] = target;
                WriteInstalledComponents(current);
            }
            Console.WriteLine($"{pack.Name} already up to date ({target}); skipping download.");
            return 0;
        }
    }

    string work = Path.Combine(Path.GetTempPath(), "animejanai-packs");
    Directory.CreateDirectory(work);
    string archive = Path.Combine(work, pack.Asset);
    if (pack.Url.Contains("://"))
    {
        await DownloadWithProgress(new Asset(pack.Asset, pack.Url), archive);
    }
    else
    {
        File.Copy(pack.Url, archive, true); // ANIMEJANAI_PACKS_DIR dev path
    }
    Console.WriteLine($"Installing {pack.Name}...");
    Extract(archive, installDir);
    TryDelete(() => File.Delete(archive));

    if (!pack.Core)
    {
        var installed = ReadInstalledComponents(index);
        // Record the dep version (not the package version) so a later reinstall can tell whether
        // this pack's content actually changed; fall back to the package version for an untagged pack.
        installed[pack.Name] = target != "" ? target : index.PackageVersion;
        WriteInstalledComponents(installed);
    }
    Console.WriteLine($"{pack.Name} installed.");
    return 0;
}

int RemoveComponent(string name)
{
    var index = GetPackIndexAsync().GetAwaiter().GetResult();
    var pack = index.Packs.FirstOrDefault(p => p.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
    if (pack is null)
    {
        Console.WriteLine($"Unknown pack '{name}'. Available: {string.Join(", ", index.Packs.Select(p => p.Name))}");
        return 2;
    }
    if (pack.Core)
    {
        Console.WriteLine($"{pack.Name} is part of every installation and cannot be removed.");
        return 2;
    }
    int gone = 0;
    foreach (var f in pack.Files)
    {
        string abs = Path.Combine(installDir, f);
        if (File.Exists(abs))
        {
            TryDelete(() => { File.SetAttributes(abs, FileAttributes.Normal); File.Delete(abs); });
            gone++;
        }
    }
    var installed = ReadInstalledComponents(index);
    installed.Remove(pack.Name);
    WriteInstalledComponents(installed);
    Console.WriteLine($"{pack.Name} removed ({gone} files). Engine caches and models you added are untouched.");
    return 0;
}

async Task<int> AutoComponentsAsync()
{
    var index = await GetPackIndexAsync();
    var (hasNvidia, sm, gpu) = DetectGpu();
    var rec = RecommendedPacks(index, hasNvidia, sm);
    var installed = ReadInstalledComponents(index);
    // "Needs installing" is not just "absent": a pack already recorded as installed is stale when
    // the dep that governs it moved (a TensorRT/RIFE bump) or when its files on disk are not this
    // pack's content. Without this, --auto reports "everything is installed" after an upgrade and
    // the old runtime is kept forever; InstallComponentAsync re-checks and still skips genuine no-ops.
    var missing = index.Packs
        .Where(p => !p.Core && PreselectPack(p, installed, rec))
        .Where(p => !installed.TryGetValue(p.Name, out var recorded) ||
                    (p.Dep is not null && ReadManifestDep(localManifest, p.Dep) is string t &&
                     t != "" && recorded != t) ||
                    !PackContentMatches(p))
        .Select(p => p.Name).ToList();
    if (missing.Count == 0)
    {
        Console.WriteLine("Everything the detected hardware needs is already installed.");
        await ComponentsAsync(index, false);
        return 0;
    }
    Console.WriteLine($"Installing for {(hasNvidia ? gpu : "DirectML-class GPU")}: {string.Join(", ", missing)}");
    foreach (var name in missing)
    {
        int rc = await InstallComponentAsync(name);
        if (rc != 0)
        {
            return rc;
        }
    }
    return 0;
}

// Hardware summary for the setup installer's component picker, as trivially
// parseable KEY=value lines (Inno Setup has no JSON parser). GPU identity is
// local NVML and always available; TRT_PACKS needs the pack index (network or
// ANIMEJANAI_PACKS_DIR) - if that fails it is emitted empty and the installer
// falls back to a generic TensorRT toggle.
async Task<int> RecommendAsync()
{
    var (hasNvidia, sm, gpu) = DetectGpu();
    Console.WriteLine($"NVIDIA={(hasNvidia ? 1 : 0)}");
    Console.WriteLine($"GPU={gpu}");
    string trtPacks = "";
    string rife = "rife";
    try
    {
        var index = await GetPackIndexAsync();
        trtPacks = string.Join(",", RecommendedPacks(index, hasNvidia, sm));
        if (!index.Packs.Any(p => p.Name == "rife"))
        {
            rife = "";
        }
    }
    catch
    {
        // offline / no published packs yet: GPU lines still printed; the
        // installer keeps the TensorRT toggle and resolves packs at install
        // time (when network is needed anyway to download them).
    }
    Console.WriteLine($"TRT_PACKS={trtPacks}");
    Console.WriteLine($"RIFE={rife}");
    return 0;
}

static HttpClient NewClient()
{
    var client = new HttpClient();
    client.DefaultRequestHeaders.UserAgent.ParseAdd("AnimeJaNaiUpdater");
    return client;
}

static class Nvml
{
    [System.Runtime.InteropServices.DllImport("nvml.dll")]
    public static extern int nvmlInit_v2();
    [System.Runtime.InteropServices.DllImport("nvml.dll")]
    public static extern int nvmlShutdown();
    [System.Runtime.InteropServices.DllImport("nvml.dll")]
    public static extern int nvmlDeviceGetHandleByIndex_v2(uint index, out IntPtr device);
    [System.Runtime.InteropServices.DllImport("nvml.dll")]
    public static extern int nvmlDeviceGetCudaComputeCapability(IntPtr device, out int major, out int minor);
    [System.Runtime.InteropServices.DllImport("nvml.dll")]
    public static extern int nvmlDeviceGetName(IntPtr device, byte[] name, uint length);
}

record Release(string Tag, List<Asset> Assets);
record Asset(string Name, string Url);
// InstalledBytes: the pack's total size once extracted (sum of its files on disk). Used to verify
// that what is on disk really is this pack's content, since components.json bookkeeping alone can
// be wrong. 0 when the index predates the field (older release) - verification is then skipped.
// Core: a pack that is part of every installation (the Manager, the models). It is published so
// that an update downloads it only when it changed; it is never offered, listed or removed.
record Pack(string Name, string Asset, string? Url, long Bytes, List<string> Files, string? Dep,
            long InstalledBytes = 0, bool Core = false);
record PackIndex(string PackageVersion, List<Pack> Packs);
