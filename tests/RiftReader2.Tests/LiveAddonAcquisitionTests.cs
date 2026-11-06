using System.Security.Cryptography;
using System.Text;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Tests;

public sealed class LiveAddonEnvelopeTests
{
    private const string Challenge = "0123456789abcdef0123456789abcdef";
    private const string OtherChallenge = "fedcba9876543210fedcba9876543210";

    [Fact]
    public void Decoder_AcceptsExactEnvelopeAndPreservesBothByteIdentities()
    {
        var addonFrame = AddonFrame(7, 2, 12.5);
        var envelope = Envelope(Challenge, addonFrame);

        var decoded = LiveAddonEnvelopeDecoder.Decode(envelope, Challenge);

        Assert.Equal(4144, LiveAddonEnvelopeDecoder.MaxEnvelopeBytes);
        Assert.Equal(Challenge, decoded.Challenge);
        Assert.Equal(7, decoded.Observation.Sequence);
        Assert.Equal(2, decoded.Observation.Epoch);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(envelope)), decoded.EnvelopeSha256);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(addonFrame)), decoded.AddonFrameSha256);
    }

    [Theory]
    [InlineData("RR2L1|0123456789abcdef0123456789abcdef|RR2A1|{}|ENDRR2A1")]
    [InlineData("RR2L1|0123456789ABCDEF0123456789ABCDEF|RR2A1|{}|ENDRR2A1|ENDRR2L1")]
    [InlineData("RR2L2|0123456789abcdef0123456789abcdef|RR2A1|{}|ENDRR2A1|ENDRR2L1")]
    [InlineData("RR2L1|0123456789abcdef0123456789abcdef/RR2A1|{}|ENDRR2A1|ENDRR2L1")]
    public void Decoder_RejectsInvalidOuterFraming(string text) =>
        Assert.Throws<InvalidDataException>(() =>
            LiveAddonEnvelopeDecoder.Decode(Encoding.ASCII.GetBytes(text), Challenge));

    [Fact]
    public void Decoder_RejectsUnexpectedChallenge() =>
        Assert.Throws<InvalidDataException>(() =>
            LiveAddonEnvelopeDecoder.Decode(Envelope(OtherChallenge, AddonFrame(1, 1, 1)), Challenge));

    [Fact]
    public void Selector_ChoosesHighestSequenceCollapsesCopiesAndIgnoresOldChallenge()
    {
        var first = Envelope(Challenge, AddonFrame(3, 1, 3));
        var newest = Envelope(Challenge, AddonFrame(4, 1, 4));
        var staleAttachment = Envelope(OtherChallenge, AddonFrame(99, 1, 99));

        var result = LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { first, newest, newest.ToArray(), staleAttachment }, Challenge, true);

        Assert.Equal(LiveAddonSelectionStatus.Selected, result.Status);
        Assert.Equal(4, result.Frame!.Observation.Sequence);
        Assert.Equal(3, result.MatchingCandidateCount);
        Assert.Equal(2, result.IdenticalCopyCount);
    }

    [Fact]
    public void Selector_BlocksSameSequenceConflictingExactBytes()
    {
        var left = Envelope(Challenge, AddonFrame(5, 1, 5, "player-a"));
        var right = Envelope(Challenge, AddonFrame(5, 1, 5, "player-b"));

        var result = LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { left, right }, Challenge, true);

        Assert.Equal(LiveAddonSelectionStatus.Conflict, result.Status);
        Assert.Null(result.Frame);
    }

    [Fact]
    public void Selector_NeverUsesCandidatesFromAnIncompleteScan()
    {
        var result = LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { Envelope(Challenge, AddonFrame(5, 1, 5)) }, Challenge, false);

        Assert.Equal(LiveAddonSelectionStatus.IncompleteScan, result.Status);
        Assert.Null(result.Frame);
    }

    [Fact]
    public void Selector_RejectsMalformedCompleteCandidate()
    {
        var malformed = Encoding.ASCII.GetBytes($"RR2L1|{Challenge}|RR2A1|{{}}|ENDRR2A1|BADEND");

        Assert.Throws<InvalidDataException>(() => LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { malformed }, Challenge, true));
    }

    [Fact]
    public void Selector_IgnoresMalformedCandidateThatCannotMatchCurrentChallenge()
    {
        var malformedOldAttachment = Encoding.ASCII.GetBytes(
            "RR2L1|FEDCBA9876543210FEDCBA9876543210|not-a-frame|BADEND");
        var current = Envelope(Challenge, AddonFrame(1, 1, 1));

        var result = LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { malformedOldAttachment, current }, Challenge, true);

        Assert.Equal(LiveAddonSelectionStatus.Selected, result.Status);
        Assert.Equal(1, result.MatchingCandidateCount);
    }

    internal static byte[] Envelope(string challenge, byte[] addonFrame) =>
        Encoding.ASCII.GetBytes($"RR2L1|{challenge}|{Encoding.ASCII.GetString(addonFrame)}|ENDRR2L1");

    internal static byte[] AddonFrame(long sequence, long epoch, double clock, string player = "player") =>
        Encoding.ASCII.GetBytes(
            "RR2A1|{\"schemaVersion\":1,\"addonVersion\":\"0.1.0\",\"sequence\":" + sequence +
            ",\"epoch\":" + epoch + ",\"clock\":{\"status\":\"ok\",\"value\":" +
            clock.ToString(System.Globalization.CultureInfo.InvariantCulture) +
            "},\"player\":{\"status\":\"ok\",\"value\":\"" + player +
            "\"},\"fields\":{\"coordX\":{\"status\":\"ok\",\"value\":1}," +
            "\"coordY\":{\"status\":\"ok\",\"value\":2},\"coordZ\":{\"status\":\"ok\",\"value\":3}," +
            "\"health\":{\"status\":\"ok\",\"value\":4},\"healthMax\":{\"status\":\"ok\",\"value\":5}," +
            "\"combat\":{\"status\":\"ok\",\"value\":false}}}|ENDRR2A1");
}

