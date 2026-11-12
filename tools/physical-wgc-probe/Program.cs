using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WgcSharp;

namespace PhysicalWgcProbe;

internal sealed record Options(
    string Mode, string Host, string ProcessName, int Pid, long ProcessStartTicks,
    string Sha256, nint Hwnd, string Backend, int TimeoutMilliseconds,
    string? Output, bool CaptureExplicitlyRequested)
{
    internal static Options Parse(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test")
            return new("self-test", "AMD-DESKTOP", "", 0, 0, "", 0, "wgc", 2000, null, false);
        if (args.Length == 0 || args[0] is not ("--inspect" or "--capture"))
            throw new ArgumentException("Choose --self-test, --inspect, or --capture.");
        var dict = new Dictionary<string, string>(StringComparer.Ordinal);
        var confirmed = false;
        for (int i = 1; i < args.Length; i++)
        {
            if (args[i] == "--allow-one-capture")
            {
                if (confirmed) throw new ArgumentException("Duplicate capture approval switch.");
                confirmed = true;
                continue;
            }
            if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Missing or unknown argument.");
            if (!dict.TryAdd(args[i], args[++i]))
                throw new ArgumentException("Duplicate argument.");
        }
        var permitted = new HashSet<string>(StringComparer.Ordinal)
        {
            "--host", "--process", "--pid", "--start-ticks", "--sha256",
            "--hwnd", "--backend", "--timeout-ms", "--out"
        };
        if (dict.Keys.Any(x => !permitted.Contains(x)))
            throw new ArgumentException("Unsupported argument.");
        static string Required(Dictionary<string, string> d, string k) =>
            d.TryGetValue(k, out var value) && value.Length > 0 ? value :
                throw new ArgumentException($"Missing {k}.");
        var host = Required(dict, "--host");
        if (!string.Equals(host, "AMD-DESKTOP", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("This probe is bound to AMD-DESKTOP only.");
        var processName = Required(dict, "--process");
        if (!System.Text.RegularExpressions.Regex.IsMatch(processName,
                @"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$"))
            throw new ArgumentException("Invalid process name.");
        if (!int.TryParse(Required(dict, "--pid"), out int pid) || pid <= 0)
            throw new ArgumentException("Invalid PID.");
        if (!long.TryParse(Required(dict, "--start-ticks"), out long ticks)
            || ticks <= 0 || ticks > DateTime.MaxValue.Ticks)
            throw new ArgumentException("Invalid process start epoch.");
        var hash = Required(dict, "--sha256").ToUpperInvariant();
        if (!System.Text.RegularExpressions.Regex.IsMatch(hash, "^[0-9A-F]{64}$"))
            throw new ArgumentException("Invalid executable SHA-256.");
        var hwndText = Required(dict, "--hwnd");
        var validHwnd = hwndText.StartsWith("0x", StringComparison.OrdinalIgnoreCase)
            ? long.TryParse(hwndText.AsSpan(2), System.Globalization.NumberStyles.HexNumber,
                System.Globalization.CultureInfo.InvariantCulture, out var ignored)
            : long.TryParse(hwndText, out _);
        if (!validHwnd) throw new ArgumentException("Invalid HWND.");
        var hwndValue = hwndText.StartsWith("0x", StringComparison.OrdinalIgnoreCase)
            ? Convert.ToInt64(hwndText[2..], 16)
            : long.Parse(hwndText);
        if (hwndValue <= 0) throw new ArgumentException("HWND must be positive.");
        var backend = dict.GetValueOrDefault("--backend", "wgc");
        if (backend is not ("wgc" or "dxgi"))
            throw new ArgumentException("Backend must be wgc or dxgi; never silently fall back.");
        if (!int.TryParse(dict.GetValueOrDefault("--timeout-ms", "2000"), out var timeout)
            || timeout < 250 || timeout > 4000)
            throw new ArgumentException("Capture timeout must be 250..4000 ms.");
        var output = dict.GetValueOrDefault("--out");
        if (args[0] == "--inspect")
        {
            if (confirmed || output is not null)
                throw new ArgumentException("--inspect never authorizes capture/output.");
        }
        else
        {
            if (!confirmed)
                throw new ArgumentException("--capture requires --allow-one-capture.");
            if (string.IsNullOrWhiteSpace(output) || !Path.IsPathFullyQualified(output)
                || !string.Equals(Path.GetExtension(output), ".png", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Capture output must be an absolute PNG path.");
        }
        return new(args[0][2..], host, processName, pid, ticks, hash,
            new nint(hwndValue), backend, timeout, output, confirmed);
    }
}

internal sealed record TargetInfo(
    int Pid, long StartTicks, string Sha256, long Hwnd,
    string ProcessName, int Width, int Height, bool Foreground, bool IsCloaked);

internal static class CapturePolicy
{
    private const string EvidenceDirectory =
        @"C:\work\workbridge-mcp\.tools\desktop-evidence";
    private const string LockPath =
        @"C:\work\workbridge-mcp\.tools\desktop-evidence\desktop-input-turn.lock";
    private const string AdmissionPath =
        @"C:\work\workbridge-mcp\.tools\desktop-evidence\desktop-turn-admission.lock";
    internal const string ArtifactRoot =
        @"C:\work\riftreader2\artifacts";

    internal static string? BlockReason(bool hasLock, bool quarantineExists)
        => hasLock || quarantineExists ? "desktop-turn-recovery-required" : null;

    internal static void RequireUnquarantined()
    {
        if (!Directory.Exists(EvidenceDirectory))
            throw new InvalidOperationException("shared-gui-evidence-directory-missing");
        if (BlockReason(File.Exists(LockPath) || File.Exists(AdmissionPath),
            Directory.EnumerateFiles(EvidenceDirectory, "desktop-turn-quarantine-*.json").Any())
            is { } reason)
            throw new InvalidOperationException(reason);
    }

    // This capture-only experiment never creates or releases the Workbridge
    // shared GUI locks. Their watchdog owner uses a different, durable stamp
    // contract. Snapshot-check the live lock and quarantine at both boundaries
    // and reject frames acquired across a newly occupied desktop turn.
}

internal static partial class Native
{
    [DllImport("user32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll", ExactSpelling = true)]
    internal static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
    [DllImport("user32.dll", ExactSpelling = true)]
    internal static extern nint GetForegroundWindow();
    [DllImport("user32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetClientRect(nint hwnd, out Rect rect);
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    internal static extern int DwmGetWindowAttribute(nint hwnd, uint attribute,
        out uint value, uint valueLength);
    [StructLayout(LayoutKind.Sequential)]
    internal struct Rect { public int Left, Top, Right, Bottom; }
}

internal static class Target
{
    internal static TargetInfo Inspect(Options options)
    {
        if (Environment.MachineName != options.Host)
            throw new InvalidOperationException("wrong-host");
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("windows-only");
        using var process = Process.GetProcessById(options.Pid);
        process.Refresh();
        if (process.HasExited || !string.Equals(process.ProcessName,
                options.ProcessName, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("process-name-or-pid-changed");
        var start = process.StartTime.ToUniversalTime().Ticks;
        if (start != options.ProcessStartTicks)
            throw new InvalidOperationException("process-epoch-changed");
        var path = process.MainModule?.FileName ??
            throw new InvalidOperationException("process-image-unavailable");
        var name = Path.GetFileNameWithoutExtension(path);
        if (!string.Equals(name, options.ProcessName, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("process-image-name-changed");
        string hash;
        using (var stream = File.OpenRead(path))
            hash = Convert.ToHexString(SHA256.HashData(stream));
        if (!string.Equals(hash, options.Sha256, StringComparison.Ordinal))
            throw new InvalidOperationException("process-image-sha-changed");
        if (!Native.IsWindow(options.Hwnd) || !Native.IsWindowVisible(options.Hwnd)
            || Native.IsIconic(options.Hwnd))
            throw new InvalidOperationException("window-absent-hidden-or-minimized");
        if (Native.GetWindowThreadProcessId(options.Hwnd, out var windowPid) == 0
            || windowPid != (uint)options.Pid)
            throw new InvalidOperationException("hwnd-owner-changed");
        if (!Native.GetClientRect(options.Hwnd, out var rect))
            throw new InvalidOperationException("window-client-geometry-unavailable");
        var width = rect.Right - rect.Left;
        var height = rect.Bottom - rect.Top;
        if (width < 64 || height < 64 || width > 4096 || height > 2160)
            throw new InvalidOperationException("window-client-dimensions-invalid");
        var cloaked = Native.DwmGetWindowAttribute(options.Hwnd, 14, out var state, 4) == 0
            && state != 0;
        if (cloaked) throw new InvalidOperationException("window-cloaked");
        return new(options.Pid, start, hash, options.Hwnd.ToInt64(), options.ProcessName,
            width, height, Native.GetForegroundWindow() == options.Hwnd, cloaked);
    }
}

internal static class Probe
{
    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = false,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private static int Main(string[] args)
    {
        try
        {
            var options = Options.Parse(args);
            if (options.Mode == "self-test")
                return SelfTest();
            // Deny any capture while an older GUI turn is unresolved, even if
            // the requested PID/HWND has disappeared or been reused.
            if (options.Mode == "capture")
                CapturePolicy.RequireUnquarantined();
            var before = Target.Inspect(options);
            if (options.Mode == "inspect")
            {
                Print(new {
                    status = "read-only-window-identity-pinned", machine = Environment.MachineName,
                    backend = options.Backend, target = before, inputSent = false,
                    imageCaptureAttempted = false, desktopCaptureApproved = false
                });
                return 0;
            }

            var output = Path.GetFullPath(options.Output!);
            var relative = Path.GetRelativePath(CapturePolicy.ArtifactRoot, output);
            if (relative == "." || relative == ".."
                || relative.StartsWith(".." + Path.DirectorySeparatorChar,
                    StringComparison.Ordinal) || Path.IsPathRooted(relative))
                throw new InvalidOperationException("capture-output-must-be-in-rr2-artifacts");
            var receipt = output + ".json";
            if (!Directory.Exists(Path.GetDirectoryName(output))
                || File.Exists(output) || File.Exists(receipt)
                || (File.GetAttributes(Path.GetDirectoryName(output)!) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("capture-output-path-invalid-or-already-used");
            CapturePolicy.RequireUnquarantined();
            var exact = Target.Inspect(options);
            if (before != exact)
                throw new InvalidOperationException("window-identity-changed-before-capture");
            var started = DateTimeOffset.UtcNow;
            var timer = Stopwatch.StartNew();
            using var image = WindowCapture.CaptureWindow(options.Hwnd,
                options.Backend == "wgc" ? CaptureStrategy.WgcOnly : CaptureStrategy.DxgiOnly,
                timeoutMs: options.TimeoutMilliseconds);
            timer.Stop();
            var completed = DateTimeOffset.UtcNow;
            if (image is null) throw new InvalidOperationException("gpu-capture-returned-no-frame");
            if (image.Width < 64 || image.Height < 64 || image.Width > 4096 || image.Height > 2160)
                throw new InvalidOperationException("gpu-capture-frame-dimensions-invalid");
            CapturePolicy.RequireUnquarantined();
            var after = Target.Inspect(options);
            if (exact != after)
                throw new InvalidOperationException("window-identity-changed-during-capture");
            var quality = SampleQuality(image);
            using var memory = new MemoryStream();
            image.Save(memory, ImageFormat.Png);
            var bytes = memory.ToArray();
            if (bytes.Length < 45 || bytes.Length > 8 * 1024 * 1024)
                throw new InvalidOperationException("gpu-capture-image-size-invalid");
            var imageHash = Convert.ToHexString(SHA256.HashData(bytes));
            var report = new {
                schemaVersion = 1, status = "unqualified-gpu-window-frame",
                machine = Environment.MachineName,
                requestedBackend = options.Backend,
                targetBefore = before, targetAfter = after,
                capturedStartedAtUtc = started, capturedCompletedAtUtc = completed,
                captureCallMilliseconds = timer.Elapsed.TotalMilliseconds,
                frameWidth = image.Width, frameHeight = image.Height,
                imageSha256 = imageHash, imageBytes = bytes.Length,
                outputPath = output, quality,
                inputSent = false, focusChangedByProbe = false,
                gameResponseVerified = false, bodyHeadingVerified = false,
                qualification = "Screenshot pixels only; gameplay response, camera-vs-body and frame freshness not established."
            };
            // New-only output; no overwrite and no implicit retry.
            using (var file = new FileStream(output, FileMode.CreateNew,
                       FileAccess.Write, FileShare.None))
            {
                file.Write(bytes);
                file.Flush(true);
            }
            using (var file = new FileStream(receipt, FileMode.CreateNew,
                       FileAccess.Write, FileShare.None))
            {
                var recordBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(report, Json) + "\n");
                file.Write(recordBytes);
                file.Flush(true);
            }
            Print(report);
            return 0;
        }
        catch (Exception error)
        {
            Print(new { status = "blocked", reason = error.Message,
                inputSent = false, frameAccepted = false });
            return 2;
        }
    }

    internal static object SampleQuality(Bitmap bitmap)
    {
        var sampleColors = new HashSet<int>();
        var total = 0;
        var veryDark = 0;
        long brightness = 0;
        for (int y = 0; y < bitmap.Height; y += Math.Max(1, bitmap.Height / 12))
            for (int x = 0; x < bitmap.Width; x += Math.Max(1, bitmap.Width / 20))
            {
                var c = bitmap.GetPixel(x, y);
                sampleColors.Add((c.R >> 4) << 8 | (c.G >> 4) << 4 | (c.B >> 4));
                var light = (c.R * 54 + c.G * 183 + c.B * 19) / 256;
                brightness += light;
                if (light < 12) veryDark++;
                total++;
            }
        return new {
            sampleCount = total, quantizedDistinctColors = sampleColors.Count,
            veryDarkFraction = (double)veryDark / total,
            meanBrightness = (double)brightness / total,
            potentiallyBlankOrBlack = sampleColors.Count < 4 || veryDark > total * 0.95
        };
    }

    private static int SelfTest()
    {
        int passed = 0;
        void Check(bool outcome, string label)
        {
            if (!outcome) throw new InvalidOperationException("self-test-" + label);
            passed++;
        }
        void MustReject(string[] a, string label)
        {
            try { _ = Options.Parse(a); }
            catch (ArgumentException) { passed++; return; }
            throw new InvalidOperationException("self-test-missing-rejection-" + label);
        }
        var valid = new[] { "--inspect", "--host", "AMD-DESKTOP", "--process", "notepad",
            "--pid", "123", "--start-ticks", "639299470183328173",
            "--sha256", new string('A', 64), "--hwnd", "0x100" };
        var opt = Options.Parse(valid);
        Check(opt.Mode == "inspect" && opt.Pid == 123 && opt.Hwnd == 0x100
              && !opt.CaptureExplicitlyRequested, "inspect-parse");
        MustReject(valid.Take(1).Concat(valid.Skip(3)).ToArray(), "host-required");
        MustReject(valid.Concat(["--backend", "printwindow"]).ToArray(), "unsupported-backend");
        MustReject(valid.Concat(["--out", "C:\\temp\\hello.png"]).ToArray(), "inspect-output");
        MustReject(new[] { "--capture" }.Concat(valid.Skip(1)).ToArray(), "capture-approval-required");
        Check(CapturePolicy.BlockReason(hasLock: false, quarantineExists: false) is null,
            "clear-gui");
        Check(CapturePolicy.BlockReason(hasLock: true, quarantineExists: false) is not null,
            "locked-gui");
        Check(CapturePolicy.BlockReason(hasLock: false, quarantineExists: true) is not null,
            "quarantined-gui");
        using var bitmap = new Bitmap(80, 80);
        using (var canvas = Graphics.FromImage(bitmap))
        {
            canvas.Clear(Color.Black);
            canvas.FillRectangle(Brushes.White, 0, 0, 40, 40);
            canvas.FillRectangle(Brushes.Red, 40, 0, 40, 40);
            canvas.FillRectangle(Brushes.Blue, 0, 40, 40, 40);
        }
        var quality = SampleQuality(bitmap);
        Check(quality is not null, "synthetic-image-quality");
        Print(new { status = "offline-self-test-passed",
            passed, inputSent = false, frameCaptured = false });
        return 0;
    }

    private static void Print(object output) => Console.WriteLine(JsonSerializer.Serialize(output, Json));
}
