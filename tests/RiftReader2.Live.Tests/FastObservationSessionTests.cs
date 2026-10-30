using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using System.Text.Json;

namespace RiftReader2.Live.Tests;

public sealed class FastObservationSessionTests
{
    private const string Nonce = "0123456789abcdef0123456789abcdef";
    private static readonly LiveAttachmentIdentity Identity = new(123, 456, new string('A', 64), Nonce);
    private static readonly DiscoveredTarget Target = new(Identity, @"C:\RIFT\rift_x64.exe", "rift_x64");

    [Fact]
    public void AnchoredScopeProducesExplicitFreshScopedReportAfterStrictAdvance()
    {
        var time = new ManualTimeProvider(2_000_000);
        var anchorSelection = Selected(6, 2, 29, "unit-1", 'a', 'b');
        var fullScan = CompleteScan(anchorSelection.Frame!.Challenge) with
        {
            CandidateRegions = [Region(0x10000, 4096), Region(0x20000, 8192)]
        };

        Assert.True(FastObservationSession.TryCreate(
            Target, fullScan, anchorSelection, 1_000_000, 2_000_000,
            new() { FreshnessTimeout = TimeSpan.FromSeconds(5), MaxClockSkew = TimeSpan.FromSeconds(1) },
            time, out var session, out var reason, out var diagnostic), reason);
        Assert.Equal("created", diagnostic.Status);
        Assert.Null(diagnostic.Reason);
        Assert.Equal(2, diagnostic.CandidateRegionCount);
        Assert.Equal(12_288, diagnostic.CandidateRegionBytes);
        var diagnosticJson = JsonSerializer.SerializeToElement(diagnostic, JsonFormat.Options);
        Assert.True(new HashSet<string>
        {
            "schemaVersion", "provenance", "status", "reason", "fullScanCompleted",
            "fullScanStatus", "selectionStatus", "candidateRegionCount",
            "candidateRegionBytes", "maximumRegionBytes", "maximumAnchorAgeMilliseconds"
        }.SetEquals(diagnosticJson.EnumerateObject().Select(property => property.Name)));
        Assert.DoesNotContain("address", diagnosticJson.GetRawText(), StringComparison.OrdinalIgnoreCase);

        time.Timestamp = 3_000_000;
        var scopedSelection = Selected(7, 2, 30, "unit-1", 'c', 'd');
        var report = session!.Observe(
            Target, CompleteScan(Nonce, 12_288, 2), scopedSelection,
            2_500_000, 3_000_000, out var canContinue);

        Assert.True(canContinue);
        Assert.Equal("recent-full-scan-anchored-candidate-regions/1", report.Provenance);
        Assert.Equal("fresh-scoped", report.FreshnessStatus);
        Assert.Equal("selected-scoped", report.SelectionStatus);
        Assert.Equal("candidate-regions", report.Scan.Scope);
        Assert.Equal(12_288, report.Anchor.TotalRegionBytes);
        Assert.Equal(1_000_000, report.Anchor.TimestampFrequency);
        Assert.Equal("unit-1", report.Anchor.PlayerId);
        Assert.Equal(29, report.Anchor.CandidateClock);
        Assert.Equal(7, report.CandidateSequence);
        Assert.Equal(3_000_000, report.PublishedAtTimestamp);
        Assert.Equal(2_500_000, report.LastAdvanceAtTimestamp);
        Assert.Equal(500, report.LastAdvanceAgeMilliseconds);
        Assert.Equal(5_000, report.FreshnessTimeoutMilliseconds);
        Assert.Null(report.Reason);

        var published = LiveOutput.StampFastObservation(report, 3_250_000, time);
        Assert.Equal(3_250_000, published.PublishedAtTimestamp);
        Assert.Equal(750, published.LastAdvanceAgeMilliseconds);
        var json = JsonSerializer.SerializeToElement(published, JsonFormat.Options);
        Assert.True(
            new HashSet<string>
            {
                "schemaVersion", "provenance", "bindingStatus", "freshnessStatus", "reason",
                "publishedAtTimestamp", "lastAdvanceAtTimestamp", "lastAdvanceAgeMilliseconds",
                "freshnessTimeoutMilliseconds", "anchor", "selectionStatus", "envelopeSha256",
                "addonFrameSha256", "candidateSequence", "candidateEpoch", "observation", "scan"
            }.SetEquals(json.EnumerateObject().Select(property => property.Name)));
    }

