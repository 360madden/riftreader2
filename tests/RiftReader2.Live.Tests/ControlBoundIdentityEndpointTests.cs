using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

/// <summary>Offline control identity binding tests; no process discovery or game input.</summary>
public sealed class ControlBoundIdentityEndpointTests
{
    private static readonly DesktopTarget Target = new(
        Environment.MachineName, 222, 638000000000000000L,
        "0x1234", @"C:\RIFT\rift_x64.exe", new string('A', 64),
        true, 0, 0, 1280, 720);

    private static ControlIdentityRequest Expected => new(
        Target.MachineName, Target.ProcessId, Target.ProcessStartUtcTicks,
        Target.ExecutableSha256);

    private static ControlAgentConfiguration Unbound => new(
        1, "192.168.1.1", 12345, new string('T', 32),
        Environment.MachineName, "rift_x64", Target.ExecutablePath,
        Target.ExecutableSha256, Path.GetTempPath());

    [Theory]
    [InlineData("pid")]
    [InlineData("epoch")]
    public void BoundIdentityRefusesAnotherProcessBeforeInspection(string mismatch)
    {
        var bound = Unbound with
        {
            BoundProcessId = Expected.ProcessId,
            BoundProcessStartUtcTicks = Expected.ProcessStartUtcTicks
        };
        var requested = mismatch switch
        {
            "pid" => Expected with { ProcessId = Expected.ProcessId + 1 },
            _ => Expected with { ProcessStartUtcTicks = Expected.ProcessStartUtcTicks + 1 }
        };
        var calls = 0;
        Assert.Throws<InvalidOperationException>(() => ControlAgent.InspectFreshIdentity(
            requested, () => { calls++; return Target; }, bound));
        Assert.Equal(0, calls);
    }

    [Fact]
    public void MatchingBoundIdentityRetainsFreshInspectionAndReceipt()
    {
        var bound = Unbound with
        {
            BoundProcessId = Expected.ProcessId,
            BoundProcessStartUtcTicks = Expected.ProcessStartUtcTicks
        };
        var calls = 0;
        var result = ControlAgent.InspectFreshIdentity(Expected, () =>
        {
            calls++;
            return Target;
        }, bound);
        Assert.Equal(1, calls);
        Assert.Equal(Target, result.Target);
        Assert.Equal("fresh-bytes", result.HashMode);
    }

    [Fact]
    public void UnboundConfigurationRetainsPriorIdentityBehavior()
    {
        var calls = 0;
        var result = ControlAgent.InspectFreshIdentity(Expected, () =>
        {
            calls++;
            return Target;
        }, Unbound);
        Assert.Equal(1, calls);
        Assert.Equal(Target, result.Target);
    }
}
