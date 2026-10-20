using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace RiftReader2.Live.Control;

public sealed record DesktopTarget(
    string MachineName,
    int ProcessId,
    long ProcessStartUtcTicks,
    string WindowHandle,
    string ExecutablePath,
    string ExecutableSha256,
    bool IsForeground,
    int ClientX,
    int ClientY,
    int ClientWidth,
    int ClientHeight);

public readonly record struct DesktopPoint(int X, int Y);

public enum MouseButton
{
    Left,
    Right
}

public static class WindowsControlDesktop
{
    private const int MaxCaptureWidth = 4096;
    private const int MaxCaptureHeight = 2160;
    private const int BitmapFileHeaderSize = 14;
    private const int BitmapInfoHeaderSize = 40;
    private const uint DibRgbColors = 0;
    private const uint SourceCopy = 0x00CC0020;
    private const uint WindowOwner = 4;
    private const uint RootWindow = 2;

    private const uint InputMouse = 0;
    private const uint InputKeyboard = 1;
    private const uint KeyEventKeyUp = 0x0002;
    private const uint KeyEventScanCode = 0x0008;
    private const uint MouseEventMove = 0x0001;
    private const uint MouseEventLeftDown = 0x0002;
    private const uint MouseEventLeftUp = 0x0004;
    private const uint MouseEventRightDown = 0x0008;
    private const uint MouseEventRightUp = 0x0010;
    private const uint MouseEventWheel = 0x0800;
    private const int WheelDelta = 120;

    private static readonly ConcurrentDictionary<ExecutableCacheKey, string> ExecutableHashes = new();

