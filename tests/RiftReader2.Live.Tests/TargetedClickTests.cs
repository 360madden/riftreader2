using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class TargetedClickTests
{
    private static DesktopTarget Target => new("guest", 1, 1, "0x1", "rift.exe", "sha", true, -100, 23, 1211, 686);

    [Fact]
    public void HotbarNearBottom_UsesButtonCenterWithoutCameraHeadroom()
    {
        var button = new ClickTarget(608, 640, 30, 30);
        var center = WindowsControlDesktop.TargetedClickPoint(Target, button);
        Assert.Equal(new DesktopPoint(523, 678), center);
        WindowsControlDesktop.ValidateTargetedClickPosition(Target, button, new(524, 679));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.ValidateTargetedClickPosition(Target, button, new(505, 366)));
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.ValidateTargetedClickPosition(Target, button, new(526, 678)));
    }

    [Theory]
    [InlineData(-1, 5, 30, 30)]
    [InlineData(1200, 640, 30, 30)]
    [InlineData(608, 680, 30, 30)]
    [InlineData(int.MaxValue, 0, 30, 30)]
    [InlineData(608, 640, 129, 30)]
    public void InvalidOrClippedButton_IsRejected(int x, int y, int width, int height)
    {
        Assert.Throws<InvalidOperationException>(() =>
            WindowsControlDesktop.TargetedClickPoint(Target, new(x, y, width, height)));
    }

    [Fact]
    public void TargetedClick_CannotBeMixedWithMovementOrDrag()
    {
        var click = new ControlAction([], 100, "left", ClickTarget: new(608, 640, 30, 30));
        BoundedControlExecutor.Validate(click);
        Assert.Throws<InvalidDataException>(() => BoundedControlExecutor.Validate(click with { Keys = ["w"] }));
        Assert.Throws<InvalidDataException>(() => BoundedControlExecutor.Validate(click with { DeltaX = 1 }));
        Assert.Throws<InvalidDataException>(() => BoundedControlExecutor.Validate(click with { MouseButton = "right" }));
        Assert.Throws<InvalidDataException>(() => BoundedControlExecutor.Validate(click with { WheelNotches = 1 }));
    }
}
