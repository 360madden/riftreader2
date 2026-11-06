using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CastingReferenceInlineCaptureRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    string StartAddress,
    long MaxScanBytes,
    int MaxDurationMilliseconds,
    int MaxRegionCount,
    int MaxMatchCount,
    int MaxCopiedCandidates);

internal sealed record CastingReferenceInlineCandidate(
    string MarkerAddress,
    string Status,
    string? Reason,
    CastingReferenceNeighborhood? Neighborhood);

internal sealed record CastingReferenceNeighborhood(
    string Status,
    string? Reason,
    string MarkerAddress,
    string WindowStart,
    string StartedAtUtc,
    string CompletedAtUtc,
    IReadOnlyList<NativeMemorySnapshotChunk> Chunks);

internal sealed record CastingReferenceInlineCaptureResult(
    int SchemaVersion,
    string EvidenceKind,
    CastingReferenceInlineCaptureRequest Request,
    NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    string Status,
    string? Reason,
    TypedApiScoutResult Scout,
    int CopiedCandidates,
    bool CopyLimited,
    IReadOnlyList<CastingReferenceInlineCandidate> Candidates,
    IReadOnlyList<string> Limitations);

/// <summary>
/// Fixed-marker, read-only scan/copy core for RR2CASTREF1 ability-reference wires.
/// It deliberately exposes no caller-selected marker or action capability. A future
/// command wrapper owns request-file hashing and atomic report publication.
/// </summary>
internal static class CastingReferenceInlineCaptureCore
{
    internal const string MarkerText = "RR2CASTREF1|";
    internal const string RequestKind = "native-casting-reference-inline-capture-request/1";
    internal const string EvidenceKind = "native-casting-reference-inline-capture/1";
    internal const string CurrentBuildSha256 =
        "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8";
    internal const int ChunkBytes = 64 * 1024;
    internal const long MaxScanBytes = 512L * 1024 * 1024;
    internal const int MaxMatches = 128;
    internal const int MaxCopies = 8;
    internal const int PageBytes = 4096;
    internal const int PagesBefore = 2;
    internal const int PagesAfter = 4;
    internal const int WindowBytes = (PagesBefore + 1 + PagesAfter) * PageBytes;
    private const ulong MinUserAddress = 0x10000;
    private const ulong MaxUserEnd = 0x00007FFF_FFFF_FFFF;
    private const uint MemPrivate = 0x20000;
    private const uint PageGuard = 0x100;
    private static readonly HashSet<uint> ReadableBaseProtections =
        [0x02, 0x04, 0x08, 0x20, 0x40, 0x80];
    private static readonly byte[] Marker = Encoding.ASCII.GetBytes(MarkerText);
    private static readonly byte[] PlausibleStart = Encoding.ASCII.GetBytes(MarkerText + "{");

