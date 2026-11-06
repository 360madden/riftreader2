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
    public void PressedInputDiagnostic_DecodesOnlyTheHighBitInStableOrder()
    {
        var down = unchecked((short)0x8001);
        var states = new Dictionary<int, short>
        {
            [0x10] = down,
            [0x11] = 0x0001,
            [0x12] = down,
            [0x5B] = 0x0001,
            [0x5C] = down,
            [0x01] = down,
            [0x02] = 0x0001,
            [0x04] = down,
            ['W'] = down,
            ['A'] = 0x0001,
            ['S'] = down,
            ['D'] = 0x0001,
            ['Q'] = down,
            ['E'] = 0x0001
        };

        var pressed = DecodePressedInputs(key => states.GetValueOrDefault(key));

        Assert.Equal(
            ["shift", "alt", "right-win", "mouse-left", "mouse-middle", "w", "s", "q"],
            pressed);
    }

    [Fact]
    public void PressedInputDiagnostic_ReportsNoInputsForLowToggleBitsOnly()
    {
        var pressed = DecodePressedInputs(_ => 0x0001);

        Assert.Empty(pressed);
    }

    [Theory]
    [InlineData(500, 400, 100, 100, 800, 600, 0, 0)]
    [InlineData(532, 432, 100, 100, 800, 600, 0, 0)]
    [InlineData(668, 568, 100, 100, 800, 600, 36, 36)]
    public void CursorPreparation_PreservesPointWithRequiredHeadroom(
        int cursorX,
        int cursorY,
        int clientX,
        int clientY,
        int width,
        int height,
        int deltaX,
        int deltaY)
    {
        var original = new DesktopPoint(cursorX, cursorY);

        var result = PlanCursorPreparation(original, clientX, clientY, width, height, deltaX, deltaY);

        Assert.Equal(new CursorPreparation(original, original, Repositioned: false), result);
    }

    [Theory]
    [InlineData(99, 400, 100, 100, 800, 600, 0, 0)]
    [InlineData(131, 400, 100, 100, 800, 600, 0, 0)]
    [InlineData(350, 400, 100, 100, 800, 600, 219, 0)]
    [InlineData(900, 700, 100, 100, 800, 600, 0, 0)]
    public void CursorPreparation_CentersOutsideOrNearEdgePoint(
        int cursorX,
        int cursorY,
        int clientX,
        int clientY,
        int width,
        int height,
        int deltaX,
        int deltaY)
    {
        var original = new DesktopPoint(cursorX, cursorY);

        var result = PlanCursorPreparation(original, clientX, clientY, width, height, deltaX, deltaY);

        Assert.Equal(new CursorPreparation(original, new DesktopPoint(500, 400), Repositioned: true), result);
    }

    [Theory]
    [InlineData(0, 100)]
    [InlineData(100, 0)]
    [InlineData(4097, 100)]
    [InlineData(100, 2161)]
    public void CursorPreparation_RejectsUnboundedClientGeometry(int width, int height)
    {
        var error = Assert.Throws<TargetInvocationException>(() =>
            InvokeCursorPreparation(new DesktopPoint(), 0, 0, width, height, 0, 0));

        Assert.IsType<InvalidOperationException>(error.InnerException);
    }

    [Fact]
    public void CursorPreparation_AcceptsCenterAtExactRequiredHeadroom()
    {
        var original = new DesktopPoint(-1, -1);

        var result = PlanCursorPreparation(original, 0, 0, 65, 65, 0, 0);

        Assert.Equal(
            new CursorPreparation(original, new DesktopPoint(32, 32), Repositioned: true),
            result);
    }

    [Theory]
    [InlineData(64, 65)]
    [InlineData(65, 64)]
    [InlineData(136, 137)]
    public void CursorPreparation_RejectsCenterWithoutRequiredHeadroom(int width, int height)
    {
        var delta = width > 65 || height > 65 ? 36 : 0;

        var error = Assert.Throws<TargetInvocationException>(() =>
            InvokeCursorPreparation(new DesktopPoint(-1, -1), 0, 0, width, height, delta, delta));

        Assert.IsType<InvalidOperationException>(error.InnerException);
        Assert.Contains("cannot provide", error.InnerException.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CursorPreparation_MouseButtonGuardUsesHighBitOnly()
    {
        EnsureNoMouseButtonDown(_ => 0x0001);
        var error = Assert.Throws<TargetInvocationException>(() =>
            EnsureNoMouseButtonDown(key => key == 0x02 ? unchecked((short)0x8000) : (short)0));
        var inner = Assert.IsType<InvalidOperationException>(error.InnerException);
        Assert.Equal(
            "Cursor preparation is blocked while Windows reports a mouse button down.",
            inner.Message);
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

    [Theory]
    [InlineData(-3, 0xFE980000u)]
    [InlineData(-1, 0xFF880000u)]
    [InlineData(1, 0x00780000u)]
    [InlineData(3, 0x01680000u)]
    public void TargetedWheel_EncodesSignedDeltaInHighWord(int notches, uint expected)
    {
        Assert.Equal(expected, EncodeWheelWParam(notches).ToUInt64());
    }

    [Theory]
    [InlineData(-4)]
    [InlineData(0)]
    [InlineData(4)]
    public void TargetedWheel_RejectsZeroAndOutOfBoundsNotches(int notches)
    {
        var error = Assert.Throws<TargetInvocationException>(() => EncodeWheelWParam(notches));

        Assert.IsType<ArgumentOutOfRangeException>(error.InnerException);
    }

    [Theory]
    [InlineData(0, 0, 0x00000000u)]
    [InlineData(32767, 32767, 0x7FFF7FFFu)]
    [InlineData(-32768, -32768, 0x80008000u)]
    [InlineData(-1, 1, 0x0001FFFFu)]
    public void TargetedWheel_PacksSignedScreenCoordinates(int x, int y, uint expected)
    {
        var packed = unchecked((uint)EncodeScreenPointLParam(new DesktopPoint(x, y)).ToInt64());

        Assert.Equal(expected, packed);
    }

    [Theory]
    [InlineData(-32769, 0)]
    [InlineData(32768, 0)]
    [InlineData(0, -32769)]
    [InlineData(0, 32768)]
    public void TargetedWheel_RejectsCoordinatesOutsideSignedWords(int x, int y)
    {
        var error = Assert.Throws<TargetInvocationException>(() =>
            EncodeScreenPointLParam(new DesktopPoint(x, y)));

        Assert.IsType<InvalidOperationException>(error.InnerException);
    }

    [Fact]
    public void TargetedWheel_DispatchesExactlyOnceWithBoundedTimeoutFlags()
    {
        var calls = 0;
        (IntPtr ReturnValue, int Error) Sender(
            IntPtr window,
            uint message,
            UIntPtr wParam,
            IntPtr lParam,
            uint flags,
            uint timeout)
        {
            calls++;
            Assert.Equal(new IntPtr(0x123), window);
            Assert.Equal(0x020Au, message);
            Assert.Equal(0x00780000u, wParam.ToUInt64());
            Assert.Equal(new IntPtr(0x00640032), lParam);
            Assert.Equal(0x0023u, flags);
            Assert.Equal(100u, timeout);
            return (new IntPtr(1), 0);
        }

        SendWheelMessage(
            new IntPtr(0x123),
            new UIntPtr(0x00780000u),
            new IntPtr(0x00640032),
            Sender);

        Assert.Equal(1, calls);
    }

    [Fact]
    public void TargetedWheel_FailureIsNotRetriedAndReportsUnknownOutcome()
    {
        var calls = 0;
        (IntPtr ReturnValue, int Error) Sender(
            IntPtr window,
            uint message,
            UIntPtr wParam,
            IntPtr lParam,
            uint flags,
            uint timeout)
        {
            _ = window;
            _ = message;
            _ = wParam;
            _ = lParam;
            _ = flags;
            _ = timeout;
            calls++;
            return (IntPtr.Zero, 0);
        }

        var error = Assert.Throws<TargetInvocationException>(() => SendWheelMessage(
            new IntPtr(0x123), UIntPtr.Zero, IntPtr.Zero, Sender));

        Assert.Equal(1, calls);
        Assert.Contains("outcome is unknown", error.InnerException!.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(100, 200, 800, 600, true)]
    [InlineData(99, 200, 800, 600, false)]
    [InlineData(100, 199, 800, 600, false)]
    [InlineData(100, 200, 799, 600, false)]
    [InlineData(100, 200, 800, 599, false)]
    public void TargetedWheel_BindsReviewedClientGeometry(
        int clientX,
        int clientY,
        int clientWidth,
        int clientHeight,
        bool expected)
    {
        var target = new DesktopTarget(
            "machine", 1, 2, "0x3", @"C:\rift_x64.exe", new string('A', 64),
            true, 100, 200, 800, 600);

        Assert.Equal(expected, HasReviewedGeometry(target, clientX, clientY, clientWidth, clientHeight));
    }

    private static int SizeOfNested(string name)
    {
        var type = typeof(WindowsControlDesktop).GetNestedType(name, BindingFlags.NonPublic);
        Assert.NotNull(type);
        return Marshal.SizeOf(type);
    }

    private static string[] DecodePressedInputs(Func<int, short> getState)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "DecodePressedInputs", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        return Assert.IsType<string[]>(method.Invoke(null, [getState]));
    }

    private static CursorPreparation PlanCursorPreparation(
        DesktopPoint cursor,
        int clientX,
        int clientY,
        int clientWidth,
        int clientHeight,
        int deltaX,
        int deltaY) => Assert.IsType<CursorPreparation>(InvokeCursorPreparation(
            cursor, clientX, clientY, clientWidth, clientHeight, deltaX, deltaY));

    private static object? InvokeCursorPreparation(
        DesktopPoint cursor,
        int clientX,
        int clientY,
        int clientWidth,
        int clientHeight,
        int deltaX,
        int deltaY)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "PlanCursorPreparation", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        return method.Invoke(null, [cursor, clientX, clientY, clientWidth, clientHeight, deltaX, deltaY]);
    }

    private static void EnsureNoMouseButtonDown(Func<int, short> getState)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "EnsureNoMouseButtonDown", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        _ = method.Invoke(null, [getState]);
    }

    private static UIntPtr EncodeWheelWParam(int notches)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "EncodeWheelWParam", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        return Assert.IsType<UIntPtr>(method.Invoke(null, [notches]));
    }

    private static IntPtr EncodeScreenPointLParam(DesktopPoint point)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "EncodeScreenPointLParam", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        return Assert.IsType<IntPtr>(method.Invoke(null, [point]));
    }

    private static void SendWheelMessage(
        IntPtr window,
        UIntPtr wheelParameter,
        IntPtr pointParameter,
        Func<IntPtr, uint, UIntPtr, IntPtr, uint, uint, (IntPtr ReturnValue, int Error)> sender)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "SendWheelMessage", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        _ = method.Invoke(null, [window, wheelParameter, pointParameter, sender]);
    }

    private static bool HasReviewedGeometry(
        DesktopTarget target,
        int clientX,
        int clientY,
        int clientWidth,
        int clientHeight)
    {
        var method = typeof(WindowsControlDesktop).GetMethod(
            "HasReviewedGeometry", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(method);
        return Assert.IsType<bool>(method.Invoke(
            null,
            [target, clientX, clientY, clientWidth, clientHeight]));
    }
}
