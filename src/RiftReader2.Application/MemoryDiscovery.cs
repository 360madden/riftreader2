using System.Buffers.Binary;
using System.Globalization;
using System.Numerics;
using RiftReader2.Domain;

namespace RiftReader2.Application;

public static class MemoryDiscovery
{
    private const long MaxSnapshotBytes = 64L * 1024 * 1024;
    private const long MaxPatternByteComparisons = 64L * 1024 * 1024;
    private const int MaxPointerEdgesExamined = 2_000_000;
    private const ulong MinUserAddress = 0x10000;
    private const ulong MaxUserAddress = 0x00007FFF_FFFF_FFFF;

    public static MemorySearchResult Search(
        MemorySnapshot snapshot,
        MemoryValueKind kind,
        string value,
        double? tolerance,
        int maxMatches,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var regions = ValidateAndJoin(snapshot);
        ValidateLimit(maxMatches, nameof(maxMatches));
        if (!Enum.IsDefined(kind))
            throw new ArgumentOutOfRangeException(nameof(kind));
        if (tolerance is < 0 || (tolerance.HasValue && !double.IsFinite(tolerance.Value)))
            throw new ArgumentOutOfRangeException(nameof(tolerance), "Tolerance must be finite and nonnegative.");
        if (kind is not (MemoryValueKind.Float32 or MemoryValueKind.Float64) && tolerance is not null and not 0)
            throw new ArgumentException("Tolerance is only supported for floating-point searches.", nameof(tolerance));

        var width = Width(kind);
        var matches = new List<MemorySearchMatch>(Math.Min(maxMatches, 1024));
        var truncated = false;
        long searchedBytes = 0;

        switch (kind)
        {
            case MemoryValueKind.Int32:
                SearchValue(regions, int.Parse(value, NumberStyles.Integer, CultureInfo.InvariantCulture), width,
                    static (span, expected) => BinaryPrimitives.ReadInt32LittleEndian(span) == expected,
                    static span => BinaryPrimitives.ReadInt32LittleEndian(span).ToString(CultureInfo.InvariantCulture));
                break;
            case MemoryValueKind.UInt32:
                SearchValue(regions, uint.Parse(value, NumberStyles.Integer, CultureInfo.InvariantCulture), width,
                    static (span, expected) => BinaryPrimitives.ReadUInt32LittleEndian(span) == expected,
                    static span => BinaryPrimitives.ReadUInt32LittleEndian(span).ToString(CultureInfo.InvariantCulture));
                break;
            case MemoryValueKind.Int64:
                SearchValue(regions, long.Parse(value, NumberStyles.Integer, CultureInfo.InvariantCulture), width,
                    static (span, expected) => BinaryPrimitives.ReadInt64LittleEndian(span) == expected,
                    static span => BinaryPrimitives.ReadInt64LittleEndian(span).ToString(CultureInfo.InvariantCulture));
                break;
            case MemoryValueKind.UInt64:
                SearchValue(regions, ulong.Parse(value, NumberStyles.Integer, CultureInfo.InvariantCulture), width,
                    static (span, expected) => BinaryPrimitives.ReadUInt64LittleEndian(span) == expected,
                    static span => BinaryPrimitives.ReadUInt64LittleEndian(span).ToString(CultureInfo.InvariantCulture));
                break;
            case MemoryValueKind.Float32:
                {
                    var expected = float.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
                    if (!float.IsFinite(expected))
                        throw new ArgumentException("Floating-point search values must be finite.", nameof(value));
                    var allowed = tolerance ?? 0;
                    SearchValue(regions, expected, width,
                    (span, item) => float.IsFinite(BinaryPrimitives.ReadSingleLittleEndian(span)) &&
                        Math.Abs((double)BinaryPrimitives.ReadSingleLittleEndian(span) - item) <= allowed,
                        static span => BinaryPrimitives.ReadSingleLittleEndian(span).ToString("R", CultureInfo.InvariantCulture));
                    break;
                }
            case MemoryValueKind.Float64:
                {
                    var expected = double.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
                    if (!double.IsFinite(expected))
                        throw new ArgumentException("Floating-point search values must be finite.", nameof(value));
                    var allowed = tolerance ?? 0;
                    SearchValue(regions, expected, width,
                        (span, item) => double.IsFinite(BinaryPrimitives.ReadDoubleLittleEndian(span)) &&
                            Math.Abs(BinaryPrimitives.ReadDoubleLittleEndian(span) - item) <= allowed,
                        static span => BinaryPrimitives.ReadDoubleLittleEndian(span).ToString("R", CultureInfo.InvariantCulture));
                    break;
                }
        }

        return new(searchedBytes, width, matches, truncated);

        void SearchValue<T>(
            IReadOnlyList<Region> source,
            T expected,
            int itemWidth,
            SpanPredicate<T> predicate,
            SpanFormatter formatter)
        {
            foreach (var region in source)
            {
                var completedRegion = true;
                for (var offset = 0; offset <= region.Bytes.Length - itemWidth; offset++)
                {
                    if ((offset & 0xFFF) == 0)
                        cancellationToken.ThrowIfCancellationRequested();
                    var span = region.Bytes.AsSpan(offset, itemWidth);
                    if (!predicate(span, expected))
                        continue;
                    if (matches.Count == maxMatches)
                    {
                        truncated = true;
                        searchedBytes += Math.Min(region.Bytes.Length, offset + itemWidth);
                        completedRegion = false;
                        return;
                    }
                    matches.Add(new(checked(region.StartAddress + (ulong)offset), formatter(span)));
                }
                if (completedRegion)
                    searchedBytes += region.Bytes.Length;
            }
        }
    }

