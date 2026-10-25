using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class PositionPanelControllerTests
{
    private const string BuildSha = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD";
    private static readonly PositionCandidateProfile Profile = new(BuildSha, 0x32E0200, 0x320, 0x324, 0x328);

    [Fact]
    public async Task StartReadStopPublishesFreshValueThenClearsIt()
    {
        var identity = Identity(42, 100);
        using var controller = new PositionPanelController(_ => Task.FromResult(Report(identity, 1, 2, 3)));

        controller.Start();
        Assert.Equal("waiting", controller.State.Status);
        await controller.ReadAsync();

        Assert.Equal("live", controller.State.Status);
        Assert.Equal(identity, controller.State.Identity);
        Assert.Equal(1f, controller.State.Observation!.X);
        controller.Stop();
        Assert.Equal(new PositionPanelState("stopped", null, null, null, false, false), controller.State);
    }

    [Fact]
    public async Task ConcurrentReadIsIgnored()
    {
        var release = new TaskCompletionSource<NativePositionSamplesReport>(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls = 0;
        using var controller = new PositionPanelController(_ =>
        {
            Interlocked.Increment(ref calls);
            return release.Task;
        });
        controller.Start();

        var first = controller.ReadAsync();
        await controller.ReadAsync();
        Assert.Equal(1, calls);
        release.SetResult(Report(Identity(42, 100), 1, 2, 3));
        await first;
        Assert.Equal("live", controller.State.Status);
    }

    [Fact]
    public async Task StopPreventsLateIgnoringCancellationResultFromReappearing()
    {
        var release = new TaskCompletionSource<NativePositionSamplesReport>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var controller = new PositionPanelController(_ => release.Task);
        controller.Start();
        var pending = controller.ReadAsync();

        controller.Stop();
        release.SetResult(Report(Identity(42, 100), 1, 2, 3));
        await pending;

        Assert.Equal("stopped", controller.State.Status);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task RestartWaitsForOldPhysicalReadBeforeReadingNewEpoch()
    {
        var oldRelease = new TaskCompletionSource<NativePositionSamplesReport>(TaskCreationOptions.RunContinuationsAsynchronously);
        var call = 0;
        var active = 0;
        var peak = 0;
        using var controller = new PositionPanelController(async _ =>
        {
            var current = Interlocked.Increment(ref active);
            InterlockedExtensions.Max(ref peak, current);
            try
            {
                return Interlocked.Increment(ref call) == 1
                    ? await oldRelease.Task
                    : Report(Identity(84, 200), 4, 5, 6);
            }
            finally
            {
                Interlocked.Decrement(ref active);
            }
        });
        controller.Start();
        var oldRead = controller.ReadAsync();

        controller.Stop();
        controller.Start();
        await controller.ReadAsync();
        Assert.Equal(1, call);
        Assert.True(controller.State.IsReading);

        oldRelease.SetResult(Report(Identity(42, 100), 1, 2, 3));
        await oldRead;
        Assert.Equal("waiting", controller.State.Status);
        Assert.False(controller.State.IsReading);

        await controller.ReadAsync();
        Assert.Equal(2, call);
        Assert.Equal(1, peak);
        Assert.Equal(84, controller.State.Identity!.ProcessId);
        Assert.Equal(4f, controller.State.Observation!.X);
    }

    [Fact]
    public async Task ReadWhileStoppedTakesOneFreshSampleWithoutStartingMonitoring()
    {
        var time = new ManualTimeProvider();
        using var controller = new PositionPanelController(
            _ => Task.FromResult(Report(Identity(42, 100), 7, 8, 9)), time,
            TimeSpan.FromSeconds(3));

        await controller.ReadAsync();

        Assert.Equal("live", controller.State.Status);
        Assert.False(controller.State.IsMonitoring);
        Assert.False(controller.State.IsReading);
        Assert.Equal(7f, controller.State.Observation!.X);

        time.Advance(TimeSpan.FromSeconds(3.1));
        controller.RefreshFreshness();
        Assert.Equal("stale", controller.State.Status);
        Assert.False(controller.State.IsMonitoring);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task SlowCompletionIsNeverLabeledLive()
    {
        var time = new ManualTimeProvider();
        using var controller = new PositionPanelController(_ =>
        {
            time.Advance(TimeSpan.FromSeconds(4));
            return Task.FromResult(Report(Identity(42, 100), 1, 2, 3));
        }, time, TimeSpan.FromSeconds(3));
        controller.Start();

        await controller.ReadAsync();

        Assert.Equal("stale", controller.State.Status);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task FreshValueExpiresFromInvocationTime()
    {
        var time = new ManualTimeProvider();
        using var controller = new PositionPanelController(_ =>
        {
            time.Advance(TimeSpan.FromSeconds(1));
            return Task.FromResult(Report(Identity(42, 100), 1, 2, 3));
        }, time, TimeSpan.FromSeconds(3));
        controller.Start();
        await controller.ReadAsync();
        Assert.Equal("live", controller.State.Status);

        time.Advance(TimeSpan.FromSeconds(2.1));
        controller.RefreshFreshness();

        Assert.Equal("stale", controller.State.Status);
        Assert.Null(controller.State.Identity);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task BadReportsAndExpectedErrorsClearCoordinates()
    {
        var reports = new Queue<Func<Task<NativePositionSamplesReport>>>([
            () => Task.FromResult(Report(Identity(42, 100), float.NaN, 2, 3)),
            () => Task.FromResult(Report(Identity(42, 100), 1, 2, 3, status: "partial")),
            () => throw new InvalidOperationException("RIFT is not running.")
        ]);
        using var controller = new PositionPanelController(_ => reports.Dequeue()());
        controller.Start();

        await controller.ReadAsync();
        Assert.Equal("unavailable", controller.State.Status);
        Assert.Null(controller.State.Observation);
        await controller.ReadAsync();
        Assert.Equal("unavailable", controller.State.Status);
        Assert.Null(controller.State.Observation);
        await controller.ReadAsync();
        Assert.Equal("unavailable", controller.State.Status);
        Assert.Equal("RIFT is not running.", controller.State.Reason);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task WrongBuildAndExpiredMonitoringFailClosed()
    {
        var time = new ManualTimeProvider();
        var wrongIdentity = Identity(42, 100) with { ExecutableSha256 = new string('A', 64) };
        using var controller = new PositionPanelController(
            _ => Task.FromResult(Report(wrongIdentity, 1, 2, 3)), time,
            TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(5));
        controller.Start();
        await controller.ReadAsync();
        Assert.Equal("unavailable", controller.State.Status);
        Assert.Equal("profile-process-build-mismatch", controller.State.Reason);

        time.Advance(TimeSpan.FromSeconds(6));
        controller.RefreshFreshness();
        Assert.Equal("expired", controller.State.Status);
        Assert.False(controller.State.IsMonitoring);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task NonFatalUnexpectedExceptionDoesNotEscapeUiBoundary()
    {
        using var controller = new PositionPanelController(
            _ => throw new FormatException("malformed provider response"));
        controller.Start();

        await controller.ReadAsync();

        Assert.Equal("unavailable", controller.State.Status);
        Assert.Contains("malformed provider response", controller.State.Reason);
        Assert.Null(controller.State.Observation);
    }

    [Theory]
    [InlineData("profile")]
    [InlineData("samples")]
    [InlineData("identity")]
    [InlineData("observations")]
    [InlineData("observation")]
    public async Task NullReportStructuresFailClosedWithoutEscaping(string missing)
    {
        var report = Report(Identity(42, 100), 1, 2, 3);
        report = missing switch
        {
            "profile" => report with { Profile = null! },
            "samples" => report with { Samples = null! },
            "identity" => report with { Samples = report.Samples with { Identity = null! } },
            "observations" => report with { Samples = report.Samples with { Observations = null! } },
            "observation" => report with { Samples = report.Samples with { Observations = [null!] } },
            _ => throw new ArgumentOutOfRangeException(nameof(missing))
        };
        using var controller = new PositionPanelController(_ => Task.FromResult(report));
        controller.Start();

        await controller.ReadAsync();

        Assert.Equal("unavailable", controller.State.Status);
        Assert.Equal("read-returned-malformed-report", controller.State.Reason);
        Assert.Null(controller.State.Identity);
        Assert.Null(controller.State.Observation);
        Assert.False(controller.State.IsReading);
    }

    [Theory]
    [InlineData("x")]
    [InlineData("y")]
    [InlineData("z")]
    public async Task SubnormalCoordinateOnAnyAxisIsNotPublished(string axis)
    {
        var subnormal = float.Epsilon;
        var x = axis == "x" ? subnormal : 1f;
        var y = axis == "y" ? subnormal : 2f;
        var z = axis == "z" ? subnormal : 3f;
        using var controller = new PositionPanelController(
            _ => Task.FromResult(Report(Identity(42, 100), x, y, z)));
        controller.Start();

        await controller.ReadAsync();

        Assert.Equal("unavailable", controller.State.Status);
        Assert.Equal("position-values-not-ready", controller.State.Reason);
        Assert.Null(controller.State.Identity);
        Assert.Null(controller.State.Observation);
    }

    [Fact]
    public async Task MonitoringRecoversWhenSameNewProcessCoordinatesInitialize()
    {
        var identity = Identity(11712, 200);
        var reports = new Queue<NativePositionSamplesReport>([
            Report(identity, 9.918325e-39f, 1.63e-43f, 4.2245e-39f),
            Report(identity, 0f, -1.25f, 2.5f)
        ]);
        using var controller = new PositionPanelController(
            _ => Task.FromResult(reports.Dequeue()));
        controller.Start();

        await controller.ReadAsync();
        Assert.Equal("unavailable", controller.State.Status);
        Assert.Equal("position-values-not-ready", controller.State.Reason);
        Assert.Null(controller.State.Observation);

        await controller.ReadAsync();
        Assert.Equal("live", controller.State.Status);
        Assert.Equal(identity, controller.State.Identity);
        Assert.Equal(0f, controller.State.Observation!.X);
        Assert.Equal(-1.25f, controller.State.Observation.Y);
        Assert.Equal(2.5f, controller.State.Observation.Z);
    }

    private static NativeProcessIdentity Identity(int processId, long ticks) =>
        new(processId, ticks, @"C:\RIFT\rift_x64.exe", BuildSha, 0x140000000, 0x4000000);

    private static NativePositionSamplesReport Report(
        NativeProcessIdentity identity,
        float x,
        float y,
        float z,
        string status = "complete")
    {
        var observation = new PositionCandidateObservation(
            1, "2026-10-25T00:00:00Z", "2026-10-25T00:00:00Z", 0, 1,
            status == "complete" ? "complete" : "read-failed",
            status == "complete" ? null : "read-failed", x, y, z,
            "0x1234", new string('B', 64), null);
        var summary = new PositionCandidateSampleSummary(
            status, status == "complete" ? null : "sampling-failed", identity,
            "2026-10-25T00:00:00Z", "2026-10-25T00:00:00Z", 1, 1,
            [observation], new("insufficient-complete-samples", 0.1, status == "complete" ? 1 : 0,
                null, null, null));
        return new NativePositionSamplesReport(
            1, "native-position-samples/1", "candidate-only-not-motion-or-update-qualified",
            new string('C', 64), "test", Profile, summary, []);
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private long timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => Interlocked.Read(ref timestamp);

        internal void Advance(TimeSpan value) => Interlocked.Add(ref timestamp, value.Ticks);
    }

    private static class InterlockedExtensions
    {
        internal static void Max(ref int location, int value)
        {
            var current = Volatile.Read(ref location);
            while (current < value)
            {
                var prior = Interlocked.CompareExchange(ref location, value, current);
                if (prior == current)
                    return;
                current = prior;
            }
        }
    }
}
