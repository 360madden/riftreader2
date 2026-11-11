using RiftReader2.Live.Control;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class MoveKeyCommandTests
{
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
