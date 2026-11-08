using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeXyzTests
{
    private static readonly ControlIdentityRequest Expected = new(Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256);
    private static readonly ControlAgentConfiguration Config = new(1, "192.168.1.1", 12345,
        new string('T', 32), Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, Path.GetTempPath());

    [Fact]
    public async Task SuccessfulCaptureRevalidatesDisposesAndSerializesLosslessly()
    {
        var session = new Fake();
        var response = await Capture(session);
        Assert.True(session.Revalidated && session.Disposed);
        var json = JsonSerializer.SerializeToElement(response, JsonFormat.Options);
        Assert.Equal(1, json.GetProperty("nativeXyzVersion").GetInt32());
        Assert.Equal("fresh-bytes", json.GetProperty("hashMode").GetString());
        var report = json.GetProperty("report");
        Assert.Equal("native-current-position-candidate-sample/1", report.GetProperty("contractVersion").GetString());
        Assert.Equal("candidate-only-not-passive-fresh-or-player-semantic-qualified", report.GetProperty("qualification").GetString());
        Assert.Equal("18446744073709551615", report.GetProperty("unitKey").GetString());
        Assert.Equal("uFFFFFFFFFFFFFFFF", report.GetProperty("unitIdCandidate").GetString());
        Assert.Equal("player-component-chain-anchored", report.GetProperty("ownerIdentityStatus").GetString());
        Assert.Equal(1.5f, report.GetProperty("x").GetSingle());
    }

    [Theory]
    [InlineData("pid")]
    [InlineData("epoch")]
    [InlineData("hash")]
    [InlineData("path")]
    public async Task WrongSessionIsDisposedBeforeRead(string field)
    {
        var session = new Fake();
        session.Identity = field switch
        {
            "pid" => session.Identity with { ProcessId = 124 },
            "epoch" => session.Identity with { ProcessStartUtcTicks = 457 },
            "hash" => session.Identity with { ExecutableSha256 = new string('A', 64) },
            _ => session.Identity with { ExecutablePath = @"C:\other\rift_x64.exe" }
        };
        await Assert.ThrowsAsync<InvalidOperationException>(() => ControlNativeXyz.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(session), _ => throw new Exception("read"), default));
        Assert.True(session.Disposed);
        Assert.False(session.Revalidated);
    }

    [Fact]
    public async Task InvalidatedOrChangedIdentityIsRejected()
    {
        var invalid = new Fake { Invalidation = "changed" };
        await Assert.ThrowsAsync<InvalidDataException>(() => Capture(invalid));
        Assert.True(invalid.Disposed);
        var changed = new Fake { ChangeEpoch = true };
        await Assert.ThrowsAsync<InvalidOperationException>(() => Capture(changed));
        Assert.True(changed.Disposed);
    }

    [Fact]
    public async Task BadCandidateAndCanceledRequestsNeverPublish()
    {
        var s = new Fake();
        await Assert.ThrowsAsync<InvalidDataException>(() => ControlNativeXyz.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(s), _ => new(0, new(1, 2, 3)), default));
        Assert.True(s.Disposed);
        s = new Fake();
        await Assert.ThrowsAsync<InvalidDataException>(() => ControlNativeXyz.CaptureAsync(Config, Expected,
            _ => Task.FromResult<IReadOnlyNativeMemorySession>(s), _ => new(1, new(float.NaN, 2, 3)), default));
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var opened = false;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ControlNativeXyz.CaptureAsync(Config, Expected,
            _ => { opened = true; throw new Exception(); }, _ => new(1, new(1, 2, 3)), cancellation.Token));
        Assert.False(opened);
    }

    [Fact]
    public async Task WrongMachineRejectedBeforeSessionOpen()
    {
        var opened = false;
        await Assert.ThrowsAsync<InvalidOperationException>(() => ControlNativeXyz.CaptureAsync(Config,
            Expected with { MachineName = "wrong" },
            _ => { opened = true; throw new Exception(); }, _ => new(1, new(1, 2, 3)), default));
        Assert.False(opened);
    }

    private static Task<ControlNativeXyzResponse> Capture(Fake s) => ControlNativeXyz.CaptureAsync(Config, Expected,
        _ => Task.FromResult<IReadOnlyNativeMemorySession>(s), _ => new(ulong.MaxValue, new(1.5f, -2, 3)), default);

    private sealed class Fake : IReadOnlyNativeMemorySession
    {
        public NativeProcessIdentity Identity { get; set; } = new(123, 456, Config.ExecutablePath,
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        public string? Invalidation { get; init; }
        public bool ChangeEpoch { get; init; }
        public bool Revalidated { get; private set; }
        public bool Disposed { get; private set; }
        public NativeReadResult Read(ulong address, int length) => throw new InvalidOperationException();
        public ValueTask<string?> RevalidateAsync(CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            Revalidated = true;
            if (ChangeEpoch) Identity = Identity with { ProcessStartUtcTicks = 457 };
            return ValueTask.FromResult(Invalidation);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
