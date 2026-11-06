using System.Buffers.Binary;
using System.Globalization;
using RiftReader2.Domain;

namespace RiftReader2.Application;

/// <summary>Pure bounded numeric scan. The caller owns process identity and wall-clock limits.</summary>
public static class NativeValueScout
{
    public const int ChunkBytes = 64 * 1024;
    public const long MaxScanBytes = 1024L * 1024 * 1024;
    public const int MaxReferences = 8;
    public const int MaxMatches = 128;
    public const ulong MinUserAddress = 0x10000;
    public const ulong MaxUserEnd = 0x00007FFF_FFFF_FFFF;
    private const uint MemPrivate = 0x20000;
    private const int Alignment = 4;
    private const int MaxValueWidth = 8;

    public static NativeValueScanResult Scan(
        IReadOnlyList<NativeValueScanRegion> regions,
        ulong startAddress,
        IReadOnlyList<NativeValueReference> references,
        long maxScanBytes,
        int maxMatchCount,
        Func<ulong, byte[], int, NativeValueScanReadResult> readChunk,
        Func<bool> timeBudgetExceeded,
        CancellationToken cancellationToken = default,
        Action<NativeValueScanMatch>? onMatch = null)
    {
        ArgumentNullException.ThrowIfNull(regions);
        ArgumentNullException.ThrowIfNull(references);
        ArgumentNullException.ThrowIfNull(readChunk);
        ArgumentNullException.ThrowIfNull(timeBudgetExceeded);
        if (startAddress < MinUserAddress || startAddress >= MaxUserEnd)
            throw new ArgumentOutOfRangeException(nameof(startAddress));
        if (maxScanBytes is < ChunkBytes or > MaxScanBytes)
            throw new ArgumentOutOfRangeException(nameof(maxScanBytes));
        if (maxMatchCount is < 1 or > MaxMatches)
            throw new ArgumentOutOfRangeException(nameof(maxMatchCount));
        var compiled = Compile(references);

        var scopes = SelectScopes(regions, startAddress, out var eligibleBytes);
        var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
        var combinedBuffer = GC.AllocateUninitializedArray<byte>(ChunkBytes + MaxValueWidth - 1);
        var priorTail = new byte[MaxValueWidth - 1];
        var priorTailCount = 0;
        ulong priorReadableEnd = 0;
        var covered = new List<NativeValueScanSpan>();
        var holes = new List<NativeValueScanHole>();
        var matches = new List<NativeValueScanMatch>(maxMatchCount);
        var retainedAddresses = new HashSet<ulong>();
        long attempted = 0;
        long examined = 0;
        var touchedRegions = 0;
        var hadReadHole = false;
        var lastCursor = startAddress;

        NativeValueScanResult Finish(string status, string? reason, ulong? nextAddress) =>
            new(status, reason, startAddress, nextAddress, eligibleBytes, attempted, examined,
                scopes.Count, touchedRegions, matches.ToArray(), covered.ToArray(), holes.ToArray());

        ulong ResumeAt(ulong address)
        {
            const ulong overlap = MaxValueWidth - 1;
            return address - startAddress > overlap ? address - overlap : startAddress;
        }

        foreach (var scope in scopes)
        {
            var address = scope.Begin;
            var touched = false;
            priorTailCount = 0;
            priorReadableEnd = 0;
            while (address < scope.End)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (timeBudgetExceeded())
                    return Finish("partial", "time-budget-exceeded", ResumeAt(address));
                if (attempted >= maxScanBytes)
                    return Finish("partial", "byte-budget-exceeded", ResumeAt(address));
                if (!touched)
                {
                    touched = true;
                    touchedRegions++;
                }

                var remaining = checked((ulong)(maxScanBytes - attempted));
                var count = checked((int)Math.Min((ulong)ChunkBytes, Math.Min(scope.End - address, remaining)));
                var read = readChunk(address, buffer, count);
                if (read.BytesRead < 0 || read.BytesRead > count || (read.Complete && read.BytesRead != count))
                    throw new InvalidDataException("Memory reader returned an inconsistent byte count.");
                attempted += count;

                // A failed call claiming a full buffer is not trusted as readable.
                var readable = read.Complete || read.BytesRead < count ? read.BytesRead : 0;
                var consumed = readable;
                if (readable > 0)
                {
                    var contiguous = priorTailCount > 0 && priorReadableEnd == address;
                    var prefix = contiguous ? priorTailCount : 0;
                    var combinedLength = prefix + readable;
                    if (prefix > 0)
                        priorTail.AsSpan(0, prefix).CopyTo(combinedBuffer);
                    buffer.AsSpan(0, readable).CopyTo(combinedBuffer.AsSpan(prefix));
                    var combinedStart = checked(address - (ulong)prefix);

                    var firstAlignedOffset = checked((int)((Alignment - combinedStart % Alignment) % Alignment));
                    for (var offset = firstAlignedOffset; offset < combinedLength; offset += Alignment)
                    {
                        var candidateAddress = checked(combinedStart + (ulong)offset);
                        if (candidateAddress < startAddress)
                            continue;
                        var names = new List<string>();
                        var widest = 0;
                        foreach (var reference in compiled)
                        {
                            if (offset + reference.Width > combinedLength ||
                                !reference.Matches(combinedBuffer.AsSpan(offset, reference.Width)))
                                continue;
                            names.Add(reference.Name);
                            widest = Math.Max(widest, reference.Width);
                        }
                        if (names.Count == 0)
                            continue;
                        if (retainedAddresses.Contains(candidateAddress))
                            continue;
                        if (matches.Count == maxMatchCount)
                        {
                            var unretainedEnd = checked(candidateAddress + (ulong)widest);
                            consumed = unretainedEnd <= address ? 0 :
                                checked((int)Math.Min((ulong)readable, unretainedEnd - address));
                            AddCovered(covered, address, consumed);
                            examined += consumed;
                            return Finish("partial", "candidate-budget-exceeded", candidateAddress);
                        }
                        var match = new NativeValueScanMatch(candidateAddress, widest, names.ToArray());
                        retainedAddresses.Add(candidateAddress);
                        matches.Add(match);
                        onMatch?.Invoke(match);
                    }

                    priorTailCount = Math.Min(MaxValueWidth - 1, readable);
                    buffer.AsSpan(readable - priorTailCount, priorTailCount).CopyTo(priorTail);
                    priorReadableEnd = checked(address + (ulong)readable);
                    AddCovered(covered, address, consumed);
                    examined += consumed;
                }

                if (readable < count)
                {
                    var holeAddress = checked(address + (ulong)readable);
                    holes.Add(new(holeAddress, count - readable,
                        readable > 0 ? "partial-read" : "unavailable", read.Win32Error));
                    hadReadHole = true;
                    priorTailCount = 0;
                    priorReadableEnd = 0;
                }
                address = checked(address + (ulong)count);
                lastCursor = address;
            }
        }

