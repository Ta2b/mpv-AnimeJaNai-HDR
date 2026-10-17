#!/usr/bin/env python3
"""CPU-only check of real native identity and copied production overlay decision.
Creates a disposable .NET project; never starts the updater or touches an install.
"""
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2];out=Path(sys.argv[1]).resolve();out.mkdir(exist_ok=False)
source=(root/'AnimeJaNaiUpdater/Program.cs').read_text()
def method(signature):
    start=source.index(signature);end=source.index('{',start)+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
methods='\n'.join(method(s) for s in ['async Task<bool> IsOverlaySufficientAsync(', 'static Dictionary<string, string> ManifestDeps(', 'static string? ReadDepsRaw('])
(out/'Production.cs').write_text('''using System.Text.Json;
class Production {
 readonly string installDir,remoteManifest;
 readonly bool isWinRid=false;
 readonly string platformRid="linux-x64";
 public Production(string root,string remote){installDir=root;remoteManifest=remote;}
 Task DownloadFileAsync(string url,string dest,Action<int> progress){File.Copy(remoteManifest,dest,true);return Task.CompletedTask;}
 Task<PackIndex> ReleasePackIndexAsync(Release release)=>Task.FromResult(new PackIndex(release.Tag,
   new List<Pack>{new("models","component-models.7z",null,1,new(),"models")}));
 public Task<bool> Overlay(string work)=>IsOverlaySufficientAsync(new Release("next",new(){new("manifest-linux-x64.json","fixture")}),work);
'''+methods+'\n}\n'+source[source.index('record Release('):])
(out/'LinuxMpvIdentity.cs').write_bytes((root/'BuildMpvUpscale2xAnimeJaNai/LinuxMpvIdentity.cs').read_bytes())
(out/'Checks.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><UseAppHost>false</UseAppHost></PropertyGroup></Project>')
(out/'Program.cs').write_text('''using System.Text.Json;
if(args.Length==1){Console.WriteLine(LinuxMpvIdentity.Capture(args[0]));return;}
string root=Path.Combine(AppContext.BaseDirectory,"fixtures");Directory.CreateDirectory(root);
void Check(bool ok,string why){if(!ok)throw new Exception(why);}
string a=Path.Combine(root,"a"),b=Path.Combine(root,"b");Directory.CreateDirectory(a);Directory.CreateDirectory(b);
foreach(string name in new[]{"mpv","libmpv.so.2","libplacebo.so.1","build-info.txt"})File.WriteAllText(Path.Combine(a,name),"owned-"+name);
foreach(string p in Directory.GetFiles(a).Reverse()){string q=Path.Combine(b,Path.GetFileName(p));File.Copy(p,q);File.SetLastWriteTimeUtc(q,new DateTime(2000,1,1));}
string id=LinuxMpvIdentity.Capture(a);Check(id==LinuxMpvIdentity.Capture(b),"identity depends on path/order/mtime");
foreach(string name in new[]{"mpv","libmpv.so.2","libplacebo.so.1","build-info.txt"}){
 string p=Path.Combine(b,name),original=File.ReadAllText(p);File.AppendAllText(p,"changed");
 Check(id!=LinuxMpvIdentity.Capture(b),"missed change: "+name);File.WriteAllText(p,original);
}
File.Delete(Path.Combine(b,"libmpv.so.2"));bool refused=false;try{LinuxMpvIdentity.Capture(b);}catch(InvalidDataException){refused=true;}
Check(refused,"accepted a missing native reader");
string local=Path.Combine(root,"local"),work=Path.Combine(root,"work");Directory.CreateDirectory(local);Directory.CreateDirectory(work);
string remote=Path.Combine(root,"remote.json");
void Manifest(string path,string native,string models="same")=>File.WriteAllText(path,JsonSerializer.Serialize(new{deps=new{mpvfork=native,models}}));
var app=new Production(local,remote);
Manifest(Path.Combine(local,"manifest.json"),"old-manual-native-label");Manifest(remote,id);
Check(!await app.Overlay(work),"old reader can receive only new scripts");
Manifest(Path.Combine(local,"manifest.json"),id);Manifest(remote,id);
Check(await app.Overlay(work),"script-only release forces native download");
Manifest(remote,id,"new-models-pack");Check(await app.Overlay(work),"pack-managed change forces full native update");
Manifest(remote,id+"changed");Check(!await app.Overlay(work),"native change does not force full package");
Console.WriteLine("PASS: content identity stable across paths/order/mtime; every native/build input invalidates; missing reader refused; actual overlay decision requires a full package for older/changed native readers and retains overlay for unchanged/script/pack-only updates");
''')
print(out/'Checks.csproj')