    public static MemorySearchResult SearchPattern(
        MemorySnapshot snapshot,
        string pattern,
        int maxMatches,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var regions = ValidateAndJoin(snapshot);
        ValidateLimit(maxMatches, nameof(maxMatches));
        var tokens = ParsePattern(pattern);
        var matches = new List<MemorySearchMatch>(Math.Min(maxMatches, 1024));
        var truncated = false;
        long searchedBytes = 0;
        long comparisons = 0;
        foreach (var region in regions)
        {
            for (var offset = 0; offset <= region.Bytes.Length - tokens.Length; offset++)
            {
                if ((offset & 0xFFF) == 0)
                    cancellationToken.ThrowIfCancellationRequested();
                var found = true;
                for (var index = 0; index < tokens.Length; index++)
                {
                    if (++comparisons > MaxPatternByteComparisons)
                    {
                        truncated = true;
                        searchedBytes += Math.Min(region.Bytes.Length, offset + tokens.Length);
                        return Result();
                    }
                    if (tokens[index].HasValue && region.Bytes[offset + index] != tokens[index])
                    {
                        found = false;
                        break;
                    }
                }
                if (!found)
                    continue;
                if (matches.Count == maxMatches)
                {
                    truncated = true;
                    searchedBytes += Math.Min(region.Bytes.Length, offset + tokens.Length);
                    return Result();
                }
                var bytes = region.Bytes.AsSpan(offset, tokens.Length);
                matches.Add(new(checked(region.StartAddress + (ulong)offset), Convert.ToHexString(bytes)));
            }
            searchedBytes += region.Bytes.Length;
        }
        return Result();

        MemorySearchResult Result() => new(searchedBytes, tokens.Length, matches, truncated);
    }

