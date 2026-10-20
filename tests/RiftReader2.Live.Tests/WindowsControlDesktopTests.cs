using System.Reflection;
using System.Runtime.InteropServices;
using RiftReader2.Live.Control;

namespace RiftReader2.Live.Tests;

public sealed class WindowsControlDesktopTests
{
    [Theory]
    [InlineData('q', 0x10)]
    [InlineData('W', 0x11)]
    [InlineData('e', 0x12)]
    [InlineData('A', 0x1E)]
    [InlineData('s', 0x1F)]
    [InlineData('D', 0x20)]
    public void ScanCodeFor_MapsOnlyTheBoundedControlKeys(char key, ushort expected)
    {
        Assert.Equal(expected, WindowsControlDesktop.ScanCodeFor(key));
    }

    [Fact]
    public void ScanCodeFor_RejectsUnapprovedKeys()
    {
        var error = Assert.Throws<ArgumentOutOfRangeException>(() => WindowsControlDesktop.ScanCodeFor('x'));
        Assert.Contains("W, A, S, D, Q, and E", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(0, 100)]
    [InlineData(100, 0)]
    [InlineData(4097, 100)]
    [InlineData(100, 2161)]
    public void CaptureDimensions_RejectUnsupportedBounds(int width, int height)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "ValidateCaptureDimensions", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);

        var error = Assert.Throws<TargetInvocationException>(() => method.Invoke(null, [width, height]));
        Assert.IsType<InvalidOperationException>(error.InnerException);
    }

    [Theory]
    [InlineData(0, 0, 1, 1, 0, 0)]
    [InlineData(100, 200, 1920, 1080, 1060, 740)]
    [InlineData(-1920, 0, 1920, 1080, -960, 540)]
    public void ClientCenter_UsesScreenCoordinates(
        int x,
        int y,
        int width,
        int height,
        int expectedX,
        int expectedY)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "GetClientCenter", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);

        var result = Assert.IsType<DesktopPoint>(method.Invoke(null, [x, y, width, height]));

        Assert.Equal(new DesktopPoint(expectedX, expectedY), result);
    }

    [Theory]
    [InlineData(0, 100)]
    [InlineData(100, 0)]
    public void ClientCenter_RejectsEmptyClientArea(int width, int height)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "GetClientCenter", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);

        var error = Assert.Throws<TargetInvocationException>(() => method.Invoke(null, [0, 0, width, height]));
        Assert.IsType<InvalidOperationException>(error.InnerException);
    }

    [Fact]
    public void InputInteropLayouts_AreWin64Compatible()
    {
        Assert.True(Environment.Is64BitProcess);
        Assert.Equal(40, SizeOfNested("Input"));
        Assert.Equal(32, SizeOfNested("InputUnion"));
        Assert.Equal(32, SizeOfNested("MouseInput"));
        Assert.Equal(24, SizeOfNested("KeyboardInput"));
        Assert.Equal(40, SizeOfNested("BitmapInfoHeader"));
    }

    private static int SizeOfNested(string name)
    {
        var type = typeof(WindowsControlDesktop).GetNestedType(name, BindingFlags.NonPublic);
        Assert.NotNull(type);
        return Marshal.SizeOf(type);
    }
}