    public static DesktopTarget Inspect(
        string expectedProcessName,
        string expectedExecutablePath,
        string expectedExecutableSha256)
    {
        EnsureWindows();
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedProcessName);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedExecutablePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedExecutableSha256);

        var processName = Path.GetFileNameWithoutExtension(expectedProcessName.Trim());
        var expectedPath = Path.GetFullPath(expectedExecutablePath);
        var expectedHash = NormalizeSha256(expectedExecutableSha256);
        var processes = Process.GetProcessesByName(processName);
        try
        {
            if (processes.Length != 1)
                throw new InvalidOperationException(
                    $"Expected exactly one '{processName}' process, but found {processes.Length}.");

            var process = processes[0];
            process.Refresh();
            if (process.HasExited)
                throw new InvalidOperationException($"The '{processName}' process exited during inspection.");

            var processId = process.Id;
            var startTicks = process.StartTime.ToUniversalTime().Ticks;
            var actualPath = process.MainModule?.FileName;
            if (string.IsNullOrWhiteSpace(actualPath))
                throw new InvalidOperationException("The process executable path is unavailable.");
            actualPath = Path.GetFullPath(actualPath);
            if (!string.Equals(expectedPath, actualPath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException(
                    $"The executable path does not match the expected target. Expected '{expectedPath}', found '{actualPath}'.");

            var actualHash = GetExecutableSha256(processId, startTicks, actualPath);
            if (!string.Equals(expectedHash, actualHash, StringComparison.Ordinal))
                throw new InvalidOperationException(
                    $"The executable SHA-256 does not match the expected target. Expected '{expectedHash}', found '{actualHash}'.");

            var window = FindProcessWindow(processId);
            var geometry = GetClientGeometry(window);
            RevalidateProcess(process, processId, startTicks, actualPath);

            return new DesktopTarget(
                Environment.MachineName,
                processId,
                startTicks,
                FormatWindowHandle(window),
                actualPath,
                actualHash,
                IsTargetForeground(window),
                geometry.X,
                geometry.Y,
                geometry.Width,
                geometry.Height);
        }
        finally
        {
            foreach (var process in processes)
                process.Dispose();
        }
    }

    public static byte[] CaptureBmp(DesktopTarget target)
    {
        ArgumentNullException.ThrowIfNull(target);
        EnsureWindows();
        var window = ParseWindowHandle(target.WindowHandle);
        RevalidateTarget(target, window);
        if (!IsTargetForeground(window))
            throw new InvalidOperationException("The desktop target must be foreground before centering the cursor.");
        var geometry = GetClientGeometry(window);
        ValidateCaptureDimensions(geometry.Width, geometry.Height);

        var windowDc = NativeMethods.GetDC(window);
        if (windowDc == IntPtr.Zero)
            throw LastWin32("GetDC failed for the target window.");

        IntPtr memoryDc = IntPtr.Zero;
        IntPtr bitmap = IntPtr.Zero;
        IntPtr previousObject = IntPtr.Zero;
        try
        {
            memoryDc = NativeMethods.CreateCompatibleDC(windowDc);
            if (memoryDc == IntPtr.Zero)
                throw LastWin32("CreateCompatibleDC failed.");
            bitmap = NativeMethods.CreateCompatibleBitmap(windowDc, geometry.Width, geometry.Height);
            if (bitmap == IntPtr.Zero)
                throw LastWin32("CreateCompatibleBitmap failed.");
            previousObject = NativeMethods.SelectObject(memoryDc, bitmap);
            if (previousObject == IntPtr.Zero || previousObject == new IntPtr(-1))
                throw LastWin32("SelectObject failed.");
            if (!NativeMethods.BitBlt(
                    memoryDc, 0, 0, geometry.Width, geometry.Height, windowDc, 0, 0, SourceCopy))
                throw LastWin32("BitBlt failed.");

            return EncodeBitmap(bitmap, memoryDc, geometry.Width, geometry.Height);
        }
        finally
        {
            if (previousObject != IntPtr.Zero && memoryDc != IntPtr.Zero)
                _ = NativeMethods.SelectObject(memoryDc, previousObject);
            if (bitmap != IntPtr.Zero)
                _ = NativeMethods.DeleteObject(bitmap);
            if (memoryDc != IntPtr.Zero)
                _ = NativeMethods.DeleteDC(memoryDc);
            _ = NativeMethods.ReleaseDC(window, windowDc);
        }
    }

    public static void SendKeys(IEnumerable<char> keys, bool down)
    {
        ArgumentNullException.ThrowIfNull(keys);
        EnsureWindows();
        var materialized = keys.ToArray();
        if (materialized.Length == 0)
            throw new ArgumentException("At least one key is required.", nameof(keys));
        var inputs = new Input[materialized.Length];
        for (var index = 0; index < materialized.Length; index++)
            inputs[index] = Keyboard(ScanCodeFor(materialized[index]), down);
        Send(inputs, "keyboard");
    }

    public static void SendMouseButton(MouseButton button, bool down)
    {
        EnsureWindows();
        var flags = (button, down) switch
        {
            (MouseButton.Left, true) => MouseEventLeftDown,
            (MouseButton.Left, false) => MouseEventLeftUp,
            (MouseButton.Right, true) => MouseEventRightDown,
            (MouseButton.Right, false) => MouseEventRightUp,
            _ => throw new ArgumentOutOfRangeException(nameof(button), button, "Unsupported mouse button.")
        };
        Send([Mouse(flags: flags)], "mouse button");
    }

    public static void MoveRelative(int dx, int dy)
    {
        EnsureWindows();
        if (dx == 0 && dy == 0)
            return;
        Send([Mouse(dx, dy, flags: MouseEventMove)], "relative mouse movement");
    }

    public static void Wheel(int notches)
    {
        EnsureWindows();
        if (notches == 0)
            return;
        var wheelData = checked(notches * WheelDelta);
        Send([Mouse(mouseData: unchecked((uint)wheelData), flags: MouseEventWheel)], "mouse wheel");
    }

    public static DesktopPoint GetCursorPosition()
    {
        EnsureWindows();
        if (!NativeMethods.GetCursorPos(out var point))
            throw LastWin32("GetCursorPos failed.");
        return new DesktopPoint(point.X, point.Y);
    }

    public static void SetCursorPosition(int x, int y)
    {
        EnsureWindows();
        if (!NativeMethods.SetCursorPos(x, y))
            throw LastWin32("SetCursorPos failed.");
    }

    public static DesktopPoint CenterCursor(DesktopTarget target)
    {
        ArgumentNullException.ThrowIfNull(target);
        EnsureWindows();
        var window = ParseWindowHandle(target.WindowHandle);
        RevalidateTarget(target, window);
        var geometry = GetClientGeometry(window);
        var center = GetClientCenter(geometry.X, geometry.Y, geometry.Width, geometry.Height);
        var previous = GetCursorPosition();
        SetCursorPosition(center.X, center.Y);
        return previous;
    }

    public static ushort ScanCodeFor(char key) => char.ToLowerInvariant(key) switch
    {
        'q' => 0x10,
        'w' => 0x11,
        'e' => 0x12,
        'a' => 0x1E,
        's' => 0x1F,
        'd' => 0x20,
        _ => throw new ArgumentOutOfRangeException(nameof(key), key, "Only W, A, S, D, Q, and E are supported.")
    };

    private static void EnsureWindows()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows desktop control requires Windows.");
    }

    private static string NormalizeSha256(string value)
    {
        var normalized = value.Trim().ToUpperInvariant();
        if (normalized.Length != 64 || normalized.Any(character => !Uri.IsHexDigit(character)))
            throw new ArgumentException("Expected executable SHA-256 must be 64 hexadecimal characters.", nameof(value));
        return normalized;
    }

    private static string GetExecutableSha256(int processId, long startTicks, string executablePath)
    {
        var info = new FileInfo(executablePath);
        var key = new ExecutableCacheKey(
            processId,
            startTicks,
            executablePath,
            info.Length,
            info.LastWriteTimeUtc.Ticks);
        return ExecutableHashes.GetOrAdd(key, static item =>
        {
            using var stream = new FileStream(
                item.Path, FileMode.Open, FileAccess.Read, FileShare.Read, 128 * 1024, FileOptions.SequentialScan);
            return Convert.ToHexString(SHA256.HashData(stream));
        });
    }

    private static IntPtr FindProcessWindow(int processId)
    {
        IntPtr selected = IntPtr.Zero;
        long selectedArea = -1;
        if (!NativeMethods.EnumWindows((window, parameter) =>
            {
                _ = parameter;
                _ = NativeMethods.GetWindowThreadProcessId(window, out var candidateProcessId);
                if (candidateProcessId != processId ||
                    !NativeMethods.IsWindowVisible(window) ||
                    NativeMethods.IsIconic(window) ||
                    NativeMethods.GetWindow(window, WindowOwner) != IntPtr.Zero ||
                    !NativeMethods.GetClientRect(window, out var rect))
                    return true;
                var width = rect.Right - rect.Left;
                var height = rect.Bottom - rect.Top;
                var area = (long)width * height;
                if (width > 0 && height > 0 && area > selectedArea)
                {
                    selected = window;
                    selectedArea = area;
                }
                return true;
            }, IntPtr.Zero))
            throw LastWin32("EnumWindows failed.");
        if (selected == IntPtr.Zero)
            throw new InvalidOperationException("No visible top-level client window belongs to the target process.");
        return selected;
    }

    private static ClientGeometry GetClientGeometry(IntPtr window)
    {
        if (!NativeMethods.GetClientRect(window, out var rect))
            throw LastWin32("GetClientRect failed for the target window.");
        var origin = new Point();
        if (!NativeMethods.ClientToScreen(window, ref origin))
            throw LastWin32("ClientToScreen failed for the target window.");
        return new ClientGeometry(origin.X, origin.Y, rect.Right - rect.Left, rect.Bottom - rect.Top);
    }

    private static DesktopPoint GetClientCenter(int x, int y, int width, int height)
    {
        if (width <= 0 || height <= 0)
            throw new InvalidOperationException("The target client area is empty.");
        return new DesktopPoint(checked(x + (width / 2)), checked(y + (height / 2)));
    }

    private static bool IsTargetForeground(IntPtr targetWindow)
    {
        var foreground = NativeMethods.GetForegroundWindow();
        if (foreground == IntPtr.Zero)
            return false;
        if (foreground == targetWindow)
            return true;
        return NativeMethods.GetAncestor(foreground, RootWindow) == targetWindow;
    }

    private static void ValidateCaptureDimensions(int width, int height)
    {
        if (width is <= 0 or > MaxCaptureWidth || height is <= 0 or > MaxCaptureHeight)
            throw new InvalidOperationException(
                $"Client capture dimensions {width}x{height} are outside the supported 1..{MaxCaptureWidth} by 1..{MaxCaptureHeight} bounds.");
    }

    private static void RevalidateTarget(DesktopTarget target, IntPtr window)
    {
        if (!string.Equals(target.MachineName, Environment.MachineName, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The desktop target belongs to a different machine.");
        if (!NativeMethods.IsWindow(window))
            throw new InvalidOperationException("The desktop target window no longer exists.");
        if (!NativeMethods.IsWindowVisible(window) || NativeMethods.IsIconic(window))
            throw new InvalidOperationException("The desktop target window is hidden or minimized.");
        _ = NativeMethods.GetWindowThreadProcessId(window, out var windowProcessId);
        if (windowProcessId != target.ProcessId)
            throw new InvalidOperationException("The desktop target window no longer belongs to the bound process.");

        using var process = Process.GetProcessById(target.ProcessId);
        RevalidateProcess(process, target.ProcessId, target.ProcessStartUtcTicks, target.ExecutablePath);
        var currentHash = GetExecutableSha256(
            target.ProcessId,
            target.ProcessStartUtcTicks,
            target.ExecutablePath);
        if (!string.Equals(NormalizeSha256(target.ExecutableSha256), currentHash, StringComparison.Ordinal))
            throw new InvalidOperationException("The desktop target executable hash changed.");
    }

    private static void RevalidateProcess(
        Process process,
        int expectedProcessId,
        long expectedStartTicks,
        string expectedPath)
    {
        process.Refresh();
        var actualPath = process.MainModule?.FileName;
        if (process.HasExited ||
            process.Id != expectedProcessId ||
            process.StartTime.ToUniversalTime().Ticks != expectedStartTicks ||
            string.IsNullOrWhiteSpace(actualPath) ||
            !string.Equals(Path.GetFullPath(actualPath), expectedPath, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The desktop target process identity changed during inspection.");
    }

    private static byte[] EncodeBitmap(IntPtr bitmap, IntPtr memoryDc, int width, int height)
    {
        ValidateCaptureDimensions(width, height);
        var pixelLength = checked(width * height * 4);
        var pixels = new byte[pixelLength];
        var info = new BitmapInfo
        {
            Header = new BitmapInfoHeader
            {
                Size = BitmapInfoHeaderSize,
                Width = width,
                Height = -height,
                Planes = 1,
                BitCount = 32,
                Compression = 0,
                SizeImage = (uint)pixelLength
            }
        };
        var scanLines = NativeMethods.GetDIBits(
            memoryDc, bitmap, 0, (uint)height, pixels, ref info, DibRgbColors);
        if (scanLines != height)
            throw LastWin32($"GetDIBits returned {scanLines} of {height} scan lines.");

        var result = new byte[checked(BitmapFileHeaderSize + BitmapInfoHeaderSize + pixelLength)];
        WriteBitmapHeader(result, width, height, pixelLength);
        pixels.CopyTo(result, BitmapFileHeaderSize + BitmapInfoHeaderSize);
        return result;
    }

    private static void WriteBitmapHeader(Span<byte> output, int width, int height, int pixelLength)
    {
        ValidateCaptureDimensions(width, height);
        if (pixelLength != checked(width * height * 4) ||
            output.Length < BitmapFileHeaderSize + BitmapInfoHeaderSize + pixelLength)
            throw new ArgumentException("The bitmap buffer size does not match its dimensions.", nameof(output));

        output[0] = (byte)'B';
        output[1] = (byte)'M';
        BinaryPrimitives.WriteUInt32LittleEndian(output[2..], (uint)output.Length);
        BinaryPrimitives.WriteUInt32LittleEndian(output[10..], BitmapFileHeaderSize + BitmapInfoHeaderSize);
        BinaryPrimitives.WriteUInt32LittleEndian(output[14..], BitmapInfoHeaderSize);
        BinaryPrimitives.WriteInt32LittleEndian(output[18..], width);
        BinaryPrimitives.WriteInt32LittleEndian(output[22..], -height);
        BinaryPrimitives.WriteUInt16LittleEndian(output[26..], 1);
        BinaryPrimitives.WriteUInt16LittleEndian(output[28..], 32);
        BinaryPrimitives.WriteUInt32LittleEndian(output[34..], (uint)pixelLength);
    }

    private static Input Keyboard(ushort scanCode, bool down) => new()
    {
        Type = InputKeyboard,
        Data = new InputUnion
        {
            Keyboard = new KeyboardInput
            {
                ScanCode = scanCode,
                Flags = KeyEventScanCode | (down ? 0u : KeyEventKeyUp)
            }
        }
    };

    private static Input Mouse(int dx = 0, int dy = 0, uint mouseData = 0, uint flags = 0) => new()
    {
        Type = InputMouse,
        Data = new InputUnion
        {
            Mouse = new MouseInput { Dx = dx, Dy = dy, MouseData = mouseData, Flags = flags }
        }
    };

    private static void Send(Input[] inputs, string operation)
    {
        var sent = NativeMethods.SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<Input>());
        if (sent != inputs.Length)
            throw LastWin32(
                $"SendInput delivered {sent} of {inputs.Length} events for {operation}; the caller must release the full intended input set.");
    }

    private static string FormatWindowHandle(IntPtr window) => $"0x{window.ToInt64():X}";

    private static IntPtr ParseWindowHandle(string value)
    {
        if (string.IsNullOrWhiteSpace(value) ||
            !long.TryParse(
                value.AsSpan().StartsWith("0x", StringComparison.OrdinalIgnoreCase) ? value.AsSpan(2) : value.AsSpan(),
                System.Globalization.NumberStyles.AllowHexSpecifier,
                System.Globalization.CultureInfo.InvariantCulture,
                out var parsed) ||
            parsed == 0)
            throw new InvalidOperationException("The desktop target window handle is invalid.");
        return new IntPtr(parsed);
    }

    private static Win32Exception LastWin32(string message) =>
        new(Marshal.GetLastWin32Error(), message);

    private sealed record ExecutableCacheKey(
        int ProcessId,
        long ProcessStartUtcTicks,
        string Path,
        long Length,
        long LastWriteUtcTicks);

    private readonly record struct ClientGeometry(int X, int Y, int Width, int Height);

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapInfoHeader
    {
        public uint Size;
        public int Width;
        public int Height;
        public ushort Planes;
        public ushort BitCount;
        public uint Compression;
        public uint SizeImage;
        public int XPixelsPerMeter;
        public int YPixelsPerMeter;
        public uint ColorsUsed;
        public uint ColorsImportant;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapInfo
    {
        public BitmapInfoHeader Header;
    }

    [StructLayout(LayoutKind.Explicit, Size = 40)]
    private struct Input
    {
        [FieldOffset(0)] public uint Type;
        [FieldOffset(8)] public InputUnion Data;
    }

    [StructLayout(LayoutKind.Explicit, Size = 32)]
    private struct InputUnion
    {
        [FieldOffset(0)] public MouseInput Mouse;
        [FieldOffset(0)] public KeyboardInput Keyboard;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MouseInput
    {
        public int Dx;
        public int Dy;
        public uint MouseData;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardInput
    {
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    private static class NativeMethods
    {
        internal delegate bool EnumWindowsProc(IntPtr window, IntPtr parameter);

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);

        [DllImport("user32.dll")]
        internal static extern uint GetWindowThreadProcessId(IntPtr window, out int processId);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool IsWindowVisible(IntPtr window);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool IsIconic(IntPtr window);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool IsWindow(IntPtr window);

        [DllImport("user32.dll")]
        internal static extern IntPtr GetWindow(IntPtr window, uint command);

        [DllImport("user32.dll")]
        internal static extern IntPtr GetAncestor(IntPtr window, uint flags);

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetClientRect(IntPtr window, out Rect rect);

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ClientToScreen(IntPtr window, ref Point point);

        [DllImport("user32.dll")]
        internal static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetCursorPos(out Point point);

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool SetCursorPos(int x, int y);

        [DllImport("user32.dll", SetLastError = true)]
        internal static extern IntPtr GetDC(IntPtr window);

        [DllImport("user32.dll", SetLastError = true)]
        internal static extern int ReleaseDC(IntPtr window, IntPtr deviceContext);

        [DllImport("user32.dll", SetLastError = true)]
        internal static extern uint SendInput(uint inputCount, [In] Input[] inputs, int inputSize);

        [DllImport("gdi32.dll", SetLastError = true)]
        internal static extern IntPtr CreateCompatibleDC(IntPtr deviceContext);

        [DllImport("gdi32.dll", SetLastError = true)]
        internal static extern IntPtr CreateCompatibleBitmap(IntPtr deviceContext, int width, int height);

        [DllImport("gdi32.dll", SetLastError = true)]
        internal static extern IntPtr SelectObject(IntPtr deviceContext, IntPtr value);

        [DllImport("gdi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool DeleteObject(IntPtr value);

        [DllImport("gdi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool DeleteDC(IntPtr deviceContext);

        [DllImport("gdi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool BitBlt(
            IntPtr destination,
            int destinationX,
            int destinationY,
            int width,
            int height,
            IntPtr source,
            int sourceX,
            int sourceY,
            uint rasterOperation);

        [DllImport("gdi32.dll", SetLastError = true)]
        internal static extern int GetDIBits(
            IntPtr deviceContext,
            IntPtr bitmap,
            uint startScan,
            uint scanLines,
            [Out] byte[] bits,
            ref BitmapInfo bitmapInfo,
            uint usage);
    }
}