    public static MemorySearchResult Compare(
        MemorySnapshot before,
        MemorySnapshot after,
        MemoryValueKind kind,
        MemoryComparison comparison,
        int maxMatches,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var left = ValidateAndJoin(before);
        var right = ValidateAndJoin(after);
        ValidateLimit(maxMatches, nameof(maxMatches));
        if (!Enum.IsDefined(kind) || !Enum.IsDefined(comparison))
            throw new ArgumentOutOfRangeException("The value kind or comparison is undefined.");
        if (!IdentityEquals(before.Identity, after.Identity))
            throw new InvalidDataException("Snapshots must have the same exact process identity.");
        if (left.Count != right.Count || left.Where((region, index) =>
                region.StartAddress != right[index].StartAddress || region.Bytes.Length != right[index].Bytes.Length).Any())
            throw new InvalidDataException("Snapshots must have the same exact successful-byte layout.");

        var width = Width(kind);
        var matches = new List<MemorySearchMatch>(Math.Min(maxMatches, 1024));
        var truncated = false;
        long searchedBytes = 0;
        for (var regionIndex = 0; regionIndex < left.Count; regionIndex++)
        {
            var leftRegion = left[regionIndex];
            var rightRegion = right[regionIndex];
            for (var offset = 0; offset <= leftRegion.Bytes.Length - width; offset++)
            {
                if ((offset & 0xFFF) == 0)
                    cancellationToken.ThrowIfCancellationRequested();
                var prior = leftRegion.Bytes.AsSpan(offset, width);
                var current = rightRegion.Bytes.AsSpan(offset, width);
                if (!CompareValues(prior, current, kind, comparison))
                    continue;
                if (matches.Count == maxMatches)
                {
                    truncated = true;
                    searchedBytes += Math.Min(leftRegion.Bytes.Length, offset + width);
                    return Result();
                }
                matches.Add(new(checked(leftRegion.StartAddress + (ulong)offset), Format(current, kind)));
            }
            searchedBytes += leftRegion.Bytes.Length;
        }
        return Result();

        MemorySearchResult Result() => new(searchedBytes, width, matches, truncated);
    }

    public static MemoryPointerSearchResult FindPointerChains(
        MemorySnapshot snapshot,
        ulong targetAddress,
        MemoryPointerSearchOptions options,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var regions = ValidateAndJoin(snapshot);
        ValidatePointerOptions(options);
        RequireUserAddress(targetAddress, nameof(targetAddress));
        var entries = new List<PointerEntry>(Math.Min(options.MaxIndexEntries, 65536));
        var indexTruncated = false;
        var pointerSlotsExamined = 0;
        foreach (var region in regions)
        {
            var firstOffset = (int)((8 - (region.StartAddress & 7)) & 7);
            for (var offset = firstOffset; offset <= region.Bytes.Length - 8; offset += 8)
            {
                if ((pointerSlotsExamined++ & 0xFFF) == 0)
                    cancellationToken.ThrowIfCancellationRequested();
                var value = BinaryPrimitives.ReadUInt64LittleEndian(region.Bytes.AsSpan(offset, 8));
                if (value < MinUserAddress || value > MaxUserAddress)
                    continue;
                if (entries.Count == options.MaxIndexEntries)
                {
                    indexTruncated = true;
                    continue;
                }
                entries.Add(new(value, checked(region.StartAddress + (ulong)offset)));
            }
        }
        entries.Sort(static (left, right) => left.Value != right.Value
            ? left.Value.CompareTo(right.Value)
            : left.Address.CompareTo(right.Address));

        var identity = snapshot.Identity;
        var moduleEnd = checked(identity.ModuleBaseAddress + identity.ModuleSize);
        var frontier = new List<PointerState> { new(targetAddress, Array.Empty<uint>(), new HashSet<ulong> { targetAddress }) };
        var chains = new List<MemoryPointerChain>();
        var keys = new HashSet<string>(StringComparer.Ordinal);
        var truncated = indexTruncated;
        var edgesExamined = 0;
        for (var depth = 1; depth <= options.MaxDepth && frontier.Count > 0; depth++)
        {
            var next = new List<PointerState>();
            foreach (var state in frontier.OrderBy(item => item.Target))
            {
                cancellationToken.ThrowIfCancellationRequested();
                var minimum = state.Target > options.MaxOffset ? state.Target - options.MaxOffset : 0;
                for (var index = LowerBound(entries, minimum); index < entries.Count && entries[index].Value <= state.Target; index++)
                {
                    if (++edgesExamined > MaxPointerEdgesExamined)
                    {
                        truncated = true;
                        goto SearchComplete;
                    }
                    if ((edgesExamined & 0xFFF) == 0)
                        cancellationToken.ThrowIfCancellationRequested();
                    var entry = entries[index];
                    if (!state.Visited.Add(entry.Address))
                        continue;
                    var offset = checked((uint)(state.Target - entry.Value));
                    var reverseOffsets = state.ReverseOffsets.Append(offset).ToArray();
                    if (entry.Address >= identity.ModuleBaseAddress && entry.Address <= moduleEnd - 8)
                    {
                        var offsets = reverseOffsets.Reverse().ToArray();
                        var chain = new MemoryPointerChain(entry.Address - identity.ModuleBaseAddress, offsets);
                        var key = $"{chain.RootRva:X}:{string.Join(',', offsets)}";
                        if (keys.Add(key))
                        {
                            if (chains.Count == options.MaxCandidates)
                            {
                                truncated = true;
                                goto SearchComplete;
                            }
                            else
                                chains.Add(chain);
                        }
                    }
                    else if (depth < options.MaxDepth)
                    {
                        if (next.Count == options.MaxFrontier)
                            truncated = true;
                        else
                            next.Add(new(entry.Address, reverseOffsets, new HashSet<ulong>(state.Visited)));
                    }
                    state.Visited.Remove(entry.Address);
                }
            }
            frontier = next
                .OrderBy(item => item.Target)
                .ThenBy(item => string.Join(',', item.ReverseOffsets))
                .ToList();
        }
    SearchComplete:
        chains.Sort(CompareChains);
        return new(chains, truncated, indexTruncated);
    }

