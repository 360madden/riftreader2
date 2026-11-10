using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;
using RiftReader2.Live.Control;

namespace RiftReader2.Tests;

public sealed class ControlNativeSmoothedScalarTests
{
    private static readonly ControlIdentityRequest Expected = new(
        Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256);
    private static readonly ControlAgentConfiguration Config = new(1, "192.168.1.1", 12345,
        new string('T', 32), Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, Path.GetTempPath());

    [Fact]
    public async Task PublishesOnlyAfterFreshProcessRevalidation()
    {
        var session = new Fake();
        var response = await Capture(session);
        Assert.True(session.Revalidated);
        Assert.True(session.Disposed);
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(response, JsonFormat.Options));
        var root = document.RootElement;
        Assert.Equal(1, root.GetProperty("nativeSmoothedScalarVersion").GetInt32());
        Assert.Equal("fresh-bytes", root.GetProperty("hashMode").GetString());
        Assert.False(root.GetProperty("report").GetProperty("headingQualified").GetBoolean());
    }

    [Fact]
    public async Task WrongEpochOrInvalidatedSessionRefusesReport()
    {
        var changedEpoch = new Fake { Identity = new(123, 457, Config.ExecutablePath,
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000) };
        await Assert.ThrowsAsync<InvalidOperationException>(() => Capture(changedEpoch));
        Assert.True(changedEpoch.Disposed);
        Assert.False(changedEpoch.Revalidated);

        var invalid = new Fake { Invalidation = "changed" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Capture(invalid));
        Assert.True(invalid.Disposed);
        Assert.True(invalid.Revalidated);
    }

    private static Task<ControlNativeSmoothedScalarResponse> Capture(Fake session) =>
        ControlNativeSmoothedScalar.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(session),
            memory => new(memory.Identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                456, 0x200000, 0x300000, [1u, 2u, 3u, 4u], 1, 2, 3, 4),
            default);

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, Config.ExecutablePath,
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public string? Invalidation { get; init; }
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException();
        public ValueTask<string?> RevalidateAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Revalidated = true;
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
