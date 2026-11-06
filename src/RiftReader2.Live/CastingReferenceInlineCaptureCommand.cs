using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CastingReferencePublishedCandidate(
    string MarkerAddress,
    string Status,
    string? Reason,
    string? RequestFile,
    string? RequestSha256,
    string? SnapshotFile,
    string? SnapshotSha256);

internal sealed record CastingReferenceInlineCaptureManifest(
    int SchemaVersion,
    string EvidenceKind,
    string SourceRequestFile,
    string RequestSha256,
    NativeImplementationIdentity Implementation,
    CastingReferenceInlineCaptureRequest Request,
    RiftReader2.Domain.NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    string Status,
    string? Reason,
    TypedApiScoutResult Scout,
    int CapturedCandidates,
    int PublishedSnapshots,
    bool CopyLimited,
    IReadOnlyList<CastingReferencePublishedCandidate> Candidates,
    IReadOnlyList<string> Limitations);

internal sealed record CastingReferenceInlineCaptureReceipt(
    int SchemaVersion,
    string EvidenceKind,
    string Status,
    string? Reason,
    string StartedAtUtc,
    string CompletedAtUtc,
    int CapturedCandidates,
    int PublishedSnapshots,
    string IndexSha256,
    string Output);

/// <summary>File/request/publish wrapper for the fixed RR2CASTREF1 scan/copy core.</summary>
internal static class CastingReferenceInlineCaptureCommand
{
    private const int MaxRequestBytes = 65_536;
    private static readonly HashSet<string> RequestKeys =
    [
        "schemaVersion", "evidenceKind", "target", "startAddress", "maxScanBytes",
        "maxDurationMilliseconds", "maxRegionCount", "maxMatchCount", "maxCopiedCandidates"
    ];
    private static readonly HashSet<string> TargetKeys =
        ["processId", "processStartUtcTicks", "executableSha256"];
    internal static readonly IReadOnlyList<string> CommandLimitations =
    [
        "The Windows collector supplied only committed, readable, nonguard MEM_PRIVATE regions from the exact requested process epoch.",
        "The fixed-marker core independently validates region ordering, type and page protection before scanning.",
        "Only the fixed RR2CASTREF1| marker is searched within the caller-declared byte, time, region, match and copy bounds.",
        "A marker plus opening brace is only a plausibility gate; a retained wire requires strict offline decoding.",
        "A partial scan is bounded coverage and never a whole-process absence claim.",
        "No captured snapshot is published as usable when exact process postflight identity fails.",
        "The command sends no input, invokes no game function and writes no process memory."
    ];

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--request", out var requestPath) ||
            !options.TryGetValue("--output", out var outputDirectory))
            throw new ArgumentException("--request and --output are required.");
        var fullOutput = Path.GetFullPath(outputDirectory);
        if (Directory.Exists(fullOutput) || File.Exists(fullOutput))
            throw new IOException("Casting-reference output already exists; overwriting evidence is prohibited.");
        var loaded = await LoadRequestAsync(requestPath, cancellationToken);
        var request = loaded.Request;
        CastingReferenceInlineCaptureCore.ValidateRequestBounds(request);
        var timer = Stopwatch.StartNew();
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            request.Target.ProcessId, request.Target.ProcessStartUtcTicks,
            request.Target.ExecutableSha256, cancellationToken);
        var remaining = request.MaxDurationMilliseconds - timer.ElapsedMilliseconds;
        if (remaining <= 0)
            throw new TimeoutException("Exact-process open exhausted the casting-reference acquisition budget.");
        var regions = session.EnumerateReadableRegions(
            request.MaxRegionCount, checked((int)remaining), cancellationToken, requiredType: 0x20000);
        var result = CastingReferenceInlineCaptureCore.Run(
            request, session.Identity, regions, session.ReadScanChunk, session.Read,
            () => session.RevalidateAsync(cancellationToken).AsTask().GetAwaiter().GetResult(),
            () => timer.ElapsedMilliseconds, deadlineStartedAtMilliseconds: 0,
            cancellationToken: cancellationToken);

        var parent = Path.GetDirectoryName(fullOutput)
            ?? throw new InvalidDataException("Output directory must have an explicit parent.");
        Directory.CreateDirectory(parent);
        var staging = Path.Combine(parent,
            $".{Path.GetFileName(fullOutput)}.{Guid.NewGuid():N}.tmp");
        Directory.CreateDirectory(staging);
        try
        {
            var sourceRequestName = await RetainSourceRequestAsync(
                staging, loaded.Raw, loaded.Sha256, cancellationToken);
            var implementation = NativeCommandRunner.CreateImplementationIdentity();
            var files = new List<CastingReferencePublishedCandidate>();
            var published = 0;
            foreach (var candidate in result.Candidates)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var neighborhood = candidate.Neighborhood;
                if (neighborhood is null)
                {
                    files.Add(new(candidate.MarkerAddress, candidate.Status, candidate.Reason,
                        null, null, null, null));
                    continue;
                }
                var prefix = $"capture-{++published:D2}";
                var sourceName = prefix + ".request.json";
                var snapshotName = prefix + ".snapshot.json";
                var sourcePath = Path.Combine(staging, sourceName);
                var snapshotPath = Path.Combine(staging, snapshotName);
                var sourceRequest = new MemorySnapshotRequest(
                    1, "native-memory-snapshot-request/1", request.Target,
                    request.MaxDurationMilliseconds,
                    [new("absolute-session-address", neighborhood.WindowStart,
                        CastingReferenceInlineCaptureCore.WindowBytes)]);
                await JsonReportWriter.WriteNewAsync(sourcePath, sourceRequest, cancellationToken);
                var sourceSha = await FileShaAsync(sourcePath, cancellationToken);
                var source = new NativeMemorySnapshotSource(
                    "native-memory-snapshot-request/1", sourceSha,
                    "producer-declared", implementation);
                var snapshot = new NativeMemorySnapshotFile(
                    1, "native-memory-snapshot/1", source, result.Identity,
                    neighborhood.StartedAtUtc, neighborhood.CompletedAtUtc,
                    neighborhood.Status, neighborhood.Reason, neighborhood.Chunks,
                    [
                        "The pages were copied through read-only memory calls immediately after a fixed RR2CASTREF1| prefix match.",
                        "The opening-brace gate is not a decoded, current or advancing casting-reference frame.",
                        "Addresses are valid only for the exact process epoch; missing bytes are never zero-filled."
                    ]);
                await JsonReportWriter.WriteNewAsync(snapshotPath, snapshot, cancellationToken);
                var verified = await NativeMemorySnapshotFile.LoadAsync(snapshotPath, cancellationToken);
                files.Add(new(candidate.MarkerAddress, candidate.Status, candidate.Reason,
                    sourceName, sourceSha, snapshotName, verified.FileSha256));
            }
            var manifest = new CastingReferenceInlineCaptureManifest(
                1, CastingReferenceInlineCaptureCore.EvidenceKind, sourceRequestName, loaded.Sha256,
                implementation, request, result.Identity, result.StartedAtUtc,
                result.CompletedAtUtc, result.Status, result.Reason, result.Scout,
                result.CopiedCandidates, published, result.CopyLimited, files,
                CommandLimitations);
            var indexSha = await PublishManifestAsync(
                staging, fullOutput, manifest, cancellationToken);
            var receipt = new CastingReferenceInlineCaptureReceipt(
                manifest.SchemaVersion, manifest.EvidenceKind, manifest.Status,
                manifest.Reason, manifest.StartedAtUtc, manifest.CompletedAtUtc,
                manifest.CapturedCandidates, manifest.PublishedSnapshots,
                indexSha, fullOutput);
            await output.WriteLineAsync(JsonSerializer.Serialize(receipt, JsonFormat.Options));
            return result.Status == "complete" ? 0 : 3;
        }
        finally
        {
            if (Directory.Exists(staging))
                Directory.Delete(staging, recursive: true);
        }
    }

    internal static async Task<(
        CastingReferenceInlineCaptureRequest Request, string Sha256, byte[] Raw)>
        LoadRequestAsync(string path, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath) ||
            (File.GetAttributes(fullPath) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Casting-reference request must be a regular file.");
        byte[] raw;
        await using (var stream = new FileStream(
            fullPath, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            if (stream.Length is < 2 or > MaxRequestBytes)
                throw new InvalidDataException("Casting-reference request size is invalid.");
            raw = new byte[checked((int)stream.Length)];
            await stream.ReadExactlyAsync(raw, cancellationToken);
        }
        using var document = JsonDocument.Parse(raw, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 16
        });
        RequireExactObject(document.RootElement, RequestKeys, "request");
        if (!document.RootElement.TryGetProperty("target", out var target))
            throw new InvalidDataException("Casting-reference request target is required.");
        RequireExactObject(target, TargetKeys, "target");
        var request = JsonSerializer.Deserialize<CastingReferenceInlineCaptureRequest>(
            raw, JsonFormat.Options)
            ?? throw new InvalidDataException("Casting-reference request is empty.");
        return (request, Convert.ToHexString(SHA256.HashData(raw)), raw);
    }

    private static void RequireExactObject(
        JsonElement element, IReadOnlySet<string> expected, string label)
    {
        if (element.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"Casting-reference {label} must be an object.");
        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in element.EnumerateObject())
        {
            if (!observed.Add(property.Name))
                throw new InvalidDataException($"Casting-reference {label} contains duplicate JSON keys.");
        }
        if (!observed.SetEquals(expected))
            throw new InvalidDataException($"Casting-reference {label} has an unsupported JSON shape.");
    }

    private static async Task<string> FileShaAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
    }

    internal static async Task<string> PublishManifestAsync<T>(
        string stagingDirectory,
        string outputDirectory,
        T manifest,
        CancellationToken cancellationToken)
    {
        var indexPath = Path.Combine(stagingDirectory, "index.json");
        await JsonReportWriter.WriteNewAsync(indexPath, manifest, cancellationToken);
        var indexSha = await FileShaAsync(indexPath, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        CastingReferenceInlineCaptureCore.PublishNewDirectory(stagingDirectory, outputDirectory);
        return indexSha;
    }

    internal static async Task<string> RetainSourceRequestAsync(
        string stagingDirectory,
        byte[] raw,
        string expectedSha256,
        CancellationToken cancellationToken)
    {
        const string name = "source-request.json";
        var path = Path.Combine(stagingDirectory, name);
        await using (var retained = new FileStream(
            path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await retained.WriteAsync(raw, cancellationToken);
            await retained.FlushAsync(cancellationToken);
            retained.Flush(flushToDisk: true);
        }
        if (await FileShaAsync(path, cancellationToken) != expectedSha256)
            throw new InvalidDataException("Retained casting-reference request hash mismatch.");
        return name;
    }
}