    public static async Task<PointerResolutionResult> ResolvePointerChainAsync(
        MemoryPointerChain chain,
        NativeProcessIdentity expectedIdentity,
        IReadOnlyNativeMemorySession session,
        int terminalByteLength,
        CancellationToken cancellationToken)
    {
        ValidateChain(chain);
        ValidateIdentity(expectedIdentity);
        ArgumentNullException.ThrowIfNull(session);
        if (terminalByteLength is < 1 or > 4096)
            throw new ArgumentOutOfRangeException(nameof(terminalByteLength));
        if (!IdentityEquals(expectedIdentity, session.Identity))
            return Result("identity-mismatch", "The opened session does not exactly match the requested process identity.");
        var initialFailure = await session.RevalidateAsync(cancellationToken);
        if (initialFailure is not null)
            return Result("identity-invalidated", ValidReason(initialFailure));

        ulong pointerAddress;
        try
        {
            pointerAddress = checked(expectedIdentity.ModuleBaseAddress + chain.RootRva);
            if (chain.RootRva >= expectedIdentity.ModuleSize || checked(chain.RootRva + 8) > expectedIdentity.ModuleSize)
                return Result("invalid-chain", "The pointer-chain root is outside the requested main module.");
        }
        catch (OverflowException)
        {
            return Result("invalid-chain", "The pointer-chain root overflows the address space.");
        }

        var hops = new List<PointerResolutionHop>(chain.Offsets.Count);
        for (var level = 0; level < chain.Offsets.Count; level++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var read = session.Read(pointerAddress, 8);
            ValidateRead(read, 8);
            if (read.Status != "success")
                return await FinishFailureAsync(
                    "read-failed", $"Pointer hop {level + 1} was not fully readable.", hops,
                    pointerAddress, new(read.Status, read.Bytes.ToArray(), read.Win32ErrorCode, read.Reason));
            var value = BinaryPrimitives.ReadUInt64LittleEndian(read.Bytes);
            if (value < MinUserAddress || value > MaxUserAddress)
                return await FinishFailureAsync(
                    "invalid-pointer", $"Pointer hop {level + 1} produced an invalid user address.", hops,
                    pointerAddress, new(read.Status, read.Bytes.ToArray(), read.Win32ErrorCode, read.Reason));
            ulong resolved;
            try
            {
                resolved = checked(value + chain.Offsets[level]);
            }
            catch (OverflowException)
            {
                return await FinishFailureAsync(
                    "invalid-pointer", $"Pointer hop {level + 1} overflowed while applying its offset.", hops,
                    pointerAddress, new(read.Status, read.Bytes.ToArray(), read.Win32ErrorCode, read.Reason));
            }
            if (resolved < MinUserAddress || resolved > MaxUserAddress)
                return await FinishFailureAsync(
                    "invalid-pointer", $"Pointer hop {level + 1} resolved outside the supported user address range.", hops,
                    pointerAddress, new(read.Status, read.Bytes.ToArray(), read.Win32ErrorCode, read.Reason));
            hops.Add(new(level + 1, pointerAddress, read.Bytes.ToArray(), value, chain.Offsets[level], resolved));
            pointerAddress = resolved;
        }

        cancellationToken.ThrowIfCancellationRequested();
        var terminal = session.Read(pointerAddress, terminalByteLength);
        ValidateRead(terminal, terminalByteLength);
        var terminalEvidence = new MemoryReadEvidence(
            terminal.Status, terminal.Bytes.ToArray(), terminal.Win32ErrorCode, terminal.Reason);
        var finalFailure = await session.RevalidateAsync(cancellationToken);
        if (finalFailure is not null)
            return Result("identity-invalidated", ValidReason(finalFailure), hops, pointerAddress, terminalEvidence);
        if (!IdentityEquals(expectedIdentity, session.Identity))
            return Result("identity-invalidated", "The session identity changed during pointer resolution.", hops, pointerAddress, terminalEvidence);
        return terminal.Status == "success"
            ? Result("complete", null, hops, pointerAddress, terminalEvidence)
            : Result("read-failed", "The terminal range was not fully readable.", hops, pointerAddress, terminalEvidence);

        PointerResolutionResult Result(
            string status,
            string? reason,
            IReadOnlyList<PointerResolutionHop>? resultHops = null,
            ulong? terminalAddress = null,
            MemoryReadEvidence? terminalRead = null,
            ulong? failedReadAddress = null,
            MemoryReadEvidence? failedRead = null) =>
            new(status, reason, expectedIdentity, session.Identity, resultHops ?? Array.Empty<PointerResolutionHop>(),
                terminalAddress, terminalRead, failedReadAddress, failedRead);

        async Task<PointerResolutionResult> FinishFailureAsync(
            string status,
            string reason,
            IReadOnlyList<PointerResolutionHop> resultHops,
            ulong failedReadAddress,
            MemoryReadEvidence failedRead)
        {
            var identityFailure = await session.RevalidateAsync(cancellationToken);
            if (identityFailure is not null)
                return Result("identity-invalidated", ValidReason(identityFailure), resultHops,
                    failedReadAddress: failedReadAddress, failedRead: failedRead);
            if (!IdentityEquals(expectedIdentity, session.Identity))
                return Result("identity-invalidated", "The session identity changed during pointer resolution.", resultHops,
                    failedReadAddress: failedReadAddress, failedRead: failedRead);
            return Result(status, reason, resultHops, failedReadAddress: failedReadAddress, failedRead: failedRead);
        }
    }

