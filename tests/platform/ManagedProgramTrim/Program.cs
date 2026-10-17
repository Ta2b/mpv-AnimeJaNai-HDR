using AnimeJaNai.Platform;
ManagedProgramFiles.WriteInventory(args[0]);
var report = ManagedProgramFiles.Sync(args[0], args[1]);
Console.WriteLine($"installed={report.Installed.Count},removed={report.Removed.Count},conflicts={report.Conflicts.Count}");
