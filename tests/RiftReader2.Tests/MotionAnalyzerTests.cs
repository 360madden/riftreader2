global using Xunit;

using System.IO;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Tests;

public sealed class MotionAnalyzerTests
{
    private readonly MotionAnalyzer analyzer = new();

    [Fact]
    public async Task AnalyzeAsync_ComputesContinuousDerivativesAndSummary()
    {
        var samples = ToAsync(
            Sample(10, 2.0, x: 0.0, z: 0.0, yaw: 0.0),
            Sample(11, 2.2, x: 3.0, z: 4.0, yaw: 0.1),
            Sample(12, 2.4, x: 3.0, z: 6.0, yaw: 0.3));

        var summary = await analyzer.AnalyzeAsync(samples, new AnalysisOptions());

        Assert.Equal("capture-a", summary.SessionId);
        Assert.Equal(3, summary.SampleCount);
        Assert.Equal(10, summary.FirstSequence);
        Assert.Equal(12, summary.LastSequence);
        Assert.Equal(2.0, summary.StartTimestampSeconds);
        Assert.Equal(2.4, summary.EndTimestampSeconds);
        Assert.Equal(0.4, summary.DurationSeconds, precision: 12);
        Assert.Equal(2, summary.DerivedIntervalCount);
        Assert.Equal(0, summary.SkippedDerivativeIntervalCount);
        Assert.Equal(25.0, summary.MaxHorizontalDerivedSpeed!.Value, precision: 12);
        Assert.Equal(1.0, summary.MaxAbsoluteDerivedYawRate!.Value, precision: 12);
    }

    [Fact]
    public async Task AnalyzeAsync_DisclosesAndSkipsSequenceAndTimingGaps()
    {
        var samples = ToAsync(
            Sample(1, 0.0),
            Sample(4, 0.1, x: 100.0),
            Sample(5, 1.0, x: 200.0));

        var summary = await analyzer.AnalyzeAsync(
            samples,
            new AnalysisOptions(MaxGapSeconds: 0.25));

        Assert.Equal(2, summary.MissingSequenceCount);
        Assert.Equal(1, summary.SequenceGapCount);
        Assert.Equal(1, summary.TimingGapCount);
        Assert.Equal(0, summary.DerivedIntervalCount);
        Assert.Equal(2, summary.SkippedDerivativeIntervalCount);
        Assert.Null(summary.MaxHorizontalDerivedSpeed);
        Assert.Null(summary.MaxAbsoluteDerivedYawRate);
    }

    [Fact]
    public async Task AnalyzeAsync_UsesShortestYawPathAcrossTurnBoundary()
    {
        var samples = ToAsync(
            Sample(1, 0.0, yaw: Degrees(179.0)),
            Sample(2, 0.1, yaw: Degrees(-179.0)));

        var summary = await analyzer.AnalyzeAsync(samples, new AnalysisOptions());

        Assert.Equal(Degrees(20.0), summary.MaxAbsoluteDerivedYawRate!.Value, precision: 12);
    }

    [Theory]
    [InlineData(0.0, 10)]
    [InlineData(double.NaN, 10)]
    [InlineData(0.25, 1)]
    public async Task AnalyzeAsync_RejectsInvalidOptions(double maxGapSeconds, int maxSamples)
    {
        var options = new AnalysisOptions(maxGapSeconds, maxSamples);

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => analyzer.AnalyzeAsync(ToAsync(Sample(1, 0.0), Sample(2, 0.1)), options));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsMixedSessions()
    {
        var samples = ToAsync(
            Sample(1, 0.0),
            Sample(2, 0.1) with { SessionId = "capture-b" });

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsBlankSession()
    {
        var samples = ToAsync(
            Sample(1, 0.0) with { SessionId = "  " },
            Sample(2, 0.1) with { SessionId = "  " });

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsNonfiniteSampleData()
    {
        var samples = ToAsync(
            Sample(1, 0.0),
            Sample(2, 0.1) with { X = double.PositiveInfinity });

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Theory]
    [InlineData(-1, 0.0)]
    [InlineData(1, -0.1)]
    public async Task AnalyzeAsync_RejectsNegativeSequenceOrTimestamp(
        long sequence,
        double timestamp)
    {
        var samples = ToAsync(
            Sample(sequence, timestamp),
            Sample(2, 0.1));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Theory]
    [InlineData(1, 1, 0.0, 0.1)]
    [InlineData(2, 1, 0.0, 0.1)]
    [InlineData(1, 2, 0.1, 0.1)]
    [InlineData(1, 2, 0.2, 0.1)]
    public async Task AnalyzeAsync_RejectsDuplicateOrBackwardsOrder(
        long firstSequence,
        long secondSequence,
        double firstTimestamp,
        double secondTimestamp)
    {
        var samples = ToAsync(
            Sample(firstSequence, firstTimestamp),
            Sample(secondSequence, secondTimestamp));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsFewerThanTwoSamples()
    {
        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(ToAsync(Sample(1, 0.0)), new AnalysisOptions()));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(ToAsync(), new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_EnforcesMaximumSampleCount()
    {
        var samples = ToAsync(Sample(1, 0.0), Sample(2, 0.1), Sample(3, 0.2));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions(MaxSamples: 2)));
    }

    [Fact]
    public async Task AnalyzeAsync_ObservesCancellationWhileStreaming()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => analyzer.AnalyzeAsync(
                ToAsync(Sample(1, 0.0), Sample(2, 0.1)),
                new AnalysisOptions(),
                cancellation.Token));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsOverflowingDerivedSpeed()
    {
        var samples = ToAsync(
            Sample(1, 0.0, x: -double.MaxValue),
            Sample(2, 0.1, x: double.MaxValue));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsSpeedOverflowFromFiniteDeltaAndSubnormalInterval()
    {
        var samples = ToAsync(
            Sample(1, 0.0),
            Sample(2, double.Epsilon, x: 1.0));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_RejectsYawRateOverflowFromSubnormalInterval()
    {
        var samples = ToAsync(
            Sample(1, 0.0),
            Sample(2, double.Epsilon, yaw: 1.0));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => analyzer.AnalyzeAsync(samples, new AnalysisOptions()));
    }

    [Fact]
    public async Task AnalyzeAsync_ReducesExtremeFiniteYawBeforeTakingDelta()
    {
        var samples = ToAsync(
            Sample(1, 0.0, yaw: double.MaxValue),
            Sample(2, 0.1, yaw: -double.MaxValue));

        var summary = await analyzer.AnalyzeAsync(samples, new AnalysisOptions());

        var rate = summary.MaxAbsoluteDerivedYawRate.GetValueOrDefault(double.NaN);
        Assert.True(double.IsFinite(rate));
        Assert.InRange(rate, 0.0, Math.PI / 0.1);
    }

    private static MotionSample Sample(
        long sequence,
        double timestamp,
        double x = 0.0,
        double z = 0.0,
        double yaw = 0.0) =>
        new("capture-a", sequence, timestamp, x, 0.0, z, yaw);

    private static double Degrees(double value) => value * Math.PI / 180.0;

    private static async IAsyncEnumerable<MotionSample> ToAsync(
        params MotionSample[] samples)
    {
        foreach (var sample in samples)
        {
            await Task.Yield();
            yield return sample;
        }
    }
}
