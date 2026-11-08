using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeLeaseIntegrationTests
{
    [Theory]
    [InlineData("native-xyz")]
    [InlineData("native-vitals")]
    public async Task LeaseFailureBlocksCapture(string operation)
    {
        var called = false;
        await using var f = await Fixture.Create(
            (_, _, _) => { called = true; throw new Exception("capture called"); },
            (_, _) => throw new TimeoutException("lease busy"));
        await f.Send(operation);
        using var result = await f.Receive();
        Assert.Equal("TimeoutException", result.RootElement.GetProperty("payload").GetProperty("errorType").GetString());
        Assert.False(called);
        Assert.False(result.RootElement.GetProperty("payload").TryGetProperty("report", out _));
    }

    [Theory]
    [InlineData("native-xyz")]
    [InlineData("native-vitals")]
    public async Task LeaseIsHeldThroughCaptureAndDisposedOnFailure(string operation)
    {
        var lease = new FakeLease();
        var entered = false;
        await using var f = await Fixture.Create(
            (_, _, _) => { entered = true; Assert.False(lease.Disposed); throw new InvalidDataException("test capture"); },
            (_, _) => Task.FromResult<IAsyncDisposable>(lease));
        await f.Send(operation);
        using var result = await f.Receive();
        Assert.Equal("InvalidDataException", result.RootElement.GetProperty("payload").GetProperty("errorType").GetString());
        Assert.True(entered);
        Assert.True(lease.Disposed);
    }

    private sealed class FakeLease : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class Fixture : IAsyncDisposable
    {
        private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-native-lease-lane-" + Guid.NewGuid().ToString("N"));
        private ControlAgent agent = null!;
        private TcpListener listener = null!;
        private TcpClient client = null!, peer = null!;
        private StreamReader reader = null!;
        public static async Task<Fixture> Create(
            Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken, Task> capture,
            Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> acquire)
        {
            var f = new Fixture();
            var config = new ControlAgentConfiguration(1, "192.168.1.1", 12345, new string('T', 32),
                Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
                CurrentBuildPlayerLookup.GameSha256, f.directory);
            f.agent = new(config,
                async (c, i, t) => { await capture(c, i, t); throw new Exception(); },
                async (c, i, t) => { await capture(c, i, t); throw new Exception(); }, acquire);
            f.listener = new(IPAddress.Loopback, 0); f.listener.Start();
            f.client = new(); await f.client.ConnectAsync((IPEndPoint)f.listener.LocalEndpoint);
            f.peer = await f.listener.AcceptTcpClientAsync(); f.reader = new(f.client.GetStream());
            return f;
        }
        public Task Send(string operation) => agent.DispatchCommandAsync(peer.GetStream(),
            new("command", Guid.NewGuid().ToString("N"), 1, operation,
                JsonSerializer.SerializeToElement(new ControlIdentityRequest(Environment.MachineName, 123, 456,
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
