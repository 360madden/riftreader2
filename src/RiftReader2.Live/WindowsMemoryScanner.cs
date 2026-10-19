using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace RiftReader2.Live;

public sealed record LiveScanResult(
    bool Completed,
    string Status,
    long PlannedBytes,
    long ScannedBytes,
    int RegionCount,
    TimeSpan Elapsed,
    IReadOnlyList<ReadOnlyMemory<byte>> Candidates,
    int EndpointCandidateCount,
    int MalformedCandidateCount,
    string? Reason);

public static class WindowsMemoryScanner
{
    private const int ChunkBytes = 64 * 1024;
    private const int MaxRegionCount = 262_144;

    public static LiveScanResult Scan(
        DiscoveredTarget target,
        string challenge,
        long maxScanBytes,
        TimeSpan maxScanTime,
        CancellationToken cancellationToken)
    {
        var stopwatch = Stopwatch.StartNew();
        var handle = NativeMethods.OpenProcess(
            NativeMethods.ProcessAccess.VirtualMemoryRead |
            NativeMethods.ProcessAccess.QueryInformation |
            NativeMethods.ProcessAccess.QueryLimitedInformation,
            false,
            target.Identity.ProcessId);
        if (handle == 0)
            return Incomplete("open-failed", 0, 0, 0, stopwatch.Elapsed, $"OpenProcess failed: {Win32Error()}");

        try
        {
            var regions = EnumerateReadablePrivateRegions(handle, target.Identity.ProcessId, maxScanTime, stopwatch, cancellationToken);
            long plannedBytes = 0;
            foreach (var region in regions)
            {
                plannedBytes = checked(plannedBytes + region.Size);
                if (plannedBytes > maxScanBytes)
                    return Incomplete("byte-budget-exceeded", plannedBytes, 0, regions.Count, stopwatch.Elapsed,
                        $"Readable private memory exceeds the configured {maxScanBytes} byte budget.");
            }

            var accumulator = new EnvelopeCandidateAccumulator(challenge);
            var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
            long scannedBytes = 0;
            MemoryRegion? previous = null;
            foreach (var region in regions)
            {
                if (previous is null || previous.BaseAddress.ToInt64() + previous.Size != region.BaseAddress.ToInt64())
                    accumulator.ResetMemoryBoundary();
                long offset = 0;
                while (offset < region.Size)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    if (stopwatch.Elapsed > maxScanTime)
                        return Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                            $"Scan exceeded the configured {maxScanTime.TotalSeconds:F0} second budget.", accumulator);
                    var count = checked((int)Math.Min(buffer.Length, region.Size - offset));
                    var address = checked(new nint(region.BaseAddress.ToInt64() + offset));
                    if (!NativeMethods.ReadProcessMemory(handle, address, buffer, (nuint)count, out var read) || read != (nuint)count)
                    {
                        return Incomplete("read-failed", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                            $"ReadProcessMemory failed at 0x{address.ToInt64():X}: {Win32Error()}", accumulator);
                    }
                    accumulator.Feed(buffer.AsSpan(0, count));
                    if (accumulator.BudgetExceeded)
                        return Incomplete("candidate-budget-exceeded", plannedBytes, scannedBytes + count, regions.Count,
                            stopwatch.Elapsed, "Envelope endpoint or valid-candidate budget was exceeded.", accumulator);
                    scannedBytes += count;
                    offset += count;
                }
                previous = region;
            }
            cancellationToken.ThrowIfCancellationRequested();
            if (stopwatch.Elapsed > maxScanTime)
                return Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                    "The final memory read or candidate decode exceeded the scan time budget.", accumulator);
            return new(
                true,
                "complete",
                plannedBytes,
                scannedBytes,
                regions.Count,
                stopwatch.Elapsed,
                accumulator.ValidCandidates,
                accumulator.EndpointCandidateCount,
                accumulator.MalformedCandidateCount,
                null);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception exception)
        {
            return Incomplete("scan-error", 0, 0, 0, stopwatch.Elapsed, exception.Message);
        }
        finally
        {
            NativeMethods.CloseHandle(handle);
        }
    }

    private static List<MemoryRegion> EnumerateReadablePrivateRegions(
        nint handle,
        int processId,
        TimeSpan maxScanTime,
        Stopwatch stopwatch,
        CancellationToken cancellationToken)
    {
        NativeMethods.GetNativeSystemInfo(out var systemInfo);
        var address = systemInfo.MinimumApplicationAddress;
        var maximum = systemInfo.MaximumApplicationAddress.ToInt64();
        if (address == 0 || maximum <= address.ToInt64())
            throw new InvalidOperationException("GetNativeSystemInfo returned an invalid application range.");
        var querySize = (nuint)Marshal.SizeOf<NativeMethods.MemoryBasicInformation>();
        var regions = new List<MemoryRegion>();
        while (address.ToInt64() <= maximum)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (stopwatch.Elapsed > maxScanTime)
                throw new TimeoutException("Memory-map enumeration exceeded the scan time budget.");
            var result = NativeMethods.VirtualQueryEx(handle, address, out var info, querySize);
            if (result < querySize)
                throw new InvalidOperationException(
                    $"VirtualQueryEx failed for PID {processId} at 0x{address.ToInt64():X}: {Win32Error()}");
            var size = checked((long)info.RegionSize);
            var regionBase = info.BaseAddress.ToInt64();
            var next = checked(regionBase + size);
            if (size <= 0 || regionBase > address.ToInt64() || next <= address.ToInt64())
                throw new InvalidOperationException($"VirtualQueryEx returned a nonadvancing region at 0x{address.ToInt64():X}.");
            if (IsReadablePrivate(info))
            {
                if (regions.Count >= MaxRegionCount)
                    throw new InvalidDataException($"Readable private region count exceeds {MaxRegionCount}.");
                regions.Add(new(info.BaseAddress, size));
            }
            address = new nint(next);
        }
        return regions;
    }

    private static bool IsReadablePrivate(NativeMethods.MemoryBasicInformation info)
    {
        if (info.State != NativeMethods.MemCommit || info.Type != NativeMethods.MemPrivate ||
            (info.Protect & NativeMethods.PageGuard) != 0)
            return false;
        return (info.Protect & 0xff) is NativeMethods.PageReadOnly or
            NativeMethods.PageReadWrite or NativeMethods.PageWriteCopy or
            NativeMethods.PageExecuteRead or NativeMethods.PageExecuteReadWrite or
            NativeMethods.PageExecuteWriteCopy;
    }

    private static LiveScanResult Incomplete(
        string status,
        long planned,
        long scanned,
        int regionCount,
        TimeSpan elapsed,
        string reason,
        EnvelopeCandidateAccumulator? accumulator = null) =>
        new(
            false,
            status,
            planned,
            scanned,
            regionCount,
            elapsed,
            accumulator?.ValidCandidates ?? [],
            accumulator?.EndpointCandidateCount ?? 0,
            accumulator?.MalformedCandidateCount ?? 0,
            reason);

    private static string Win32Error()
    {
        var code = Marshal.GetLastWin32Error();
        return $"{new Win32Exception(code).Message} (Win32 {code})";
    }

    private sealed record MemoryRegion(nint BaseAddress, long Size);

    private static class NativeMethods
    {
        internal const uint MemCommit = 0x1000;
        internal const uint MemPrivate = 0x20000;
        internal const uint PageGuard = 0x100;
        internal const uint PageReadOnly = 0x02;
        internal const uint PageReadWrite = 0x04;
        internal const uint PageWriteCopy = 0x08;
        internal const uint PageExecuteRead = 0x20;
        internal const uint PageExecuteReadWrite = 0x40;
        internal const uint PageExecuteWriteCopy = 0x80;

        [Flags]
        internal enum ProcessAccess : uint
        {
            VirtualMemoryRead = 0x0010,
            QueryInformation = 0x0400,
            QueryLimitedInformation = 0x1000
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct MemoryBasicInformation
        {
            internal nint BaseAddress;
            internal nint AllocationBase;
            internal uint AllocationProtect;
            internal ushort PartitionId;
            internal nuint RegionSize;
            internal uint State;
            internal uint Protect;
            internal uint Type;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct SystemInfo
        {
            internal ushort ProcessorArchitecture;
            internal ushort Reserved;
            internal uint PageSize;
            internal nint MinimumApplicationAddress;
            internal nint MaximumApplicationAddress;
            internal nuint ActiveProcessorMask;
            internal uint NumberOfProcessors;
            internal uint ProcessorType;
            internal uint AllocationGranularity;
            internal ushort ProcessorLevel;
            internal ushort ProcessorRevision;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern nint OpenProcess(ProcessAccess access, [MarshalAs(UnmanagedType.Bool)] bool inherit, int processId);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ReadProcessMemory(nint process, nint address, [Out] byte[] buffer, nuint size, out nuint read);

        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern nuint VirtualQueryEx(nint process, nint address, out MemoryBasicInformation info, nuint size);

        [DllImport("kernel32.dll")]
        internal static extern void GetNativeSystemInfo(out SystemInfo info);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(nint handle);
    }
}
