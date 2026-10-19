using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class MemoryDiscoveryCommand
{
    private const int MaxRequestBytes = 65_536;
    private const long MaxSnapshotBytes = 64L * 1024 * 1024;
    private const int MaxSnapshotChunks = 16_384;
    private const int MaxReportBytes = 96 * 1024 * 1024;

    internal static async Task<int> MapAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        var paths = RequirePaths(options);
        var loaded = await LoadAsync<MemoryMapRequest>(paths.Request, cancellationToken);
        var request = loaded.Value;
        if (request.SchemaVersion != 1 || request.EvidenceKind != "native-memory-map-request/1")
            throw new InvalidDataException("Only native-memory-map-request/1 schema version 1 is supported.");
        ValidateTarget(request.Target);
        if (request.MaxRegionCount is < 1 or > 32_768)
            throw new InvalidDataException("maxRegionCount must be between 1 and 32768.");
        ValidateDuration(request.MaxDurationMilliseconds);

        await using var session = await OpenAsync(request.Target, cancellationToken);
        var startedAtUtc = UtcNow();
        var timer = Stopwatch.StartNew();
        var regions = session.EnumerateReadableRegions(
            request.MaxRegionCount, request.MaxDurationMilliseconds, cancellationToken);
        var identityFailure = await session.RevalidateAsync(cancellationToken);
        var status = identityFailure is not null
            ? "identity-invalidated"
            : timer.ElapsedMilliseconds > request.MaxDurationMilliseconds
                ? "time-budget-exceeded"
                : "complete";
        var reason = identityFailure ?? (status == "time-budget-exceeded"
            ? "Memory-map enumeration and identity validation exceeded its declared time budget."
            : null);

        var report = new MemoryMapReport(
            1,
            "native-memory-map/1",
            loaded.Sha256,
            NativeCommandRunner.CreateImplementationIdentity(),
            startedAtUtc,
            UtcNow(),
            status,
            reason,
            session.Identity,
            regions.Select(region => new MemoryMapRegion(
                Hex(region.BaseAddress), region.RegionSize, $"0x{region.Protection:X}", $"0x{region.Type:X}")).ToArray(),
            [
                "Only committed readable non-guard regions are listed.",
                "Addresses are session state for this exact process epoch; no field meaning is inferred."
            ]);
        await WriteNewAsync(paths.Output, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return status == "complete" ? 0 : 3;
    }

    internal static async Task<int> SnapshotAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        var paths = RequirePaths(options);
        var loaded = await LoadAsync<MemorySnapshotRequest>(paths.Request, cancellationToken);
        var request = loaded.Value;
        ValidateSnapshotRequest(request);
        await using var session = await OpenAsync(request.Target, cancellationToken);
        var resolvedRanges = request.Ranges
            .Select(range => new ResolvedRange(
                Resolve(range.AddressKind, ParseHex(range.Address, "range address"),
                    checked((ulong)range.ByteLength), session.Identity),
                range.ByteLength))
            .OrderBy(range => range.Address)
            .ToArray();
        ulong priorEnd = 0;
        foreach (var range in resolvedRanges)
        {
            if (range.Address < priorEnd)
                throw new InvalidDataException("Snapshot ranges overlap after resolving absolute addresses and module RVAs.");
            priorEnd = checked(range.Address + (ulong)range.ByteLength);
        }
        var startedAtUtc = UtcNow();
        var timer = Stopwatch.StartNew();
        var chunks = new List<NativeMemorySnapshotChunk>();
        var budgetExceeded = false;

        foreach (var range in resolvedRanges)
        {
            for (long offset = 0; offset < range.ByteLength; offset += 4096)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (chunks.Count > 0 && timer.ElapsedMilliseconds > request.MaxDurationMilliseconds)
                {
                    budgetExceeded = true;
                    break;
                }
                var count = checked((int)Math.Min(4096, range.ByteLength - offset));
                var address = checked(range.Address + (ulong)offset);
                var read = session.Read(address, count);
                chunks.Add(ToChunk(address, count, read));
            }
            if (budgetExceeded)
                break;
        }

        var identityFailure = await session.RevalidateAsync(cancellationToken);
        var completedAtUtc = UtcNow();
        string status;
        string? reason;
        if (identityFailure is not null)
        {
            status = "identity-invalidated";
            reason = identityFailure;
        }
        else if (budgetExceeded || timer.ElapsedMilliseconds > request.MaxDurationMilliseconds)
        {
            status = "time-budget-exceeded";
            reason = "Snapshot acquisition and identity validation exceeded its declared time budget.";
        }
        else if (chunks.All(chunk => chunk.Status == "success"))
        {
            status = "complete";
            reason = null;
        }
        else if (chunks.Any(chunk => chunk.Status == "success"))
        {
            status = "partial";
            reason = "One or more requested chunks were not read completely.";
        }
        else
        {
            status = "failed";
            reason = "No requested chunk was read completely.";
        }

        var report = new NativeMemorySnapshotFile(
            1,
            "native-memory-snapshot/1",
            new(
                request.EvidenceKind,
                loaded.Sha256,
                "producer-declared",
                NativeCommandRunner.CreateImplementationIdentity()),
            session.Identity,
            startedAtUtc,
            completedAtUtc,
            status,
            reason,
            chunks,
            [
                "Each chunk is one explicit ReadProcessMemory result of at most 4096 bytes; missing bytes are never replaced with zeroes.",
                "Absolute addresses are valid only for this exact process epoch; main-module RVAs are resolved from the bracketed module identity.",
                "ExecutableSha256 identifies on-disk file bytes; loaded module bytes were not hashed.",
                "Raw bytes remain semantically unqualified."
            ]);
        await WriteNewAsync(paths.Output, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            report.SchemaVersion,
            report.EvidenceKind,
            report.Status,
            report.Reason,
            report.StartedAtUtc,
            report.CompletedAtUtc,
            ChunkCount = report.Chunks.Count,
            SuccessfulChunkCount = report.Chunks.Count(chunk => chunk.Status == "success"),
            Output = Path.GetFullPath(paths.Output)
        }, JsonFormat.Options));
        return status == "complete" ? 0 : 3;
    }

    internal static async Task<int> FollowPointerAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        var paths = RequirePaths(options);
        var loaded = await LoadAsync<PointerFollowRequest>(paths.Request, cancellationToken);
        var request = loaded.Value;
        if (request.SchemaVersion != 1 || request.EvidenceKind != "native-pointer-follow-request/1")
            throw new InvalidDataException("Only native-pointer-follow-request/1 schema version 1 is supported.");
        ValidateTarget(request.Target);
        ValidateDuration(request.MaxDurationMilliseconds);
        if (request.TerminalByteLength is < 1 or > 4096)
            throw new InvalidDataException("terminalByteLength must be between 1 and 4096.");
        if (request.Offsets is null || request.Offsets.Count is < 1 or > 4)
            throw new InvalidDataException("offsets must contain between 1 and 4 entries.");
        var chain = new MemoryPointerChain(
            ParseHex(request.RootRva, "rootRva"),
            request.Offsets.Select((value, index) => checked((uint)ParseHex(value, $"offsets[{index}]"))).ToArray());

        await using var session = await OpenAsync(request.Target, cancellationToken);
        var timer = Stopwatch.StartNew();
        var result = await MemoryDiscovery.ResolvePointerChainAsync(
            chain, session.Identity, session, request.TerminalByteLength, cancellationToken);
        if (timer.ElapsedMilliseconds > request.MaxDurationMilliseconds && result.Status == "complete")
            result = result with
            {
                Status = "time-budget-exceeded",
                Reason = "Pointer resolution and terminal identity validation exceeded its declared time budget."
            };
        var report = new PointerFollowReport(
            1,
            "native-pointer-follow/1",
            loaded.Sha256,
            NativeCommandRunner.CreateImplementationIdentity(),
            UtcNow(),
            chain,
            result,
            [
                "The root RVA is relocatable only for the exact executable build; resolved addresses are session state.",
                "A successful chain read demonstrates address resolution, not game-field meaning."
            ]);
        await WriteNewAsync(paths.Output, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return result.Status == "complete" ? 0 : 3;
    }

    private static async Task<WindowsNativeMemorySession> OpenAsync(
        NativeCaptureTarget target,
        CancellationToken cancellationToken) =>
        await WindowsNativeMemorySession.OpenAsync(
            target.ProcessId, target.ProcessStartUtcTicks, target.ExecutableSha256, cancellationToken);

    private static NativeMemorySnapshotChunk ToChunk(ulong address, int requested, NativeReadResult read) =>
        new(
            Hex(address),
            requested,
            read.Status,
            read.Bytes.Length,
            read.Bytes.Length == 0 ? null : Convert.ToBase64String(read.Bytes),
            read.Bytes.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(read.Bytes)),
            read.Win32ErrorCode,
            read.Reason);

    private static void ValidateSnapshotRequest(MemorySnapshotRequest request)
    {
        if (request.SchemaVersion != 1 || request.EvidenceKind != "native-memory-snapshot-request/1")
            throw new InvalidDataException("Only native-memory-snapshot-request/1 schema version 1 is supported.");
        ValidateTarget(request.Target);
        ValidateDuration(request.MaxDurationMilliseconds);
        if (request.Ranges is null || request.Ranges.Count is < 1 or > 256)
            throw new InvalidDataException("ranges must contain between 1 and 256 entries.");
        long total = 0;
        long chunks = 0;
        foreach (var range in request.Ranges)
        {
            if (range is null || range.AddressKind is not ("module-relative-rva" or "absolute-session-address"))
                throw new InvalidDataException("Each snapshot range must have a supported addressKind.");
            if (range.ByteLength is < 1 || range.ByteLength > MaxSnapshotBytes)
                throw new InvalidDataException("Each range byteLength must be between 1 and 67108864.");
            var address = ParseHex(range.Address, "range address");
            _ = checked(address + (ulong)range.ByteLength);
            total = checked(total + range.ByteLength);
            chunks = checked(chunks + (range.ByteLength + 4095L) / 4096L);
        }
        if (total > MaxSnapshotBytes || chunks > MaxSnapshotChunks)
            throw new InvalidDataException("Snapshot requests are limited to 67108864 raw bytes and 16384 chunks.");
    }

    private static void ValidateTarget(NativeCaptureTarget target)
    {
        if (target is null || target.ProcessId <= 0 || target.ProcessStartUtcTicks <= 0 ||
            string.IsNullOrWhiteSpace(target.ExecutableSha256) || target.ExecutableSha256.Length != 64 ||
            !target.ExecutableSha256.All(Uri.IsHexDigit))
            throw new InvalidDataException("target must contain an exact positive PID/start identity and 64-digit executable SHA-256.");
    }

    private static void ValidateDuration(int value)
    {
        if (value is < 1 or > 30_000)
            throw new InvalidDataException("maxDurationMilliseconds must be between 1 and 30000.");
    }

    private static ulong Resolve(string kind, ulong address, ulong length, NativeProcessIdentity identity)
    {
        var end = checked(address + length);
        ulong resolved;
        if (kind == "module-relative-rva")
        {
            if (address >= identity.ModuleSize || end > identity.ModuleSize)
                throw new InvalidDataException("A module-relative snapshot range extends outside the identified main module.");
            resolved = checked(identity.ModuleBaseAddress + address);
        }
        else
        {
            resolved = address;
        }
        var resolvedEnd = checked(resolved + length);
        if (resolved < 0x10000 || resolvedEnd > 0x00007FFF_FFFF_FFFF)
            throw new InvalidDataException("A snapshot range is outside the supported 64-bit user address range.");
        return resolved;
    }

    private static ulong ParseHex(string value, string name)
    {
        if (string.IsNullOrWhiteSpace(value) || !value.StartsWith("0x", StringComparison.Ordinal) ||
            value.Length is < 3 or > 18 ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var parsed) ||
            !string.Equals(value, Hex(parsed), StringComparison.Ordinal))
            throw new InvalidDataException($"{name} must be canonical uppercase hexadecimal such as 0x1000.");
        return parsed;
    }

    private static (string Request, string Output) RequirePaths(IReadOnlyDictionary<string, string> options)
    {
        if (!options.TryGetValue("--request", out var request) || !options.TryGetValue("--output", out var output))
            throw new ArgumentException("--request and --output are required.");
        return (request, output);
    }

    private static async Task<Loaded<T>> LoadAsync<T>(string path, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        await using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaxRequestBytes)
            throw new InvalidDataException("Memory discovery request exceeds 65536 bytes.");
        using var buffer = new MemoryStream(checked((int)stream.Length));
        var block = new byte[8192];
        while (true)
        {
            var remaining = MaxRequestBytes + 1 - checked((int)buffer.Length);
            if (remaining <= 0)
                throw new InvalidDataException("Memory discovery request exceeds 65536 bytes.");
            var count = await stream.ReadAsync(block.AsMemory(0, Math.Min(block.Length, remaining)), cancellationToken);
            if (count == 0)
                break;
            buffer.Write(block, 0, count);
        }
        if (buffer.Length > MaxRequestBytes)
            throw new InvalidDataException("Memory discovery request exceeds 65536 bytes.");
        var bytes = buffer.ToArray();
        var value = JsonSerializer.Deserialize<T>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Memory discovery request is empty.");
        return new(value, Convert.ToHexString(SHA256.HashData(bytes)));
    }

    private static async Task WriteNewAsync<T>(string path, T value, CancellationToken cancellationToken)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value, JsonFormat.Options);
        if (bytes.Length > MaxReportBytes)
            throw new InvalidDataException($"Memory discovery report exceeds the {MaxReportBytes}-byte output limit.");
        await JsonReportWriter.WriteNewAsync(path, value, cancellationToken);
    }

    private static string Hex(ulong value) => $"0x{value:X}";
    private static string UtcNow() => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);

    private sealed record Loaded<T>(T Value, string Sha256);
    private sealed record ResolvedRange(ulong Address, long ByteLength);
}