        cancellationToken.ThrowIfCancellationRequested();
        if (timeBudgetExceeded())
            return Finish("partial", "time-budget-exceeded", ResumeAt(lastCursor));
        if (hadReadHole)
            return Finish("partial", "read-holes", ResumeAt(lastCursor));
        return Finish("complete", null, null);
    }

    private static IReadOnlyList<(ulong Begin, ulong End)> SelectScopes(
        IReadOnlyList<NativeValueScanRegion> regions, ulong startAddress, out long eligibleBytes)
    {
        var scopes = new List<(ulong Begin, ulong End)>();
        eligibleBytes = 0;
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
        return scopes;
    }

    private static IReadOnlyList<CompiledReference> Compile(IReadOnlyList<NativeValueReference> references)
    {
        if (references.Count is < 1 or > MaxReferences || references.Any(value => value is null))
            throw new ArgumentException($"references must contain between 1 and {MaxReferences} entries.", nameof(references));
        if (references.Select(value => value.Name).Distinct(StringComparer.Ordinal).Count() != references.Count)
            throw new ArgumentException("Reference names must be unique.", nameof(references));
        var result = new List<CompiledReference>(references.Count);
        foreach (var reference in references)
        {
            if (string.IsNullOrWhiteSpace(reference.Name) || reference.Name.Length > 32)
                throw new ArgumentException("Reference names must be 1..32 characters.", nameof(references));
            if (reference.Kind is not (MemoryValueKind.Int32 or MemoryValueKind.Float32 or MemoryValueKind.Float64))
                throw new ArgumentException("Only int32, float32 and float64 references are supported.", nameof(references));
            if (!double.IsFinite(reference.Tolerance) || reference.Tolerance < 0)
                throw new ArgumentException("Reference tolerance must be finite and nonnegative.", nameof(references));
            if (reference.Kind == MemoryValueKind.Int32 && reference.Tolerance != 0)
                throw new ArgumentException("int32 references require zero tolerance.", nameof(references));
            result.Add(reference.Kind switch
            {
                MemoryValueKind.Int32 => CompiledReference.Int32(reference.Name,
                    int.Parse(reference.Value, NumberStyles.Integer, CultureInfo.InvariantCulture)),
                MemoryValueKind.Float32 => CompiledReference.Float32(reference.Name,
                    float.Parse(reference.Value, NumberStyles.Float, CultureInfo.InvariantCulture), reference.Tolerance),
                MemoryValueKind.Float64 => CompiledReference.Float64(reference.Name,
                    double.Parse(reference.Value, NumberStyles.Float, CultureInfo.InvariantCulture), reference.Tolerance),
                _ => throw new InvalidOperationException("Unsupported numeric reference kind.")
            });
        }
        return result;
    }

    private static void AddCovered(List<NativeValueScanSpan> spans, ulong address, int count)
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

    private delegate bool SpanMatch(ReadOnlySpan<byte> span);

    private sealed record CompiledReference(string Name, int Width, SpanMatch Matches)
    {
        public static CompiledReference Int32(string name, int expected) =>
            new(name, 4, span => BinaryPrimitives.ReadInt32LittleEndian(span) == expected);

        public static CompiledReference Float32(string name, float expected, double tolerance)
        {
            if (!float.IsFinite(expected))
                throw new ArgumentException("float32 reference values must be finite.");
            return new(name, 4, span =>
            {
                var actual = BinaryPrimitives.ReadSingleLittleEndian(span);
                return float.IsFinite(actual) && Math.Abs((double)actual - expected) <= tolerance;
            });
        }

        public static CompiledReference Float64(string name, double expected, double tolerance)
        {
            if (!double.IsFinite(expected))
                throw new ArgumentException("float64 reference values must be finite.");
            return new(name, 8, span =>
            {
                var actual = BinaryPrimitives.ReadDoubleLittleEndian(span);
                return double.IsFinite(actual) && Math.Abs(actual - expected) <= tolerance;
            });
        }
    }
}
