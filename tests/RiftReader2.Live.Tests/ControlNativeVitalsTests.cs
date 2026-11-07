using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeVitalsTests
{
    private static readonly ControlIdentityRequest Expected = new(Environment.MachineName,
        123, 456, CurrentBuildPlayerLookup.GameSha256);
    private static readonly ControlAgentConfiguration Configuration = new(1, "192.168.1.1", 12345,
        new string('T', 32), Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, Path.GetTempPath());

    [Fact]
    public async Task ReturnsSameCandidateReportOnlyAfterRevalidationAndDisposesSession()
    {
        var session = new FakeSession();
        var before = DateTimeOffset.UtcNow;
        var result = await Capture(Expected, session);
        Assert.True(session.Revalidated);
        Assert.True(session.Disposed);
        Assert.Equal(1, result.NativeVitalsVersion);
        Assert.Equal("fresh-bytes", result.HashMode);
        Assert.InRange(result.ObservedAtUtc, before, DateTimeOffset.UtcNow);
        Assert.Equal(session.Identity, result.Report.Observation.Identity);
        var json = JsonSerializer.SerializeToElement(result, JsonFormat.Options);
        var report = json.GetProperty("report");
        Assert.Equal("native-current-vitals-candidate-sample/2", report.GetProperty("contractVersion").GetString());
        Assert.Equal("complete", report.GetProperty("status").GetString());
        Assert.Equal("native-process-memory", report.GetProperty("source").GetString());
        Assert.Equal("candidate-only; semantics/passive-freshness/restart-unverified",
            report.GetProperty("qualification").GetString());
        Assert.Equal(6, report.GetProperty("limitations").GetArrayLength());
    }

    [Fact]
    public async Task EveryInvocationOpensAndDisposesAnIndependentSession()
    {
        var sessions = new List<FakeSession>();
        for (var index = 0; index < 2; index++)
            await ControlNativeVitals.CaptureAsync(Configuration, Expected, _ =>
            {
                var session = new FakeSession();
                sessions.Add(session);
                return Task.FromResult<IReadOnlyNativeMemorySession>(session);
            }, Observation, default);
        Assert.Equal(2, sessions.Count);
        Assert.All(sessions, session => Assert.True(session.Disposed && session.Revalidated));
    }

    [Theory]
    [InlineData("machine")]
    [InlineData("hash")]
    [InlineData("invalid-pid")]
    public async Task InvalidExpectedMachineOrBuildRejectsBeforeOpening(string field)
    {
        var request = field switch
        {
            "machine" => Expected with { MachineName = "wrong-guest" },
            "hash" => Expected with { ExecutableSha256 = new string('A', 64) },
            _ => Expected with { ProcessId = 0 }
        };
        var opened = false;
        await Assert.ThrowsAnyAsync<Exception>(() => ControlNativeVitals.CaptureAsync(Configuration, request,
            _ => { opened = true; throw new Exception("must not open"); }, Observation, default));
        Assert.False(opened);
    }

    [Fact]
    public async Task ConfiguredBuildMismatchRejectsBeforeOpening()
    {
        var opened = false;
        await Assert.ThrowsAsync<InvalidOperationException>(() => ControlNativeVitals.CaptureAsync(
            Configuration with { ExecutableSha256 = new string('A', 64) }, Expected,
            _ => { opened = true; throw new Exception("must not open"); }, Observation, default));
        Assert.False(opened);
    }

    [Theory]
    [InlineData("pid")]
    [InlineData("epoch")]
    [InlineData("hash")]
    [InlineData("path")]
    public async Task WrongOpenedSessionRejectsBeforeReadingAndIsDisposed(string field)
    {
        var session = new FakeSession();
        session.Identity = field switch
        {
            "pid" => session.Identity with { ProcessId = 124 },
            "epoch" => session.Identity with { ProcessStartUtcTicks = 457 },
            "hash" => session.Identity with { ExecutableSha256 = new string('B', 64) },
            _ => session.Identity with { ExecutablePath = @"C:\other\rift_x64.exe" }
        };
        await Assert.ThrowsAsync<InvalidOperationException>(() => ControlNativeVitals.CaptureAsync(
            Configuration, Expected, _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            _ => throw new Exception("must not read"), default));
        Assert.True(session.Disposed);
        Assert.False(session.Revalidated);
    }

    [Fact]
    public async Task InvalidatedSessionNeverReturnsAReport()
    {
        var session = new FakeSession { Invalidation = "process-changed" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Capture(Expected, session));
        Assert.True(session.Revalidated && session.Disposed);
    }

    [Fact]
    public async Task SessionIdentityChangeDuringRevalidationRejectsReport()
    {
        var session = new FakeSession { ChangeEpochOnRevalidate = true };
        await Assert.ThrowsAsync<InvalidOperationException>(() => Capture(Expected, session));
        Assert.True(session.Revalidated && session.Disposed);
    }

    [Fact]
    public async Task ForeignObservationIdentityRejectsReport()
    {
        var session = new FakeSession();
        await Assert.ThrowsAsync<InvalidDataException>(() => ControlNativeVitals.CaptureAsync(
            Configuration, Expected, _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            source => Observation(source) with { Identity = source.Identity with { ProcessId = 124 } }, default));
        Assert.True(session.Revalidated && session.Disposed);
    }

    [Fact]
    public async Task CancellationRejectsBeforeOpening()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ControlNativeVitals.CaptureAsync(
            Configuration, Expected, _ => { opened = true; throw new Exception("must not open"); },
            Observation, cancellation.Token));
        Assert.False(opened);
    }

    private static Task<ControlNativeVitalsResponse> Capture(ControlIdentityRequest request, FakeSession session) =>
        ControlNativeVitals.CaptureAsync(Configuration, request,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(session), Observation, default);

    private static CurrentBuildVitalsObservation Observation(IReadOnlyNativeMemorySession session) =>
        new(session.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 123,
            new("calculated-candidate", null, 700, 1000), new("unavailable", "not-energy-kind-four"))
        { Mana = new("calculated-candidate", null, 3980, 3980) };

    private sealed class FakeSession : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456,
            Configuration.ExecutablePath, CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public string? Invalidation { get; init; }
        public bool ChangeEpochOnRevalidate { get; init; }
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException("No raw reads in operation tests.");
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Revalidated = true;
            if (ChangeEpochOnRevalidate)
                Identity = Identity with { ProcessStartUtcTicks = Identity.ProcessStartUtcTicks + 1 };
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
