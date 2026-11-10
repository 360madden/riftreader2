namespace RiftReader2.Live.Tests;

/// <summary>Physical RIFT inspection binding checks; no process or game access.</summary>
public sealed class NativeInspectionBindingTests
{
    [Fact]
    public void UnpinnedInspectionKeepsLegacySingleProcessSelection()
    {
        var binding = NativeCommandRunner.ParseInspectProcessBinding(
            new Dictionary<string, string> { ["--output"] = "new-report.json" });
        Assert.Null(binding.ProcessId);
        Assert.Null(binding.StartTicks);
    }

    [Fact]
    public void PinnedInspectionRetainsExactPidAndEpoch()
    {
        var options = NativeCommandRunner.ParseOptions(
            ["--output", "new-report.json", "--pid", "44888",
             "--start-ticks", "639299470183328173"],
            "--output", "--pid", "--start-ticks");
        var binding = NativeCommandRunner.ParseInspectProcessBinding(options);
        Assert.Equal(44888, binding.ProcessId);
        Assert.Equal(639299470183328173L, binding.StartTicks);
    }

    [Theory]
    [InlineData("--pid")]
    [InlineData("--start-ticks")]
    public void PartialBindingFailsClosed(string option)
    {
        Assert.Throws<ArgumentException>(() =>
            NativeCommandRunner.ParseInspectProcessBinding(
                new Dictionary<string, string> { [option] = "123" }));
    }

    [Theory]
    [InlineData("0", "638000000000000000")]
    [InlineData("-1", "638000000000000000")]
    [InlineData("4294967296", "638000000000000000")]
    [InlineData("123", "0")]
    [InlineData("123", "-1")]
    [InlineData("123", "999999999999999999999999")]
    [InlineData("1.5", "638000000000000000")]
    public void InvalidPinnedIdentityFailsClosed(string pid, string ticks)
    {
        Assert.Throws<ArgumentException>(() =>
            NativeCommandRunner.ParseInspectProcessBinding(
                new Dictionary<string, string> { ["--pid"] = pid, ["--start-ticks"] = ticks }));
    }
}
