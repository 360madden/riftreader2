using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using Domain = RiftReader2.Domain;

namespace RiftReader2.Live;

public sealed record LiveTargetReport(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutablePath,
    string ExecutableSha256,
    string ReaderSessionNonce);

public sealed record LiveScanReport(
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

public sealed record LiveRiftReader2Report(
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
    string? EnvelopeSha256,
    string? AddonFrameSha256,
    long? CandidateSequence,
    long? CandidateEpoch,
    IReadOnlyDictionary<string, object?>? Observation,
    LiveScanReport Scan);

public sealed record LiveDeliveryReport(
    bool Enabled,
    string Status,
    string? Endpoint,
    string? LastSuccessUtc,
    string? Error);

public sealed record FastObservationAnchorReport(
    long FullScanStartedAtTimestamp,
    long FullScanCompletedAtTimestamp,
    long TimestampFrequency,
    string EnvelopeSha256,
    string AddonFrameSha256,
    long CandidateSequence,
    long CandidateEpoch,
    double CandidateClock,
    string PlayerId,
    int RegionCount,
    long TotalRegionBytes,
    double MaxAgeMilliseconds);

public sealed record FastObservationScanReport(
    string Scope,
    string Status,
    bool Completed,
    long StartedAtTimestamp,
    long CompletedAtTimestamp,
    long PlannedBytes,
    long ScannedBytes,
    int RegionCount,
    double ElapsedMilliseconds,
    int EndpointCandidateCount,
    int MalformedCandidateCount,
    int MatchingCandidateCount,
    int IdenticalCopyCount,
    string? Reason);

public sealed record FastObservationReport(
    int SchemaVersion,
    string Provenance,
    string BindingStatus,
    string FreshnessStatus,
    string? Reason,
    long PublishedAtTimestamp,
    long? LastAdvanceAtTimestamp,
    double? LastAdvanceAgeMilliseconds,
    double FreshnessTimeoutMilliseconds,
    FastObservationAnchorReport Anchor,
    string SelectionStatus,
    string? EnvelopeSha256,
    string? AddonFrameSha256,
    long? CandidateSequence,
    long? CandidateEpoch,
    IReadOnlyDictionary<string, object?>? Observation,
    FastObservationScanReport Scan);

public sealed record FastObservationAnchorDiagnostic(
    int SchemaVersion,
    string Provenance,
    string Status,
    string? Reason,
    bool FullScanCompleted,
    string FullScanStatus,
    string SelectionStatus,
    int CandidateRegionCount,
    long? CandidateRegionBytes,
    long MaximumRegionBytes,
    double MaximumAnchorAgeMilliseconds);

public sealed record LiveReaderSnapshot(
    int SchemaVersion,
    Guid InstanceId,
    string Nonce,
    long Sequence,
    string CapturedAtUtc,
    double MonotonicMilliseconds,
    string ReaderStatus,
    string? ReaderReason,
    LiveTargetReport? Target,
    LiveRiftReader2Report RiftReader2,
    LiveDeliveryReport Delivery)
{
    // Additive independent source block; the existing addon contract is unchanged.
    public LivePowerReport NativePower { get; init; } = LivePowerRead.Unavailable("native-power-not-read");

    // A separately scoped, recent-full-scan-anchored observation. It is never a
    // replacement for the whole-process riftReader2 scan contract.
    public FastObservationReport? FastObservation { get; init; }

    // Address-free explanation of the latest full-scan anchor attempt. This is
    // diagnostic provenance only and never participates in freshness decisions.
    public FastObservationAnchorDiagnostic? FastObservationDiagnostic { get; init; }
}

public static class LiveOutput
{
    public static LiveRiftReader2Report CreateRiftReader2Report(
        LiveAddonFreshness freshness,
        LiveAddonSelection selection,
        LiveScanResult scan,
        long scanStartedAt,
        long publishedAt,
        TimeSpan freshnessTimeout,
        TimeProvider timeProvider,
        string? overrideStatus = null,
        string? overrideReason = null)
    {
        var age = freshness.ObservedAtTimestamp is { } observedAt
            ? timeProvider.GetElapsedTime(observedAt, publishedAt)
            : freshness.Age;
        if (age is { } negativeAge && negativeAge < TimeSpan.Zero)
            age = null;
        double? remaining = age is null
            ? null
            : Math.Max(0, (freshnessTimeout - age.Value).TotalMilliseconds);
        var selected = selection.Frame;
        return new(
            1,
            overrideStatus is not null
                ? overrideStatus == "unavailable" ? "unbound" : "invalidated"
                : freshness.Status == Domain.LiveFreshnessStatus.Invalidated
                    ? "invalidated"
                    : selection.Status == Domain.LiveAddonSelectionStatus.Selected ? "bound" : "unbound",
            overrideStatus ?? FreshnessStatus(freshness.Status),
            overrideReason ?? freshness.Reason,
            scanStartedAt,
            publishedAt,
            freshness.ObservedAtTimestamp,
            age?.TotalMilliseconds,
            freshnessTimeout.TotalMilliseconds,
            remaining,
            SelectionStatus(selection.Status),
            freshness.EnvelopeSha256 ?? selected?.EnvelopeSha256,
            selected?.AddonFrameSha256,
            selected?.Observation.Sequence,
            selected?.Observation.Epoch,
            overrideStatus is not null || freshness.Observation is null
                ? null
                : AddonDecodedReport.ToWireObservation(freshness.Observation),
            new(
                scan.Status,
                scan.Completed,
                scan.PlannedBytes,
                scan.ScannedBytes,
                scan.RegionCount,
                scan.Elapsed.TotalMilliseconds,
                scan.EndpointCandidateCount,
                scan.MalformedCandidateCount,
                selection.MatchingCandidateCount,
                selection.IdenticalCopyCount,
                scan.Reason ?? selection.Reason));
    }

    public static async Task WriteAtomicAsync(string path, LiveReaderSnapshot snapshot, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(fullPath)!;
        Directory.CreateDirectory(directory);
        var temporary = Path.Combine(directory, $".{Path.GetFileName(fullPath)}.{Environment.ProcessId}.tmp");
        try
        {
            await using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                await JsonSerializer.SerializeAsync(stream, snapshot, JsonFormat.Options, cancellationToken);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(true);
            }
            File.Move(temporary, fullPath, true);
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    public static FastObservationReport CreateFastObservationReport(
        FastObservationAnchorReport anchor,
        LiveAddonFreshness freshness,
        LiveAddonSelection selection,
        LiveScanResult scan,
        long startedAt,
        long completedAt,
        TimeSpan freshnessTimeout,
        TimeProvider timeProvider)
    {
        var selected = selection.Frame;
        var publishedAt = timeProvider.GetTimestamp();
        var age = freshness.ObservedAtTimestamp is { } observedAt
            ? timeProvider.GetElapsedTime(observedAt, publishedAt)
            : freshness.Age;
        if (age is { } negativeAge && negativeAge < TimeSpan.Zero)
            age = null;
        return new(
            1,
            "recent-full-scan-anchored-candidate-regions/1",
            freshness.Status == Domain.LiveFreshnessStatus.Invalidated
                ? "invalidated"
                : selection.Status == Domain.LiveAddonSelectionStatus.Selected ? "bound-scoped" : "unbound",
            freshness.Status switch
            {
                Domain.LiveFreshnessStatus.Warming => "warming-scoped",
                Domain.LiveFreshnessStatus.Fresh => "fresh-scoped",
                Domain.LiveFreshnessStatus.Invalidated => "invalidated",
                _ => "unavailable"
            },
            freshness.Reason ?? scan.Reason ?? selection.Reason,
            publishedAt,
            freshness.ObservedAtTimestamp,
            age?.TotalMilliseconds,
            freshnessTimeout.TotalMilliseconds,
            anchor,
            selection.Status == Domain.LiveAddonSelectionStatus.Selected
                ? "selected-scoped"
                : SelectionStatus(selection.Status),
            freshness.EnvelopeSha256 ?? selected?.EnvelopeSha256,
            selected?.AddonFrameSha256,
            selected?.Observation.Sequence,
            selected?.Observation.Epoch,
            freshness.Observation is null ? null : AddonDecodedReport.ToWireObservation(freshness.Observation),
            new(
                "candidate-regions",
                scan.Status,
                scan.Completed,
                startedAt,
                completedAt,
                scan.PlannedBytes,
                scan.ScannedBytes,
                scan.RegionCount,
                scan.Elapsed.TotalMilliseconds,
                scan.EndpointCandidateCount,
                scan.MalformedCandidateCount,
                selection.MatchingCandidateCount,
                selection.IdenticalCopyCount,
                scan.Reason ?? selection.Reason));
    }

    public static FastObservationReport StampFastObservation(
        FastObservationReport report,
        long publishedAt,
        TimeProvider timeProvider)
    {
        TimeSpan? age = report.LastAdvanceAtTimestamp is { } observedAt
            ? timeProvider.GetElapsedTime(observedAt, publishedAt)
            : null;
        if (age is { } negativeAge && negativeAge < TimeSpan.Zero)
            age = null;
        return report with
        {
            PublishedAtTimestamp = publishedAt,
            LastAdvanceAgeMilliseconds = age?.TotalMilliseconds
        };
    }

    private static string FreshnessStatus(Domain.LiveFreshnessStatus status) => status switch
    {
        Domain.LiveFreshnessStatus.Warming => "warming",
        Domain.LiveFreshnessStatus.Fresh => "fresh",
        Domain.LiveFreshnessStatus.Unavailable => "unavailable",
        Domain.LiveFreshnessStatus.Invalidated => "invalidated",
        Domain.LiveFreshnessStatus.Expired => "expired",
        _ => "invalidated"
    };

    private static string SelectionStatus(Domain.LiveAddonSelectionStatus status) => status switch
    {
        Domain.LiveAddonSelectionStatus.Selected => "selected",
        Domain.LiveAddonSelectionStatus.NoMatchingCandidate => "no-matching-candidate",
        Domain.LiveAddonSelectionStatus.IncompleteScan => "incomplete-scan",
        Domain.LiveAddonSelectionStatus.Conflict => "conflict",
        _ => "conflict"
    };
}
