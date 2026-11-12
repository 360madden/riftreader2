using System.Diagnostics;
using System.Text.Json;
using RiftReader2.Live.Control;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class MoveKeyCommandTests
{
    [Theory]
    [InlineData('q', 0xC0100001u)]
    [InlineData('e', 0xC0120001u)]
    public void BackgroundReleaseMessageHasScanCodeAndKeyUpFlagsOnly(char key, uint expected)
    {
        Assert.Equal(expected, WindowsControlDesktop.KeyUpMessageParameters(key));
    }

    [Fact]
    public void RecoveryIsExplicitKeyUpOnlyAndCannotAlsoHoldOrMeasure()
    {
        var options = MoveKeyCommand.Parse(["--pid", "123", "--key", "q", "--release-only"]);
        Assert.True(options.ReleaseOnly);
        Assert.False(options.Execute);
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "123", "--key", "q", "--release-only", "--hold-ms", "100"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "123", "--key", "q", "--release-only", "--measure-xyz"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "123", "--key", "q,w", "--release-only"]));
    }

    [Theory]
    [InlineData("0", 0)]
    [InlineData("500", 500)]
    [InlineData("1000", 1000)]
    public void ParsesOptionalActorPoseDelay(string value, int expected)
    {
        var options = MoveKeyCommand.Parse(["--pid", "123", "--key", "a",
            "--measure-actor-pose", "--actor-pose-settle-ms", value]);
        Assert.Equal(expected, options.ActorPoseSettleMilliseconds);
        Assert.False(options.Execute);
    }

    [Theory]
    [InlineData("-1")]
    [InlineData("1001")]
    [InlineData("abc")]
    public void RejectsInvalidActorPoseDelay(string value)
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "123", "--key", "a", "--measure-actor-pose",
             "--actor-pose-settle-ms", value]));
    }

    [Fact]
    public void ActorPoseDelayRequiresPoseMeasurement()
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "123", "--key", "a", "--actor-pose-settle-ms", "500"]));
        Assert.Equal(0, MoveKeyCommand.Parse(["--pid", "123", "--key", "a"])
            .ActorPoseSettleMilliseconds);
    }

    [Fact]
    public void InputCallTimingProvidesUsableUtcEnvelopeWithoutClaimingKeyDownOrGameResponse()
    {
        var start = DateTimeOffset.Parse("2026-11-11T18:00:00.1000000Z");
        var result = MoveKeyCommand.SummarizeInputCallTiming(
            start, start.AddMilliseconds(518), TimeSpan.FromMilliseconds(517.4),
            TimeSpan.FromMilliseconds(516.8));
        Assert.Equal(start, result.StartedAtUtc);
        Assert.Equal(start.AddMilliseconds(518), result.CompletedAtUtc);
        Assert.Equal(517.4, result.MonotonicElapsedMilliseconds, 6);
        Assert.Equal(516.8, result.ExecutorObservedMilliseconds, 6);
        Assert.True(result.UtcOrderValid);
        Assert.True(result.WallClockConsistentWithMonotonic);
        Assert.False(result.ExactKeyDownUpTimesKnown);
        Assert.Contains("unverified", result.Qualification);
    }

    [Fact]
    public void InputCallTimingDetectsWallClockJumpWithoutConcealingInputReceipt()
    {
        var start = DateTimeOffset.Parse("2026-11-11T18:00:00Z");
        var jumped = MoveKeyCommand.SummarizeInputCallTiming(
            start, start.AddSeconds(4), TimeSpan.FromMilliseconds(500),
            TimeSpan.FromMilliseconds(497));
        Assert.True(jumped.UtcOrderValid);
        Assert.False(jumped.WallClockConsistentWithMonotonic);
        Assert.False(jumped.ExactKeyDownUpTimesKnown);
        var reversed = MoveKeyCommand.SummarizeInputCallTiming(
            start, start.AddSeconds(-1), TimeSpan.FromMilliseconds(500),
            TimeSpan.FromMilliseconds(497));
        Assert.False(reversed.UtcOrderValid);
        Assert.False(reversed.WallClockConsistentWithMonotonic);
        var missed = MoveKeyCommand.SummarizeInputCallTiming(
            start, start.AddMilliseconds(500), TimeSpan.FromMilliseconds(200),
            TimeSpan.FromMilliseconds(500));
        Assert.False(missed.WallClockConsistentWithMonotonic);
    }

    private static MoveKeyCommand.KeySendTimeline DeterministicTimeline(
        IReadOnlyList<int> millisecondTicks)
    {
        var ticks = new Queue<long>(millisecondTicks.Select(ms =>
            (long)Math.Round(ms * Stopwatch.Frequency / 1000.0)));
        var origin = DateTimeOffset.Parse("2026-11-11T18:00:00Z");
        var dates = new Queue<DateTimeOffset>(millisecondTicks.Select(ms => origin.AddMilliseconds(ms)));
        return new MoveKeyCommand.KeySendTimeline(
            monotonicTick: () => ticks.Dequeue(),
            utcNow: () => dates.Dequeue());
    }

    [Fact]
    public async Task SuccessfulDownAndWatchdogThreadUpProduceTightMonotonicHoldBounds()
    {
        var sends = new List<string>();
        var timeline = DeterministicTimeline([0, 1, 511, 512]);
        timeline.Send("a", true, () => sends.Add("down"));
        // The actual bounded-release worker can call KeyUp from a different thread.
        await Task.Run(() => timeline.Send("a", false, () =>
        {
            lock (sends) sends.Add("up");
        }));
        var events = timeline.Snapshot();
        Assert.Equal(["down", "up"], sends);
        Assert.Equal(2, events.Length);
        Assert.Equal(["key-down", "key-up"], events.Select(e => e.Phase));
        Assert.All(events, e => Assert.True(e.Inserted));
        var window = MoveKeyCommand.SummarizeKeyHold("a", events);
        Assert.Equal("candidate-sendinput-hold-bounds", window.Status);
        Assert.Equal(510, window.MinimumMillisecondsCandidate!.Value, 2);
        Assert.Equal(512, window.MaximumMillisecondsCandidate!.Value, 2);
        Assert.Equal(511, window.MidpointMillisecondsCandidate!.Value, 2);
        Assert.False(window.ExactKeyDownUpTimesKnown);
        Assert.False(window.GameResponseVerified);
        var startedAt = DateTimeOffset.Parse("2026-11-11T18:00:00Z");
        var timing = MoveKeyCommand.SummarizeInputCallTiming(
            startedAt, startedAt.AddMilliseconds(512),
            TimeSpan.FromMilliseconds(512), TimeSpan.FromMilliseconds(511));
        Assert.Equal(511,
            MoveKeyCommand.TurnRateHoldCandidateMilliseconds(window, timing), 2);
        Assert.True(double.IsNaN(MoveKeyCommand.TurnRateHoldCandidateMilliseconds(
            window, timing with { WallClockConsistentWithMonotonic = false })));
        Assert.NotNull(window.DownCallStartedAtUtc);
        Assert.NotNull(window.UpCallCompletedAtUtc);
        // Stopwatch ticks are internal, not serialized as huge unstable host values.
        var serialized = JsonSerializer.Serialize(events);
        Assert.DoesNotContain("MonotonicStartTick", serialized);
        Assert.DoesNotContain("MonotonicEndTick", serialized);
    }

    [Fact]
    public void FailedDownOrUpNeverProduceAQualifiedHoldDuration()
    {
        var failedDown = DeterministicTimeline([0, 1, 100, 101]);
        Assert.Throws<InvalidOperationException>(() =>
            failedDown.Send("q", true, () => throw new InvalidOperationException("down refused")));
        failedDown.Send("q", false, () => { });
        var unsuccessful = MoveKeyCommand.SummarizeKeyHold("q", failedDown.Snapshot());
        Assert.Equal("unavailable-keydown-not-confirmed", unsuccessful.Status);
        Assert.Null(unsuccessful.MidpointMillisecondsCandidate);
        Assert.False(failedDown.Snapshot()[0].Inserted);
        Assert.True(failedDown.Snapshot()[1].Inserted);

        var failedUp = DeterministicTimeline([0, 1, 100, 101]);
        failedUp.Send("d", true, () => { });
        Assert.Throws<InvalidOperationException>(() =>
            failedUp.Send("d", false, () => throw new InvalidOperationException("up failed")));
        Assert.Equal("unavailable-keyup-not-confirmed",
            MoveKeyCommand.SummarizeKeyHold("d", failedUp.Snapshot()).Status);
        Assert.Null(MoveKeyCommand.SummarizeKeyHold("d", failedUp.Snapshot())
            .MaximumMillisecondsCandidate);
    }

    [Fact]
    public void MissingReplayedOrOverlappingEventsDoNotInventASingleCleanRelease()
    {
        var clean = DeterministicTimeline([0, 1, 100, 101]);
        clean.Send("e", true, () => { });
        clean.Send("e", false, () => { });
        var events = clean.Snapshot();
        Assert.Equal("unavailable-keyup-not-confirmed",
            MoveKeyCommand.SummarizeKeyHold("e", events.Take(1).ToArray()).Status);
        Assert.Equal("unavailable-keydown-not-confirmed",
            MoveKeyCommand.SummarizeKeyHold("e", events.Skip(1).ToArray()).Status);
        Assert.Equal("unavailable-keyup-not-confirmed",
            MoveKeyCommand.SummarizeKeyHold("e", [events[0], events[1], events[1]]).Status);
        var overlapping = events[1] with
        {
            MonotonicStartTick = events[0].MonotonicEndTick - 1
        };
        Assert.Equal("unavailable-send-order",
            MoveKeyCommand.SummarizeKeyHold("e", [events[0], overlapping]).Status);
    }

    [Fact]
    public void DefaultOneSecondHoldSupportsEachMovementKey()
    {
        foreach (var key in new[] { "w", "a", "s", "d", "q", "e" })
        {
            var options = MoveKeyCommand.Parse(["--pid", "12345", "--key", key]);
            Assert.Equal(new[] { key }, options.Keys);
            Assert.Equal(1000, options.HoldMilliseconds);
            Assert.False(options.Execute);
            Assert.True(options.Focus);
            Assert.False(options.MeasureXyz);
            Assert.Equal(0, options.XyzSettleMilliseconds);
        }
    }

    [Fact]
    public void CombinedForwardAndTurnKeyUsesSameBoundedExecutorValidation()
    {
        var options = MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w,e", "--hold-ms", "1250",
             "--focus", "--execute", "--json",
             "--expect-start-ticks", "639299470183328173",
             "--expect-sha256", new string('a', 64)]);
        Assert.Equal(new[] { "w", "e" }, options.Keys);
        Assert.Equal(1250, options.HoldMilliseconds);
        Assert.True(options.Focus);
        Assert.True(options.Execute);
        Assert.True(options.Json);
        Assert.False(options.MeasureXyz);
        Assert.Equal(639299470183328173, options.ExpectedStartTicks);
        Assert.Equal(new string('A', 64), options.ExpectedSha256);
    }

    [Fact]
    public void FocusIsDefaultAndNoFocusOptsOut()
    {
        var defaultOptions = MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--execute"]);
        Assert.True(defaultOptions.Focus);
        var noFocus = MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--no-focus", "--execute"]);
        Assert.False(noFocus.Focus);
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--focus", "--no-focus"]));
    }

    [Fact]
    public void MeasureXyzIsExplicitAndDoesNotEnableInput()
    {
        var options = MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--measure-xyz"]);
        Assert.True(options.MeasureXyz);
        Assert.False(options.Execute);
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--measure-xyz", "--measure-xyz"]));
    }

    [Theory]
    [InlineData("0", 0)]
    [InlineData("250", 250)]
    [InlineData("2000", 2000)]
    public void XyzSettleIsOptionalBoundedAndNeverEnablesInput(string raw, int expected)
    {
        var options = MoveKeyCommand.Parse([
            "--pid", "12345", "--key", "w", "--measure-xyz", "--xyz-settle-ms", raw]);
        Assert.True(options.MeasureXyz);
        Assert.False(options.Execute);
        Assert.Equal(expected, options.XyzSettleMilliseconds);
    }

    [Theory]
    [InlineData("-1")]
    [InlineData("2001")]
    [InlineData("NaN")]
    [InlineData("100.5")]
    [InlineData("2147483648")]
    public void InvalidXyzSettleIsRejected(string raw)
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse([
            "--pid", "12345", "--key", "w", "--measure-xyz", "--xyz-settle-ms", raw]));
    }

    [Fact]
    public void SettleRequiresExplicitXyzMeasurement()
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse([
            "--pid", "12345", "--key", "w", "--xyz-settle-ms", "250"]));
    }

    [Fact]
    public void SettledCaptureRequiresCompletedActionAndConfirmedRelease()
    {
        Assert.True(MoveKeyCommand.MayTakeSettledXyz(Execution(delivered: true, released: true)));
        Assert.False(MoveKeyCommand.MayTakeSettledXyz(Execution(delivered: false, released: true)));
        Assert.False(MoveKeyCommand.MayTakeSettledXyz(Execution(delivered: true, released: false)));
        Assert.False(MoveKeyCommand.MayTakeSettledXyz(
            Execution(delivered: false, released: true, cancelled: true)));
        Assert.False(MoveKeyCommand.MayTakeSettledXyz(
            Execution(delivered: false, released: true, targetLost: true)));
    }

    [Fact]
    public void CancelledHoldPreservesConfirmedWindowsKeyDownRatherThanFalseNegative()
    {
        // KeyDown was successfully inserted, then cancellation caused the
        // bounded action to abort and release. DeliverySucceeded is false.
        var result = Execution(delivered: false, released: true, cancelled: true);
        var evidence = MoveKeyCommand.SummarizeInsertion(result, 1, 1, 1);
        Assert.True(evidence.WindowsInputAttempted);
        Assert.True(evidence.WindowsInputInserted);
        Assert.True(evidence.AllRequestedKeyDownsInserted);
        Assert.False(evidence.BoundedActionCompleted);
        Assert.False(evidence.InsertionUncertain);
    }

    [Fact]
    public void TargetLossAfterKeyDownIsNotReportedAsNoInput()
    {
        var result = Execution(delivered: false, released: true, targetLost: true);
        var evidence = MoveKeyCommand.SummarizeInsertion(result, 2, 1, 1);
        Assert.True(evidence.WindowsInputInserted);
        Assert.False(evidence.AllRequestedKeyDownsInserted);
        Assert.False(evidence.BoundedActionCompleted);
        Assert.Equal(1, evidence.KeyDownInsertions);
    }

    [Fact]
    public void FailedWindowsSendIsAttemptedButNotAssertedInserted()
    {
        var result = Execution(delivered: false, released: true);
        var evidence = MoveKeyCommand.SummarizeInsertion(result, 1, 1, 0);
        Assert.True(evidence.WindowsInputAttempted);
        Assert.False(evidence.WindowsInputInserted);
        Assert.True(evidence.InsertionUncertain);
        Assert.False(evidence.BoundedActionCompleted);
        var noSend = MoveKeyCommand.SummarizeInsertion(result, 1, 0, 0);
        Assert.False(noSend.WindowsInputAttempted);
        Assert.False(noSend.InsertionUncertain);
    }

    [Fact]
    public void CompletedHoldRequiresReleaseSuccessAndDoesNotProveGameResponse()
    {
        var delivered = Execution(delivered: true, released: true);
        var evidence = MoveKeyCommand.SummarizeInsertion(delivered, 1, 1, 1);
        Assert.True(evidence.BoundedActionCompleted);
        Assert.True(evidence.WindowsInputInserted);
        var releaseFailed = MoveKeyCommand.SummarizeInsertion(
            Execution(delivered: true, released: false), 1, 1, 1);
        Assert.True(releaseFailed.WindowsInputInserted);
        Assert.False(releaseFailed.BoundedActionCompleted);
    }

    [Fact]
    public void ActorPoseMeasurementIsExplicitPreviewOnlyAndRejectsDuplicates()
    {
        var options = MoveKeyCommand.Parse([
            "--pid", "12345", "--key", "a", "--measure-actor-pose"]);
        Assert.True(options.MeasureActorPose);
        Assert.False(options.MeasureXyz);
        Assert.False(options.Execute);
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse([
            "--pid", "12345", "--key", "d",
            "--measure-actor-pose", "--measure-actor-pose"]));
    }

    [Theory]
    [InlineData(179, -179, 2)]
    [InlineData(-179, 179, -2)]
    [InlineData(10, 10, 0)]
    [InlineData(40, 130, 90)]
    public void ActorPoseAngleDeltaWrapsAcrossSignedBoundary(double before, double after, double expected)
    {
        Assert.Equal(expected, MoveKeyCommand.ShortestPlanarAngleDelta(before, after)!.Value, 6);
        Assert.Null(MoveKeyCommand.ShortestPlanarAngleDelta(null, after));
        Assert.Null(MoveKeyCommand.ShortestPlanarAngleDelta(before, double.NaN));
        Assert.Null(MoveKeyCommand.ShortestPlanarAngleDelta(0, 180));
    }

    private static CurrentBuildActorPoseCandidate Pose(
        DateTimeOffset start, double angle, ulong playerKey = 42, ulong actorComponent = 2000)
    {
        var identity = new NativeProcessIdentity(44888, 639299470183328173,
            @"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
            new string('A', 64), 0x140000000, 63164416);
        static CurrentBuildMatrixDescriptorCandidate Matrix(double degrees, int offset) =>
            new(offset, new uint[] { (uint)(degrees + 400), 0, 0, 0, 0, 0, 0, 0, 0 },
                new float[9], "structural-y-planar-matrix-candidate", 0, 1, 0,
                degrees * Math.PI / 180.0, degrees);
        return new CurrentBuildActorPoseCandidate(
            identity, start, start.AddMilliseconds(5), playerKey,
            1000, actorComponent, 3000, 0,
            Matrix(angle, 0x398), Matrix(0, 0x3EC), null,
            "alternate-reference-branch-not-followed", null);
    }

    [Fact]
    public void ActorPoseCandidateComparisonDetectsChangeWithoutClaimingQualifiedHeading()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var result = MoveKeyCommand.ComparePose(
            Pose(t, 179), Pose(t.AddSeconds(1), -179));
        Assert.Equal("candidate-native-actor-pose-feedback", result.Status);
        Assert.Equal(2, result.ActorPlanarDeltaDegreesCandidate!.Value, 6);
        Assert.Equal(0, result.ModelPlanarDeltaDegreesCandidate!.Value, 6);
        Assert.True(result.ActorMatrixBitsChanged);
        Assert.False(result.ActorHeadingQualified);
        Assert.False(result.GameResponseVerified);
        Assert.Equal(.995, result.CaptureGapSeconds!.Value, 6);
    }

    [Fact]
    public void ActorPoseComparisonRejectsOwnerAndTimeChanges()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var before = Pose(t, 10);
        var after = Pose(t.AddSeconds(1), 30);
        Assert.Equal("unavailable-owner-changed",
            MoveKeyCommand.ComparePose(before, after with { ActorComponent = 99 }).Status);
        Assert.Equal("unavailable-owner-changed",
            MoveKeyCommand.ComparePose(before, after with { PlayerKey = 99 }).Status);
        Assert.Equal("unavailable-capture-time",
            MoveKeyCommand.ComparePose(before, after with { StartedAtUtc = t }).Status);
        Assert.Equal("unavailable-capture-time",
            MoveKeyCommand.ComparePose(before, after with
            {
                StartedAtUtc = t.AddSeconds(31),
                CompletedAtUtc = t.AddSeconds(31.005)
            }).Status);
    }

    [Theory]
    [InlineData("a", 10.0, 28.0, 36.0)]
    [InlineData("d", 10.0, -8.0, -36.0)]
    public void TurnRateUsesActualHoldAndSignedCandidateAngle(
        string key, double beforeAngle, double afterAngle, double expectedRate)
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var pose = MoveKeyCommand.ComparePose(
            Pose(t, beforeAngle), Pose(t.AddMilliseconds(500), afterAngle));
        var evidence = MoveKeyCommand.SummarizeInsertion(
            Execution(delivered: true, released: true), 1, 1, 1);
        var result = MoveKeyCommand.SummarizeTurnRate(key, evidence, pose, 500);
        Assert.Equal("candidate-native-actor-matrix-turn-rate", result.Status);
        var delayed = pose with { CaptureGapSeconds = 3.5 };
        Assert.Equal("unavailable-timing",
            MoveKeyCommand.SummarizeTurnRate(key, evidence, delayed, 500).Status);
        Assert.Equal(expectedRate, MoveKeyCommand.SummarizeTurnRate(
            key, evidence, delayed, 500, 3000).SignedDegreesPerSecondCandidate!.Value, 5);
        Assert.Equal(expectedRate, result.SignedDegreesPerSecondCandidate!.Value, 5);
        Assert.Equal(Math.Abs(expectedRate), result.MagnitudeDegreesPerSecondCandidate!.Value, 5);
        Assert.False(result.ActorHeadingQualified);
        Assert.False(result.NavigationEligible);
    }

    [Fact]
    public void TurnRateRefusesUnqualifiedOrIncorrectInputConditions()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var validPose = MoveKeyCommand.ComparePose(Pose(t, 10),
            Pose(t.AddMilliseconds(500), 28));
        var success = MoveKeyCommand.SummarizeInsertion(
            Execution(delivered: true, released: true), 1, 1, 1);
        var failedRelease = MoveKeyCommand.SummarizeInsertion(
            Execution(delivered: true, released: false), 1, 1, 1);
        Assert.Equal("unavailable-input-or-release",
            MoveKeyCommand.SummarizeTurnRate("a", failedRelease, validPose, 500).Status);
        Assert.Equal("not-turn-key",
            MoveKeyCommand.SummarizeTurnRate("q", success, validPose, 500).Status);
        Assert.Equal("unavailable-pose",
            MoveKeyCommand.SummarizeTurnRate("d", success, null, 500).Status);
        Assert.Equal("unavailable-pose",
            MoveKeyCommand.SummarizeTurnRate("a", success,
                MoveKeyCommand.ComparePose(Pose(t, 10),
                    Pose(t.AddMilliseconds(500), 28) with { ActorComponent = 123 }), 500).Status);
        Assert.Equal("unavailable-timing",
            MoveKeyCommand.SummarizeTurnRate("a", success, validPose, 0).Status);
        Assert.Equal("unavailable-timing",
            MoveKeyCommand.SummarizeTurnRate("a", success, validPose, 5000).Status);
        Assert.Equal("unavailable-timing",
            MoveKeyCommand.SummarizeTurnRate("a", success, validPose with
            {
                CaptureGapSeconds = 8
            }, 500).Status);
        Assert.Equal("unavailable-angle-change",
            MoveKeyCommand.SummarizeTurnRate("a", success,
                MoveKeyCommand.ComparePose(Pose(t, 10), Pose(t.AddMilliseconds(500), 10)), 500).Status);
        Assert.Equal("unavailable-angle-change",
            MoveKeyCommand.SummarizeTurnRate("a", success,
                MoveKeyCommand.ComparePose(Pose(t, 10), Pose(t.AddMilliseconds(500), 190)), 500).Status);
    }

    private static ControlExecutionResult Execution(bool delivered, bool released,
        bool cancelled = false, bool targetLost = false) => new(
        delivered, released, cancelled, targetLost, !released, !released,
        TimeSpan.FromMilliseconds(120), ResponseVerified: false, Error: null);

    [Fact]
    public void NativeXyzComparisonReportsCandidatePlanarDisplacement()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var before = new MoveKeyCommand.XyzSample(t, t.AddMilliseconds(10), "42", 100, 20, 200);
        var after = new MoveKeyCommand.XyzSample(
            t.AddMilliseconds(1010), t.AddMilliseconds(1020), "42", 103, 21, 204);
        var feedback = MoveKeyCommand.CompareXyz(before, after);
        Assert.Equal("candidate-native-xyz-feedback", feedback.Status);
        Assert.True(feedback.MovementCandidate);
        Assert.Equal(5, feedback.PlanarDisplacementCandidate);
        Assert.Equal(1, feedback.DeltaXYZ!.Y);
        Assert.Equal(1, feedback.CaptureGapSeconds);
        Assert.False(feedback.GameResponseVerified);
    }

    [Fact]
    public void NativeXyzComparisonDoesNotInventMovementForUnchangedCoordinates()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var before = new MoveKeyCommand.XyzSample(t, t.AddMilliseconds(10), "42", 100, 20, 200);
        var after = new MoveKeyCommand.XyzSample(
            t.AddMilliseconds(1010), t.AddMilliseconds(1020), "42", 100, 20, 200);
        var feedback = MoveKeyCommand.CompareXyz(before, after);
        Assert.Equal("candidate-native-xyz-feedback", feedback.Status);
        Assert.False(feedback.MovementCandidate);
        Assert.Equal(0, feedback.PlanarDisplacementCandidate);
    }

    [Fact]
    public void NativeXyzComparisonRejectsOwnerChangesAndStaleReadings()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var before = new MoveKeyCommand.XyzSample(t, t.AddMilliseconds(10), "42", 100, 20, 200);
        var changedOwner = new MoveKeyCommand.XyzSample(
            t.AddSeconds(1), t.AddSeconds(1.1), "99", 103, 20, 204);
        var stale = new MoveKeyCommand.XyzSample(
            t.AddSeconds(31), t.AddSeconds(31.1), "42", 103, 20, 204);
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(before, changedOwner).Status);
        Assert.False(MoveKeyCommand.CompareXyz(before, changedOwner).MovementCandidate);
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(before, stale).Status);
    }

    [Fact]
    public void NativeXyzComparisonRejectsReversedOrOverlongAcquisitionIntervals()
    {
        var t = DateTimeOffset.Parse("2026-11-11T12:00:00Z");
        var baseline = new MoveKeyCommand.XyzSample(t, t.AddMilliseconds(10), "42", 100, 20, 200);
        var normal = new MoveKeyCommand.XyzSample(
            t.AddSeconds(1), t.AddSeconds(1.01), "42", 102, 20, 200);
        var reversedBefore = baseline with { CompletedAtUtc = t.AddMilliseconds(-1) };
        var reversedAfter = normal with { CompletedAtUtc = t.AddMilliseconds(900) };
        var longBefore = baseline with { CompletedAtUtc = t.AddSeconds(6) };
        var longAfter = normal with { CompletedAtUtc = t.AddSeconds(7) };
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(reversedBefore, normal).Status);
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(baseline, reversedAfter).Status);
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(longBefore, normal).Status);
        Assert.Equal("unavailable", MoveKeyCommand.CompareXyz(baseline, longAfter).Status);
    }

    [Theory]
    [InlineData("w,s")]
    [InlineData("a,d")]
    [InlineData("q,e")]
    [InlineData("w,w")]
    [InlineData("W")]
    [InlineData("z")]
    [InlineData("")]
    public void InvalidOrConflictingKeysAreRejectedWithoutInput(string keys)
    {
        Assert.ThrowsAny<Exception>(() =>
            MoveKeyCommand.Parse(["--pid", "12345", "--key", keys, "--execute"]));
    }

    [Theory]
    [InlineData("19")]
    [InlineData("3001")]
    [InlineData("-100")]
    [InlineData("invalid")]
    public void InvalidHoldDurationsAreRejected(string hold)
    {
        Assert.ThrowsAny<Exception>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--hold-ms", hold]));
    }

    [Fact]
    public void RequiresExactPidAndRejectsDuplicateOrUnknownOptions()
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(["--key", "w"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(["--pid", "0", "--key", "w"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--key", "s"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--sendinput-unrestricted"]));
    }
}
