using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlNativeReadLaneTests
{
    private static readonly ControlIdentityRequest Expected = new(Environment.MachineName,
        123, 456, CurrentBuildPlayerLookup.GameSha256);

    [Fact]
    public async Task StopAcknowledgesWhileReadIsUnfinishedAndLaneStaysExclusiveUntilDisposal()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        CancellationToken capturedToken = default;
        var calls = 0;
        await using var fixture = await Fixture.Create(async (_, _, token) =>
        {
            calls++;
            capturedToken = token;
            started.SetResult();
            await finish.Task; // Deliberately model slow disposal that ignores cancellation.
            return Result();
        });
        await fixture.Send("native-vitals", Expected);
        await started.Task.WaitAsync(TimeSpan.FromSeconds(3));
        foreach (var operation in new[] { "action", "arm", "capture", "recover", "native-vitals", "identity" })
        {
            await fixture.Send(operation, new { });
            using var refused = await fixture.Receive();
            Assert.Equal("Native read still active.", refused.RootElement.GetProperty("payload").GetProperty("error").GetString());
        }
        await fixture.Send("stop", new { });
        using var stopped = await fixture.Receive();
        Assert.True(stopped.RootElement.GetProperty("payload").GetProperty("stopped").GetBoolean());
        Assert.True(capturedToken.IsCancellationRequested);
        Assert.False(finish.Task.IsCompleted);
        Assert.False(fixture.NativeRead.IsCompleted);
        await fixture.Send("native-vitals", Expected);
        using var stillBusy = await fixture.Receive();
        Assert.Equal("Native read still active.", stillBusy.RootElement.GetProperty("payload").GetProperty("error").GetString());
        Assert.Equal(1, calls);
        finish.SetResult();
        await fixture.NativeRead.WaitAsync(TimeSpan.FromSeconds(3));
        using var cancelled = await fixture.Receive();
        Assert.Equal("OperationCanceledException", cancelled.RootElement.GetProperty("payload").GetProperty("errorType").GetString());
        Assert.False(cancelled.RootElement.GetProperty("payload").TryGetProperty("report", out _));
    }

    [Fact]
    public async Task SuccessfulReadReturnsActualExecutingAgentInstanceId()
    {
        await using var fixture = await Fixture.Create((_, _, _) => Task.FromResult(Result()));
        await fixture.Send("native-vitals", Expected);
        using var response = await fixture.Receive();
        var actual = response.RootElement.GetProperty("payload").GetProperty("instanceId").GetString();
        Assert.Equal(fixture.GetField("instanceId"), actual);
        Assert.True(Guid.TryParseExact(actual, "N", out _));
        await fixture.NativeRead;
    }

    [Theory]
    [InlineData("armed")]
    [InlineData("action")]
    [InlineData("recovery")]
    public async Task UnsafeAdmissionRejectsBeforeInvokingNativeCapture(string state)
    {
        var calls = 0;
        await using var fixture = await Fixture.Create((_, _, _) => { calls++; return Task.FromResult(Result()); });
        if (state == "armed")
        {
            fixture.SetField("armToken", "active-token");
            fixture.SetField("armedAt", Stopwatch.GetTimestamp());
        }
        else if (state == "action")
            fixture.SetField("activeAction", new TaskCompletionSource().Task);
        else
            await File.WriteAllTextAsync(Path.Combine(fixture.Directory, "pending.json"), "pending");
        await fixture.Send("native-vitals", Expected);
        using var response = await fixture.Receive();
        Assert.Contains("disarmed, idle control with no pending recovery",
            response.RootElement.GetProperty("payload").GetProperty("error").GetString());
        Assert.Equal(0, calls);
        await fixture.NativeRead;
    }

    private static ControlNativeVitalsResponse Result() => new(1, "fresh-bytes", DateTimeOffset.UtcNow,
        new CurrentBuildVitalsReport(new(new(123, 456, @"C:\RIFT\rift_x64.exe",
            CurrentBuildPlayerLookup.GameSha256, 0x140000000, 0x4000000),
            DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, 123,
            new("unavailable", "test"), new("unavailable", "test"))));

    private sealed class Fixture : IAsyncDisposable
    {
        public string Directory { get; } = Path.Combine(Path.GetTempPath(), "rr2-native-lane-" + Guid.NewGuid().ToString("N"));
        private ControlAgent agent = null!;
        private TcpListener listener = null!;
        private TcpClient client = null!, peer = null!;
        private StreamReader reader = null!;
        private long sequence;
        public Task NativeRead => (Task)GetField("activeNativeRead")!;
        public object? GetField(string name) => typeof(ControlAgent).GetField(name,
            BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(agent);
        public void SetField(string name, object value) => typeof(ControlAgent).GetField(name,
            BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(agent, value);
        public static async Task<Fixture> Create(Func<ControlAgentConfiguration, ControlIdentityRequest,
            CancellationToken, Task<ControlNativeVitalsResponse>> capture)
        {
            var fixture = new Fixture();
            fixture.agent = new(new(1, "192.168.1.1", 12345, new string('T', 32), Environment.MachineName,
                "rift_x64", @"C:\RIFT\rift_x64.exe", CurrentBuildPlayerLookup.GameSha256, fixture.Directory), capture);
            fixture.listener = new(IPAddress.Loopback, 0);
            fixture.listener.Start();
            fixture.client = new();
            await fixture.client.ConnectAsync((IPEndPoint)fixture.listener.LocalEndpoint);
            fixture.peer = await fixture.listener.AcceptTcpClientAsync();
            fixture.reader = new(fixture.client.GetStream());
            return fixture;
        }
        public Task Send(string operation, object payload) => agent.DispatchCommandAsync(peer.GetStream(),
            new("command", Guid.NewGuid().ToString("N"), ++sequence, operation,
                JsonSerializer.SerializeToElement(payload, JsonFormat.Options)), default);
        public async Task<JsonDocument> Receive() => JsonDocument.Parse(
            (await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(3)))!);
        public ValueTask DisposeAsync()
        {
            reader.Dispose(); client.Dispose(); peer.Dispose(); listener.Dispose();
            System.IO.Directory.Delete(Directory, recursive: true);
            return ValueTask.CompletedTask;
        }
    }
}