    private static List<Region> ValidateAndJoin(MemorySnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ValidateIdentity(snapshot.Identity);
        ArgumentNullException.ThrowIfNull(snapshot.Segments);
        var ordered = snapshot.Segments.OrderBy(segment => segment?.StartAddress ?? 0).ToArray();
        long total = 0;
        ulong previousEnd = 0;
        foreach (var segment in ordered)
        {
            if (segment is null || segment.Bytes is null || segment.Bytes.Length == 0)
                throw new InvalidDataException("Snapshot segments must contain explicit nonempty bytes.");
            RequireUserAddress(segment.StartAddress, nameof(snapshot));
            ulong end;
            try
            {
                end = checked(segment.StartAddress + (ulong)segment.Bytes.Length);
                total = checked(total + segment.Bytes.Length);
            }
            catch (OverflowException exception)
            {
                throw new InvalidDataException("A snapshot segment range or byte total overflowed.", exception);
            }
            if (end - 1 > MaxUserAddress)
                throw new InvalidDataException("A snapshot segment extends outside the supported user address range.");
            if (segment.StartAddress < previousEnd)
                throw new InvalidDataException("Snapshot segments cannot overlap.");
            if (total > MaxSnapshotBytes)
                throw new InvalidDataException("Snapshot raw bytes exceed the 64 MiB discovery limit.");
            previousEnd = end;
        }

        var regions = new List<Region>();
        for (var first = 0; first < ordered.Length;)
        {
            var last = first + 1;
            var byteLength = ordered[first]!.Bytes.Length;
            var groupEnd = checked(ordered[first]!.StartAddress + (ulong)byteLength);
            while (last < ordered.Length && ordered[last]!.StartAddress == groupEnd)
            {
                byteLength = checked(byteLength + ordered[last]!.Bytes.Length);
                groupEnd = checked(groupEnd + (ulong)ordered[last]!.Bytes.Length);
                last++;
            }
            var joined = new byte[byteLength];
            var destination = 0;
            for (var index = first; index < last; index++)
            {
                ordered[index]!.Bytes.CopyTo(joined, destination);
                destination += ordered[index]!.Bytes.Length;
            }
            regions.Add(new(ordered[first]!.StartAddress, joined));
            first = last;
        }
        return regions;
    }

