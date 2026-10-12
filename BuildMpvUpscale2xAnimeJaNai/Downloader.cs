using System.Security.Cryptography;
using System.Text;

public class Downloader
{
    public delegate void ProgressChanged(double percentage);

    public static async Task DownloadFileAsync(string url, string destinationFilePath, ProgressChanged progressChanged)
    {
        // Cache archives, never assembled trees or user settings. Mutable URLs
        // (notably yt-dlp's latest release) must still reach their source.
        string? cacheRoot = Environment.GetEnvironmentVariable("ANIMEJANAI_DOWNLOAD_CACHE");
        string? cached = null;
        if (!string.IsNullOrWhiteSpace(cacheRoot) &&
            !new Uri(url).AbsolutePath.Split('/').Contains("latest", StringComparer.OrdinalIgnoreCase))
        {
            Directory.CreateDirectory(cacheRoot);
            string key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(url))).ToLowerInvariant();
            cached = Path.Combine(cacheRoot, key);
            if (File.Exists(cached) && File.Exists(cached + ".sha256"))
            {
                using var input = File.OpenRead(cached);
                string actual = Convert.ToHexString(SHA256.HashData(input));
                if (actual.Equals(File.ReadAllText(cached + ".sha256").Trim(), StringComparison.OrdinalIgnoreCase))
                {
                    File.Copy(cached, destinationFilePath, true);
                    Console.WriteLine($"Using download cache: {Path.GetFileName(destinationFilePath)}");
                    progressChanged?.Invoke(100);
                    return;
                }
                Console.WriteLine($"Discarding corrupt download cache: {Path.GetFileName(destinationFilePath)}");
            }
        }

        using HttpClient client = new();
        using HttpResponseMessage response = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);

        response.EnsureSuccessStatusCode();

        long totalBytes = response.Content.Headers.ContentLength ?? -1L;
        var totalRead = 0L;
        var buffer = new byte[8192];
        int read;
        using (Stream contentStream = await response.Content.ReadAsStreamAsync(),
                      fileStream = new FileStream(destinationFilePath, FileMode.Create, FileAccess.Write, FileShare.None, 8192, true))
        {
            while ((read = await contentStream.ReadAsync(buffer)) > 0)
            {
                await fileStream.WriteAsync(buffer.AsMemory(0, read));
                totalRead += read;
                if (totalBytes > 0)
                    progressChanged?.Invoke(Math.Round((double)totalRead / totalBytes * 100, 0));
            }
        }
        if (totalBytes >= 0 && totalRead != totalBytes)
            throw new IOException($"Incomplete download: {url}");

        // Publish complete files only. Existing NVIDIA pin checks still run
        // in the assembler, including after a cache hit.
        if (cached != null)
        {
            string temporary = cached + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.Copy(destinationFilePath, temporary);
                using (var input = File.OpenRead(temporary))
                    File.WriteAllText(temporary + ".sha256", Convert.ToHexString(SHA256.HashData(input)));
                File.Move(temporary, cached, true);
                File.Move(temporary + ".sha256", cached + ".sha256", true);
            }
            finally
            {
                File.Delete(temporary);
                File.Delete(temporary + ".sha256");
            }
        }
    }
}
