using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class ControlInputInspectionStateTests
{
    [Theory]
    [InlineData(0, 2, 0, true)]  // Before input: full admission remains enabled.
    [InlineData(1, 2, 0, false)] // Input held.
    [InlineData(1, 1, 0, false)] // Some releases still outstanding.
    [InlineData(1, 0, 0, true)]  // All releases succeeded.
    [InlineData(1, 1, 1, false)] // Failed release with more attempts pending.
    [InlineData(1, 0, 1, false)] // Last up failed: the physical key may still be down.
    [InlineData(0, 0, 1, false)] // Failed precautionary release is uncertain too.
    public void FullInspectionRequiresNoHeldOrUncertainInput(
        int inputStarted, int remainingReleases, int releaseFailed, bool expected)
    {
        Assert.Equal(expected, ControlAgent.CanInspectFullInputIdentity(
            inputStarted, remainingReleases, releaseFailed));
    }
}
