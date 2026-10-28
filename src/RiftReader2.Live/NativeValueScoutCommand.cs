using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class NativeValueScoutCommand
{
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--request", out var requestPath) ||
            !options.TryGetValue("--output", out var outputPath))
            throw new ArgumentException("--request and --output are required.");
        var fullOutput = Path.GetFullPath(outputPath);
        if (Directory.Exists(fullOutput) || File.Exists(fullOutput))
            throw new IOException("Native value scout output directory already exists; overwriting evidence is prohibited.");

        var loaded = await NativeValueScoutRequestFile.LoadAsync(requestPath, cancellationToken);
        var plan = loaded.Plan;
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            plan.ProcessId, plan.ProcessStartUtcTicks, plan.ExecutableSha256, cancellationToken);
        var startedAtUtc = UtcNow();
        var timer = Stopwatch.StartNew();
        var regions = session.EnumerateReadableRegions(
            plan.MaxRegionCount, plan.MaxDurationMilliseconds, cancellationToken, requiredType: 0x20000);
        var contexts = new List<ContextCapture>(plan.MaxMatchCount);
        var scan = NativeValueScout.Scan(
            regions.Select(region => new NativeValueScanRegion(
                region.BaseAddress, region.RegionSize, region.Type)).ToArray(),
            plan.StartAddress,
            plan.References,
            plan.MaxScanBytes,
            plan.MaxMatchCount,
            (address, buffer, count) =>
            {
                var read = session.ReadScanChunk(address, buffer, count);
                return new(read.Complete, read.BytesRead, read.Win32Error);
            },
            () => timer.ElapsedMilliseconds >= plan.MaxDurationMilliseconds,
            cancellationToken,
            match => contexts.Add(CaptureContext(session, plan, match)));

        var identityFailure = await session.RevalidateAsync(cancellationToken);
        var completedAtUtc = UtcNow();
        var contextFailure = contexts.Any(context => context.Read.Status != "success");
        var status = identityFailure is not null ? "identity-invalidated" :
            timer.ElapsedMilliseconds > plan.MaxDurationMilliseconds ? "partial" :
            scan.Status != "complete" || contextFailure ? "partial" : "complete";
        var reason = identityFailure ??
            (timer.ElapsedMilliseconds > plan.MaxDurationMilliseconds
                ? "time-budget-exceeded-during-scan-or-revalidation"
                : scan.Status != "complete" ? scan.Reason
                : contextFailure ? "context-read-failures" : null);

        var destinationParent = Path.GetDirectoryName(fullOutput)
            ?? throw new InvalidDataException("Output directory must have an explicit parent.");
        Directory.CreateDirectory(destinationParent);
        var staging = Path.Combine(destinationParent, $".{Path.GetFileName(fullOutput)}.{Guid.NewGuid():N}.tmp");
        Directory.CreateDirectory(staging);
        try
        {
            var retainedRequestName = "source-request.json";
            await WriteNewBytesAsync(Path.Combine(staging, retainedRequestName), loaded.RawBytes, cancellationToken);
            var implementation = NativeCommandRunner.CreateImplementationIdentity();
            var candidates = new List<NativeValueScoutCandidateReport>(contexts.Count);
            for (var index = 0; index < contexts.Count; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var context = contexts[index];
                if (identityFailure is not null)
                {
                    candidates.Add(ToCandidate(context, "identity-invalidated",
                        "The process changed identity; captured bytes were not published as usable snapshots.",
                        null, null, null, null));
                    continue;
                }

                var prefix = $"capture-{index + 1:D3}";
                var candidateRequest = new MemorySnapshotRequest(
                    1,
                    "native-memory-snapshot-request/1",
                    loaded.Request.Target,
                    plan.MaxDurationMilliseconds,
                    [new("absolute-session-address", Hex(context.ContextAddress), context.ContextLength)]);
                var candidateRequestName = $"{prefix}.request.json";
                var snapshotName = $"{prefix}.snapshot.json";
                var candidateRequestPath = Path.Combine(staging, candidateRequestName);
                var snapshotPath = Path.Combine(staging, snapshotName);
                await JsonReportWriter.WriteNewAsync(candidateRequestPath, candidateRequest, cancellationToken);
                var candidateRequestBytes = await File.ReadAllBytesAsync(candidateRequestPath, cancellationToken);
                var candidateRequestSha = Convert.ToHexString(SHA256.HashData(candidateRequestBytes));
                var chunk = ToChunk(context.ContextAddress, context.ContextLength, context.Read);
                var snapshot = new NativeMemorySnapshotFile(
                    1,
                    "native-memory-snapshot/1",
                    new("native-memory-snapshot-request/1", candidateRequestSha,
                        "producer-declared", implementation),
                    session.Identity,
                    context.StartedAtUtc,
                    context.CompletedAtUtc,
                    context.Read.Status == "success" ? "complete" : "failed",
                    context.Read.Status == "success" ? null : "The retained context read was incomplete.",
                    [chunk],
                    [
                        "This bounded context was copied immediately when an aligned numeric value matched during the read-only scan.",
                        "A numeric match is a candidate copy, not an authoritative gameplay field or durable locator.",
                        "Failed or partial bytes remain explicit and are never replaced with zeros."
                    ]);
                await JsonReportWriter.WriteNewAsync(snapshotPath, snapshot, cancellationToken);
                var verified = await NativeMemorySnapshotFile.LoadAsync(snapshotPath, cancellationToken);
                candidates.Add(ToCandidate(context, context.Read.Status, context.Read.Reason,
                    candidateRequestName, candidateRequestSha, snapshotName, verified.FileSha256));
            }

            var report = new NativeValueScoutManifest(
                1,
                "native-value-scout/1",
                loaded.RequestSha256,
                retainedRequestName,
                loaded.Request,
                implementation,
                session.Identity,
                startedAtUtc,
                completedAtUtc,
                status,
                reason,
                "aligned-4-byte-values-in-committed-readable-nonguard-MEM_PRIVATE-at-or-after-startAddress",
                identityFailure is null && scan.NextAddress is { } next ? Hex(next) : null,
                scan.EligiblePrivateBytes,
                scan.AttemptedBytes,
                scan.ExaminedBytes,
                scan.EligiblePrivateRegionCount,
                scan.TouchedPrivateRegionCount,
                scan.CoveredSpans.Select(span =>
                    new NativeValueScoutSpanReport(Hex(span.BaseAddress), span.ByteLength)).ToArray(),
                scan.Holes.Select(hole => new NativeValueScoutHoleReport(
                    Hex(hole.BaseAddress), hole.ByteLength, hole.Reason, hole.Win32Error)).ToArray(),
                candidates,
                [
                    "Only committed, readable, non-guard MEM_PRIVATE regions are eligible; image and mapped memory are excluded.",
                    "The scan is little-endian and tests 4-byte-aligned int32, float32 and float64 references only.",
                    "Coverage, holes and a resume cursor distinguish a bounded negative result from a whole-process absence claim.",
                    "The resume cursor can overlap up to seven prior bytes; deduplicate by exact process epoch and address.",
                    "Numeric equality can identify caches, UI copies or serialized data. Changed-state correlation and a restart-stable locator remain separate gates.",
                    "No usable snapshot files are published when post-acquisition process identity validation fails."
                ]);
            var indexPath = Path.Combine(staging, "index.json");
            await JsonReportWriter.WriteNewAsync(indexPath, report, cancellationToken);
            var indexSha = Convert.ToHexString(SHA256.HashData(
                await File.ReadAllBytesAsync(indexPath, cancellationToken)));
            cancellationToken.ThrowIfCancellationRequested();
            Directory.Move(staging, fullOutput);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                report.SchemaVersion,
                report.EvidenceKind,
                report.Status,
                report.Reason,
                report.NextAddress,
                report.AttemptedBytes,
                report.ExaminedBytes,
                MatchCount = report.Candidates.Count,
                HoleCount = report.Holes.Count,
                IndexSha256 = indexSha,
                Output = fullOutput
            }, JsonFormat.Options));
            return status == "complete" ? 0 : 3;
        }
        catch
        {
            if (Directory.Exists(staging) && Path.GetDirectoryName(staging) == destinationParent)
                Directory.Delete(staging, recursive: true);
            throw;
        }
    }

    private static ContextCapture CaptureContext(
        WindowsNativeMemorySession session,
        NativeValueScoutPlan plan,
        NativeValueScanMatch match)
    {
        var bytesBelow = match.Address - NativeValueScout.MinUserAddress;
        var before = Math.Min((ulong)plan.ContextBeforeBytes, bytesBelow);
        var contextAddress = match.Address - before;
        var desiredLength = checked((int)before + match.Width + plan.ContextAfterBytes);
        var available = checked((long)(NativeValueScout.MaxUserEnd - contextAddress));
        var length = checked((int)Math.Min(desiredLength, available));
        var started = UtcNow();
        var read = session.Read(contextAddress, length);
        return new(match, contextAddress, length, started, UtcNow(), read);
    }

    private static NativeValueScoutCandidateReport ToCandidate(
        ContextCapture context,
        string status,
        string? reason,
        string? requestFile,
        string? requestSha256,
        string? snapshotFile,
        string? snapshotSha256) =>
        new(Hex(context.Match.Address), context.Match.Width, context.Match.ReferenceNames,
            Hex(context.ContextAddress), context.ContextLength, status, reason,
            requestFile, requestSha256, snapshotFile, snapshotSha256);

    private static NativeMemorySnapshotChunk ToChunk(ulong address, int requested, NativeReadResult read) =>
        new(Hex(address), requested, read.Status, read.Bytes.Length,
            read.Bytes.Length == 0 ? null : Convert.ToBase64String(read.Bytes),
            read.Bytes.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(read.Bytes)),
            read.Win32ErrorCode, read.Reason);

    private static async Task WriteNewBytesAsync(string path, byte[] bytes, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None,
            8192, FileOptions.Asynchronous | FileOptions.WriteThrough);
        await stream.WriteAsync(bytes, cancellationToken);
        await stream.FlushAsync(cancellationToken);
        stream.Flush(flushToDisk: true);
    }

    private static string Hex(ulong value) => $"0x{value:X}";
    private static string UtcNow() => DateTime.UtcNow.ToString("O", System.Globalization.CultureInfo.InvariantCulture);

    private sealed record ContextCapture(
        NativeValueScanMatch Match,
        ulong ContextAddress,
        int ContextLength,
        string StartedAtUtc,
        string CompletedAtUtc,
        NativeReadResult Read);
}

