using AnimeJaNaiConfEditor.ViewModels;
using ReactiveUI.Builder;
using System.Text.Json;

RxAppBuilder.CreateReactiveUIBuilder().WithCoreServices().BuildApp();
var vm = new ReferenceExportViewModel(() => args[0]);
while (Console.ReadLine() is string line)
{
    using var doc = JsonDocument.Parse(line);
    var input = doc.RootElement;
    bool? exported = null;
    switch (input.GetProperty("action").GetString())
    {
        case "refresh":
            await vm.RefreshAsync(input.TryGetProperty("endpoints", out var eps)
                ? eps.EnumerateArray().Select(e => e.GetString()!).ToArray() : null);
            break;
        case "select":
            vm.SelectedSession = vm.Sessions.Single(s => s.Endpoint == input.GetProperty("endpoint").GetString());
            break;
        case "export":
            exported = await vm.ExportAsync(input.GetProperty("output").GetString()!);
            break;
        default: throw new InvalidOperationException("Unknown probe action");
    }
    Console.WriteLine(JsonSerializer.Serialize(new { exported, vm.Status, vm.CanExport, vm.IsBusy,
        selected = vm.SelectedSession?.Endpoint, sessions = vm.Sessions }));
}
