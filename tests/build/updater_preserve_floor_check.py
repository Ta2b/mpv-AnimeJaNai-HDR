#!/usr/bin/env python3
"""Exercise current apply/preservation code on new CPU-only directories.
No updater executable/network/install is used. Reuses the audit's concluded
missing/corrupt-manifest failure; do not repeat that baseline trial.
"""
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2];out=Path(sys.argv[1]).resolve();out.mkdir(exist_ok=False)
s=(root/'AnimeJaNaiUpdater/Program.cs').read_text()
def method(signature):
    start=s.index(signature);end=s.index('{',start)+1;depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[start:end]
methods='\n'.join(method(x) for x in ['void ApplyOver(', 'void CopyTree(', 'static bool IsPreserved(', 'static HashSet<string> ReadUserPreserve(', 'void BackupInputConf(', 'static void TryDelete('])
a=s.index('        BackupInputConf(local);');b=s.index('        Console.WriteLine("Applying update',a);backup=s[a:b]
(out/'Production.cs').write_text('''using System.Text.Json;
class Production {
 readonly string installDir;
 string localManifest=>Path.Combine(installDir,"manifest.json");
 public Production(string root){installDir=root;}
 static string NormalizeRel(string path)=>path.Replace('\\\\','/');
 public void Apply(string source){string local="fixture-old";
'''+backup+'''ApplyOver(source,installDir,false);}
'''+methods+'\n}\n')
(out/'ManagedProgramFiles.cs').write_bytes((root/'AnimeJaNaiPlatform/ManagedProgramFiles.cs').read_bytes())
(out/'Checks.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><UseAppHost>false</UseAppHost></PropertyGroup></Project>')
(out/'Program.cs').write_text('''using System.Text.Json;
using AnimeJaNai.Platform;
string root=Path.Combine(AppContext.BaseDirectory,"fixtures");Directory.CreateDirectory(root);
void Write(string root,string rel,string text){string p=Path.Combine(root,rel);Directory.CreateDirectory(Path.GetDirectoryName(p)!);File.WriteAllText(p,text);}
void Check(bool ok,string why){if(!ok)throw new Exception(why);}
string[] files={"animejanai/animejanai.conf","portable_config/mpv.conf","portable_config/input.conf","portable_config/saved-props.json","portable_config/settings.xml","portable_config/script-opts/animejanai_hdr_auto.conf","portable_config/profiles/linux-amd/animejanai.conf"};
var results=new List<object>();
foreach(string mode in (args.Length==0?new[]{"missing","corrupt","valid-custom","fresh"}:args.Where(x=>x!="linked"))){
 string target=Path.Combine(root,mode),source=Path.Combine(root,mode+"-package"),old=Path.Combine(root,mode+"-old-programs");
 Directory.CreateDirectory(target);
 foreach(string rel in new[]{"portable_config/scripts/owned.lua","portable_config/scripts/custom.lua"})Write(old,rel,"old program");
 ManagedProgramFiles.WriteInventory(old);ManagedProgramFiles.Sync(old,target);
 Write(target,"portable_config/scripts/custom.lua","user program override");
 foreach(string rel in files)Write(source,rel,"shipped default");
 Write(source,"portable_config/profiles/linux-nvidia/animejanai.conf","new missing bank");
 Write(source,"portable_config/scripts/owned.lua","new managed program");
 Write(source,"portable_config/scripts/custom.lua","new program version");
 Write(source,"custom/prefs.ini","new custom path default");
 Write(source,"manifest.json","{\\"user_preserve\\":[]}");ManagedProgramFiles.WriteInventory(source);
 if(mode!="fresh")foreach(string rel in files)Write(target,rel,"user value "+rel);
 Write(target,"custom/prefs.ini","custom user value");
 Write(target,"animejanai/sdk/private.bin","user SDK");Write(target,"animejanai/onnx/custom-model.onnx","user model");
 if(mode=="corrupt")Write(target,"manifest.json","{broken local metadata");
 if(mode=="valid-custom")Write(target,"manifest.json",JsonSerializer.Serialize(new{user_preserve=new[]{"CuStOm"+(char)92+"prefs.ini"}}));
 new Production(target).Apply(source);
 foreach(string rel in files)Check(File.ReadAllText(Path.Combine(target,rel))==(mode=="fresh"?"shipped default":"user value "+rel),mode+" lost or failed to seed "+rel);
 Check(File.ReadAllText(Path.Combine(target,"portable_config/profiles/linux-nvidia/animejanai.conf"))=="new missing bank","missing bank not seeded");
 Check(File.ReadAllText(Path.Combine(target,"portable_config/scripts/owned.lua"))=="new managed program","managed code not refreshed");
 Check(File.ReadAllText(Path.Combine(target,"portable_config/scripts/custom.lua"))=="user program override","program override lost");
 Check(File.ReadAllText(Path.Combine(target,"animejanai/sdk/private.bin"))=="user SDK"&&File.ReadAllText(Path.Combine(target,"animejanai/onnx/custom-model.onnx"))=="user model","unknown assets changed");
 if(mode=="valid-custom")Check(File.ReadAllText(Path.Combine(target,"custom/prefs.ini"))=="custom user value","valid additional preserve/casing/backslash ignored");
 if(mode=="corrupt")Check(File.ReadAllText(Path.Combine(target,"manifest.prev.json"))=="{broken local metadata","lost raw malformed-manifest backup");
 if(mode!="fresh")Check(File.ReadAllText(Path.Combine(target,"portable_config/input.conf.bak-fixture-old"))=="user value portable_config/input.conf","input backup differs");
 results.Add(new{mode,settings_preserved_or_seeded=true,managed_program_updated=true,override_and_unknown_assets_preserved=true});
}
if(!OperatingSystem.IsWindows()&&(args.Length==0||args.Contains("linked"))){
 string target=Path.Combine(root,"linked"),source=Path.Combine(root,"linked-package"),external=Path.Combine(root,"external");
 Directory.CreateDirectory(Path.Combine(target,"portable_config"));Directory.CreateDirectory(external);
 File.WriteAllText(Path.Combine(external,"original.conf"),"external user data");
 Directory.CreateSymbolicLink(Path.Combine(target,"portable_config/profiles"),external);
 string missing=Path.Combine(external,"must-not-create.conf");File.CreateSymbolicLink(Path.Combine(target,"portable_config/mpv.conf"),missing);
 Write(source,"portable_config/profiles/default/animejanai.conf","shipped profile");Write(source,"portable_config/mpv.conf","shipped config");
 Write(source,"manifest.json","{}");new Production(target).Apply(source);
 Check(new DirectoryInfo(Path.Combine(target,"portable_config/profiles")).LinkTarget==external,"profile link replaced");
 Check(Directory.GetFileSystemEntries(external).Length==1&&!File.Exists(missing),"followed a user profile/config link");
 Check(new FileInfo(Path.Combine(target,"portable_config/mpv.conf")).LinkTarget==missing,"dangling config link replaced");
 results.Add(new{mode="linked",user_links_and_external_data_preserved=true});
}
Console.WriteLine(JsonSerializer.Serialize(new{passed=true,cases=results,scope="current production methods and real managed inventory, CPU fixtures only, no user installation"}));
''')
print(out/'Checks.csproj')