public sealed class LiveAddonFreshnessTests
{
    private const string Challenge = "0123456789abcdef0123456789abcdef";
    private const string Sha = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

    [Fact]
    public void TwoAdvancingScansWarmThenBecomeFresh()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);

        var firstAt = time.GetTimestamp();
        Assert.Equal(LiveFreshnessStatus.Warming,
            tracker.Observe(identity, Selected(1, 1, 10), firstAt).Status);
        time.Advance(TimeSpan.FromMilliseconds(500));
        var secondAt = time.GetTimestamp();
        var result = tracker.Observe(identity, Selected(2, 1, 10.5), secondAt);

        Assert.Equal(LiveFreshnessStatus.Fresh, result.Status);
        Assert.Equal(2, result.Observation!.Sequence);
        Assert.Equal(TimeSpan.Zero, result.Age);
    }

    [Fact]
    public void DuplicateDoesNotRenewFreshnessTimeout()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(1, 1, 1), time.GetTimestamp());
        time.Advance(TimeSpan.FromSeconds(1));
        var selected = Selected(2, 1, 2);
        tracker.Observe(identity, selected, time.GetTimestamp());

        time.Advance(TimeSpan.FromSeconds(4));
        Assert.Equal(LiveFreshnessStatus.Fresh,
            tracker.Observe(identity, selected, time.GetTimestamp()).Status);
        time.Advance(TimeSpan.FromSeconds(2));

        Assert.Equal(LiveFreshnessStatus.Expired, tracker.GetCurrent().Status);
    }

    [Fact]
    public void LostScanWithholdsImmediatelyAndRecoveryWarms()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = FreshTracker(time, identity);

        var lost = tracker.Observe(identity,
            new(LiveAddonSelectionStatus.IncompleteScan, null, 0, 0, "scan-incomplete"), time.GetTimestamp());
        Assert.Equal(LiveFreshnessStatus.Unavailable, lost.Status);
        Assert.NotNull(lost.ObservedAtTimestamp);
        Assert.Equal(TimeSpan.Zero, lost.Age);
        time.Advance(TimeSpan.FromMilliseconds(500));
        Assert.Equal(LiveFreshnessStatus.Warming,
            tracker.Observe(identity, Selected(3, 1, 3), time.GetTimestamp()).Status);
        time.Advance(TimeSpan.FromMilliseconds(500));
        Assert.Equal(LiveFreshnessStatus.Fresh,
            tracker.Observe(identity, Selected(4, 1, 3.5), time.GetTimestamp()).Status);
    }

    [Fact]
    public void LossPreservesHighWaterAndRegressionInvalidates()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = FreshTracker(time, identity);
        tracker.Observe(identity,
            new(LiveAddonSelectionStatus.NoMatchingCandidate, null, 0, 0, "not-found"), time.GetTimestamp());
        time.Advance(TimeSpan.FromMilliseconds(500));

        var result = tracker.Observe(identity, Selected(1, 1, 1), time.GetTimestamp());

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("source-sequence-regressed", result.Reason);
    }

    [Fact]
    public void LongGapRequiresARecoveryBaselineThenAnotherAdvance()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = FreshTracker(time, identity);
        time.Advance(TimeSpan.FromSeconds(6));

        Assert.Equal(LiveFreshnessStatus.Warming,
            tracker.Observe(identity, Selected(3, 1, 8), time.GetTimestamp()).Status);
        time.Advance(TimeSpan.FromMilliseconds(500));
        Assert.Equal(LiveFreshnessStatus.Fresh,
            tracker.Observe(identity, Selected(4, 1, 8.5), time.GetTimestamp()).Status);
    }

    [Theory]
    [InlineData("conflict")]
    [InlineData("epoch")]
    [InlineData("sequence")]
    [InlineData("clock")]
    [InlineData("identity")]
    public void UnsafeTransitionInvalidatesStickily(string transition)
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(5, 2, 10), time.GetTimestamp());
        time.Advance(TimeSpan.FromMilliseconds(500));

        var observedIdentity = transition == "identity" ? identity with { ProcessId = 43 } : identity;
        var selection = transition switch
        {
            "conflict" => new LiveAddonSelection(LiveAddonSelectionStatus.Conflict, null, 2, 0, "conflict"),
            "epoch" => Selected(6, 3, 10.5),
            "sequence" => Selected(4, 2, 10.5),
            "clock" => Selected(6, 2, 9.5),
            _ => Selected(6, 2, 10.5)
        };

        Assert.Equal(LiveFreshnessStatus.Invalidated,
            tracker.Observe(observedIdentity, selection, time.GetTimestamp()).Status);
        time.Advance(TimeSpan.FromMilliseconds(500));
        Assert.Equal(LiveFreshnessStatus.Invalidated,
            tracker.Observe(identity, Selected(7, 2, 11), time.GetTimestamp()).Status);
    }

    [Fact]
    public void NewChallengeExcludesOldHeapFrames()
    {
        const string newChallenge = "fedcba9876543210fedcba9876543210";
        var oldHighWater = LiveAddonEnvelopeTests.Envelope(Challenge,
            LiveAddonEnvelopeTests.AddonFrame(500, 1, 500));
        var newFrame = LiveAddonEnvelopeTests.Envelope(newChallenge,
            LiveAddonEnvelopeTests.AddonFrame(1, 1, 501));

        var selected = LiveAddonCandidateSelector.Select(
            new ReadOnlyMemory<byte>[] { oldHighWater, newFrame }, newChallenge, true);

        Assert.Equal(1, selected.Frame!.Observation.Sequence);
        Assert.Equal(newChallenge, selected.Frame.Challenge);
    }

    [Fact]
    public void ConservativeScanStartAgeWithholdsLongAcquisitionAndRecoveryWarms()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(1, 1, 1), time.GetTimestamp());
        time.Advance(TimeSpan.FromSeconds(1));
        var scanStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromSeconds(6));

        var result = tracker.Observe(identity, Selected(2, 1, 2), scanStartedAt);

        Assert.Equal(LiveFreshnessStatus.Unavailable, result.Status);
        Assert.Equal("observation-already-expired", result.Reason);
        var recoveryStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromMilliseconds(100));
        Assert.Equal(LiveFreshnessStatus.Warming,
            tracker.Observe(identity, Selected(3, 1, 3), recoveryStartedAt).Status);
        time.Advance(TimeSpan.FromSeconds(1));
        Assert.Equal(LiveFreshnessStatus.Fresh,
            tracker.Observe(identity, Selected(4, 1, 4), time.GetTimestamp()).Status);
    }

    [Fact]
    public void SourceClockCannotAdvanceBeyondReceiptDeltaAndTolerance()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(1, 1, 1), time.GetTimestamp());
        time.Advance(TimeSpan.FromMilliseconds(500));

        var result = tracker.Observe(identity, Selected(2, 1, 3), time.GetTimestamp());

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("source-clock-delta-implausible", result.Reason);
    }

    [Fact]
    public void SlowSourceClockCannotTrailReceiptDeltaBeyondTolerance()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(1, 1, 10), time.GetTimestamp());
        time.Advance(TimeSpan.FromSeconds(4));

        var result = tracker.Observe(identity, Selected(2, 1, 10.01), time.GetTimestamp());

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("source-clock-delta-implausible", result.Reason);
    }

    [Fact]
    public void VariableScanDurationsUseAcquisitionIntervalsWithoutWideningClockSkew()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var firstStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromSeconds(2.4));
        var firstCompletedAt = time.GetTimestamp();
        Assert.Equal(LiveFreshnessStatus.Warming,
            tracker.Observe(identity, Selected(1, 1, 10), firstStartedAt, firstCompletedAt).Status);
        time.Advance(TimeSpan.FromMilliseconds(250));
        var secondStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromSeconds(1.2));
        var secondCompletedAt = time.GetTimestamp();

        var result = tracker.Observe(
            identity, Selected(2, 1, 12.5), secondStartedAt, secondCompletedAt);

        Assert.Equal(LiveFreshnessStatus.Fresh, result.Status);
        Assert.Equal(2, result.Observation!.Sequence);
        Assert.Equal(TimeSpan.FromSeconds(1.2), result.Age);
    }

    [Fact]
    public void SourceClockOutsideAcquisitionIntervalsAndToleranceStillInvalidates()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var firstStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromSeconds(1));
        tracker.Observe(identity, Selected(1, 1, 10), firstStartedAt, time.GetTimestamp());
        time.Advance(TimeSpan.FromMilliseconds(500));
        var secondStartedAt = time.GetTimestamp();
        time.Advance(TimeSpan.FromSeconds(1));

        var result = tracker.Observe(
            identity, Selected(2, 1, 14), secondStartedAt, time.GetTimestamp());

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("source-clock-delta-implausible", result.Reason);
    }

    [Fact]
    public void ReversedOrFutureAcquisitionIntervalInvalidates()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var reversed = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var now = time.GetTimestamp();

        var reversedResult = reversed.Observe(
            identity, Selected(1, 1, 1), now + TimeSpan.TicksPerSecond, now);

        Assert.Equal(LiveFreshnessStatus.Invalidated, reversedResult.Status);
        Assert.Equal("observation-interval-invalid", reversedResult.Reason);

        var future = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var futureResult = future.Observe(
            identity, Selected(1, 1, 1), now, now + TimeSpan.TicksPerSecond);
        Assert.Equal(LiveFreshnessStatus.Invalidated, futureResult.Status);
        Assert.Equal("observation-time-in-future", futureResult.Reason);
    }

    [Fact]
    public void AcquisitionIntervalsMustAdvanceByStartTime()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var firstStartedAt = time.GetTimestamp();
        tracker.Observe(identity, Selected(1, 1, 1), firstStartedAt, firstStartedAt);
        time.Advance(TimeSpan.FromSeconds(1));

        var result = tracker.Observe(
            identity, Selected(2, 1, 2), firstStartedAt, time.GetTimestamp());

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("receiver-time-not-advanced", result.Reason);
    }

    [Fact]
    public void FutureObservedAtTimestampInvalidatesAttachment()
    {
        var time = new ManualTimeProvider();
        var identity = Identity();
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        var future = time.GetTimestamp() + TimeSpan.FromMilliseconds(1).Ticks;

        var result = tracker.Observe(identity, Selected(1, 1, 1), future);

        Assert.Equal(LiveFreshnessStatus.Invalidated, result.Status);
        Assert.Equal("observation-time-in-future", result.Reason);
    }

    private static LiveAddonFreshnessTracker FreshTracker(ManualTimeProvider time, LiveAttachmentIdentity identity)
    {
        var tracker = new LiveAddonFreshnessTracker(identity, timeProvider: time);
        tracker.Observe(identity, Selected(1, 1, 1), time.GetTimestamp());
        time.Advance(TimeSpan.FromSeconds(1));
        Assert.Equal(LiveFreshnessStatus.Fresh,
            tracker.Observe(identity, Selected(2, 1, 2), time.GetTimestamp()).Status);
        return tracker;
    }

    private static LiveAttachmentIdentity Identity() => new(42, 638000000000000000, Sha, Challenge);

    private static LiveAddonSelection Selected(long sequence, long epoch, double clock)
    {
        var envelope = LiveAddonEnvelopeTests.Envelope(Challenge,
            LiveAddonEnvelopeTests.AddonFrame(sequence, epoch, clock));
        return LiveAddonCandidateSelector.Select(new ReadOnlyMemory<byte>[] { envelope }, Challenge, true);
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private long timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => timestamp;

        internal void Advance(TimeSpan value) => timestamp = checked(timestamp + value.Ticks);
    }
}
