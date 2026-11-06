using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record GuidanceSnapshotTarget(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutablePath,
    string ExecutableSha256);
public sealed record GuidanceSnapshotReader(string InstanceId, long SnapshotSequence, string Nonce);
public sealed record GuidanceSnapshotProvenance(
    string SourcePath,
    string SnapshotFileSha256,
    GuidanceSnapshotTarget Target,
    GuidanceSnapshotReader Reader,
    string CapturedAtUtc,
    long ScanStartedAtTimestamp,
    long PublishedAtTimestamp,
    long LastAdvanceAtTimestamp,
    double SnapshotAgeMilliseconds,
    double EffectiveLastAdvanceAgeMilliseconds,
    double FreshnessTimeoutMilliseconds);
public sealed record GuidanceSnapshotInput(LiveAddonFrame Frame, GuidanceSnapshotProvenance Provenance);

/// <summary>Strictly gates one current Live latest.json before guidance calculation.</summary>
public static class GuidanceSnapshotFile
{
    private const long MaxExactInteger = 9_007_199_254_740_991;
    public const double MaximumSnapshotAgeMilliseconds = 2_000;
    public const double AssumedUtcSkewMilliseconds = 250;

    public static async Task<GuidanceSnapshotInput> ReadAsync(
        string path,
        string expectedSessionId,
        DateTimeOffset? nowUtc = null,
        CancellationToken cancellationToken = default)
    {
        var bytes = await BoundedJson.ReadAsync(path, cancellationToken);
        Snapshot snapshot;
        try
        {
            snapshot = JsonSerializer.Deserialize<Snapshot>(bytes, JsonFormat.Options)
                ?? throw Invalid("Live snapshot is empty.");
        }
        catch (JsonException error)
        {
            throw Invalid("Live snapshot is not strict schema-1 JSON.", error);
        }
        if (snapshot.SchemaVersion != 1)
            throw Invalid("Unsupported live snapshot schema.");
        if (snapshot.ReaderStatus != "running")
            throw Invalid("Live reader is not running.");
        ValidateNonce(expectedSessionId, "expected session id");
        ValidateNonce(snapshot.Nonce, "snapshot nonce");
        if (!string.Equals(snapshot.Nonce, expectedSessionId, StringComparison.Ordinal))
            throw Invalid("Live snapshot nonce does not match the requested session.");
        if (snapshot.InstanceId == Guid.Empty || snapshot.Sequence is < 1 or > MaxExactInteger)
            throw Invalid("Live snapshot reader identity is invalid.");
        RequireFinite(snapshot.MonotonicMilliseconds, "monotonicMilliseconds", minimum: 0);

        var captured = ParseUtc(snapshot.CapturedAtUtc);
        var now = (nowUtc ?? DateTimeOffset.UtcNow).ToUniversalTime();
        var ageMilliseconds = (now - captured).TotalMilliseconds;
        if (ageMilliseconds < -AssumedUtcSkewMilliseconds || ageMilliseconds > MaximumSnapshotAgeMilliseconds)
            throw Invalid("Live snapshot is stale or outside the assumed UTC skew bound.");

        var target = snapshot.Target ?? throw Invalid("Live snapshot target is unavailable.");
        if (target.ProcessId <= 0 || target.ProcessStartUtcTicks <= 0 || string.IsNullOrWhiteSpace(target.ExecutablePath))
            throw Invalid("Live snapshot target identity is invalid.");
        ValidateSha256(target.ExecutableSha256, "target executable hash");
        ValidateNonce(target.ReaderSessionNonce, "target reader session");
        if (!string.Equals(target.ReaderSessionNonce, expectedSessionId, StringComparison.Ordinal))
            throw Invalid("Live snapshot target session does not match the requested session.");

        var report = snapshot.RiftReader2;
        if (report.SchemaVersion != 1 || report.BindingStatus != "bound" || report.FreshnessStatus != "fresh")
            throw Invalid("Live snapshot addon observation is not bound and fresh.");
        if (report.ScanStartedAtTimestamp <= 0 || report.PublishedAtTimestamp < report.ScanStartedAtTimestamp ||
            report.LastAdvanceAtTimestamp is not > 0 || report.LastAdvanceAtTimestamp > report.PublishedAtTimestamp)
            throw Invalid("Live snapshot collection timestamps are invalid.");
        if (report.SelectionStatus != "selected" || report.Observation.ValueKind != JsonValueKind.Object)
            throw Invalid("Live snapshot addon selection is not selected.");
        if (!report.Scan.Completed || report.Scan.Status != "complete")
            throw Invalid("Live snapshot memory scan is incomplete.");
        ValidateScan(report.Scan);
        ValidateSha256(report.EnvelopeSha256, "reported envelope hash");
        ValidateSha256(report.AddonFrameSha256, "reported addon frame hash");
        if (report.CandidateSequence is not (>= 1 and <= MaxExactInteger) ||
            report.CandidateEpoch is not (>= 1 and <= MaxExactInteger))
            throw Invalid("Live snapshot candidate identity is invalid.");

        var reportedAge = RequireFinite(report.LastAdvanceAgeMilliseconds, "lastAdvanceAgeMilliseconds", minimum: 0);
        var timeout = RequireFinite(report.FreshnessTimeoutMilliseconds, "freshnessTimeoutMilliseconds", minimum: double.Epsilon);
        var remaining = RequireFinite(report.RemainingFreshMilliseconds, "remainingFreshMilliseconds", minimum: double.Epsilon);
        var elapsedAfterCapture = Math.Max(0, ageMilliseconds + AssumedUtcSkewMilliseconds);
        var effectiveAge = reportedAge + elapsedAfterCapture;
        if (effectiveAge >= timeout || remaining <= elapsedAfterCapture)
            throw Invalid("Live snapshot addon observation has expired under the UTC skew assumption.");

        var observationBytes = Encoding.UTF8.GetBytes(report.Observation.GetRawText());
        var prefix = "RR2A1|"u8;
        var suffix = "|ENDRR2A1"u8;
        var frameBytes = new byte[prefix.Length + observationBytes.Length + suffix.Length];
        prefix.CopyTo(frameBytes);
        observationBytes.CopyTo(frameBytes.AsSpan(prefix.Length));
        suffix.CopyTo(frameBytes.AsSpan(prefix.Length + observationBytes.Length));
        var observation = AddonFrameDecoder.Decode(frameBytes);
        if (observation.Sequence != report.CandidateSequence || observation.Epoch != report.CandidateEpoch)
            throw Invalid("Live snapshot candidate sequence or epoch differs from its decoded observation.");
        if (observation.Player.Status != AddonFieldStatus.Ok || observation.Player.Value is null)
            throw Invalid("Live snapshot selected observation has no usable player identity.");

        var fileSha = Convert.ToHexString(SHA256.HashData(bytes));
        var liveFrame = new LiveAddonFrame(
            expectedSessionId, observation, report.EnvelopeSha256, report.AddonFrameSha256);
        var provenance = new GuidanceSnapshotProvenance(
            Path.GetFullPath(path),
            fileSha,
            new(target.ProcessId, target.ProcessStartUtcTicks, target.ExecutablePath, target.ExecutableSha256),
            new(snapshot.InstanceId.ToString("D"), snapshot.Sequence, snapshot.Nonce),
            captured.ToString("O", CultureInfo.InvariantCulture),
            report.ScanStartedAtTimestamp,
            report.PublishedAtTimestamp,
            report.LastAdvanceAtTimestamp!.Value,
            ageMilliseconds,
            effectiveAge,
            timeout);
        return new(liveFrame, provenance);
    }

