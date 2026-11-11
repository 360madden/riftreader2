using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class MoveKeyCommandTests
{
    [Fact]
    public void DefaultOneSecondHoldSupportsEachMovementKey()
    {
        foreach (var key in new[] { "w", "a", "s", "d", "q", "e" })
        {
            var options = MoveKeyCommand.Parse(["--pid", "12345", "--key", key]);
            Assert.Equal(new[] { key }, options.Keys);
            Assert.Equal(1000, options.HoldMilliseconds);
            Assert.False(options.Execute);
            Assert.False(options.Focus);
        }
    }

    [Fact]
    public void CombinedForwardAndTurnKeyUsesSameBoundedExecutorValidation()
    {
        var options = MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w,e", "--hold-ms", "1250",
             "--focus", "--execute", "--json",
             "--expect-start-ticks", "639299470183328173",
             "--expect-sha256", new string('a', 64)]);
        Assert.Equal(new[] { "w", "e" }, options.Keys);
        Assert.Equal(1250, options.HoldMilliseconds);
        Assert.True(options.Focus);
        Assert.True(options.Execute);
        Assert.True(options.Json);
        Assert.Equal(639299470183328173, options.ExpectedStartTicks);
        Assert.Equal(new string('A', 64), options.ExpectedSha256);
    }

    [Theory]
    [InlineData("w,s")]
    [InlineData("a,d")]
    [InlineData("q,e")]
    [InlineData("w,w")]
    [InlineData("W")]
    [InlineData("z")]
    [InlineData("")]
    public void InvalidOrConflictingKeysAreRejectedWithoutInput(string keys)
    {
        Assert.ThrowsAny<Exception>(() =>
            MoveKeyCommand.Parse(["--pid", "12345", "--key", keys, "--execute"]));
    }

    [Theory]
    [InlineData("19")]
    [InlineData("3001")]
    [InlineData("-100")]
    [InlineData("invalid")]
    public void InvalidHoldDurationsAreRejected(string hold)
    {
        Assert.ThrowsAny<Exception>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--hold-ms", hold]));
    }

    [Fact]
    public void RequiresExactPidAndRejectsDuplicateOrUnknownOptions()
    {
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(["--key", "w"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(["--pid", "0", "--key", "w"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--key", "s"]));
        Assert.Throws<InvalidDataException>(() => MoveKeyCommand.Parse(
            ["--pid", "12345", "--key", "w", "--sendinput-unrestricted"]));
    }
}
