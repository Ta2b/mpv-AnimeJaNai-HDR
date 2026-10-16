using System.Runtime.InteropServices;
using System.Runtime.Intrinsics.X86;
using System.Security.Cryptography;

namespace AnimeJaNai.Platform;

// On-demand evidence from loaded modules; separate from implemented-path notices
// and from qualification of a neural model. No vendor-based compatibility guess.
public static class DeviceCapabilities
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]
    struct CudaResult
    {
        public uint size, version, api;
        public int ordinal, major, minor, integrated, driver, cuda, trt, driverError, cudaError;
        public uint kernel;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string pci;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string name;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string message;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]
    struct CpuResult
    {
        public uint size, version, abi, features, conversion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string ort;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string message;
    }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int CudaProbe(int ordinal, IntPtr output, nuint size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int CpuProbe(IntPtr output, nuint size);

    static object Module<T>(string path, string symbol, Func<IntPtr, object> call) where T : Delegate
    {
        if (!File.Exists(path)) return new { state = "absent", path, qualified = false };
        string? hash = null;
        IntPtr module = IntPtr.Zero;
        try
        {
            using (var file = File.OpenRead(path)) hash = Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
            module = NativeLibrary.Load(path);
            if (!NativeLibrary.TryGetExport(module, symbol, out var fn))
                return new { state = "probe-unavailable", path, file_sha256 = hash, qualified = false,
                    reason = "Older/different module; file presence and loading do not prove compatible kernels." };
            return new { state = "probed", path, file_sha256 = hash, evidence = call(fn) };
        }
        catch (Exception e) when (e is DllNotFoundException or BadImageFormatException or EntryPointNotFoundException
                                  or IOException or UnauthorizedAccessException)
        {
            return new { state = "load-failed", path, file_sha256 = hash, qualified = false, reason = e.Message };
        }
        finally { if (module != IntPtr.Zero) NativeLibrary.Free(module); }
    }

    static object Cpu(string path, bool minimum)
    {
        // This module is compiled with AVX/F16C on x86-64. Do not call its
        // startup/probe code on a CPU/OS that cannot execute those instructions.
        if (RuntimeInformation.ProcessArchitecture == Architecture.X64 && !minimum)
            return new { state = "cpu-incompatible", path, qualified = false, reason = "OS-enabled AVX and CPU F16C required." };
        return Module<CpuProbe>(path, "aji_ort_probe_v1", fn =>
        {
            int size = Marshal.SizeOf<CpuResult>();
            IntPtr output = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.Copy(new byte[size], 0, output, size);
                int status = Marshal.GetDelegateForFunctionPointer<CpuProbe>(fn)(output, (nuint)size);
                var value = Marshal.PtrToStructure<CpuResult>(output);
                bool valid = value.size == size && value.version == 1 && value.abi == 1;
                return new { status, signature_valid = valid, compatible_conversion = valid && status == 0 && value.conversion == 1,
                    bridge_abi = value.abi, required_cpu_feature_bits = value.features, ort_runtime = value.ort,
                    message = value.message, qualification = "Compiled conversion only; providers, operators and model quality not tested." };
            }
            finally { Marshal.FreeHGlobal(output); }
        });
    }

    static object Cuda(string path, int ordinal) => Module<CudaProbe>(path, "aji_trt_probe_v1", fn =>
    {
        int size = Marshal.SizeOf<CudaResult>();
        IntPtr output = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.Copy(new byte[size], 0, output, size);
            int status = Marshal.GetDelegateForFunctionPointer<CudaProbe>(fn)(ordinal, output, (nuint)size);
            var value = Marshal.PtrToStructure<CudaResult>(output);
            bool valid = value.size == size && value.version == 1 && value.api == 9;
            return new { status, signature_valid = valid, compatible_kernel = valid && status == 0 && value.kernel == 1,
                backend_abi = value.api, cuda_device_ordinal = value.ordinal, pci_bus_id = value.pci, device_name = value.name,
                compute_capability = value.major < 0 ? null : new { major = value.major, minor = value.minor },
                integrated = value.integrated < 0 ? (bool?)null : value.integrated != 0,
                driver_version = value.driver > 0 ? (int?)value.driver : null,
                cuda_runtime_version = value.cuda > 0 ? (int?)value.cuda : null,
                tensorrt_runtime_version = value.trt > 0 ? (int?)value.trt : null,
                driver_error = value.driverError, cuda_error = value.cudaError, message = value.message,
                qualification = "One shipped FP16 kernel on the requested CUDA device; not neural operator/model/plan qualification." };
        }
        finally { Marshal.FreeHGlobal(output); }
    });

    public static object Capture(string root, int ordinal = 0)
    {
        root = Path.GetFullPath(root);
        string directory = new[] { Path.Combine(root, "animejanai", "inference"), Path.Combine(root, "inference") }
            .FirstOrDefault(Directory.Exists) ?? Path.Combine(root, "animejanai", "inference");
        bool f16c = X86Base.IsSupported && (X86Base.CpuId(1, 0).Ecx & (1 << 29)) != 0;
        bool avx = Avx.IsSupported; // Includes the OS's extended-register support.
        return new {
            schema = "animejanai.device-capabilities.v1", platform = RuntimeInformation.OSDescription,
            architecture = RuntimeInformation.ProcessArchitecture.ToString(),
            cpu = new { avx_os_enabled = avx, f16c, minimum_x64_conversion_supported = avx && f16c },
            ort_cpu = OperatingSystem.IsLinux() ? Cpu(Path.Combine(directory, "libaji_ort.so"), avx && f16c) : (object)new { state = "not-probed-on-this-os" },
            tensorrt_cuda = OperatingSystem.IsLinux() ? Cuda(Path.Combine(directory, "libaji_trt.so"), ordinal) : (object)new { state = "not-probed-on-this-os" },
            implemented_paths = BackendCapabilities.Describe(),
            remaining = new[] { "AMD gfx1201/gfx1152, Intel XMX/NPU and Apple need their native runtime probes; vendor/name is insufficient.",
                "Neural models, rank-5, ensemble, Fast/drawings and surface importability need separate provider/model/device evidence.",
                "On-disk file fingerprints and successful module probes are separate from modules already loaded in a player.",
                "This on-demand diagnostic uses its own stream; do not run during timing measurements. Automatic selection remains separate." }
        };
    }
}
