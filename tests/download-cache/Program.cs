using System.Net;
using System.Net.Sockets;
using System.Text;

string root = Path.Combine(Path.GetTempPath(), "ajn-download-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
string cache = Path.Combine(root, "cache"), destination = Path.Combine(root, "archive");
string? previous = Environment.GetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE");
using var cancellation = new CancellationTokenSource();
var listener = new TcpListener(IPAddress.Loopback, 0);
listener.Start();
string origin = "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port;
int requests = 0, passed = 0;
var server = Task.Run(async () =>
{
    try
    {
        while (!cancellation.IsCancellationRequested)
        {
            using var client = await listener.AcceptTcpClientAsync(cancellation.Token);
            using var stream = client.GetStream();
            using var reader = new StreamReader(stream, leaveOpen: true);
            string path = (await reader.ReadLineAsync())!.Split(' ')[1];
            while (!string.IsNullOrEmpty(await reader.ReadLineAsync())) { }
            Interlocked.Increment(ref requests);
            byte[] body = Encoding.UTF8.GetBytes("payload:" + path);
            int length = body.Length + (path.Contains("truncated") ? 4 : 0);
            await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Length: {length}\r\nConnection: close\r\n\r\n"));
            await stream.WriteAsync(body);
        }
    }
    catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
});
void Check(bool result, string name)
{
    if (!result) throw new Exception(name);
    Console.WriteLine("PASS " + name);
    passed++;
}
Task Download(string path) => Downloader.DownloadFileAsync(origin + path, destination, _ => { });
try
{
    Environment.SetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE", cache);
    await Download("/v1/model.7z");
    Check(requests == 1 && File.ReadAllText(destination) == "payload:/v1/model.7z", "first download");
    await Download("/v1/model.7z");
    Check(requests == 1, "cache reuse avoids HTTP");
    string blob = Directory.GetFiles(cache).Single(p => !p.EndsWith(".sha256"));
    File.WriteAllText(blob, "corrupt");
    await Download("/v1/model.7z");
    Check(requests == 2 && File.ReadAllText(destination) == "payload:/v1/model.7z", "corrupt cache downloaded again");
    File.WriteAllText(blob + ".sha256", "invalid");
    await Download("/v1/model.7z");
    Check(requests == 3, "invalid checksum downloaded again");
    await Download("/v2/model.7z");
    Check(requests == 4 && File.ReadAllText(destination) == "payload:/v2/model.7z", "new version has separate cache");
    await Download("/latest/model.7z");
    await Download("/latest/model.7z");
    Check(requests == 6 && Directory.GetFiles(cache).Length == 4, "latest bypasses cache");
    Environment.SetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE", null);
    await Download("/v1/model.7z");
    Check(requests == 7, "disabled cache keeps direct download");
    Environment.SetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE", cache);
    bool rejected = false;
    try { await Download("/v1/truncated.7z"); }
    catch (IOException) { rejected = true; }
    catch (HttpRequestException) { rejected = true; }
    Check(rejected && Directory.GetFiles(cache).Length == 4, "interrupted download never cached");
    cancellation.Cancel();
    await server;
    listener.Stop();
    await Download("/v1/model.7z");
    Check(File.ReadAllText(destination) == "payload:/v1/model.7z", "cache works offline");
    Check(!Directory.GetFiles(cache).Any(p => p.Contains(".tmp")), "no temporary cache files remain");
    Console.WriteLine($"{passed} download-cache checks passed");
}
finally
{
    cancellation.Cancel();
    await server;
    listener.Stop();
    Environment.SetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE", previous);
    Directory.Delete(root, true);
}
