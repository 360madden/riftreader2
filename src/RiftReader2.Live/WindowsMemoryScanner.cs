using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using RiftReader2.Infrastructure;

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
    string? Reason)
{
    public IReadOnlyList<LiveCandidateRegion> CandidateRegions { get; init; } = [];
}

public sealed record LiveCandidateRegion(
    nint BaseAddress,
    long Size,
    nint AllocationBase,
    uint AllocationProtect,
    uint State,
    uint Protect,
    uint Type);

public static class WindowsMemoryScanner
{
    private const int ChunkBytes = 64 * 1024;
    private const int MaxRegionCount = 262_144;
    private const int MaxStableChunkPartialCopyRetries = 2;

    public static LiveScanResult Scan(
        DiscoveredTarget target,
        string challenge,
        long maxScanBytes,
        TimeSpan maxScanTime,
        CancellationToken cancellationToken,
        Action? attemptStarting = null)
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
            return RunWithPartialCopyRetry(
                () => ScanAttempt(
                    handle,
                    target.Identity.ProcessId,
                    challenge,
                    maxScanBytes,
                    maxScanTime,
                    stopwatch,
                    cancellationToken),
                () => stopwatch.Elapsed,
                maxScanTime,
                attemptStarting);
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

    public static LiveScanResult ScanCandidateRegions(
        DiscoveredTarget target,
        string challenge,
        IReadOnlyList<LiveCandidateRegion> regions,
        long maxScanBytes,
        TimeSpan maxScanTime,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(regions);
        var stopwatch = Stopwatch.StartNew();
        if (regions.Count == 0)
            return Incomplete("scope-empty", 0, 0, 0, stopwatch.Elapsed, "Candidate-region scope is empty.");

        long plannedBytes = 0;
        foreach (var region in regions.Distinct())
        {
            if (region.Size <= 0)
                return Incomplete("scope-invalid", 0, 0, regions.Count, stopwatch.Elapsed, "Candidate-region scope contains a nonpositive region size.");
            plannedBytes = checked(plannedBytes + region.Size);
            if (plannedBytes > maxScanBytes)
                return Incomplete("byte-budget-exceeded", plannedBytes, 0, regions.Count, stopwatch.Elapsed,
                    $"Candidate-region scope exceeds the configured {maxScanBytes} byte budget.");
        }

        var handle = NativeMethods.OpenProcess(
            NativeMethods.ProcessAccess.VirtualMemoryRead |
            NativeMethods.ProcessAccess.QueryInformation |
            NativeMethods.ProcessAccess.QueryLimitedInformation,
            false,
            target.Identity.ProcessId);
        if (handle == 0)
            return Incomplete("open-failed", plannedBytes, 0, regions.Count, stopwatch.Elapsed, $"OpenProcess failed: {Win32Error()}");

        try
        {
            var ordered = regions.Distinct().OrderBy(region => region.BaseAddress.ToInt64()).ToArray();
            var accumulator = new EnvelopeCandidateAccumulator(challenge);
            var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
            long scannedBytes = 0;
            LiveCandidateRegion? previous = null;
            foreach (var region in ordered)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (stopwatch.Elapsed > maxScanTime)
                    return Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                        "Candidate-region scan exceeded its time budget.", accumulator);
                if (!RegionMetadataMatches(handle, region))
                    return Incomplete("scope-drifted", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                        $"Candidate region metadata changed at 0x{region.BaseAddress.ToInt64():X}.", accumulator);
                if (previous is null || previous.BaseAddress.ToInt64() + previous.Size != region.BaseAddress.ToInt64())
                    accumulator.ResetMemoryBoundary();

                long offset = 0;
                while (offset < region.Size)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    if (stopwatch.Elapsed > maxScanTime)
                        return Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                            "Candidate-region scan exceeded its time budget.", accumulator);
                    var count = checked((int)Math.Min(buffer.Length, region.Size - offset));
                    var address = checked(new nint(region.BaseAddress.ToInt64() + offset));
                    var readResult = ReadChunkWithStableRegionRetry(
                        () =>
                        {
                            var succeeded = NativeMethods.ReadProcessMemory(handle, address, buffer, (nuint)count, out var read);
                            return new(succeeded, read, succeeded ? null : Marshal.GetLastWin32Error());
                        },
                        () => stopwatch.Elapsed <= maxScanTime && RegionStillCoversExactRead(handle, region, address, count),
                        (nuint)count);
                    if (!readResult.Succeeded || readResult.BytesRead != (nuint)count)
                    {
                        var detail = readResult.ErrorCode is { } code
                            ? Win32Error(code)
                            : $"ReadProcessMemory returned {readResult.BytesRead} of {count} requested bytes without a Win32 error.";
                        return Incomplete("read-failed", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                            $"ReadProcessMemory failed at 0x{address.ToInt64():X}: {detail}", accumulator);
                    }
                    accumulator.Feed(buffer.AsSpan(0, count));
                    if (accumulator.BudgetExceeded)
                        return Incomplete("candidate-budget-exceeded", plannedBytes, scannedBytes + count, ordered.Length,
                            stopwatch.Elapsed, "Envelope endpoint or valid-candidate budget was exceeded.", accumulator);
                    scannedBytes += count;
                    offset += count;
                }
                if (!RegionMetadataMatches(handle, region))
                    return Incomplete("scope-drifted", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                        $"Candidate region metadata changed while reading 0x{region.BaseAddress.ToInt64():X}.", accumulator);
                previous = region;
            }

            return new(true, "complete", plannedBytes, scannedBytes, ordered.Length, stopwatch.Elapsed,
                accumulator.ValidCandidates, accumulator.EndpointCandidateCount, accumulator.MalformedCandidateCount, null);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception exception)
        {
            return Incomplete("scan-error", plannedBytes, 0, regions.Count, stopwatch.Elapsed, exception.Message);
        }
        finally
        {
            NativeMethods.CloseHandle(handle);
        }
    }

    internal static LiveScanResult RunWithPartialCopyRetry(
        Func<ScanAttemptResult> scan,
        Func<TimeSpan> elapsed,
        TimeSpan maxScanTime,
        Action? attemptStarting = null)
    {
        ArgumentNullException.ThrowIfNull(scan);
        ArgumentNullException.ThrowIfNull(elapsed);
        attemptStarting?.Invoke();
        var first = scan();
        if (first.ReadErrorCode != NativeMethods.ErrorPartialCopy ||
            first.Result.Completed ||
            first.Result.Status != "read-failed" ||
            elapsed() >= maxScanTime)
            return first.Result;
        attemptStarting?.Invoke();
        return scan().Result;
    }

    private static ScanAttemptResult ScanAttempt(
        nint handle,
        int processId,
        string challenge,
        long maxScanBytes,
        TimeSpan maxScanTime,
        Stopwatch stopwatch,
        CancellationToken cancellationToken)
    {
        var regions = EnumerateReadablePrivateRegions(handle, processId, maxScanTime, stopwatch, cancellationToken);
        long plannedBytes = 0;
        foreach (var region in regions)
        {
            plannedBytes = checked(plannedBytes + region.Size);
            if (plannedBytes > maxScanBytes)
                return new(Incomplete("byte-budget-exceeded", plannedBytes, 0, regions.Count, stopwatch.Elapsed,
                    $"Readable private memory exceeds the configured {maxScanBytes} byte budget."), null);
        }

        var accumulator = new EnvelopeCandidateAccumulator(challenge);
        var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
        long scannedBytes = 0;
        LiveCandidateRegion? previous = null;
        var candidateRegions = new HashSet<LiveCandidateRegion>();
        var contiguousTailRegions = new List<LiveCandidateRegion>();
        long contiguousTailBytes = 0;
        foreach (var region in regions)
        {
            if (previous is null || previous.BaseAddress.ToInt64() + previous.Size != region.BaseAddress.ToInt64())
            {
                accumulator.ResetMemoryBoundary();
                contiguousTailRegions.Clear();
                contiguousTailBytes = 0;
            }
            long offset = 0;
            while (offset < region.Size)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (stopwatch.Elapsed > maxScanTime)
                    return new(Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                        $"Scan exceeded the configured {maxScanTime.TotalSeconds:F0} second budget.", accumulator), null);
                var count = checked((int)Math.Min(buffer.Length, region.Size - offset));
                var address = checked(new nint(region.BaseAddress.ToInt64() + offset));
                var readResult = ReadChunkWithStableRegionRetry(
                    () =>
                    {
                        var succeeded = NativeMethods.ReadProcessMemory(
                            handle, address, buffer, (nuint)count, out var read);
                        return new(succeeded, read,
                            succeeded ? null : Marshal.GetLastWin32Error());
                    },
                    () =>
                    {
                        cancellationToken.ThrowIfCancellationRequested();
                        return stopwatch.Elapsed <= maxScanTime &&
                               RegionStillCoversExactRead(handle, region, address, count);
                    },
                    (nuint)count);
                if (!readResult.Succeeded || readResult.BytesRead != (nuint)count)
                {
                    var error = readResult.ErrorCode;
                    var detail = error is { } code
                        ? Win32Error(code)
                        : $"ReadProcessMemory returned {readResult.BytesRead} of {count} requested bytes without a Win32 error.";
                    return new(Incomplete("read-failed", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                        $"ReadProcessMemory failed at 0x{address.ToInt64():X}: {detail}", accumulator), error);
                }
                var candidateCountBefore = accumulator.ValidCandidates.Count;
                accumulator.Feed(buffer.AsSpan(0, count));
                if (accumulator.ValidCandidates.Count > candidateCountBefore)
                {
                    candidateRegions.Add(region);
                    foreach (var tailRegion in contiguousTailRegions)
                        candidateRegions.Add(tailRegion);
                }
                if (accumulator.BudgetExceeded)
                    return new(Incomplete("candidate-budget-exceeded", plannedBytes, scannedBytes + count, regions.Count,
                        stopwatch.Elapsed, "Envelope endpoint or valid-candidate budget was exceeded.", accumulator), null);
                scannedBytes += count;
                offset += count;
            }
            contiguousTailRegions.Add(region);
            contiguousTailBytes = checked(contiguousTailBytes + region.Size);
            while (contiguousTailRegions.Count > 1 &&
                   contiguousTailBytes - contiguousTailRegions[0].Size >= LiveAddonEnvelopeDecoder.MaxEnvelopeBytes - 1)
            {
                contiguousTailBytes -= contiguousTailRegions[0].Size;
                contiguousTailRegions.RemoveAt(0);
            }
            previous = region;
        }
        cancellationToken.ThrowIfCancellationRequested();
        if (stopwatch.Elapsed > maxScanTime)
            return new(Incomplete("time-budget-exceeded", plannedBytes, scannedBytes, regions.Count, stopwatch.Elapsed,
                "The final memory read or candidate decode exceeded the scan time budget.", accumulator), null);
        return new(new(
            true,
            "complete",
            plannedBytes,
            scannedBytes,
            regions.Count,
            stopwatch.Elapsed,
            accumulator.ValidCandidates,
            accumulator.EndpointCandidateCount,
            accumulator.MalformedCandidateCount,
            null)
        {
            CandidateRegions = candidateRegions.OrderBy(region => region.BaseAddress.ToInt64()).ToArray()
        }, null);
    }

    internal static ChunkReadResult ReadChunkWithStableRegionRetry(
        Func<ChunkReadResult> read,
        Func<bool> regionStillCoversExactRead,
        nuint expectedBytes)
    {
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(regionStillCoversExactRead);
        if (expectedBytes == 0)
            throw new ArgumentOutOfRangeException(nameof(expectedBytes));

        var result = read();
        for (var retry = 0;
             retry < MaxStableChunkPartialCopyRetries &&
             (!result.Succeeded || result.BytesRead != expectedBytes) &&
             result.ErrorCode == NativeMethods.ErrorPartialCopy;
             retry++)
        {
            if (!regionStillCoversExactRead())
                break;
            result = read();
        }
        return result;
    }

    private static bool RegionStillCoversExactRead(
        nint handle,
        LiveCandidateRegion original,
        nint address,
        int count)
    {
        var querySize = (nuint)Marshal.SizeOf<NativeMethods.MemoryBasicInformation>();
        var queried = NativeMethods.VirtualQueryEx(handle, address, out var current, querySize);
        if (queried < querySize || !IsReadablePrivate(current))
            return false;
        var readStart = address.ToInt64();
        var readEnd = checked(readStart + count);
        var regionEnd = checked(current.BaseAddress.ToInt64() + (long)current.RegionSize);
        return current.BaseAddress == original.BaseAddress &&
               (long)current.RegionSize == original.Size &&
               current.AllocationBase == original.AllocationBase &&
               current.AllocationProtect == original.AllocationProtect &&
               current.State == original.State &&
               current.Protect == original.Protect &&
               current.Type == original.Type &&
               readStart >= current.BaseAddress.ToInt64() &&
               readEnd <= regionEnd;
    }

    private static bool RegionMetadataMatches(nint handle, LiveCandidateRegion original)
    {
        var querySize = (nuint)Marshal.SizeOf<NativeMethods.MemoryBasicInformation>();
        var queried = NativeMethods.VirtualQueryEx(handle, original.BaseAddress, out var current, querySize);
        return queried >= querySize && IsReadablePrivate(current) &&
               current.BaseAddress == original.BaseAddress &&
               (long)current.RegionSize == original.Size &&
               current.AllocationBase == original.AllocationBase &&
               current.AllocationProtect == original.AllocationProtect &&
               current.State == original.State &&
               current.Protect == original.Protect &&
               current.Type == original.Type;
    }

    private static List<LiveCandidateRegion> EnumerateReadablePrivateRegions(
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
        var regions = new List<LiveCandidateRegion>();
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
                regions.Add(new(info.BaseAddress, size, info.AllocationBase,
                    info.AllocationProtect, info.State, info.Protect, info.Type));
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
        return Win32Error(code);
    }

    private static string Win32Error(int code) =>
        $"{new Win32Exception(code).Message} (Win32 {code})";

    internal sealed record ScanAttemptResult(LiveScanResult Result, int? ReadErrorCode);

    internal readonly record struct ChunkReadResult(
        bool Succeeded,
        nuint BytesRead,
        int? ErrorCode);

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
        internal const int ErrorPartialCopy = 299;

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
