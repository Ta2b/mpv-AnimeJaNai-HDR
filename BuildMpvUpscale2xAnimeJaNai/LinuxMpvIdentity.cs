using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

// Identity of the native files actually assembled, not a manually maintained
// capability label. Script-only releases keep it; a changed reader or dependency
// forces the folder updater to install the full package containing that reader.
public static class LinuxMpvIdentity
{
    public static string Capture(string directory)
    {
        foreach (string required in new[] { "mpv", "libmpv.so.2" })
            if (!File.Exists(Path.Combine(directory, required)))
                throw new InvalidDataException("Incomplete Linux mpv bundle: " + required);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        hash.AppendData(Encoding.UTF8.GetBytes("animejanai-linux-mpv-bundle-v1\0"));
        byte[] frame = new byte[8];
        foreach (string path in Directory.EnumerateFiles(directory).OrderBy(Path.GetFileName, StringComparer.Ordinal))
        {
            byte[] name = Encoding.UTF8.GetBytes(Path.GetFileName(path));
            BinaryPrimitives.WriteInt64LittleEndian(frame, name.Length);
            hash.AppendData(frame); hash.AppendData(name);
            using var file = File.OpenRead(path);
            BinaryPrimitives.WriteInt64LittleEndian(frame, file.Length);
            hash.AppendData(frame); hash.AppendData(SHA256.HashData(file));
        }
        return "linux-mpv-bundle-v1-sha256-" + Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }
}