    private static void ValidateScan(Scan scan)
    {
        if (scan.PlannedBytes < 0 || scan.ScannedBytes < 0 || scan.ScannedBytes > scan.PlannedBytes ||
            scan.RegionCount < 0 || scan.EndpointCandidateCount < 0 || scan.MalformedCandidateCount < 0 ||
            scan.MatchingCandidateCount < 1 || scan.IdenticalCopyCount < 1)
            throw Invalid("Live snapshot scan counts are invalid.");
        RequireFinite(scan.ElapsedMilliseconds, "scan.elapsedMilliseconds", minimum: 0);
    }

    private static DateTimeOffset ParseUtc(string value)
    {
        if (!DateTimeOffset.TryParseExact(value, "O", CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind, out var parsed) || parsed.Offset != TimeSpan.Zero)
            throw Invalid("capturedAtUtc must be an exact UTC timestamp.");
        return parsed;
    }

    private static double RequireFinite(double? value, string name, double minimum)
    {
        if (value is not double number || !double.IsFinite(number) || number < minimum)
            throw Invalid($"Live snapshot {name} is outside its valid range.");
        return number;
    }

    private static void ValidateNonce(string value, string name)
    {
        if (value.Length != 32 || value.Any(c => c is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw Invalid($"Live snapshot {name} must be 32 lowercase hexadecimal characters.");
    }

    private static void ValidateSha256(string value, string name)
    {
        if (value.Length != 64 || value.Any(c => c is not (>= '0' and <= '9') and not (>= 'A' and <= 'F')))
            throw Invalid($"Live snapshot {name} must be 64 uppercase hexadecimal characters.");
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null) => new(message, inner);

    private sealed record Snapshot(
        int SchemaVersion,
        Guid InstanceId,
        string Nonce,
        long Sequence,
        string CapturedAtUtc,
        double MonotonicMilliseconds,
        string ReaderStatus,
        string? ReaderReason,
        Target? Target,
        RiftReaderReport RiftReader2,
        JsonElement Delivery,
        JsonElement NativePower);

    private sealed record Target(
        int ProcessId,
        long ProcessStartUtcTicks,
        string ExecutablePath,
        string ExecutableSha256,
        string ReaderSessionNonce);

    private sealed record RiftReaderReport(
        int SchemaVersion,
        string BindingStatus,
        string FreshnessStatus,
        string? Reason,
        long ScanStartedAtTimestamp,
        long PublishedAtTimestamp,
        long? LastAdvanceAtTimestamp,
        double? LastAdvanceAgeMilliseconds,
        double FreshnessTimeoutMilliseconds,
        double? RemainingFreshMilliseconds,
        string SelectionStatus,
        string EnvelopeSha256,
        string AddonFrameSha256,
        long? CandidateSequence,
        long? CandidateEpoch,
        JsonElement Observation,
        Scan Scan);

    private sealed record Scan(
        string Status,
        bool Completed,
        long PlannedBytes,
        long ScannedBytes,
        int RegionCount,
        double ElapsedMilliseconds,
        int EndpointCandidateCount,
        int MalformedCandidateCount,
        int MatchingCandidateCount,
        int IdenticalCopyCount,
        string? Reason);
}