internal sealed record MemoryMapRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    int MaxRegionCount,
    int MaxDurationMilliseconds);

internal sealed record MemoryMapRegion(string BaseAddress, ulong RegionSize, string Protection, string Type);

internal sealed record MemoryMapReport(
    int SchemaVersion,
    string EvidenceKind,
    string RequestSha256,
    NativeImplementationIdentity Implementation,
    string StartedAtUtc,
    string CompletedAtUtc,
    string Status,
    string? Reason,
    NativeProcessIdentity Identity,
    IReadOnlyList<MemoryMapRegion> Regions,
    IReadOnlyList<string> Limitations);

internal sealed record MemorySnapshotRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    int MaxDurationMilliseconds,
    IReadOnlyList<MemorySnapshotRangeRequest> Ranges);

internal sealed record MemorySnapshotRangeRequest(string AddressKind, string Address, long ByteLength);

internal sealed record PointerFollowRequest(
    int SchemaVersion,
    string EvidenceKind,
    NativeCaptureTarget Target,
    string RootRva,
    IReadOnlyList<string> Offsets,
    int TerminalByteLength,
    int MaxDurationMilliseconds);

internal sealed record PointerFollowReport(
    int SchemaVersion,
    string EvidenceKind,
    string RequestSha256,
    NativeImplementationIdentity Implementation,
    string CompletedAtUtc,
    MemoryPointerChain Chain,
    PointerResolutionResult Resolution,
    IReadOnlyList<string> Limitations);
