using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

/// <summary>
/// Offline physical-process selection tests. No process enumeration or game input.
/// </summary>
public sealed class ControlNativeProcessGateTests
{
    private const long StartTicks = 638000000000000000L;
    private static readonly string GameSha = new('A', 64);
    private static readonly ControlIdentityRequest Expected =
        new(Environment.MachineName, 222, StartTicks, GameSha);

    private static readonly ControlAgentConfiguration Unbound = new(
        1, "192.168.1.1", 12345, new string('T', 32),
        Environment.MachineName, "rift_x64", @"C:\RIFT\rift_x64.exe",
        GameSha, Path.GetTempPath());

    private static ControlAgentConfiguration Bound =>
        Unbound with { BoundProcessId = Expected.ProcessId,
                       BoundProcessStartUtcTicks = Expected.ProcessStartUtcTicks };

    [Fact]
    public void UnboundSingleRiftSelectsExpectedProcess()
    {
        Assert.Equal(0, ControlNativeProcessGate.SelectExpectedProcessIndex(
            [Expected.ProcessId], Unbound, Expected));
    }

    [Fact]
    public void UnboundMultiboxRejectsAmbiguityEvenWhenExpectedPidIsPresent()
    {
        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [111, Expected.ProcessId, 333], Unbound, Expected));
    }

    [Fact]
    public void BoundMultiboxSelectsOnlyMatchingPid()
    {
        Assert.Equal(1, ControlNativeProcessGate.SelectExpectedProcessIndex(
            [111, Expected.ProcessId, 333], Bound, Expected));
    }

    [Fact]
    public void BoundMultiboxRejectsWrongExpectedPidOrEpoch()
    {
        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [111, Expected.ProcessId, 333], Bound,
                Expected with { ProcessId = 333 }));

        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [111, Expected.ProcessId, 333], Bound,
                Expected with { ProcessStartUtcTicks = StartTicks + 1 }));
    }

    [Fact]
    public void BoundMultiboxRejectsMissingOrDuplicateSelectedPid()
    {
        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [111, 333], Bound, Expected));

        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [Expected.ProcessId, Expected.ProcessId], Bound, Expected));
    }

    [Fact]
    public void UnboundSingleRiftRejectsWrongExpectedPid()
    {
        Assert.Throws<InvalidOperationException>(() =>
            ControlNativeProcessGate.SelectExpectedProcessIndex(
                [111], Unbound, Expected));
    }
}
