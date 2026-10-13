"""Generate an offline .NET test project using current updater methods unchanged.

Usage: python tests/updater-regressions/generate.py OUTPUT_DIRECTORY
Then: dotnet run --project OUTPUT_DIRECTORY/Checks.csproj
The HTTP-client factory is substituted; filesystem operations are real.
"""
from pathlib import Path
import sys

here=Path(__file__).resolve().parent
source=(here.parents[1]/'AnimeJaNaiUpdater/Program.cs').read_text(encoding='utf-8-sig')
out=Path(sys.argv[1]).resolve(); out.mkdir(parents=True,exist_ok=True)
def method(signature):
    start=source.index(signature); end=source.index('{',start)+1; depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}'); end+=1
    return source[start:end]
methods=[method(s) for s in ('void SyncInputConf()', 'string ReadLocalVersion()',
    'static string ReadManifestString(', 'string? PackVersionMismatch(',
    'Task<Release> GetInstalledReleaseAsync()', 'async Task<Release> GetReleaseAsync(string url)',
    'async Task<PackIndex> GetPackIndexAsync()', 'void CopyTree(', 'static bool IsPreserved(', 'static void TryDelete(',
    # macOS: the application is replaced as a whole.
    'static string? BundleOf(', 'static string? MacBlocked(', 'static bool ChecksumMatches(',
    'static string StagedApp(', 'static void ReplaceBundle(', 'async Task<Release> PagesReleaseAsync(',
    'static string AppImageTarget(', 'static string? ListedChecksum(')]
start=source.index('string ReadComponentVersion() =>')
methods.append(source[start:source.index(';',start)+1])
start=source.index('static string NormalizeRel(')
methods.append(source[start:source.index(';',start)+1])
start=source.index('static Asset? MacAsset(')
methods.append(source[start:source.index(';',start)+1])
start=source.index('static Asset? AppImageAsset(')
methods.append(source[start:source.index(';',start)+1])
latest=next(s for s in source.splitlines() if s.startswith('Task<Release> GetLatestReleaseAsync()'))
repo=next(s for s in source.splitlines() if s.startswith('const string Repo ='))
wrapper='''using System.Text.Json;
using System.Text.RegularExpressions;
class Production
{
    private readonly string installDir;
    private string localManifest => Path.Combine(installDir, "manifest.json");
    private readonly HttpMessageHandler handler;
    private readonly bool isWinRid;
    private readonly string platformRid;
    REPO
    private readonly string apiLatest = $"https://api.github.com/repos/{Repo}/releases/latest";
    public Production(string root, HttpMessageHandler handler, bool windows = true)
    { installDir=root; this.handler=handler; isWinRid=windows; platformRid=windows ? "win-x64" : "linux-x64"; }
    HttpClient NewClient() => new HttpClient(handler, disposeHandler:false);
    public void Sync() => SyncInputConf();
    public void Copy(string source, HashSet<string> preserved) => CopyTree(source, installDir, source, preserved);
    public Task<PackIndex> Packs() => GetPackIndexAsync();
    public Task<Release> Latest() => GetLatestReleaseAsync();
    public string? Mismatch(PackIndex index) => PackVersionMismatch(index);
    public static string? Bundle(string path) => BundleOf(path);
    public static Asset? MacApplication(Release release, string suffix) => MacAsset(release, suffix);
    public static string? Blocked(string app) => MacBlocked(app);
    public static bool Checksum(string file, string published) => ChecksumMatches(file, published);
    public static string Staged(string staging, string launcher) => StagedApp(staging, launcher);
    public static void Replace(string staged, string app) => ReplaceBundle(staged, app);
    public static Asset? AppImage(Release release, string rid) => AppImageAsset(release, rid);
    public static string Target(string current, string oldVersion, string newVersion) => AppImageTarget(current, oldVersion, newVersion);
    public static string? Listed(string listing, string name) => ListedChecksum(listing, name);
'''.replace('REPO',repo)
(out/'Production.cs').write_text(wrapper+'\n'.join(methods)+'\n'+latest+'\n}\n'+
    source[source.index('record Release('):],encoding='utf-8')
(out/'Program.cs').write_bytes((here/'Cases.cs').read_bytes())
(out/'Checks.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
  <ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><UseAppHost>false</UseAppHost>
  </PropertyGroup>
</Project>
''',encoding='utf-8')
print(out/'Checks.csproj')
