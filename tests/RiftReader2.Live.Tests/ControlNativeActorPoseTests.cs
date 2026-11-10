using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeActorPoseTests
{
    private static readonly ControlIdentityRequest Expected = new(
        Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256);
    private static readonly ControlAgentConfiguration Config = new(1, "192.168.1.1", 12345,
        new string('T', 32), Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, Path.GetTempPath());

    [Fact]
    public async Task PublishesCandidateOnlyAfterFreshIdentityRevalidation()
    {
        var session = new Fake();
        var result = await Capture(session);
        Assert.True(session.Revalidated);
        Assert.True(session.Disposed);
        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(result, JsonFormat.Options));
        var report = doc.RootElement;
        Assert.Equal(1, report.GetProperty("nativeActorPoseVersion").GetInt32());
        Assert.Equal("fresh-bytes", report.GetProperty("hashMode").GetString());
        var pose = report.GetProperty("report");
        Assert.Equal(123, pose.GetProperty("identity").GetProperty("processId").GetInt32());
        Assert.False(pose.GetProperty("actorHeadingQualified").GetBoolean());
        Assert.Contains("candidate-only", pose.GetProperty("qualification").GetString());
        Assert.Equal("456", pose.GetProperty("playerKeyDecimal").GetString());
        Assert.Equal(9, pose.GetProperty("actorMatrix").GetProperty("rawBits").GetArrayLength());
        Assert.Equal("normal-render-matrix-candidate", pose.GetProperty("renderStatus").GetString());
    }

    [Fact]
    public async Task RefusesWrongEpochBeforeReadingAndDisposes()
    {
        var session = new Fake();
        session.Identity = session.Identity with { ProcessStartUtcTicks = 457 };
        var read = false;
        await Assert.ThrowsAsync<InvalidOperationException>(() => ControlNativeActorPose.CaptureAsync(
            Config, Expected, _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            _ => { read = true; throw new Exception("read must not run"); }, default));
        Assert.False(read);
        Assert.True(session.Disposed);
        Assert.False(session.Revalidated);
    }

    [Fact]
    public async Task RevalidationOrCancellationBlocksPublication()
    {
        var invalid = new Fake { Invalidation = "changed" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Capture(invalid));
        Assert.True(invalid.Disposed);
        Assert.True(invalid.Revalidated);

        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ControlNativeActorPose.CaptureAsync(
            Config, Expected, _ => { opened = true; throw new Exception(); },
            _ => throw new Exception(), cts.Token));
        Assert.False(opened);
    }

    private static Task<ControlNativeActorPoseResponse> Capture(Fake session) =>
        ControlNativeActorPose.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            memory =>
            {
                var matrix = new CurrentBuildMatrixDescriptorCandidate(0x398, new uint[9], new float[9],
                    "structural-y-planar-matrix-candidate", 0, 1, 0, 0, 0);
                return new(memory.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                    456, 0x200000, 0x300000, 0x400000, 0,
                    matrix, matrix, matrix, "normal-render-matrix-candidate", 0);
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
