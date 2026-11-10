using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeOrientationTests
{
    private static readonly ControlIdentityRequest Expected = new(
        Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256);
    private static readonly ControlAgentConfiguration Config = new(1, "192.168.1.1", 12345,
        new string('T', 32), Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, Path.GetTempPath());

    [Fact]
    public async Task PublishesTaggedCandidateAfterRevalidationAndDisposal()
    {
        var session = new Fake();
        var result = await Capture(session);
        Assert.True(session.Revalidated && session.Disposed);
        var json = JsonSerializer.SerializeToElement(result, JsonFormat.Options);
        Assert.Equal(1, json.GetProperty("nativeOrientationVersion").GetInt32());
        Assert.Equal("fresh-bytes", json.GetProperty("hashMode").GetString());
        var report = json.GetProperty("report");
        Assert.Equal("123", report.GetProperty("unitKey").GetString());
        Assert.Contains("candidate-only", report.GetProperty("qualification").GetString());
        Assert.Equal(88.0, report.GetProperty("primary").GetProperty("planarAngleDegreesCandidate").GetDouble());
        Assert.Equal(123, report.GetProperty("identity").GetProperty("processId").GetInt32());
    }

    [Fact]
    public async Task RejectsWrongEpochBeforeReadAndDisposes()
    {
        var session = new Fake();
        session.Identity = session.Identity with { ProcessStartUtcTicks = 457 };
        await Assert.ThrowsAsync<InvalidOperationException>(() => Capture(session));
        Assert.True(session.Disposed);
        Assert.False(session.Revalidated);
    }

    [Fact]
    public async Task InvalidationAndCancellationNeverPublish()
    {
        var session = new Fake { Invalidation = "invalidated" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Capture(session));
        Assert.True(session.Disposed);
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ControlNativeOrientation.CaptureAsync(
            Config, Expected, _ => { opened = true; throw new Exception(); },
            _ => throw new Exception(), cts.Token));
        Assert.False(opened);
    }

    private static Task<ControlNativeOrientationResponse> Capture(Fake session) =>
        ControlNativeOrientation.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            memory =>
            {
                var row = new CurrentBuildMatrixDescriptorCandidate(0x60, new uint[9], new float[9],
                    "structural-y-planar-matrix-candidate", 0, 1, 0, 88 * Math.PI / 180, 88);
                return new(memory.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                    123, 0x20000, 0, 0, row, row);
            }, default);

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, Config.ExecutablePath,
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public string? Invalidation { get; init; }
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException();
        public ValueTask<string?> RevalidateAsync(CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            Revalidated = true;
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