    internal static CastingReferenceInlineCaptureResult Run(
        CastingReferenceInlineCaptureRequest request,
        NativeProcessIdentity identity,
        IReadOnlyList<WindowsMemoryRegion> regions,
        Func<ulong, byte[], int, TypedApiScanReadResult> scanRead,
        Func<ulong, int, NativeReadResult> neighborhoodRead,
        Func<string?> revalidateIdentity,
        Func<long>? monotonicMilliseconds = null,
        long? deadlineStartedAtMilliseconds = null,
        Func<string>? utcNow = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(identity);
        ArgumentNullException.ThrowIfNull(regions);
        ArgumentNullException.ThrowIfNull(scanRead);
        ArgumentNullException.ThrowIfNull(neighborhoodRead);
        ArgumentNullException.ThrowIfNull(revalidateIdentity);
        ValidateRequestBounds(request);
        if (identity.ProcessId != request.Target.ProcessId ||
            identity.ProcessStartUtcTicks != request.Target.ProcessStartUtcTicks ||
            identity.ExecutableSha256 != CurrentBuildSha256)
            throw new InvalidDataException("Exact current-build process identity is required.");
        if (regions.Count > request.MaxRegionCount)
            throw new InvalidDataException("Enumerated region count exceeds the fixed request limit.");
        monotonicMilliseconds ??= () => Environment.TickCount64;
        var deadlineStarted = deadlineStartedAtMilliseconds ?? monotonicMilliseconds();
        var lastMonotonic = deadlineStarted;
        bool DeadlineExceeded()
        {
            var current = monotonicMilliseconds();
            if (current < lastMonotonic)
                throw new InvalidDataException("Monotonic capture clock moved backward.");
            lastMonotonic = current;
            return checked(current - deadlineStarted) >= request.MaxDurationMilliseconds;
        }
        utcNow ??= () => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
        var started = utcNow();
        var candidates = new List<CastingReferenceInlineCandidate>();
        var copied = 0;
        var copyLimited = false;

        var scout = Scan(
            regions, ParseCanonicalAddress(request.StartAddress), request.MaxScanBytes,
            request.MaxMatchCount, scanRead, DeadlineExceeded, cancellationToken,
            address =>
            {
                if (copied >= request.MaxCopiedCandidates)
                {
                    copyLimited = true;
                    candidates.Add(new($"0x{address:X}", "copy-budget-exceeded",
                        "The fixed candidate-copy budget was reached.", null));
                    return;
                }
                try
                {
                    var neighborhood = CaptureNeighborhood(
                        address, neighborhoodRead, DeadlineExceeded, utcNow, cancellationToken);
                    if (neighborhood.Chunks.Count > 0)
                        copied++;
                    candidates.Add(new($"0x{address:X}", neighborhood.Status,
                        neighborhood.Reason,
                        neighborhood.Chunks.Count == 0 ? null : neighborhood));
                }
                catch (ArgumentOutOfRangeException)
                {
                    candidates.Add(new($"0x{address:X}", "window-out-of-range",
                        "The marker is too near a supported user-address boundary.", null));
                }
            });

        var identityFailure = revalidateIdentity();
        var deadlineFailure = DeadlineExceeded();
        var completed = utcNow();
        var status = identityFailure is not null ? "identity-invalidated" :
            deadlineFailure || scout.Status != "complete" || copyLimited ? "partial" : "complete";
        var reason = identityFailure ?? (scout.Status != "complete" ? scout.Reason :
            deadlineFailure ? "time-budget-exceeded-during-capture-or-revalidation" :
            copyLimited ? "candidate-copy-budget-exceeded" : null);
        IReadOnlyList<CastingReferenceInlineCandidate> publishedCandidates =
            identityFailure is null ? candidates : candidates
            .Select(item => item with
            {
                Status = "identity-invalidated",
                Reason = "The process identity changed; captured bytes are not usable.",
                Neighborhood = null
            }).ToArray();
        return new(
            1, EvidenceKind, request, identity, started, completed, status, reason,
            scout, copied, copyLimited, publishedCandidates,
            [
                "Only the fixed RR2CASTREF1| marker is searched in the caller-provided bounded MEM_PRIVATE region inventory.",
                "This core validates region ordering, type and page protection; the future Windows collector must prove committed state when producing the inventory.",
                "A marker plus opening brace is only a plausibility gate; the retained wire requires strict offline decoding.",
                "Neighborhood pages are copied through read-only memory calls immediately in the match callback.",
                "The scan is bounded and a partial result is never a whole-process absence claim.",
                "No captured bytes are usable when exact process postflight identity fails.",
                "The core sends no input, invokes no game function and writes no process memory."
            ]);
    }

    internal static void PublishNewDirectory(string stagingDirectory, string outputDirectory)
    {
        var staging = Path.GetFullPath(stagingDirectory);
        var output = Path.GetFullPath(outputDirectory);
        if (!Directory.Exists(staging) || File.Exists(staging) ||
            Directory.Exists(output) || File.Exists(output))
            throw new IOException("Casting-reference evidence requires an existing staging directory and an unused output path.");
        Directory.Move(staging, output);
    }

    internal static void ValidateRequestBounds(CastingReferenceInlineCaptureRequest request)
    {
        if (request.SchemaVersion != 1 || request.EvidenceKind != RequestKind)
            throw new InvalidDataException("Only the fixed casting-reference capture request is supported.");
        if (request.Target.ProcessId <= 0 || request.Target.ProcessStartUtcTicks <= 0 ||
            request.Target.ExecutableSha256 != CurrentBuildSha256)
            throw new InvalidDataException("Exact current-build process identity is required.");
        _ = ParseCanonicalAddress(request.StartAddress);
        if (request.MaxScanBytes is < ChunkBytes or > MaxScanBytes ||
            request.MaxDurationMilliseconds is < 1 or > 30_000 ||
            request.MaxRegionCount is < 1 or > 32_768 ||
            request.MaxMatchCount is < 1 or > MaxMatches ||
            request.MaxCopiedCandidates is < 1 or > MaxCopies)
            throw new InvalidDataException("Casting-reference scan bounds exceed the fixed safe limits.");
    }

