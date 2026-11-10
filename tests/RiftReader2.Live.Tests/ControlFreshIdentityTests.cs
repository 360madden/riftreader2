using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Infrastructure;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlFreshIdentityTests
{
    private static readonly DesktopTarget Target = new(
        Environment.MachineName, 123, 456, "0x789", @"C:\RIFT\rift_x64.exe",
        new string('A', 64), true, 0, 0, 1280, 720);
    private static ControlIdentityRequest Expected => new(
        Target.MachineName, Target.ProcessId, Target.ProcessStartUtcTicks, Target.ExecutableSha256);

    [Theory]
    [InlineData("identity")]
    public async Task BusyReadCommandRejectsBeforeParsingOrFreshHashWork(string operation)
    {
        var directory = Path.Combine(Path.GetTempPath(), "rr2-identity-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            var agent = new ControlAgent(new ControlAgentConfiguration(
                1, "192.168.1.1", 12345, new string('T', 32), Environment.MachineName,
                "rift_x64", Target.ExecutablePath, Target.ExecutableSha256, directory));
            var active = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            typeof(ControlAgent).GetField("activeAction", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(agent, active.Task);
            using var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            using var client = new TcpClient();
            await client.ConnectAsync((IPEndPoint)listener.LocalEndpoint);
            using var peer = await listener.AcceptTcpClientAsync();
            using var malformedIdentity = JsonDocument.Parse("{}");
            var command = new ControlCommand("command", Guid.NewGuid().ToString("N"), 1,
                operation, malformedIdentity.RootElement);
            var handler = typeof(ControlAgent).GetMethod("HandleCommandAsync",
                BindingFlags.Instance | BindingFlags.NonPublic)!;
            var handling = (Task)handler.Invoke(agent, [peer.GetStream(), command, CancellationToken.None])!;
            using var reader = new StreamReader(client.GetStream());
            var line = await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5));
            await handling;
            using var response = JsonDocument.Parse(line!);
            var payload = response.RootElement.GetProperty("payload");
            Assert.Equal("Action still active.", payload.GetProperty("error").GetString());
            Assert.Equal("InvalidOperationException", payload.GetProperty("errorType").GetString());
            // The malformed request would fail deserialization if execution reached
            // identity parsing, which always precedes process inspection and hashing.
            Assert.False(active.Task.IsCompleted);
            Assert.DoesNotContain("target", payload.EnumerateObject().Select(property => property.Name));
        }
        finally
        {
            if (Directory.Exists(directory))
                Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void IdentityReturnsFreshReceiptAndInspectsEveryInvocation()
    {
        var calls = 0;
        var before = DateTimeOffset.UtcNow;
        var first = ControlAgent.InspectFreshIdentity(Expected, () => { calls++; return Target; });
        var second = ControlAgent.InspectFreshIdentity(Expected, () => { calls++; return Target; });
        Assert.Equal(2, calls);
        Assert.Equal(1, first.IdentityVersion);
        Assert.Equal("fresh-bytes", first.HashMode);
        Assert.Equal(Target, first.Target);
        Assert.InRange(first.ObservedAtUtc, before, DateTimeOffset.UtcNow);
        Assert.True(second.ObservedAtUtc >= first.ObservedAtUtc);
    }

    [Theory]
    [InlineData("machine")]
    [InlineData("pid")]
    [InlineData("epoch")]
    [InlineData("hash")]
    public void ChangedTargetRejectsExpectedIdentityIncludingPreviousEpoch(string field)
    {
        var changed = field switch
        {
            "machine" => Target with { MachineName = "other-machine" },
            "pid" => Target with { ProcessId = Target.ProcessId + 1 },
            "epoch" => Target with { ProcessStartUtcTicks = Target.ProcessStartUtcTicks + 1 },
            _ => Target with { ExecutableSha256 = new string('B', 64) }
        };
        Assert.Throws<InvalidOperationException>(() => ControlAgent.InspectFreshIdentity(Expected, () => changed));
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("null")]
    [InlineData("{\"machineName\":\"pc\",\"processId\":1,\"processStartUtcTicks\":2}")]
    [InlineData("{\"machineName\":\"pc\",\"processId\":1,\"processStartUtcTicks\":2,\"executableSha256\":null}")]
    [InlineData("{\"machineName\":\"pc\",\"machineName\":\"pc\",\"processId\":1,\"processStartUtcTicks\":2,\"executableSha256\":\"A\"}")]
    [InlineData("{\"machineName\":\"pc\",\"processId\":1,\"processStartUtcTicks\":2,\"executableSha256\":\"A\",\"extra\":true}")]
    public void MissingOrMalformedIdentityFailsBeforeInspection(string json)
    {
        var calls = 0;
        Assert.ThrowsAny<Exception>(() =>
        {
            var request = JsonSerializer.Deserialize<ControlIdentityRequest>(json, JsonFormat.Options)
                ?? throw new InvalidDataException("Missing expected identity.");
            ControlAgent.InspectFreshIdentity(request, () => { calls++; return Target; });
        });
        Assert.Equal(0, calls);
    }

    [Fact]
    public void InvalidExpectedIdentityFailsBeforeInspection()
    {
        ControlIdentityRequest[] invalid =
        [
            Expected with { MachineName = " " },
            Expected with { ProcessId = 0 },
            Expected with { ProcessStartUtcTicks = 0 },
            Expected with { ProcessStartUtcTicks = long.MaxValue },
            Expected with { ExecutableSha256 = new string('G', 64) },
            Expected with { ExecutableSha256 = "" }
        ];
        foreach (var request in invalid)
            Assert.Throws<InvalidDataException>(() => ControlAgent.InspectFreshIdentity(request,
                () => throw new Exception("Must not inspect invalid request.")));
    }

    [Fact]
    public void UnpinnedPhysicalDiscoveryRejectsMultipleOrMissingRiftProcesses()
    {
        Assert.Equal(0, WindowsControlDesktop.SelectProcessIndex([101], null, "rift_x64"));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.SelectProcessIndex([], null, "rift_x64"));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.SelectProcessIndex([101, 202], null, "rift_x64"));
    }

    [Fact]
    public void FreshPinnedPhysicalIdentitySelectsOnlyExactPidEvenDuringMultibox()
    {
        Assert.Equal(1, WindowsControlDesktop.SelectProcessIndex([101, 202, 303], 202, "rift_x64"));
        Assert.Equal(0, WindowsControlDesktop.SelectProcessIndex([101], 101, "rift_x64"));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.SelectProcessIndex([101, 202], 404, "rift_x64"));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.SelectProcessIndex([202, 202], 202, "rift_x64"));
    }

    [Fact]
    public void WrongMachineOrConfiguredBuildIsRejectedBeforeProcessInspection()
    {
        var wrongMachine = Expected with { MachineName = "not-this-guest" };
        Assert.Throws<InvalidOperationException>(() => WindowsControlDesktop.InspectFreshIdentity(
            "nonexistent-process", Target.ExecutablePath, Target.ExecutableSha256, wrongMachine));
        Assert.Throws<InvalidOperationException>(() => WindowsControlDesktop.InspectFreshIdentity(
            "nonexistent-process", Target.ExecutablePath, new string('B', 64), Expected));
    }

    [Fact]
    public void FreshHashBypassesCachedHashWhenBytesChangeWithIdenticalMetadata()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllBytes(path, [1, 2, 3, 4]);
            var originalWriteTime = File.GetLastWriteTimeUtc(path);
            var cachedMethod = typeof(WindowsControlDesktop).GetMethod("GetExecutableSha256",
                BindingFlags.NonPublic | BindingFlags.Static)!;
            var cached = (string)cachedMethod.Invoke(null, [123, 456L, path])!;
            Assert.Equal(cached, WindowsControlDesktop.GetFreshExecutableSha256(path));
            File.WriteAllBytes(path, [5, 6, 7, 8]);
            File.SetLastWriteTimeUtc(path, originalWriteTime);
            Assert.Equal(cached, cachedMethod.Invoke(null, [123, 456L, path]));
            var fresh = WindowsControlDesktop.GetFreshExecutableSha256(path);
            Assert.NotEqual(cached, fresh);
            Assert.Equal(Convert.ToHexString(SHA256.HashData(new byte[] { 5, 6, 7, 8 })), fresh);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void FreshHashRejectsFileOpenForConcurrentWriting()
    {
        var path = Path.GetTempFileName();
        try
        {
            using var writer = new FileStream(path, FileMode.Open, FileAccess.Write, FileShare.ReadWrite);
            Assert.Throws<IOException>(() => WindowsControlDesktop.GetFreshExecutableSha256(path));
        }
        finally { File.Delete(path); }
    }
}
