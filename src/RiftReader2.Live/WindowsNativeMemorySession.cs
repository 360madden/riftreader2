using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32.SafeHandles;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

public sealed class WindowsNativeMemorySession : IReadOnlyNativeMemorySession
{
    private readonly SafeProcessHandle handle;
    private readonly string initialExecutablePath;
    private bool disposed;

    private WindowsNativeMemorySession(SafeProcessHandle handle, NativeProcessIdentity identity)
    {
        this.handle = handle;
        Identity = identity;
        initialExecutablePath = identity.ExecutablePath;
    }

    public NativeProcessIdentity Identity { get; }

    public static async Task<WindowsNativeMemorySession> OpenAsync(
        int processId,
        long? expectedStartUtcTicks,
        string? expectedExecutableSha256,
        CancellationToken cancellationToken)
    {
        if (processId <= 0)
            throw new ArgumentOutOfRangeException(nameof(processId));
        var handle = NativeMethods.OpenProcess(
            NativeMethods.ProcessAccess.VirtualMemoryRead |
            NativeMethods.ProcessAccess.QueryInformation |
            NativeMethods.ProcessAccess.QueryLimitedInformation,
            false,
            processId);
        if (handle.IsInvalid)
        {
            var code = Marshal.GetLastWin32Error();
            handle.Dispose();
            throw new Win32Exception(code, $"OpenProcess failed with Win32 error {code}.");
        }

        try
        {
            var startTicks = GetStartTicks(handle);
            var executablePath = QueryExecutablePath(handle);
            var executableSha256 = await HashFileAsync(executablePath, cancellationToken);
            var module = FindMainModule(processId, executablePath);
            var startTicksAfter = GetStartTicks(handle);
            var pathAfter = QueryExecutablePath(handle);
            if (startTicks != startTicksAfter || !SamePath(executablePath, pathAfter))
                throw new InvalidDataException("Process identity changed while opening the read-only native session.");
            if (expectedStartUtcTicks is { } expectedStart && startTicks != expectedStart)
                throw new InvalidDataException("The process start identity does not match the capture request.");
            if (expectedExecutableSha256 is not null &&
                !string.Equals(executableSha256, expectedExecutableSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("The executable SHA-256 does not match the capture request.");
            var identity = new NativeProcessIdentity(
                processId,
                startTicks,
                Path.GetFullPath(executablePath),
                executableSha256,
                module.BaseAddress,
                module.Size);
            return new(handle, identity);
        }
        catch
        {
            handle.Dispose();
            throw;
        }
    }

    public NativeReadResult Read(ulong address, int byteLength)
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        if (byteLength is < 1 or > 4096)
            throw new ArgumentOutOfRangeException(nameof(byteLength));
        var buffer = GC.AllocateUninitializedArray<byte>(byteLength);
        var succeeded = NativeMethods.ReadProcessMemory(
            handle,
            new nint(checked((long)address)),
            buffer,
            (nuint)byteLength,
            out var read);
        var count = checked((int)read);
        if (count > byteLength)
            return new("unavailable", [], null, "ReadProcessMemory returned an invalid byte count.");
        if (succeeded && count == byteLength)
            return new("success", buffer, null, null);
        int? error = succeeded ? null : Marshal.GetLastWin32Error();
        var bytes = count == 0 ? [] : buffer[..count];
        return count > 0
            ? new("partial", bytes, error, $"ReadProcessMemory returned {count} of {byteLength} requested bytes.")
            : new("unavailable", [], error, "ReadProcessMemory returned no bytes.");
    }

    public async ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        try
        {
            var start = GetStartTicks(handle);
            if (start != Identity.ProcessStartUtcTicks)
                return "Process creation identity changed after capture.";
            var path = QueryExecutablePath(handle);
            if (!SamePath(path, initialExecutablePath))
                return "Process executable path changed after capture.";
            var hash = await HashFileAsync(path, cancellationToken);
            if (!string.Equals(hash, Identity.ExecutableSha256, StringComparison.OrdinalIgnoreCase))
                return "On-disk executable SHA-256 changed after capture.";
            var module = FindMainModule(Identity.ProcessId, path);
            if (module.BaseAddress != Identity.ModuleBaseAddress || module.Size != Identity.ModuleSize)
                return "Main-module mapping changed after capture.";
            if (GetStartTicks(handle) != Identity.ProcessStartUtcTicks || !SamePath(QueryExecutablePath(handle), path))
                return "Process identity changed during post-capture validation.";
            return null;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Win32Exception exception)
        {
            return $"Post-capture identity validation failed: {exception.Message}";
        }
        catch (Exception exception)
        {
            return $"Post-capture identity validation failed ({exception.GetType().Name}).";
        }
    }

    public ValueTask DisposeAsync()
    {
        if (!disposed)
        {
            disposed = true;
            handle.Dispose();
        }
        return ValueTask.CompletedTask;
    }

