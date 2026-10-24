namespace RiftReader2.Live;

/// <summary>A read-only native acquisition result; failed reads can still return a valid prefix of bytes.</summary>
public readonly record struct TypedApiScanReadResult(bool Complete, int BytesRead, int? Win32Error);

public sealed record TypedApiScanSpan(ulong BaseAddress, long ByteLength);

public sealed record TypedApiScanHole(ulong BaseAddress, int ByteLength, string Reason, int? Win32Error);

/// <summary>
/// One explicitly bounded pass over the readable private-region suffix at StartAddress.
/// Complete means every eligible byte was searched without a hole; it does not prove a
/// globally unique or valid Lua frame.
/// </summary>
public sealed record TypedApiScoutResult(
    string Status,
    string? Reason,
    ulong StartAddress,
    ulong? NextAddress,
    long EligiblePrivateBytes,
    long AttemptedBytes,
    long ExaminedBytes,
    int EligiblePrivateRegionCount,
    int TouchedPrivateRegionCount,
    IReadOnlyList<ulong> PrefixAddresses,
    IReadOnlyList<TypedApiScanSpan> CoveredSpans,
    IReadOnlyList<TypedApiScanHole> Holes);

/// <summary>Pure, deterministic bounded prefix scout; the caller owns process identity and time budget.</summary>
public static class TypedApiPrefixScout
{
    public const int ChunkBytes = 64 * 1024;
    public const long MaxScanBytes = 512L * 1024 * 1024;
    public const ulong MinUserAddress = 0x10000;
    public const ulong MaxUserEnd = 0x00007FFF_FFFF_FFFF;
    private const uint MemPrivate = 0x20000;

    public static TypedApiScoutResult Scan(
        IReadOnlyList<WindowsMemoryRegion> regions,
        ulong startAddress,
        long maxScanBytes,
        int maxMatchCount,
        Func<ulong, byte[], int, TypedApiScanReadResult> readChunk,
        Func<bool> timeBudgetExceeded,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(regions);
        ArgumentNullException.ThrowIfNull(readChunk);
        ArgumentNullException.ThrowIfNull(timeBudgetExceeded);
        if (startAddress < MinUserAddress || startAddress >= MaxUserEnd)
            throw new ArgumentOutOfRangeException(nameof(startAddress));
        if (maxScanBytes is < ChunkBytes or > MaxScanBytes)
            throw new ArgumentOutOfRangeException(nameof(maxScanBytes));

        var matcher = new TypedApiPrefixMatcher(maxMatchCount);
        var scopes = new List<(ulong Begin, ulong End)>();
        long eligibleBytes = 0;
        ulong lastRegionEnd = 0;
        foreach (var region in regions)
        {
            var end = checked(region.BaseAddress + region.RegionSize);
            if (region.RegionSize == 0 || region.BaseAddress < MinUserAddress ||
                region.BaseAddress < lastRegionEnd || end > MaxUserEnd)
                throw new InvalidDataException("Memory regions must be ordered, nonoverlapping and inside user address space.");
            lastRegionEnd = end;
            if (region.Type != MemPrivate || end <= startAddress)
                continue;
            var begin = Math.Max(region.BaseAddress, startAddress);
            scopes.Add((begin, end));
            eligibleBytes = checked(eligibleBytes + checked((long)(end - begin)));
        }

        var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
        var covered = new List<TypedApiScanSpan>();
        var holes = new List<TypedApiScanHole>();
        long attempted = 0;
        long examined = 0;
        int touchedRegions = 0;
        ulong? firstHoleAddress = null;
        ulong lastCursor = startAddress;

        TypedApiScoutResult Finish(string status, string? reason, ulong? nextAddress) =>
            new(status, reason, startAddress, nextAddress, eligibleBytes, attempted, examined,
                scopes.Count, touchedRegions, matcher.Addresses.ToArray(), covered.ToArray(), holes.ToArray());

        ulong ResumeAt(ulong address)
        {
            var overlap = (ulong)(TypedApiPrefixMatcher.MarkerText.Length - 1);
            return address - startAddress > overlap ? address - overlap : startAddress;
        }

        foreach (var scope in scopes)
        {
            var address = scope.Begin;
            var touched = false;
            while (address < scope.End)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (timeBudgetExceeded())
                    return Finish("partial", "time-budget-exceeded",
                        ResumeAt(firstHoleAddress ?? address));
                if (attempted >= maxScanBytes)
                    return Finish("partial", "byte-budget-exceeded",
                        ResumeAt(firstHoleAddress ?? address));

                if (!touched)
                {
                    touchedRegions++;
                    touched = true;
                }
                var remaining = checked((ulong)(maxScanBytes - attempted));
                var count = checked((int)Math.Min((ulong)ChunkBytes, Math.Min(scope.End - address, remaining)));
                var read = readChunk(address, buffer, count);
                if (read.BytesRead < 0 || read.BytesRead > count || (read.Complete && read.BytesRead != count))
                    throw new InvalidDataException("Memory reader returned an inconsistent byte count.");
                attempted += count;

                // A failure returning a full-length buffer is not trusted as complete.
                var readable = read.Complete || read.BytesRead < count ? read.BytesRead : 0;
                if (readable > 0)
                {
                    matcher.Feed(address, buffer.AsSpan(0, readable));
                    var consumed = readable;
                    if (matcher.MatchBudgetExceeded)
                    {
                        var firstUnretainedEnd = checked(matcher.FirstUnretainedAddress!.Value +
                            (ulong)TypedApiPrefixMatcher.MarkerText.Length);
                        consumed = checked((int)(firstUnretainedEnd - address));
                    }
                    AddCovered(covered, address, consumed);
                    examined += consumed;
                }

                if (readable < count)
                {
                    var holeAddress = checked(address + (ulong)readable);
                    holes.Add(new(holeAddress, count - readable,
                        readable > 0 ? "partial-read" : "unavailable", read.Win32Error));
                    firstHoleAddress ??= holeAddress;
                    matcher.ResetMemoryBoundary();
                }
                if (matcher.MatchBudgetExceeded)
                    return Finish("partial", "candidate-budget-exceeded", matcher.FirstUnretainedAddress);

                address = checked(address + (ulong)count);
                lastCursor = address;
            }
        }

        cancellationToken.ThrowIfCancellationRequested();
        if (timeBudgetExceeded())
            return Finish("partial", "time-budget-exceeded", ResumeAt(firstHoleAddress ?? lastCursor));
        if (firstHoleAddress is not null)
            return Finish("partial", "read-holes", ResumeAt(firstHoleAddress.Value));
        return Finish("complete", null, null);
    }

    private static void AddCovered(List<TypedApiScanSpan> spans, ulong address, int count)
    {
        if (count <= 0)
            return;
        if (spans.Count > 0)
        {
            var last = spans[^1];
            if (checked(last.BaseAddress + (ulong)last.ByteLength) == address)
            {
                spans[^1] = last with { ByteLength = checked(last.ByteLength + count) };
                return;
            }
        }
        spans.Add(new(address, count));
    }
}
