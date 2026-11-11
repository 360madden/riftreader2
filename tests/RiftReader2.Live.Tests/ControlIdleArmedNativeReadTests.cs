using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

/// <summary>Offline native-feedback admission during one bounded arm; no game input.</summary>
public sealed class ControlIdleArmedNativeReadTests
{
    private static readonly DesktopTarget Target = new(
        Environment.MachineName, 123, 456, "0x789", @"C:\RIFT\rift_x64.exe",
        CurrentBuildPlayerLookup.GameSha256, true, 0, 0, 1280, 720);

    private static ControlIdentityRequest Identity => new(
        Target.MachineName, Target.ProcessId, Target.ProcessStartUtcTicks, Target.ExecutableSha256);

    [Fact]
    public async Task MatchingArmedReadSucceedsWithoutDisarming()
    {
        var reads = 0;
        var lease = new FakeLease();
        await using var f = await Fixture.Create(
            (_, _, _) => { reads++; return Task.FromResult(Xyz()); },
            (_, _) => Task.FromResult<IAsyncDisposable>(lease));
        f.Arm();
        await f.Send("native-xyz", Identity);
        using var reply = await f.Receive();
        Assert.True(reply.RootElement.GetProperty("payload").TryGetProperty("report", out _));
        Assert.Equal(1, reads);
        Assert.True(lease.Disposed);
        Assert.True(f.IsArmed());
    }

    [Theory]
    [InlineData("pid")]
    [InlineData("epoch")]
    [InlineData("sha")]
    public async Task ArmedReadRejectsWrongReviewedTargetBeforeLease(string mismatch)
    {
        var leases = 0;
        await using var f = await Fixture.Create(
            (_, _, _) => throw new InvalidOperationException("Must not capture"),
            (_, _) => { leases++; throw new InvalidOperationException("Must not lease"); });
        f.Arm();
        var request = mismatch switch
        {
            "pid" => Identity with { ProcessId = 124 },
            "epoch" => Identity with { ProcessStartUtcTicks = 457 },
            _ => Identity with { ExecutableSha256 = new string('B', 64) }
        };
        await f.Send("native-xyz", request);
        using var reply = await f.Receive();
        Assert.Equal("InvalidOperationException",
            reply.RootElement.GetProperty("payload").GetProperty("errorType").GetString());
        Assert.Equal(0, leases);
        Assert.True(f.IsArmed());
    }

    [Fact]
    public async Task ArmedReadStillRefusesPendingRecovery()
    {
        var leases = 0;
        await using var f = await Fixture.Create(
            (_, _, _) => throw new InvalidOperationException("Must not capture"),
            (_, _) => { leases++; throw new InvalidOperationException("Must not lease"); });
        f.Arm();
        File.WriteAllText(f.PendingPath, "pending");
        await f.Send("native-xyz", Identity);
        using var reply = await f.Receive();
        Assert.Contains("pending recovery",
            reply.RootElement.GetProperty("payload").GetProperty("error").GetString());
        Assert.Equal(0, leases);
        Assert.True(f.IsArmed());
    }

    [Fact]
    public async Task ArmedReadExcludesActionAndStopDisarmsAfterCompletion()
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var f = await Fixture.Create(async (_, _, _) =>
        {
            entered.TrySetResult();
            await finish.Task;
            return Xyz();
        }, (_, _) => Task.FromResult<IAsyncDisposable>(new FakeLease()));
        f.Arm();
        await f.Send("native-xyz", Identity);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        await f.Send("action", new { });
        using (var busy = await f.Receive())
            Assert.Equal("Native read still active.",
                busy.RootElement.GetProperty("payload").GetProperty("error").GetString());
        finish.SetResult();
        using (var feedback = await f.Receive())
            Assert.True(feedback.RootElement.GetProperty("payload").TryGetProperty("report", out _));
        await f.Send("stop", new { });
        using (var stopped = await f.Receive())
            Assert.True(stopped.RootElement.GetProperty("payload").GetProperty("stopped").GetBoolean());
        Assert.False(f.IsArmed());
    }

    private static ControlNativeXyzResponse Xyz()
    {
        var id = new NativeProcessIdentity(123, 456, Target.ExecutablePath,
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000);
        return new(1, "fresh-bytes", DateTimeOffset.UtcNow,
            new(id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow,
                "123", "u000000000000007B", 1, 2, 3));
    }

    private sealed class FakeLease : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class Fixture : IAsyncDisposable
    {
        private readonly string directory = Path.Combine(Path.GetTempPath(),
            "rr2-armed-native-" + Guid.NewGuid().ToString("N"));
        private ControlAgent agent = null!;
        private TcpListener listener = null!;
        private TcpClient client = null!, peer = null!;
        private StreamReader reader = null!;
        private long sequence;

        public string PendingPath => Path.Combine(directory, "pending.json");

        public static async Task<Fixture> Create(
            Func<ControlAgentConfiguration, ControlIdentityRequest, CancellationToken,
                Task<ControlNativeXyzResponse>> xyz,
            Func<ControlIdentityRequest, CancellationToken, Task<IAsyncDisposable>> acquire)
        {
            var f = new Fixture();
            var config = new ControlAgentConfiguration(1, "192.168.1.1", 12345,
                new string('T', 32), Environment.MachineName, "rift_x64",
                Target.ExecutablePath, Target.ExecutableSha256, f.directory);
            f.agent = new(config,
                (_, _, _) => throw new InvalidOperationException("Vitals not used"),
                xyz, acquire);
            f.listener = new(IPAddress.Loopback, 0);
            f.listener.Start();
            f.client = new();
            await f.client.ConnectAsync((IPEndPoint)f.listener.LocalEndpoint);
            f.peer = await f.listener.AcceptTcpClientAsync();
            f.reader = new(f.client.GetStream());
            return f;
        }

        public void Arm()
        {
            SetField("reviewedTarget", Target);
            SetField("armToken", Guid.NewGuid().ToString("N"));
            SetField("armedAt", Stopwatch.GetTimestamp());
        }

        public bool IsArmed() => typeof(ControlAgent)
            .GetMethod("IsArmed", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(agent, null) is true;

        private void SetField(string name, object value) => typeof(ControlAgent)
            .GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!
            .SetValue(agent, value);

        public Task Send(string operation, object payload) => agent.DispatchCommandAsync(
            peer.GetStream(),
            new("command", Guid.NewGuid().ToString("N"), ++sequence, operation,
                JsonSerializer.SerializeToElement(payload, JsonFormat.Options)),
            default);

        public async Task<JsonDocument> Receive() => JsonDocument.Parse(
            (await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(3)))!);

        public ValueTask DisposeAsync()
        {
            reader.Dispose();
            client.Dispose();
            peer.Dispose();
            listener.Stop();
            Directory.Delete(directory, recursive: true);
            return ValueTask.CompletedTask;
        }
    }
}
