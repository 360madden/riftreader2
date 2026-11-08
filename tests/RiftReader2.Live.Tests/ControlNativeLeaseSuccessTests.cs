using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeLeaseSuccessTests
{
    [Fact]
    public void DeclaredLeaseCapabilityIsVersionOne() => Assert.Equal(1, ControlAgent.NativeReadLeaseVersion);

    [Theory]
    [InlineData("native-xyz")]
    [InlineData("native-vitals")]
    public async Task SuccessfulCaptureHoldsLeaseUntilCompletionAndThenReleases(string operation)
    {
        var lease = new FakeLease();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var f = await Fixture.Create(
            async (_, _, _) => { entered.TrySetResult(); await finish.Task; return Vitals(); },
            async (_, _, _) => { entered.TrySetResult(); await finish.Task; return Xyz(); },
            (_, _) => Task.FromResult<IAsyncDisposable>(lease));
        await f.Send(operation);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(lease.Disposed);
        await f.Send("action", new { });
        using (var busy = await f.Receive())
            Assert.Equal("Native read still active.", busy.RootElement.GetProperty("payload").GetProperty("error").GetString());
        Assert.False(lease.Disposed);
        finish.SetResult();
        using var reply = await f.Receive();
        Assert.True(lease.Disposed);
        Assert.True(reply.RootElement.GetProperty("payload").TryGetProperty("report", out _));
    }

    [Theory]
    [InlineData("native-xyz")]
    [InlineData("native-vitals")]
    public async Task StopDuringLeaseWaitCancelsAndNeverCallsCapture(string operation)
    {
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var captured = false;
        await using var f = await Fixture.Create(
            (_, _, _) => { captured = true; return Task.FromResult(Vitals()); },
            (_, _, _) => { captured = true; return Task.FromResult(Xyz()); },
            async (_, token) =>
            {
                waiting.TrySetResult();
                await Task.Delay(Timeout.InfiniteTimeSpan, token);
                throw new InvalidOperationException("unreachable");
            });
        await f.Send(operation);
        await waiting.Task.WaitAsync(TimeSpan.FromSeconds(3));
        await f.Send("stop", new { });
        using var first = await f.Receive();
        using var second = await f.Receive();
        var payloads = new[] { first.RootElement.GetProperty("payload"), second.RootElement.GetProperty("payload") };
        Assert.Contains(payloads, p => p.TryGetProperty("stopped", out var value) && value.GetBoolean());
        Assert.Contains(payloads, p => p.TryGetProperty("errorType", out var value) &&
            value.GetString() is "TaskCanceledException" or "OperationCanceledException");
        Assert.All(payloads, p => Assert.False(p.TryGetProperty("report", out _)));
        Assert.False(captured);
    }

    private static ControlNativeXyzResponse Xyz()
    {
        var id = new NativeProcessIdentity(123, 456, @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow, new(id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, "123", "u000000000000007B", 1, 2, 3));
    }

    private static ControlNativeVitalsResponse Vitals() => new(1, "fresh-bytes", DateTimeOffset.UtcNow,
        new CurrentBuildVitalsReport(new(new(123, 456, @"C:\RIFT\rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000),
            DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 123,
            new("unavailable", "test"), new("unavailable", "test"))));

    private sealed class FakeLease : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class Fixture : IAsyncDisposable
    {
        private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-native-lease-success-" + Guid.NewGuid().ToString("N"));
        private ControlAgent agent = null!;
        private TcpListener listener = null!;
        private TcpClient client = null!, peer = null!;
        private StreamReader reader = null!;
        private long sequence;
        public static async Task<Fixture> Create(
            Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken, Task<ControlNativeVitalsResponse>> vitals,
            Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken, Task<ControlNativeXyzResponse>> xyz,
            Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> acquire)
        {
            var f = new Fixture();
            var config = new ControlAgentConfiguration(1, "192.168.1.1", 12345, new string('T', 32),
                Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, f.directory);
            f.agent = new(config, vitals, xyz, acquire);
            f.listener = new(IPAddress.Loopback, 0); f.listener.Start();
            f.client = new(); await f.client.ConnectAsync((IPEndPoint)f.listener.LocalEndpoint);
            f.peer = await f.listener.AcceptTcpClientAsync(); f.reader = new(f.client.GetStream());
            return f;
        }
        public Task Send(string operation, object? payload = null) => agent.DispatchCommandAsync(peer.GetStream(),
            new("command", Guid.NewGuid().ToString("N"), ++sequence, operation,
                JsonSerializer.SerializeToElement(payload ?? new ControlIdentityRequest(Environment.MachineName, 123, 456,
                    CurrentBuildPlayerLookup.GameSha256), JsonFormat.Options)), default);
        public async Task<JsonDocument> Receive() => JsonDocument.Parse(
            (await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(3)))!);
        public ValueTask DisposeAsync()
        {
            reader.Dispose(); client.Dispose(); peer.Dispose(); listener.Stop();
            System.IO.Directory.Delete(directory, recursive: true);
            return ValueTask.CompletedTask;
        }
    }
}