    private static void ValidateIdentity(NativeProcessIdentity identity)
    {
        ArgumentNullException.ThrowIfNull(identity);
        ulong moduleEnd;
        try
        {
            moduleEnd = checked(identity.ModuleBaseAddress + identity.ModuleSize);
        }
        catch (OverflowException exception)
        {
            throw new InvalidDataException("The native identity contains an overflowing module range.", exception);
        }
        if (identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 ||
            string.IsNullOrWhiteSpace(identity.ExecutablePath) || identity.ExecutableSha256.Length != 64 ||
            !identity.ExecutableSha256.All(Uri.IsHexDigit) || identity.ModuleBaseAddress < MinUserAddress ||
            identity.ModuleSize == 0 || moduleEnd - 1 > MaxUserAddress)
            throw new InvalidDataException("The snapshot contains an invalid native process identity.");
    }

    private static bool IdentityEquals(NativeProcessIdentity left, NativeProcessIdentity right) =>
        left.ProcessId == right.ProcessId && left.ProcessStartUtcTicks == right.ProcessStartUtcTicks &&
        string.Equals(left.ExecutablePath, right.ExecutablePath, StringComparison.OrdinalIgnoreCase) &&
        string.Equals(left.ExecutableSha256, right.ExecutableSha256, StringComparison.OrdinalIgnoreCase) &&
        left.ModuleBaseAddress == right.ModuleBaseAddress && left.ModuleSize == right.ModuleSize;

    private static void ValidatePointerOptions(MemoryPointerSearchOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        if (options.MaxDepth is < 1 or > 4 || options.MaxOffset > 4096 || options.MaxCandidates is < 1 or > 100_000 ||
            options.MaxIndexEntries is < 1 or > 8_388_608 || options.MaxFrontier is < 1 or > 1_000_000)
            throw new ArgumentOutOfRangeException(nameof(options), "Pointer bounds exceed supported discovery limits.");
    }

