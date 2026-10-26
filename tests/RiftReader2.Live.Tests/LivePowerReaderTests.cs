using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;
using RiftReader2.Live;

namespace RiftReader2.Live.Tests;

public sealed class LivePowerReaderTests
{
    private static readonly NativeProcessIdentity Identity = new(123, 456, "rift_x64.exe",
        PowerCandidateReader.ExecutableSha256, 0x140000000, 0x4000000);
    private static readonly PowerCandidateObservation Observation = new(
        "2026-10-26T01:00:00Z", "2026-10-26T01:00:00.1Z", "complete", null,
        0, 100, 0, 1200, 9, 100, 100, [], "", "");

    [Fact]
    public void ZeroPowerIsFreshButExpiresWithoutRenewalAfterDelivery()
    {
        var clock = new Clock();
        var read = new LivePowerRead(Identity, Observation, 0, null);
        clock.Timestamp = TimeSpan.FromSeconds(1).Ticks;
        var fresh = read.Present(clock, TimeSpan.FromSeconds(5));
        Assert.Equal("fresh", fresh.Status);
        Assert.Equal(0, fresh.Value);
        Assert.Equal(100, fresh.Maximum);
        Assert.Equal(4000, fresh.RemainingFreshMilliseconds);
        Assert.Equal(Identity, fresh.Identity);
        clock.Timestamp = TimeSpan.FromSeconds(5).Ticks;
        var expired = read.Present(clock, TimeSpan.FromSeconds(5));
        Assert.Equal("expired", expired.Status);
        Assert.Null(expired.Value);
        Assert.Null(expired.Maximum);
        Assert.Equal(fresh.ObservedAtUtc, expired.ObservedAtUtc);
        Assert.Equal(fresh.ExpiresAtUtc, expired.ExpiresAtUtc);
        Assert.Equal(0, expired.RemainingFreshMilliseconds);
    }

    [Fact]
    public void FailedReadAndTerminationClearValuesAndIdentity()
    {
        var failed = new LivePowerRead(Identity, Observation with { Status = "unavailable", Reason = "stale-process" }, 0, null)
            .Present(new Clock(), TimeSpan.FromSeconds(5));
        Assert.Equal("stale-process", failed.Reason);
        Assert.Null(failed.Value);
        Assert.Null(failed.Identity);
        var terminated = LivePowerRead.Unavailable("reader-terminated");
        Assert.Equal("unavailable", terminated.Status);
        Assert.Null(terminated.Value);
        Assert.Null(terminated.Maximum);
        Assert.Null(terminated.Identity);
    }

    [Fact]
    public async Task DifferentBuildDoesNotAttemptNativeProcessAccess()
    {
        var target = new DiscoveredTarget(new(123, 456, new string('A', 64), new string('1', 32)), "absent.exe", "rift_x64");
        var read = await LivePowerReader.ReadAsync(target, new Clock(), CancellationToken.None);
        Assert.Equal("unsupported-native-power-build", read.Failure);
        Assert.Null(read.Identity);
        Assert.Null(read.Observation);
    }

    [Fact]
    public void NativeValueSerializesSeparatelyWithoutFabricatingAddonData()
    {
        var report = new LiveReaderSnapshot(1, Guid.NewGuid(), new string('1', 32), 1,
            "2026-10-26T01:00:00Z", 0, "running", null, null,
            new(1, "unbound", "unavailable", null, 0, 0, null, null, 5000, 0, "no-matching-candidate",
                null, null, null, null, null, new("partial", false, 0, 0, 0, 0, 0, 0, 0, 0, null)),
            new(false, "disabled", null, null, null))
        {
            NativePower = new LivePowerRead(Identity, Observation, 0, null).Present(new Clock(), TimeSpan.FromSeconds(5))
        };
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(report, JsonFormat.Options));
        Assert.Equal(JsonValueKind.Null, json.RootElement.GetProperty("riftReader2").GetProperty("observation").ValueKind);
        var native = json.RootElement.GetProperty("nativePower");
        Assert.Equal("native", native.GetProperty("sourceKind").GetString());
        Assert.Equal("player.resource.power", native.GetProperty("fieldId").GetString());
        Assert.Equal(0, native.GetProperty("value").GetInt32());
    }

    private sealed class Clock : TimeProvider
    {
        internal long Timestamp { get; set; }
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        public override long GetTimestamp() => Timestamp;
    }
}