internal sealed record NativeValueScoutSpanReport(string BaseAddress, long ByteLength);

internal sealed record NativeValueScoutHoleReport(
    string BaseAddress, int ByteLength, string Reason, int? Win32Error);

internal sealed record NativeValueScoutCandidateReport(
    string Address,
    int Width,
    IReadOnlyList<string> ReferenceNames,
    string ContextAddress,
    int ContextByteLength,
    string Status,
    string? Reason,
    string? RequestFile,
    string? RequestSha256,
    string? SnapshotFile,
    string? SnapshotSha256);

internal sealed record NativeValueScoutManifest(
    int SchemaVersion,
    string EvidenceKind,
    string RequestSha256,
    string RequestFile,
    NativeValueScoutRequest Request,
    NativeImplementationIdentity Implementation,
    NativeProcessIdentity Identity,
    string StartedAtUtc,
    string CompletedAtUtc,
    string Status,
    string? Reason,
    string Scope,
    string? NextAddress,
    long EligiblePrivateBytes,
    long AttemptedBytes,
    long ExaminedBytes,
    int EligiblePrivateRegionCount,
    int TouchedPrivateRegionCount,
    IReadOnlyList<NativeValueScoutSpanReport> CoveredSpans,
    IReadOnlyList<NativeValueScoutHoleReport> Holes,
    IReadOnlyList<NativeValueScoutCandidateReport> Candidates,
    IReadOnlyList<string> Limitations);