    private static void ValidateChain(MemoryPointerChain chain)
    {
        ArgumentNullException.ThrowIfNull(chain);
        ArgumentNullException.ThrowIfNull(chain.Offsets);
        if (chain.Offsets.Count is < 1 or > 4 || chain.Offsets.Any(offset => offset > 4096))
            throw new ArgumentException("A pointer chain must contain one to four offsets, each no greater than 4096.", nameof(chain));
    }

    private static void ValidateRead(NativeReadResult read, int requestedLength)
    {
        if (read is null || read.Bytes is null || read.Bytes.Length > requestedLength || read.Reason is { Length: > 1024 })
            throw new InvalidDataException("The memory session returned an invalid read result.");
        var valid = read.Status switch
        {
            "success" => read.Bytes.Length == requestedLength && read.Win32ErrorCode is null && read.Reason is null,
            "partial" => read.Bytes.Length is > 0 && read.Bytes.Length < requestedLength && !string.IsNullOrWhiteSpace(read.Reason),
            "unavailable" => read.Bytes.Length == 0 && !string.IsNullOrWhiteSpace(read.Reason),
            _ => false
        };
        if (!valid)
            throw new InvalidDataException("The memory session returned an incoherent read result.");
    }

    private static string ValidReason(string reason)
    {
        if (string.IsNullOrWhiteSpace(reason) || reason.Length > 1024)
            throw new InvalidDataException("The memory session returned an invalid identity failure reason.");
        return reason;
    }

    private static bool CompareValues(ReadOnlySpan<byte> left, ReadOnlySpan<byte> right, MemoryValueKind kind, MemoryComparison comparison)
    {
        return kind switch
        {
            MemoryValueKind.Int32 => Compare(BinaryPrimitives.ReadInt32LittleEndian(left), BinaryPrimitives.ReadInt32LittleEndian(right), comparison),
            MemoryValueKind.UInt32 => Compare(BinaryPrimitives.ReadUInt32LittleEndian(left), BinaryPrimitives.ReadUInt32LittleEndian(right), comparison),
            MemoryValueKind.Int64 => Compare(BinaryPrimitives.ReadInt64LittleEndian(left), BinaryPrimitives.ReadInt64LittleEndian(right), comparison),
            MemoryValueKind.UInt64 => Compare(BinaryPrimitives.ReadUInt64LittleEndian(left), BinaryPrimitives.ReadUInt64LittleEndian(right), comparison),
            MemoryValueKind.Float32 => CompareFloat(BinaryPrimitives.ReadSingleLittleEndian(left), BinaryPrimitives.ReadSingleLittleEndian(right), comparison),
            MemoryValueKind.Float64 => CompareFloat(BinaryPrimitives.ReadDoubleLittleEndian(left), BinaryPrimitives.ReadDoubleLittleEndian(right), comparison),
            _ => false
        };
    }

    private static bool Compare<T>(T left, T right, MemoryComparison comparison) where T : IComparable<T> => comparison switch
    {
        MemoryComparison.Changed => left.CompareTo(right) != 0,
        MemoryComparison.Unchanged => left.CompareTo(right) == 0,
        MemoryComparison.Increased => right.CompareTo(left) > 0,
        MemoryComparison.Decreased => right.CompareTo(left) < 0,
        _ => false
    };

    private static bool CompareFloat<T>(T left, T right, MemoryComparison comparison) where T : IFloatingPointIeee754<T>
    {
        if (!T.IsFinite(left) || !T.IsFinite(right))
            return false;
        return Compare(left, right, comparison);
    }

