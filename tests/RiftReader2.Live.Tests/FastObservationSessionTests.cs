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

    [Theory]
    [InlineData(512L * 1024 * 1024)]
    [InlineData(1024L * 1024 * 1024)]
    public void AllowsCandidateRegionScopeThroughOneGiBLimit(long regionBytes)
    {
        var time = new ManualTimeProvider(2_000_000);
        var selection = Selected(6, 2, 29, "unit-1", 'a', 'b');
        var scan = CompleteScan(Nonce) with
        {
            CandidateRegions = [Region(0x10000, regionBytes)]
        };

        Assert.True(FastObservationSession.TryCreate(
            Target, scan, selection, 1_000_000, 2_000_000, new(), time,
            out var session, out var reason, out var diagnostic), reason);
        Assert.NotNull(session);
        Assert.Equal("created", diagnostic.Status);
        Assert.Equal(regionBytes, diagnostic.CandidateRegionBytes);
        Assert.Equal(1024L * 1024 * 1024, diagnostic.MaximumRegionBytes);
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

    [Fact]
    public void FullRenewalPromotesOnlyNewCompleteFullScanAfterStrictAdvance()
    {
        var time = new ManualTimeProvider(2_000_000);
        var session = FreshSession(time);
        time.Timestamp = 12_100_000;
        Assert.False(session.CanObserve(Target, time.Timestamp, out var reason));
        Assert.Equal("full-scan-anchor-expired", reason);
        var prior = session.CaptureFullScanRenewal(Target);
        Assert.NotNull(prior);
        Assert.Equal(9, prior!.Observation!.Sequence);

        time.Timestamp = 12_800_000;
        var full = CompleteScan(Nonce);
        var selected = Selected(10, 2, 39, "unit-1", 'j', 'k');
        Assert.True(session.TryBridgeCompletedFullScan(
            Target, full, selected, 12_100_000, 12_800_000, prior, out var bridged));
        Assert.NotNull(bridged);
        Assert.Equal(LiveFreshnessStatus.Fresh, bridged!.Status);
        Assert.Equal(10, bridged.Observation!.Sequence);
        Assert.Equal(selected.Frame!.EnvelopeSha256, bridged.EnvelopeSha256);
        Assert.Equal(10, session.VerifiedTracker.GetCurrent().Observation!.Sequence);

        // Full-scan reporting must show the NEW full selection, not a scoped frame.
        var fullReport = LiveOutput.CreateRiftReader2Report(
            bridged, selected, full, 12_100_000, time.Timestamp,
            TimeSpan.FromSeconds(5), time);
        Assert.Equal("fresh", fullReport.FreshnessStatus);
        Assert.Equal(10, fullReport.CandidateSequence);
        Assert.True(fullReport.Scan.Completed);
        var afterDeliveryReport = LiveOutput.CreateRiftReader2Report(
            session.VerifiedTracker.GetCurrent(), selected, full,
            12_100_000, time.Timestamp, TimeSpan.FromSeconds(5), time);
        Assert.Equal(fullReport.FreshnessStatus, afterDeliveryReport.FreshnessStatus);
        Assert.Equal(fullReport.CandidateSequence, afterDeliveryReport.CandidateSequence);
        Assert.Equal(fullReport.EnvelopeSha256, afterDeliveryReport.EnvelopeSha256);
    }

    [Fact]
    public void ScopedCompletionAfterAnchorExpiryDoesNotAdvancePrivateTracker()
    {
        var time = new ManualTimeProvider(2_000_000);
        var session = FreshSession(time);
        time.Timestamp = 12_100_000;
        var expired = session.Observe(
            Target, CompleteScan(Nonce), Selected(10, 2, 38, "unit-1", 'j', 'k'),
            11_950_000, 12_100_000, out var canContinue);
        Assert.False(canContinue);
        Assert.Equal("unavailable", expired.FreshnessStatus);
        Assert.Equal("full-scan-anchor-expired", expired.Reason);
        Assert.Null(expired.Observation);
        Assert.Null(expired.CandidateSequence);
        Assert.Null(expired.AddonFrameSha256);
        Assert.Null(expired.EnvelopeSha256);
        Assert.Equal(9, session.VerifiedTracker.GetCurrent().Observation!.Sequence);

        var prior = session.CaptureFullScanRenewal(Target);
        Assert.NotNull(prior);
        time.Timestamp = 12_800_000;
        Assert.True(session.TryBridgeCompletedFullScan(
            Target, CompleteScan(Nonce), Selected(11, 2, 39, "unit-1", 'l', 'm'),
            12_100_000, 12_800_000, prior, out var bridged));
        Assert.Equal(11, bridged!.Observation!.Sequence);
    }

    [Fact]
    public void FullRenewalRejectsConflictsDuplicatesAndStaleFullAcquisition()
    {
        var time = new ManualTimeProvider(2_000_000);
        var session = FreshSession(time);
        time.Timestamp = 12_100_000;
        var prior = session.CaptureFullScanRenewal(Target);
        Assert.NotNull(prior);
        var complete = CompleteScan(Nonce);
        var bad = new[]
        {
            Selected(9, 2, 39, "unit-1", 'j', 'k'),
            Selected(10, 2, 36, "unit-1", 'j', 'k'),
            Selected(10, 3, 39, "unit-1", 'j', 'k'),
            Selected(10, 2, 39, "unit-2", 'j', 'k')
        };
        foreach (var selection in bad)
        {
            Assert.False(session.TryBridgeCompletedFullScan(
                Target, complete, selection, 12_100_000, 12_800_000, prior, out _));
        }
        var valid = Selected(10, 2, 39, "unit-1", 'j', 'k');
        var otherTarget = Target with { Identity = Identity with { ProcessId = 124 } };
        Assert.False(session.TryBridgeCompletedFullScan(
            otherTarget, complete, valid, 12_100_000, 12_800_000, prior, out _));
        Assert.False(session.TryBridgeCompletedFullScan(
            Target, complete with { Completed = false }, valid,
            12_100_000, 12_800_000, prior, out _));
        Assert.False(session.TryBridgeCompletedFullScan(
            Target, complete,
            new(LiveAddonSelectionStatus.NoMatchingCandidate, null, 0, 0, "missing"),
            12_100_000, 12_800_000, prior, out _));

        // Even a retained pre-scan ticket cannot override the unchanged 5s gap.
        time.Timestamp = 14_100_000;
        Assert.False(session.TryBridgeCompletedFullScan(
            Target, complete, valid, 12_100_000, 14_100_000, prior, out _));
        Assert.Equal(LiveFreshnessStatus.Warming, session.VerifiedTracker.GetCurrent().Status);
        Assert.Null(session.CaptureFullScanRenewal(Target));
    }

    [Fact]
    public void FullRenewalRejectsChangedBuildAndReaderNonce()
    {
        var time = new ManualTimeProvider(2_000_000);
        var session = FreshSession(time);
        time.Timestamp = 12_100_000;
        var prior = session.CaptureFullScanRenewal(Target);
        Assert.NotNull(prior);
        var full = CompleteScan(Nonce);
        var valid = Selected(10, 2, 39, "unit-1", 'j', 'k');
        var otherBuild = Target with
        {
            Identity = Identity with { ExecutableSha256 = new string('B', 64) }
        };
        Assert.False(session.TryBridgeCompletedFullScan(
            otherBuild, full, valid, 12_100_000, 12_800_000, prior, out _));

        var wrongNonceFrame = valid.Frame! with { Challenge = new string('f', 32) };
        var wrongNonce = valid with { Frame = wrongNonceFrame };
        time.Timestamp = 12_800_000;
        Assert.False(session.TryBridgeCompletedFullScan(
            Target, full, wrongNonce, 12_100_000, 12_800_000, prior, out _));
        Assert.Equal(LiveFreshnessStatus.Invalidated, session.VerifiedTracker.GetCurrent().Status);
    }

    [Fact]
    public void AlreadyExpiredContinuityCannotStartFullRenewal()
    {
        var time = new ManualTimeProvider(2_000_000);
        var session = FreshSession(time);
        time.Timestamp = 14_100_000;
        Assert.Equal(LiveFreshnessStatus.Expired, session.VerifiedTracker.GetCurrent().Status);
        Assert.Null(session.CaptureFullScanRenewal(Target));
    }

    private static FastObservationSession FreshSession(ManualTimeProvider time)
    {
        time.Timestamp = 2_000_000;
        var anchor = Selected(6, 2, 29, "unit-1", 'a', 'b');
        var full = CompleteScan(Nonce) with { CandidateRegions = [Region(0x10000, 4096)] };
        Assert.True(FastObservationSession.TryCreate(
            Target, full, anchor, 1_000_000, 2_000_000,
            new() { FreshnessTimeout = TimeSpan.FromSeconds(5), MaxClockSkew = TimeSpan.FromSeconds(1) },
            time, out var session, out _, out _));
        foreach (var (sequence, completed, clock) in new[]
        {
            (7L, 3_000_000L, 30.0), (8L, 6_000_000L, 33.0), (9L, 9_000_000L, 36.0)
        })
        {
            time.Timestamp = completed;
            var report = session!.Observe(
                Target, CompleteScan(Nonce), Selected(sequence, 2, clock, "unit-1", 'c', 'd'),
                completed - 500_000, completed, out var canContinue);
            Assert.True(canContinue);
            Assert.Equal("fresh-scoped", report.FreshnessStatus);
        }
        return session!;
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