    [Fact]
    public void ProducerIdentityChangeInvalidatesScopeAndForcesFullFallback()
    {
        var time = new ManualTimeProvider(2_000_000);
        var anchorSelection = Selected(6, 2, 29, "unit-1", 'a', 'b');
        var fullScan = CompleteScan(Nonce) with { CandidateRegions = [Region(0x10000, 4096)] };
        Assert.True(FastObservationSession.TryCreate(
            Target, fullScan, anchorSelection, 1_000_000, 2_000_000,
            new(), time, out var session, out _, out _));

        time.Timestamp = 3_000_000;
        var report = session!.Observe(
            Target, CompleteScan(Nonce, 4096, 1), Selected(7, 2, 30, "unit-2", 'c', 'd'),
            2_500_000, 3_000_000, out var canContinue);

        Assert.False(canContinue);
        Assert.Equal("invalidated", report.BindingStatus);
        Assert.Equal("invalidated", report.FreshnessStatus);
        Assert.Equal("conflict", report.SelectionStatus);
        Assert.Equal("scoped-producer-identity-mismatch", report.Reason);
    }

    [Fact]
    public void RejectsOversizedOrExpiredCandidateRegionScope()
    {
        var time = new ManualTimeProvider(2_000_000);
        var selection = Selected(6, 2, 29, "unit-1", 'a', 'b');
        var oversized = CompleteScan(Nonce) with
        {
            CandidateRegions = [Region(0x10000, FastObservationSession.MaximumRegionBytes + 1)]
        };
        Assert.False(FastObservationSession.TryCreate(
            Target, oversized, selection, 1_000_000, 2_000_000, new(), time,
            out _, out var reason, out var diagnostic));
        Assert.Equal("candidate-region-scope-too-large", reason);
        Assert.Equal("rejected", diagnostic.Status);
        Assert.Equal(reason, diagnostic.Reason);
        Assert.Equal(1, diagnostic.CandidateRegionCount);
        Assert.Equal(FastObservationSession.MaximumRegionBytes + 1,
            diagnostic.CandidateRegionBytes);
        Assert.Equal(FastObservationSession.MaximumRegionBytes,
            diagnostic.MaximumRegionBytes);

        var valid = CompleteScan(Nonce) with { CandidateRegions = [Region(0x10000, 4096)] };
        Assert.True(FastObservationSession.TryCreate(
            Target, valid, selection, 1_000_000, 2_000_000, new(), time,
            out var session, out _, out _));
        time.Timestamp = 12_000_001;
        Assert.False(session!.CanObserve(Target, time.Timestamp, out reason));
        Assert.Equal("full-scan-anchor-expired", reason);
    }

    [Fact]
    public void ScopedScannerRejectsEmptyAndOversizedScopeBeforeOpeningProcess()
    {
        var empty = WindowsMemoryScanner.ScanCandidateRegions(
            Target, Nonce, [], FastObservationSession.MaximumRegionBytes,
            TimeSpan.FromSeconds(1), CancellationToken.None);
        Assert.False(empty.Completed);
        Assert.Equal("scope-empty", empty.Status);

        var oversized = WindowsMemoryScanner.ScanCandidateRegions(
            Target, Nonce, [Region(0x10000, FastObservationSession.MaximumRegionBytes + 1)],
            FastObservationSession.MaximumRegionBytes, TimeSpan.FromSeconds(1), CancellationToken.None);
        Assert.False(oversized.Completed);
        Assert.Equal("byte-budget-exceeded", oversized.Status);
    }

    private static LiveCandidateRegion Region(long address, long size) =>
        new(new nint(address), size, new nint(address), 4, 0x1000, 4, 0x20000);

    private static LiveScanResult CompleteScan(string challenge, long bytes = 4096, int regions = 1) =>
        new(true, "complete", bytes, bytes, regions, TimeSpan.FromMilliseconds(10), [], 1, 0, null);

    private static LiveAddonSelection Selected(
        long sequence, long epoch, double clock, string player, char envelopeHash, char frameHash)
    {
        var observation = new AddonObservation(
            1, "test", sequence, epoch,
            new(AddonFieldStatus.Ok, clock),
            new(AddonFieldStatus.Ok, player),
            new(
                new(AddonFieldStatus.Ok, 1),
                new(AddonFieldStatus.Ok, 2),
                new(AddonFieldStatus.Ok, 3),
                new(AddonFieldStatus.Unavailable, null),
                new(AddonFieldStatus.Unavailable, null),
                new(AddonFieldStatus.Ok, false)));
        var frame = new LiveAddonFrame(
            Nonce, observation, new string(envelopeHash, 64), new string(frameHash, 64));
        return new(LiveAddonSelectionStatus.Selected, frame, 1, 1, null);
    }

    private sealed class ManualTimeProvider(long timestamp) : TimeProvider
    {
        public long Timestamp { get; set; } = timestamp;

        public override long TimestampFrequency => 1_000_000;

        public override long GetTimestamp() => Timestamp;
    }
}