    private static TypedApiScoutResult Scan(
        IReadOnlyList<WindowsMemoryRegion> regions,
        ulong startAddress,
        long maxScanBytes,
        int maxMatches,
        Func<ulong, byte[], int, TypedApiScanReadResult> read,
        Func<bool> timeExceeded,
        CancellationToken cancellationToken,
        Action<ulong> onMatch)
    {
        var scopes = new List<(ulong Begin, ulong End)>();
        long eligible = 0;
        ulong lastRegionEnd = 0;
        foreach (var region in regions)
        {
            var end = checked(region.BaseAddress + region.RegionSize);
            if (region.RegionSize == 0 || region.BaseAddress < MinUserAddress ||
                region.BaseAddress < lastRegionEnd || end > MaxUserEnd)
                throw new InvalidDataException("Memory regions must be ordered, nonoverlapping and inside user space.");
            lastRegionEnd = end;
            if (region.Type != MemPrivate || end <= startAddress)
                continue;
            var baseProtection = region.Protection & 0xFF;
            if ((region.Protection & PageGuard) != 0 ||
                !ReadableBaseProtections.Contains(baseProtection))
                throw new InvalidDataException(
                    "MEM_PRIVATE scan regions require exactly one readable base protection and must be nonguard.");
            var begin = Math.Max(region.BaseAddress, startAddress);
            scopes.Add((begin, end));
            eligible = checked(eligible + checked((long)(end - begin)));
        }

        var matcher = new FixedMatcher(maxMatches);
        var buffer = GC.AllocateUninitializedArray<byte>(ChunkBytes);
        var covered = new List<TypedApiScanSpan>();
        var holes = new List<TypedApiScanHole>();
        long attempted = 0, examined = 0;
        var touched = 0;
        ulong? firstHole = null;
        var lastCursor = startAddress;
        ulong Resume(ulong value) => value - startAddress > (ulong)(Marker.Length - 1)
            ? value - (ulong)(Marker.Length - 1) : startAddress;
        TypedApiScoutResult Finish(string state, string? why, ulong? next) =>
            new(state, why, startAddress, next, eligible, attempted, examined,
                scopes.Count, touched, matcher.Addresses.ToArray(), covered.ToArray(), holes.ToArray());

        foreach (var scope in scopes)
        {
            var address = scope.Begin;
            var regionTouched = false;
            while (address < scope.End)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (timeExceeded())
                    return Finish("partial", "time-budget-exceeded", Resume(firstHole ?? address));
                if (attempted >= maxScanBytes)
                    return Finish("partial", "byte-budget-exceeded", Resume(firstHole ?? address));
                if (!regionTouched) { touched++; regionTouched = true; }
                var remaining = checked((ulong)(maxScanBytes - attempted));
                var count = checked((int)Math.Min((ulong)ChunkBytes, Math.Min(scope.End - address, remaining)));
                var result = read(address, buffer, count);
                if (result.BytesRead < 0 || result.BytesRead > count ||
                    (result.Complete && result.BytesRead != count))
                    throw new InvalidDataException("Memory reader returned an inconsistent byte count.");
                attempted += count;
                var readable = result.Complete || result.BytesRead < count ? result.BytesRead : 0;
                if (readable > 0)
                {
                    var previous = matcher.Addresses.Count;
                    matcher.Feed(address, buffer.AsSpan(0, readable));
                    for (var index = previous; index < matcher.Addresses.Count; index++)
                        onMatch(matcher.Addresses[index]);
                    var consumed = readable;
                    if (matcher.Exceeded)
                    {
                        var end = checked(matcher.FirstUnretained!.Value + (ulong)Marker.Length);
                        consumed = checked((int)(end - address));
                    }
                    AddCovered(covered, address, consumed);
                    examined += consumed;
                }
                if (readable < count)
                {
                    var hole = checked(address + (ulong)readable);
                    holes.Add(new(hole, count - readable,
                        readable > 0 ? "partial-read" : "unavailable", result.Win32Error));
                    firstHole ??= hole;
                    matcher.Reset();
                }
                if (matcher.Exceeded)
                    return Finish("partial", "candidate-budget-exceeded", matcher.FirstUnretained);
                address = checked(address + (ulong)count);
                lastCursor = address;
            }
        }
        if (timeExceeded())
            return Finish("partial", "time-budget-exceeded", Resume(firstHole ?? lastCursor));
        if (firstHole is not null)
            return Finish("partial", "read-holes", Resume(firstHole.Value));
        return Finish("complete", null, null);
    }

    private static CastingReferenceNeighborhood CaptureNeighborhood(
        ulong markerAddress,
        Func<ulong, int, NativeReadResult> read,
        Func<bool> timeExceeded,
        Func<string> utcNow,
        CancellationToken cancellationToken)
    {
        if (markerAddress < MinUserAddress + PagesBefore * PageBytes ||
            markerAddress > MaxUserEnd - (PagesAfter + 1UL) * PageBytes)
            throw new ArgumentOutOfRangeException(nameof(markerAddress));
        var windowStart = (markerAddress & ~(ulong)(PageBytes - 1)) - PagesBefore * PageBytes;
        var started = utcNow();
        CastingReferenceNeighborhood Finish(string state, string? why,
            IReadOnlyList<NativeMemorySnapshotChunk> chunks) =>
            new(state, why, $"0x{markerAddress:X}", $"0x{windowStart:X}", started, utcNow(), chunks);
        if (timeExceeded())
            return Finish("time-budget-exceeded", "Capture budget expired before prefix recheck.", []);
        var header = read(markerAddress, PlausibleStart.Length);
        if (header.Status != "success" || header.Bytes.Length != PlausibleStart.Length)
            return Finish("header-unavailable", "The marker plus opening brace could not be re-read.", []);
        if (!PlausibleStart.AsSpan().SequenceEqual(header.Bytes))
            return Finish("prefix-not-plausible", "The RR2CASTREF1 marker is not immediately followed by '{'.", []);
        var chunks = new List<NativeMemorySnapshotChunk>();
        var budgetExceeded = false;
        for (var page = 0; page < PagesBefore + 1 + PagesAfter; page++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (timeExceeded()) { budgetExceeded = true; break; }
            var address = checked(windowStart + (ulong)(page * PageBytes));
            var result = read(address, PageBytes);
            if (result.Status is not ("success" or "partial" or "unavailable") ||
                result.Bytes.Length > PageBytes ||
                (result.Status == "success" && result.Bytes.Length != PageBytes) ||
                (result.Status == "unavailable" && result.Bytes.Length != 0) ||
                (result.Status == "partial" && result.Bytes.Length is 0 or PageBytes))
                throw new InvalidDataException("Read-only memory reader returned an inconsistent neighborhood chunk.");
            chunks.Add(new($"0x{address:X}", PageBytes, result.Status, result.Bytes.Length,
                result.Bytes.Length == 0 ? null : Convert.ToBase64String(result.Bytes),
                result.Bytes.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(result.Bytes)),
                result.Win32ErrorCode, result.Reason));
        }
        budgetExceeded |= timeExceeded();
        var successCount = chunks.Count(item => item.Status == "success");
        var status = budgetExceeded ? "time-budget-exceeded" :
            successCount == PagesBefore + 1 + PagesAfter ? "complete" :
            successCount > 0 ? "partial" : "failed";
        var reason = status switch
        {
            "complete" => null,
            "time-budget-exceeded" => "Capture stopped at the declared time budget.",
            "partial" => "At least one neighborhood page was inaccessible or partial.",
            _ => "No neighborhood page was read completely."
        };
        return Finish(status, reason, chunks);
    }

    private static ulong ParseCanonicalAddress(string value)
    {
        if (string.IsNullOrWhiteSpace(value) || !value.StartsWith("0x", StringComparison.Ordinal) ||
            value.Length is < 3 or > 18 || !value.AsSpan(2).ToString().All(Uri.IsHexDigit) ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier,
                CultureInfo.InvariantCulture, out var address) || address < MinUserAddress ||
            !string.Equals(value, $"0x{address:X}", StringComparison.Ordinal))
            throw new InvalidDataException("startAddress must be canonical uppercase hexadecimal inside user space.");
        return address;
    }

    private static void AddCovered(List<TypedApiScanSpan> spans, ulong address, int count)
    {
        if (count <= 0) return;
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

    private sealed class FixedMatcher
    {
        private readonly int[] failure = BuildFailure();
        private readonly int max;
        private int matched;
        private ulong? next;
        internal FixedMatcher(int maxMatches) => max = maxMatches;
        internal List<ulong> Addresses { get; } = [];
        internal bool Exceeded { get; private set; }
        internal ulong? FirstUnretained { get; private set; }
        internal void Reset() { matched = 0; next = null; }
        internal void Feed(ulong address, ReadOnlySpan<byte> bytes)
        {
            if (bytes.IsEmpty || Exceeded) return;
            var end = checked(address + (ulong)bytes.Length);
            if (next != address) matched = 0;
            next = end;
            for (var i = 0; i < bytes.Length; i++)
            {
                while (matched > 0 && bytes[i] != Marker[matched]) matched = failure[matched - 1];
                if (bytes[i] == Marker[matched]) matched++;
                if (matched != Marker.Length) continue;
                var found = checked(address + (ulong)i - (ulong)(Marker.Length - 1));
                if (Addresses.Count == max)
                {
                    FirstUnretained = found; Exceeded = true; matched = failure[matched - 1]; return;
                }
                Addresses.Add(found);
                matched = failure[matched - 1];
            }
        }
        private static int[] BuildFailure()
        {
            var table = new int[Marker.Length];
            for (var i = 1; i < Marker.Length; i++)
            {
                var prefix = table[i - 1];
                while (prefix > 0 && Marker[i] != Marker[prefix]) prefix = table[prefix - 1];
                if (Marker[i] == Marker[prefix]) prefix++;
                table[i] = prefix;
            }
            return table;
        }
    }
}
