using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Tests;

public sealed class CurrentBuildVitalsSampleCommandTests
{
    [Fact]
    public async Task PublishesUnavailableFieldsOnlyAfterProcessRevalidation()
    {
        var path = NewPath();
        try
        {
            var session = new FakeSession();
            var output = new StringWriter();
            var result = await CurrentBuildVitalsSampleCommand.CaptureAndPublishAsync(
                session, path, output, source =>
                {
                    Assert.False(session.Revalidated);
                    return Observation(source);
                }, default);
            Assert.Equal(0, result);
            Assert.True(session.Revalidated);
            using var report = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            Assert.Equal("native-process-memory", report.RootElement.GetProperty("source").GetString());
            var energy = report.RootElement.GetProperty("observation").GetProperty("energy");
            Assert.Equal("unavailable", energy.GetProperty("status").GetString());
            Assert.Equal("not-energy-kind-four", energy.GetProperty("unavailableReason").GetString());
            var mana = report.RootElement.GetProperty("observation").GetProperty("mana");
            Assert.Equal("calculated-candidate", mana.GetProperty("status").GetString());
            Assert.Equal("native-current-vitals-candidate-sample/2",
                report.RootElement.GetProperty("contractVersion").GetString());
            Assert.Contains("native-current-vitals-candidate-summary/2", output.ToString());
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task InvalidatedProcessPublishesNeitherReportNorSummary()
    {
        var path = NewPath();
        var output = new StringWriter();
        var session = new FakeSession { Invalidation = "process-epoch-changed" };
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildVitalsSampleCommand.CaptureAndPublishAsync(
                session, path, output, Observation, default));
        Assert.True(session.Revalidated);
        Assert.False(File.Exists(path));
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public async Task ExistingEvidenceIsRejectedBeforeReading()
    {
        var path = NewPath();
        await File.WriteAllTextAsync(path, "original-evidence");
        try
        {
            await Assert.ThrowsAsync<IOException>(() =>
                CurrentBuildVitalsSampleCommand.CaptureAndPublishAsync(
                    new FakeSession(), path, new StringWriter(),
                    _ => throw new InvalidOperationException("must not read"), default));
            Assert.Equal("original-evidence", await File.ReadAllTextAsync(path));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public async Task ReaderFailurePublishesNothing()
    {
        var path = NewPath();
        var output = new StringWriter();
        var session = new FakeSession();
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildVitalsSampleCommand.CaptureAndPublishAsync(session, path, output,
                _ => throw new InvalidDataException("owner changed"), default));
        Assert.False(session.Revalidated);
        Assert.False(File.Exists(path));
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public async Task InvalidArgumentsFailBeforeOpeningAProcess()
    {
        await Assert.ThrowsAsync<ArgumentException>(() => CurrentBuildVitalsSampleCommand.RunAsync(
            new Dictionary<string, string> { ["--pid"] = "123", ["--start-ticks"] = "0", ["--output"] = NewPath() },
            new StringWriter(), default));
    }

    [Fact]
    public async Task BurstCapturesSeveralVitalsWithOneSessionAndPreservesSingleShotProjection()
    {
        var path = NewPath();
        var session = new FakeSession();
        using var output = new StringWriter();
        var count = 0;
        try
        {
            Assert.Equal(0, await CurrentBuildVitalsSampleCommand.CaptureBurstAndPublishAsync(
                session, path, output, source =>
                {
                    var value = 700 + 10 * count++;
                    return Observation(source) with { Health = new("calculated-candidate", null, value, 1000) };
                }, 3, 0, default));
            Assert.Equal(3, count);
            using var json = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            var root = json.RootElement;
            Assert.Equal("native-current-vitals-candidate-burst/1", root.GetProperty("contractVersion").GetString());
            Assert.Equal(3, root.GetProperty("completedSamples").GetInt32());
            Assert.Equal(3, root.GetProperty("observations").GetArrayLength());
            Assert.Equal(700, root.GetProperty("observations")[0].GetProperty("health").GetProperty("current").GetInt64());
            Assert.Equal(720, root.GetProperty("observation").GetProperty("health").GetProperty("current").GetInt64());
            Assert.Contains("native-current-vitals-candidate-summary/2", output.ToString());
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public async Task BurstRejectsPlayerChangeWithoutPublishing()
    {
        var path = NewPath();
        var session = new FakeSession();
        using var output = new StringWriter();
        var count = 0;
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildVitalsSampleCommand.CaptureBurstAndPublishAsync(
                session, path, output,
                source => Observation(source) with { UnitKey = (ulong)++count },
                2, 0, default));
        Assert.Equal(2, count);
        Assert.False(File.Exists(path));
        Assert.DoesNotContain("summary", output.ToString());
    }

    [Fact]
    public async Task OneShotRejectsObservationFromAnotherProcess()
    {
        var path = NewPath();
        var session = new FakeSession();
        using var output = new StringWriter();
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            CurrentBuildVitalsSampleCommand.CaptureAndPublishAsync(
                session, path, output, source => Observation(source) with
                {
                    Identity = source.Identity with { ProcessId = source.Identity.ProcessId + 1 }
                }, default));
        Assert.False(File.Exists(path));
        Assert.Equal("", output.ToString());
    }

    [Theory]
    [InlineData("--samples", "0")]
    [InlineData("--samples", "31")]
    [InlineData("--interval-ms", "2001")]
    public async Task InvalidBurstScheduleFailsBeforeOpeningProcess(string option, string value)
    {
        await Assert.ThrowsAsync<ArgumentException>(() => CurrentBuildVitalsSampleCommand.RunAsync(
            new Dictionary<string, string> {
                ["--pid"] = "123", ["--start-ticks"] = "456", ["--output"] = NewPath(), [option] = value },
            new StringWriter(), default));
    }

    private static string NewPath() => Path.Combine(Path.GetTempPath(), $"rr2-vitals-{Guid.NewGuid():N}.json");
    private static CurrentBuildVitalsObservation Observation(IReadOnlyNativeMemorySession session) =>
        new(session.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 123,
            new("calculated-candidate", null, 700, 1000),
            new("unavailable", "not-energy-kind-four"))
        {
            Mana = new("calculated-candidate", null, 3980, 3980)
        };

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; } = new(123, 456,
            @"C:\RIFT\rift_x64.exe", CurrentBuildPositionSampleCommand.GameSha256, 0x140000000, 0x4000000);
        public string? Invalidation { get; init; }
        public bool Revalidated { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException("No memory reads in command tests.");
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Revalidated = true;
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
