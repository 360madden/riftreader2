using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed class FastObservationSession
{
    internal const long MaximumRegionBytes = 1024L * 1024 * 1024;
    internal static readonly TimeSpan MaximumAnchorAge = TimeSpan.FromSeconds(10);
    internal static readonly TimeSpan RenewalStartAge = TimeSpan.FromTicks(MaximumAnchorAge.Ticks / 4);

    private readonly TimeProvider timeProvider;
    private readonly LiveAddonFreshnessTracker tracker;
    private readonly TimeSpan freshnessTimeout;

    private FastObservationSession(
        LiveAttachmentIdentity identity,
        IReadOnlyList<LiveCandidateRegion> regions,
        FastObservationAnchorReport anchor,
        LiveAddonFreshnessTracker tracker,
        TimeSpan freshnessTimeout,
        TimeProvider timeProvider)
    {
        Identity = identity;
        Regions = regions;
        Anchor = anchor;
        this.tracker = tracker;
        this.freshnessTimeout = freshnessTimeout;
        this.timeProvider = timeProvider;
    }

    internal LiveAttachmentIdentity Identity { get; }

    internal IReadOnlyList<LiveCandidateRegion> Regions { get; }

    internal FastObservationAnchorReport Anchor { get; }

    internal static bool TryCreate(
        DiscoveredTarget target,
        LiveScanResult fullScan,
        LiveAddonSelection fullSelection,
        long fullScanStartedAt,
        long fullScanCompletedAt,
        LiveFreshnessOptions freshnessOptions,
        TimeProvider timeProvider,
        out FastObservationSession? session,
        out string? reason,
        out FastObservationAnchorDiagnostic diagnostic)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentNullException.ThrowIfNull(fullScan);
        ArgumentNullException.ThrowIfNull(fullSelection);
        ArgumentNullException.ThrowIfNull(freshnessOptions);
        ArgumentNullException.ThrowIfNull(timeProvider);
        session = null;

        var regions = fullScan.CandidateRegions.Distinct().OrderBy(region => region.BaseAddress.ToInt64()).ToArray();
        long? regionBytes = 0;
        try
        {
            foreach (var region in regions)
            {
                if (region.Size <= 0)
                    throw new InvalidDataException();
                regionBytes = checked(regionBytes.Value + region.Size);
            }
        }
        catch (Exception exception) when (exception is OverflowException or InvalidDataException)
        {
            regionBytes = null;
        }

        if (!fullScan.Completed || !string.Equals(fullScan.Status, "complete", StringComparison.Ordinal) ||
            fullSelection.Status != LiveAddonSelectionStatus.Selected || fullSelection.Frame is null)
        {
            reason = "full-scan-anchor-unavailable";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }
        if (timeProvider.GetElapsedTime(fullScanStartedAt, fullScanCompletedAt) < TimeSpan.Zero)
        {
            reason = "full-scan-anchor-time-invalid";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }
        if (regions.Length == 0)
        {
            reason = "candidate-region-scope-empty";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }
        if (regionBytes is null)
        {
            reason = "candidate-region-scope-invalid";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }
        if (regionBytes.Value > MaximumRegionBytes)
        {
            reason = "candidate-region-scope-too-large";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }

        var frame = fullSelection.Frame;
        if (!TryProducerIdentity(frame.Observation, out var playerId, out var clock))
        {
            reason = "anchor-producer-identity-unavailable";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }

        var freshnessTracker = new LiveAddonFreshnessTracker(target.Identity, freshnessOptions, timeProvider);
        var baseline = freshnessTracker.Observe(target.Identity, fullSelection, fullScanStartedAt, fullScanCompletedAt);
        if (baseline.Status == LiveFreshnessStatus.Invalidated)
        {
            reason = baseline.Reason ?? "full-scan-anchor-invalid";
            diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, reason);
            return false;
        }

        var anchor = new FastObservationAnchorReport(
            fullScanStartedAt,
            fullScanCompletedAt,
            timeProvider.TimestampFrequency,
            frame.EnvelopeSha256,
            frame.AddonFrameSha256,
            frame.Observation.Sequence,
            frame.Observation.Epoch,
            clock,
            playerId,
            regions.Length,
            regionBytes.Value,
            MaximumAnchorAge.TotalMilliseconds);
        session = new(target.Identity, regions, anchor, freshnessTracker, freshnessOptions.FreshnessTimeout, timeProvider);
        reason = null;
        diagnostic = Diagnostic(fullScan, fullSelection, regions.Length, regionBytes, null);
        return true;
    }

    // A full-scan renewal may use validated fast-scoped history as continuity,
    // but only the NEW completed whole-process scan is ever published as full-source data.
    // Capture this ticket before the full scan: its prior sample may expire during acquisition.
    internal LiveAddonFreshness? CaptureFullScanRenewal(DiscoveredTarget target)
    {
        if (target.Identity != Identity)
            return null;
        var freshness = tracker.GetCurrent();
        if (freshness.Status != LiveFreshnessStatus.Fresh || freshness.Observation is null ||
            !TryProducerIdentity(freshness.Observation, out var playerId, out _) ||
            !string.Equals(playerId, Anchor.PlayerId, StringComparison.Ordinal) ||
            freshness.Observation.Epoch != Anchor.CandidateEpoch)
            return null;
        return freshness;
    }

    internal bool TryBridgeCompletedFullScan(
        DiscoveredTarget target,
        LiveScanResult fullScan,
        LiveAddonSelection fullSelection,
        long startedAt,
        long completedAt,
        LiveAddonFreshness? priorFresh,
        out LiveAddonFreshness? bridged)
    {
        bridged = null;
        if (priorFresh?.Status != LiveFreshnessStatus.Fresh ||
            priorFresh.Identity != Identity || priorFresh.Observation is null ||
            target.Identity != Identity || !fullScan.Completed ||
            !string.Equals(fullScan.Status, "complete", StringComparison.Ordinal) ||
            fullSelection.Status != LiveAddonSelectionStatus.Selected || fullSelection.Frame is null ||
            !TryProducerIdentity(priorFresh.Observation, out var priorPlayer, out var priorClock) ||
            !TryProducerIdentity(fullSelection.Frame.Observation, out var playerId, out var clock) ||
            !string.Equals(priorPlayer, Anchor.PlayerId, StringComparison.Ordinal) ||
            !string.Equals(playerId, Anchor.PlayerId, StringComparison.Ordinal) ||
            fullSelection.Frame.Observation.Epoch != Anchor.CandidateEpoch ||
            priorFresh.Observation.Epoch != Anchor.CandidateEpoch ||
            fullSelection.Frame.Observation.Sequence <= priorFresh.Observation.Sequence ||
            clock <= priorClock)
            return false;

        // This enforces nonce, process identity, monotonic clock/sequence and the
        // existing acquisition-gap timeout. It never relaxes or resets freshness.
        var verified = tracker.Observe(target.Identity, fullSelection, startedAt, completedAt);
        if (verified.Status != LiveFreshnessStatus.Fresh ||
            verified.Observation?.Sequence != fullSelection.Frame.Observation.Sequence ||
            !string.Equals(verified.EnvelopeSha256, fullSelection.Frame.EnvelopeSha256, StringComparison.Ordinal))
            return false;
        bridged = verified;
        return true;
    }

    internal LiveAddonFreshnessTracker VerifiedTracker => tracker;

    internal bool CanObserve(DiscoveredTarget target, long now, out string? reason)
    {
        if (target.Identity != Identity)
        {
            reason = "source-identity-mismatch";
            return false;
        }
        var age = timeProvider.GetElapsedTime(Anchor.FullScanCompletedAtTimestamp, now);
        if (age < TimeSpan.Zero)
        {
            reason = "anchor-time-in-future";
            return false;
        }
        if (age > MaximumAnchorAge)
        {
            reason = "full-scan-anchor-expired";
            return false;
        }
        reason = null;
        return true;
    }

    internal FastObservationReport Observe(
        DiscoveredTarget target,
        LiveScanResult scopedScan,
        LiveAddonSelection scopedSelection,
        long startedAt,
        long completedAt,
        out bool canContinue)
    {
        if (scopedSelection.Status == LiveAddonSelectionStatus.Selected && scopedSelection.Frame is { } frame &&
            (!TryProducerIdentity(frame.Observation, out var playerId, out _) ||
             !string.Equals(playerId, Anchor.PlayerId, StringComparison.Ordinal) ||
             frame.Observation.Epoch != Anchor.CandidateEpoch))
        {
            scopedSelection = new(LiveAddonSelectionStatus.Conflict, null,
                scopedSelection.MatchingCandidateCount, scopedSelection.IdenticalCopyCount,
                "scoped-producer-identity-mismatch");
        }

        // A scoped scan finishing after the ten-second anchor boundary must not
        // become an accepted fast observation or advance its continuity tracker.
        // A previously valid fresh sample can still bridge the NEXT full scan.
        if (scopedScan.Completed &&
            scopedSelection.Status == LiveAddonSelectionStatus.Selected &&
            !CanObserve(target, completedAt, out var anchorReason) &&
            anchorReason == "full-scan-anchor-expired")
        {
            canContinue = false;
            return LiveOutput.CreateFastObservationReport(
                Anchor, tracker.GetCurrent(), scopedSelection, scopedScan,
                startedAt, completedAt, freshnessTimeout, timeProvider) with
            {
                FreshnessStatus = "unavailable",
                Reason = anchorReason,
                Observation = null,
                EnvelopeSha256 = null,
                AddonFrameSha256 = null,
                CandidateSequence = null,
                CandidateEpoch = null
            };
        }

        var freshness = tracker.Observe(target.Identity, scopedSelection, startedAt, completedAt);
        canContinue = scopedScan.Completed &&
                      scopedSelection.Status == LiveAddonSelectionStatus.Selected &&
                      freshness.Status != LiveFreshnessStatus.Invalidated &&
                      CanObserve(target, completedAt, out _);
        return LiveOutput.CreateFastObservationReport(
            Anchor,
            freshness,
            scopedSelection,
            scopedScan,
            startedAt,
            completedAt,
            freshnessTimeout,
            timeProvider);
    }

    private static bool TryProducerIdentity(AddonObservation observation, out string playerId, out double clock)
    {
        playerId = observation.Player.Value ?? string.Empty;
        clock = observation.Clock.Value ?? double.NaN;
        return observation.Player.Status == AddonFieldStatus.Ok &&
               !string.IsNullOrWhiteSpace(playerId) &&
               observation.Clock.Status == AddonFieldStatus.Ok &&
               double.IsFinite(clock) && clock >= 0;
    }

    private static FastObservationAnchorDiagnostic Diagnostic(
        LiveScanResult scan,
        LiveAddonSelection selection,
        int regionCount,
        long? regionBytes,
        string? reason) =>
        new(
            1,
            "candidate-region-anchor-attempt/1",
            reason is null ? "created" : "rejected",
            reason,
            scan.Completed,
            scan.Status,
            selection.Status switch
            {
                LiveAddonSelectionStatus.Selected => "selected",
                LiveAddonSelectionStatus.NoMatchingCandidate => "no-matching-candidate",
                LiveAddonSelectionStatus.IncompleteScan => "incomplete-scan",
                LiveAddonSelectionStatus.Conflict => "conflict",
                _ => "conflict"
            },
            regionCount,
            regionBytes,
            MaximumRegionBytes,
            MaximumAnchorAge.TotalMilliseconds);
}
