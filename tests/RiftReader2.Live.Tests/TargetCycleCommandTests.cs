using RiftReader2.Application;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class TargetCycleCommandTests
{
    private static string[] Args(params string[] extra) =>
        ["--expected-host", "AMD-DESKTOP", "--pid", "5", "--expect-start-ticks", "100",
         "--expect-sha256", new string('A',64), "--expect-hwnd", "0x8", "--expect-player-key", "42",
         "--owner-pid", "9", "--owner-start-ticks", "20", "--stop-file", Path.GetFullPath("cycle.stop"), .. extra];

    [Theory]
    [InlineData("--help")]
    [InlineData("-h")]
    public async Task HelpIsAvailableWithoutDesktopOrProcessPins(string flag)
    {
        using var output = new StringWriter();
        Assert.Equal(0, await TargetCycleCommand.RunAsync([flag], new CancellationToken(true), output));
        var help = output.ToString();
        Assert.Contains("--expect-target-key", help);
        Assert.Contains("0 to require an observed empty selection", help);
        Assert.Contains("40 ms Tab", help);
        Assert.Contains("releaseSucceeded", help);
        Assert.Contains("--execute", help);
    }

    [Fact]
    public void OptionalOldSelectionDistinguishesAbsentZeroAndPositive()
    {
        var now = DateTimeOffset.UtcNow;
        var zero = TargetCycleCommand.Parse(Args("--expect-target-key","0"));
        TargetCycleCommand.ValidatePins(zero, new(42,0,now,now), now);
        TargetCycleCommand.ValidatePins(TargetCycleCommand.Parse(Args()), new(42,89,now,now), now);
        Assert.Throws<InvalidDataException>(() => TargetCycleCommand.ValidatePins(zero, new(42,89,now,now), now));
        Assert.Throws<InvalidDataException>(() => TargetCycleCommand.ValidatePins(zero, new(41,0,now,now), now));
        Assert.Throws<InvalidDataException>(() => TargetCycleCommand.ValidatePins(zero, new(42,0,now.AddSeconds(-2),now), now));
        Assert.Throws<InvalidDataException>(() => TargetCycleCommand.ValidatePins(zero, new(42,0,now,now.AddSeconds(1)), now));
    }

    [Theory]
    [InlineData("--hold-ms","900")]
    [InlineData("--key","w")]
    [InlineData("--expect-target-key","-1")]
    public void RejectsArbitraryKeyDurationOrMalformedOldSelection(string flag, string value) =>
        Assert.Throws<InvalidDataException>(() => TargetCycleCommand.Parse(Args(flag,value)));

    [Fact]
    public void DedicatedTabHasCorrectScanCodeAndNeverEntersGenericActionAllowlist()
    {
        Assert.Equal(0x0F, WindowsControlDesktop.ScanCodeFor('\t'));
        Assert.Equal(0xC00F0001u, WindowsControlDesktop.KeyUpMessageParameters('\t'));
        Assert.Throws<InvalidDataException>(() => BoundedControlExecutor.Validate(new(["tab"],40)));
    }

    [Fact]
    public async Task OneTabPressCompletesWithOneVerifiedRelease()
    {
        bool held = false;
        var events = new List<string>();
        var input = new TargetCycleCommand.PulseInput(() => null, () => held ? ["tab"] : [],
            () => { held = true; events.Add("down"); }, () => { held = false; events.Add("up"); });
        var result = await new BoundedControlExecutor(input).TapTargetCycleAsync();
        Assert.True(result.DeliverySucceeded, result.Error);
        Assert.True(input.Released);
        Assert.Equal(new[]{"down","up"},events);
    }

    [Theory]
    [InlineData("stop-file-requested")]
    [InlineData("foreground-or-window-identity-changed")]
    [InlineData("owner-process-lost")]
    public async Task SafetyLossAfterDownReleasesTab(string reason)
    {
        var count = 0;
        var sent = false;
        var input = new TargetCycleCommand.PulseInput(() => sent ? reason : null, () => [],
            () => sent = true, () => ++count);
        var result = await new BoundedControlExecutor(input).TapTargetCycleAsync();
        Assert.False(result.DeliverySucceeded);
        Assert.True(result.ReleaseSucceeded);
        Assert.True(input.Released);
        Assert.Equal(1,count);
    }

    [Theory]
    [InlineData("tab")]
    [InlineData("shift")]
    public async Task ExistingOperatorKeyNeverReceivesSyntheticUp(string held)
    {
        var input = new TargetCycleCommand.PulseInput(() => null, () => [held],
            () => throw new Exception("unexpected down"), () => throw new Exception("unexpected up"));
        var result = await new BoundedControlExecutor(input).TapTargetCycleAsync();
        Assert.False(result.DeliverySucceeded);
        Assert.False(input.Attempted);
        Assert.False(input.Released);
    }

    [Fact]
    public async Task PinRefusedAtDownSendsNoKeyUp()
    {
        int calls = 0;
        var input = new TargetCycleCommand.PulseInput(() => null, () => [],
            () => ++calls, () => ++calls, () => throw new InvalidDataException("stale selection"));
        var result = await new BoundedControlExecutor(input).TapTargetCycleAsync();
        Assert.False(result.DeliverySucceeded);
        Assert.False(input.Attempted);
        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task FailedKeyUpReportsUncertainRelease()
    {
        int attempts = 0;
        var input = new TargetCycleCommand.PulseInput(() => null, () => [],
            () => {}, () => { ++attempts; throw new IOException("failed key-up"); });
        var result = await new BoundedControlExecutor(input).TapTargetCycleAsync();
        Assert.False(result.ReleaseSucceeded);
        Assert.False(input.Released);
        Assert.Equal(1, attempts);
    }
}