    private static string Format(ReadOnlySpan<byte> bytes, MemoryValueKind kind) => kind switch
    {
        MemoryValueKind.Int32 => BinaryPrimitives.ReadInt32LittleEndian(bytes).ToString(CultureInfo.InvariantCulture),
        MemoryValueKind.UInt32 => BinaryPrimitives.ReadUInt32LittleEndian(bytes).ToString(CultureInfo.InvariantCulture),
        MemoryValueKind.Int64 => BinaryPrimitives.ReadInt64LittleEndian(bytes).ToString(CultureInfo.InvariantCulture),
        MemoryValueKind.UInt64 => BinaryPrimitives.ReadUInt64LittleEndian(bytes).ToString(CultureInfo.InvariantCulture),
        MemoryValueKind.Float32 => BinaryPrimitives.ReadSingleLittleEndian(bytes).ToString("R", CultureInfo.InvariantCulture),
        MemoryValueKind.Float64 => BinaryPrimitives.ReadDoubleLittleEndian(bytes).ToString("R", CultureInfo.InvariantCulture),
        _ => throw new ArgumentOutOfRangeException(nameof(kind))
    };

    private static byte?[] ParsePattern(string pattern)
    {
        if (string.IsNullOrWhiteSpace(pattern))
            throw new ArgumentException("A byte pattern is required.", nameof(pattern));
        var parts = pattern.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length is < 1 or > 1024)
            throw new ArgumentException("A byte pattern must contain between 1 and 1024 tokens.", nameof(pattern));
        var result = new byte?[parts.Length];
        for (var index = 0; index < parts.Length; index++)
        {
            if (parts[index] == "??")
                continue;
            if (parts[index].Length != 2 || !byte.TryParse(parts[index], NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var value))
                throw new ArgumentException("Pattern tokens must be two hexadecimal digits or ??.", nameof(pattern));
            result[index] = value;
        }
        return result;
    }

    private static int Width(MemoryValueKind kind) => kind switch
    {
        MemoryValueKind.Int32 or MemoryValueKind.UInt32 or MemoryValueKind.Float32 => 4,
        MemoryValueKind.Int64 or MemoryValueKind.UInt64 or MemoryValueKind.Float64 => 8,
        _ => throw new ArgumentOutOfRangeException(nameof(kind))
    };

    private static void ValidateLimit(int value, string name)
    {
        if (value is < 1 or > 1_000_000)
            throw new ArgumentOutOfRangeException(name, "The match limit must be between 1 and 1000000.");
    }

    private static void RequireUserAddress(ulong address, string name)
    {
        if (address < MinUserAddress || address > MaxUserAddress)
            throw new ArgumentOutOfRangeException(name, "Address is outside the supported 64-bit user range.");
    }

    private static int LowerBound(IReadOnlyList<PointerEntry> entries, ulong value)
    {
        var low = 0;
        var high = entries.Count;
        while (low < high)
        {
            var middle = low + ((high - low) / 2);
            if (entries[middle].Value < value)
                low = middle + 1;
            else
                high = middle;
        }
        return low;
    }

    private static int CompareChains(MemoryPointerChain left, MemoryPointerChain right)
    {
        var comparison = left.RootRva.CompareTo(right.RootRva);
        if (comparison != 0)
            return comparison;
        var count = Math.Min(left.Offsets.Count, right.Offsets.Count);
        for (var index = 0; index < count; index++)
        {
            comparison = left.Offsets[index].CompareTo(right.Offsets[index]);
            if (comparison != 0)
                return comparison;
        }
        return left.Offsets.Count.CompareTo(right.Offsets.Count);
    }

    private delegate bool SpanPredicate<T>(ReadOnlySpan<byte> bytes, T expected);
    private delegate string SpanFormatter(ReadOnlySpan<byte> bytes);
    private sealed record Region(ulong StartAddress, byte[] Bytes)
    {
        public ulong EndAddress => checked(StartAddress + (ulong)Bytes.Length);
    }
    private sealed record PointerEntry(ulong Value, ulong Address);
    private sealed record PointerState(ulong Target, IReadOnlyList<uint> ReverseOffsets, HashSet<ulong> Visited);
}
