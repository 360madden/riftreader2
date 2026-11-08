using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeXyzDispatchTests
{
    [Fact]
    public async Task SuccessfulLoopbackDispatchPreservesRequestIdentityAndEnvelope()
    {
        var expected = new ControlIdentityRequest(Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256);
        ControlIdentityRequest? seen = null;
        await using var f = await Fixture.Create((_, identity, _) =>
        {
            seen = identity;
            return Task.FromResult(Result());
        });
        var id = Guid.NewGuid().ToString("N");
        await f.Send("native-xyz", expected, id);
        using var reply = await f.Receive();
        Assert.Equal(expected, seen);
        var root = reply.RootElement;
        Assert.Equal("response", root.GetProperty("type").GetString());
        Assert.Equal(id, root.GetProperty("id").GetString());
        var payload = root.GetProperty("payload");
        Assert.Equal(1, payload.GetProperty("nativeXyzVersion").GetInt32());
        Assert.Equal("fresh-bytes", payload.GetProperty("hashMode").GetString());
        Assert.Equal(f.InstanceId, payload.GetProperty("instanceId").GetString());
        var report = payload.GetProperty("report");
        Assert.Equal("native-current-position-candidate-sample/1", report.GetProperty("contractVersion").GetString());
        Assert.Equal("candidate-only-not-passive-fresh-or-player-semantic-qualified", report.GetProperty("qualification").GetString());
        Assert.Equal("18446744073709551615", report.GetProperty("unitKey").GetString());
        Assert.Equal(123, report.GetProperty("identity").GetProperty("processId").GetInt32());
        Assert.Equal(456, report.GetProperty("identity").GetProperty("processStartUtcTicks").GetInt64());
        Assert.Equal(CurrentBuildPlayerLookup.GameSha256, report.GetProperty("identity").GetProperty("executableSha256").GetString());
        await f.NativeRead;
    }

    [Fact]
    public async Task XyzReadOwnsLaneAndStopCancelsWithoutLateSuccess()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        CancellationToken captured = default;
        await using var f = await Fixture.Create(async (_, _, token) =>
        {
            captured = token;
            started.SetResult();
            await finish.Task;
            return Result();
        });
        await f.Send("native-xyz", new ControlIdentityRequest(Environment.MachineName, 123, 456, CurrentBuildPlayerLookup.GameSha256));
        await started.Task.WaitAsync(TimeSpan.FromSeconds(3));
        foreach (var operation in new[] { "native-xyz", "native-vitals", "action", "arm", "capture", "recover" })
        {
            await f.Send(operation, new { });
            using var busy = await f.Receive();
            Assert.Equal("Native read still active.", busy.RootElement.GetProperty("payload").GetProperty("error").GetString());
        }
        await f.Send("stop", new { });
        using var stopped = await f.Receive();
        Assert.True(stopped.RootElement.GetProperty("payload").GetProperty("stopped").GetBoolean());
        Assert.True(captured.IsCancellationRequested);
        Assert.False(f.NativeRead.IsCompleted);
        finish.SetResult();
        await f.NativeRead.WaitAsync(TimeSpan.FromSeconds(3));
        using var canceled = await f.Receive();
        Assert.Equal("OperationCanceledException", canceled.RootElement.GetProperty("payload").GetProperty("errorType").GetString());
        Assert.False(canceled.RootElement.GetProperty("payload").TryGetProperty("report", out _));
    }

    private static ControlNativeXyzResponse Result()
    {
        var identity = new NativeProcessIdentity(123, 456, @"C:\RIFT\rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow,
            new(identity, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                "18446744073709551615", "uFFFFFFFFFFFFFFFF", 1, 2, 3));
    }

    private sealed class Fixture : IAsyncDisposable
    {
        private readonly string directory = Path.Combine(Path.GetTempPath(), "rr2-xyz-lane-" + Guid.NewGuid().ToString("N"));
        private ControlAgent agent = null!;
        private TcpListener listener = null!;
        private TcpClient client = null!, peer = null!;
        private StreamReader reader = null!;
        private long sequence;
        public Task NativeRead => (Task)GetField("activeNativeRead")!;
        public string InstanceId => (string)GetField("instanceId")!;
        private object? GetField(string name) => typeof(ControlAgent).GetField(name,
            BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(agent);
        public static async Task<Fixture> Create(Func<ControlAgentConfiguration, ControlIdentityRequest,
            CancellationToken, Task<ControlNativeXyzResponse>> capture)
        {
            var f = new Fixture();
            var config = new ControlAgentConfiguration(1, "192.168.1.1", 12345, new string('T', 32),
                Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
                CurrentBuildPlayerLookup.GameSha256, f.directory);
            f.agent = new(config, (_, _, _) => throw new InvalidOperationException("unexpected vitals"), capture);
            f.listener = new(IPAddress.Loopback, 0);
            f.listener.Start();
            f.client = new();
            await f.client.ConnectAsync((IPEndPoint)f.listener.LocalEndpoint);
            f.peer = await f.listener.AcceptTcpClientAsync();
            f.reader = new(f.client.GetStream());
            return f;
        }
        public Task Send(string operation, object payload, string? id = null) => agent.DispatchCommandAsync(peer.GetStream(),
            new("command", id ?? Guid.NewGuid().ToString("N"), ++sequence, operation,
                JsonSerializer.SerializeToElement(payload, JsonFormat.Options)), default);
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