    private static long GetStartTicks(SafeProcessHandle process)
    {
        if (!NativeMethods.GetProcessTimes(process, out var created, out var exited, out _, out _))
            throw Win32("GetProcessTimes");
        if (exited.ToLong() != 0)
            throw new InvalidDataException("The identified process has exited.");
        return DateTime.FromFileTimeUtc(created.ToLong()).Ticks;
    }

    private static string QueryExecutablePath(SafeProcessHandle process)
    {
        var capacity = 32_768;
        var path = new StringBuilder(capacity);
        if (!NativeMethods.QueryFullProcessImageName(process, 0, path, ref capacity) || capacity <= 0)
            throw Win32("QueryFullProcessImageName");
        return Path.GetFullPath(path.ToString());
    }

    private static async Task<string> HashFileAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(
            path, FileMode.Open, FileAccess.Read, FileShare.Read,
            128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
    }

    private static ModuleMapping FindMainModule(int processId, string executablePath)
    {
        using var snapshot = CreateModuleSnapshot(processId);
        var entry = new NativeMethods.ModuleEntry32 { Size = (uint)Marshal.SizeOf<NativeMethods.ModuleEntry32>() };
        if (!NativeMethods.Module32First(snapshot, ref entry))
            throw Win32("Module32First");
        while (true)
        {
            if (SamePath(entry.ExePath, executablePath))
                return new(checked((ulong)entry.BaseAddress.ToInt64()), entry.BaseSize);
            entry.Size = (uint)Marshal.SizeOf<NativeMethods.ModuleEntry32>();
            if (!NativeMethods.Module32Next(snapshot, ref entry))
            {
                var error = Marshal.GetLastWin32Error();
                if (error != 18) // ERROR_NO_MORE_FILES is normal enumeration completion.
                    throw new Win32Exception(error, $"Module32Next failed with Win32 error {error}.");
                break;
            }
        }
        throw new InvalidDataException("The executable's loaded main module was not found in the identified process epoch.");
    }

    private static SafeFileHandle CreateModuleSnapshot(int processId)
    {
        const int errorBadLength = 24;
        for (var attempt = 1; attempt <= 4; attempt++)
        {
            var snapshot = NativeMethods.CreateToolhelp32Snapshot(
                NativeMethods.Th32csSnapModule | NativeMethods.Th32csSnapModule32,
                processId);
            if (!snapshot.IsInvalid)
                return snapshot;
            var error = Marshal.GetLastWin32Error();
            snapshot.Dispose();
            if (error != errorBadLength || attempt == 4)
                throw CreateWin32Exception("CreateToolhelp32Snapshot", error);
            Thread.Yield();
        }
        throw new InvalidOperationException("Unreachable module snapshot retry state.");
    }

    private static bool SamePath(string left, string right) =>
        string.Equals(Path.GetFullPath(left), Path.GetFullPath(right), StringComparison.OrdinalIgnoreCase);

    private static Win32Exception Win32(string operation) =>
        CreateWin32Exception(operation, Marshal.GetLastWin32Error());

    private static Win32Exception CreateWin32Exception(string operation, int error) =>
        new(error, $"{operation} failed with Win32 error {error}.");

    private sealed record ModuleMapping(ulong BaseAddress, ulong Size);

    private static class NativeMethods
    {
        internal const uint Th32csSnapModule = 0x00000008;
        internal const uint Th32csSnapModule32 = 0x00000010;

        [Flags]
        internal enum ProcessAccess : uint
        {
            VirtualMemoryRead = 0x0010,
            QueryInformation = 0x0400,
            QueryLimitedInformation = 0x1000
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct FileTime
        {
            internal uint Low;
            internal uint High;
            internal long ToLong() => ((long)High << 32) | Low;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        internal struct ModuleEntry32
        {
            internal uint Size;
            internal uint ModuleId;
            internal uint ProcessId;
            internal uint GlobalUsage;
            internal uint ProcessUsage;
            internal nint BaseAddress;
            internal uint BaseSize;
            internal nint ModuleHandle;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] internal string Module;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] internal string ExePath;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern SafeProcessHandle OpenProcess(ProcessAccess access, [MarshalAs(UnmanagedType.Bool)] bool inherit, int processId);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ReadProcessMemory(SafeProcessHandle process, nint address, [Out] byte[] buffer, nuint size, out nuint read);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetProcessTimes(SafeProcessHandle process, out FileTime creation, out FileTime exit, out FileTime kernel, out FileTime user);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryFullProcessImageName(SafeProcessHandle process, uint flags, StringBuilder path, ref int size);

        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern SafeFileHandle CreateToolhelp32Snapshot(uint flags, int processId);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool Module32First(SafeFileHandle snapshot, ref ModuleEntry32 entry);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool Module32Next(SafeFileHandle snapshot, ref ModuleEntry32 entry);
    }
}
