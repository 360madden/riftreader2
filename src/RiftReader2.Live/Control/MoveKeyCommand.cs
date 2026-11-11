using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live.Control;

/// <summary>
/// Disposable operator CLI for bounded physical RIFT key holds. No background
/// service, VM dependency, route scheduling or addon focus protocol.
/// </summary>
internal static class MoveKeyCommand
{
    internal sealed record Options(
        int Pid, string[] Keys, int HoldMilliseconds, bool Focus, bool Execute,
        bool Json, long? ExpectedStartTicks, string? ExpectedSha256, bool MeasureXyz);

    internal sealed record XyzSample(
        DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
        string UnitKey, float X, float Y, float Z);

    internal sealed record XyzDelta(double X, double Y, double Z);

    internal sealed record XyzFeedback(
        string Status, XyzSample? BeforeXYZ, XyzSample? AfterXYZ,
        XyzDelta? DeltaXYZ, double? PlanarDisplacementCandidate,
        bool MovementCandidate, double? CaptureGapSeconds, string? Reason = null)
    {
        public bool GameResponseVerified => false;
        public string Qualification =>
            "Cached native XYZ candidates; not independent proof that RIFT consumed Windows input.";
    }

    private const string Usage =
        "move-key --pid PID --key w[,e] [--hold-ms 1000] [--focus] [--execute] [--json] [--measure-xyz]"
        + " [--expect-start-ticks TICKS] [--expect-sha256 HASH]";

    internal static Options Parse(string[] args)
    {
        int? pid = null;
        string[]? keys = null;
        int hold = 1000;
        bool focus = false, execute = false, json = false, measureXyz = false;
        long? expectedTicks = null;
        string? expectedSha = null;
        var seen = new HashSet<string>(StringComparer.Ordinal);

        for (var i = 0; i < args.Length; i++)
        {
            var option = args[i];
            if (!seen.Add(option))
                throw new InvalidDataException($"Repeated option: {option}");
            if (option is "--focus" or "--execute" or "--json" or "--measure-xyz")
            {
                if (option == "--focus") focus = true;
                if (option == "--execute") execute = true;
                if (option == "--json") json = true;
                if (option == "--measure-xyz") measureXyz = true;
                continue;
            }
            if (i + 1 >= args.Length)
                throw new InvalidDataException($"Missing value for {option}.");
            var value = args[++i];
            switch (option)
            {
                case "--pid":
                    if (!int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var parsedPid)
                        || parsedPid <= 0)
                        throw new InvalidDataException("PID must be a positive integer.");
                    pid = parsedPid;
                    break;
                case "--key":
                    keys = value.Split(',', StringSplitOptions.None);
                    break;
                case "--hold-ms":
                    if (!int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out hold))
                        throw new InvalidDataException("Hold duration must be an integer in milliseconds.");
                    break;
                case "--expect-start-ticks":
                    if (!long.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks)
                        || ticks <= 0 || ticks > DateTime.MaxValue.Ticks)
                        throw new InvalidDataException("Invalid expected process start ticks.");
                    expectedTicks = ticks;
                    break;
                case "--expect-sha256":
                    if (value.Length != 64 || !value.All(Uri.IsHexDigit))
                        throw new InvalidDataException("Expected SHA-256 must contain 64 hex digits.");
                    expectedSha = value.ToUpperInvariant();
                    break;
                default:
                    throw new InvalidDataException($"Unknown option: {option}");
            }
        }

        if (pid is null || keys is null)
            throw new InvalidDataException("Exact --pid and --key are required.");
        // Reuse the input engine's actual six-key, conflict and hold validation.
        BoundedControlExecutor.Validate(new ControlAction(keys, hold));
        return new Options(pid.Value, keys, hold, focus, execute, json, expectedTicks, expectedSha, measureXyz);
    }

    internal static async Task<int> RunAsync(string[] args, CancellationToken cancellationToken)
    {
        var json = args.Contains("--json", StringComparer.Ordinal);
        try
        {
            var options = Parse(args);
            if (!options.Execute)
            {
                Report(options.Json, new
                {
                    status = "preview-only", machine = Environment.MachineName,
                    processId = options.Pid, keys = options.Keys, holdMilliseconds = options.HoldMilliseconds,
                    focusRequested = options.Focus, measureXyzRequested = options.MeasureXyz, inputSent = false,
                    instruction = "Add --execute to send one bounded manual pulse."
                });
                return 0;
            }

            if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess)
                throw new PlatformNotSupportedException("This helper requires 64-bit Windows.");

            var ownerName = "Local\\RiftReader2-Control-" +
                Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes("rift_x64")))[..16];
            using var owner = new Semaphore(1, 1, ownerName);
            if (!owner.WaitOne(0))
                throw new InvalidOperationException("Another RR2 control helper already owns game input.");
            try
            {
                return await ExecuteAsync(options, cancellationToken);
            }
            finally { owner.Release(); }
        }
        catch (Exception exception)
        {
            if (json)
                Report(true, new { status = "blocked", inputSent = false,
                    reason = exception.Message, errorType = exception.GetType().Name });
            else
                Console.Error.WriteLine($"move-key blocked: {exception.Message}\nUsage: {Usage}");
            return 2;
        }
    }

    private static async Task<int> ExecuteAsync(Options options, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        using var process = Process.GetProcessById(options.Pid);
        process.Refresh();
        if (process.HasExited || !string.Equals(process.ProcessName, "rift_x64", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("PID does not identify a running rift_x64 process.");
        var startTicks = process.StartTime.ToUniversalTime().Ticks;
        if (options.ExpectedStartTicks is long expectedTicks && expectedTicks != startTicks)
            throw new InvalidOperationException("RIFT process epoch does not match --expect-start-ticks.");
        var path = process.MainModule?.FileName
            ?? throw new InvalidOperationException("Cannot resolve game executable path.");
        if (!string.Equals(Path.GetFileName(path), "rift_x64.exe", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Selected process executable is not rift_x64.exe.");
        var sha = WindowsControlDesktop.GetFreshExecutableSha256(path);
        if (options.ExpectedSha256 is not null
            && !string.Equals(options.ExpectedSha256, sha, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("RIFT executable hash changed.");
        if (options.MeasureXyz && !string.Equals(sha,
            CurrentBuildPositionSampleCommand.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                "Native XYZ measurement is unavailable for this RIFT build; no game input sent.");

        DesktopTarget Inspect() => WindowsControlDesktop.InspectPinned("rift_x64", path, sha,
            options.Pid, startTicks);
        var target = Inspect();
        if (!target.IsForeground && options.Focus)
        {
            var handle = new IntPtr(long.Parse(target.WindowHandle.AsSpan(2),
                NumberStyles.HexNumber, CultureInfo.InvariantCulture));
            if (!SetForegroundWindow(handle))
                throw new InvalidOperationException("Windows refused to foreground the RIFT window.");
            var timer = Stopwatch.StartNew();
            while (timer.ElapsedMilliseconds < 600)
            {
                token.ThrowIfCancellationRequested();
                var observed = Inspect();
                if (observed.IsForeground)
                    break;
                await Task.Delay(30, token);
            }
        }
        var ready = Inspect();
        if (!ready.IsForeground)
            throw new InvalidOperationException("RIFT is not foreground; use --focus or focus it manually.");
        if (target with { IsForeground = true } != ready)
            throw new InvalidOperationException("Selected RIFT window or geometry changed before input.");

        var otherInputs = WindowsControlDesktop.ReadPressedInputs();
        if (otherInputs.Any())
            throw new InvalidOperationException("Desktop inputs already held: " + string.Join(", ", otherInputs));
        token.ThrowIfCancellationRequested();
        // An unavailable BEFORE capture blocks the pulse; an unavailable AFTER
        // capture never conceals a completed action or causes it to be repeated.
        var before = options.MeasureXyz
            ? await CaptureXyzAsync(options.Pid, startTicks, token) : null;
        if (before is not null && !Inspect().IsForeground)
            throw new InvalidOperationException("RIFT lost foreground during native XYZ pre-capture.");
        using var input = new KeyInput(WindowsControlDesktop.PinInputTarget(ready));
        var action = new ControlAction(options.Keys, options.HoldMilliseconds);
        var result = await new BoundedControlExecutor(input).ExecuteAsync(action, token);
        var success = result.DeliverySucceeded && result.ReleaseSucceeded
            && !result.Cancelled && !result.TargetLost;
        XyzFeedback? xyzFeedback = null;
        if (before is not null)
        {
            try
            {
                var after = await CaptureXyzAsync(options.Pid, startTicks, token);
                xyzFeedback = CompareXyz(before, after);
            }
            catch (Exception exception)
            {
                xyzFeedback = new XyzFeedback("unavailable-after-pulse", before, null,
                    null, null, false, null, exception.Message);
            }
        }
        Report(options.Json, new
        {
            status = success ? "input-inserted-game-response-unverified" : "input-uncertain",
            machine = ready.MachineName, processId = ready.ProcessId,
            processStartUtcTicks = ready.ProcessStartUtcTicks,
            executableSha256 = ready.ExecutableSha256,
            keys = options.Keys, holdMilliseconds = options.HoldMilliseconds,
            windowsInputInserted = result.DeliverySucceeded,
            releaseSucceeded = result.ReleaseSucceeded,
            targetLost = result.TargetLost, cancelled = result.Cancelled,
            observedMilliseconds = Math.Round(result.ObservedDuration.TotalMilliseconds, 1),
            gameResponseVerified = false, xyzFeedback, result.Error
        });
        return success ? 0 : 2;
    }

    private static async Task<XyzSample> CaptureXyzAsync(
        int pid, long startTicks, CancellationToken token)
    {
        var build = CurrentBuildPositionSampleCommand.GameSha256;
        await using var lease = await NativeReadFileLease.AcquireAsync(
            pid, startTicks, build, TimeSpan.FromSeconds(1), token);
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            pid, startTicks, build, token);
        var started = DateTimeOffset.UtcNow;
        var owned = CurrentBuildPositionCandidateReader.ReadOwned(session);
        var invalidated = await session.RevalidateAsync(token);
        if (invalidated is not null)
            throw new InvalidDataException("Native XYZ process identity changed: " + invalidated);
        var completed = DateTimeOffset.UtcNow;
        return new XyzSample(started, completed, owned.UnitKeyText,
            owned.Position.X, owned.Position.Y, owned.Position.Z);
    }

    internal static XyzFeedback CompareXyz(XyzSample before, XyzSample after)
    {
        if (!string.Equals(before.UnitKey, after.UnitKey, StringComparison.Ordinal))
            return new XyzFeedback("unavailable", before, after, null, null, false,
                null, "Native XYZ owner changed between captures.");
        var gap = (after.StartedAtUtc - before.CompletedAtUtc).TotalSeconds;
        if (gap <= 0 || gap > 30)
            return new XyzFeedback("unavailable", before, after, null, null, false,
                gap, "Native XYZ capture gap is invalid.");
        var delta = new XyzDelta(after.X - before.X, after.Y - before.Y, after.Z - before.Z);
        var planar = Math.Sqrt(delta.X * delta.X + delta.Z * delta.Z);
        if (!double.IsFinite(planar) || !double.IsFinite(delta.Y))
            return new XyzFeedback("unavailable", before, after, null, null, false,
                gap, "Native XYZ displacement is not finite.");
        return new XyzFeedback("candidate-native-xyz-feedback", before, after, delta,
            planar, planar >= 0.03, gap);
    }

    private sealed class KeyInput(WindowsControlDesktop.PinnedInputTarget pinned) : IControlInput, IDisposable
    {
        public bool IsTargetCurrent() => pinned.IsCurrent();
        public void KeyDown(string key)
        {
            if (!pinned.IsCurrent())
                throw new InvalidOperationException("RIFT window lost identity or foreground before key down.");
            WindowsControlDesktop.SendKeys(key, true);
        }
        // Never condition key-up on focus or process identity: release is unconditional.
        public void KeyUp(string key) => WindowsControlDesktop.SendKeys(key, false);
        public void ButtonDown(string _) => throw new NotSupportedException();
        public void ButtonUp(string _) => throw new NotSupportedException();
        public void MoveRelative(int _, int __) => throw new NotSupportedException();
        public void Wheel(int _) => throw new NotSupportedException();
        public void Dispose() => pinned.Dispose();
    }

    private static void Report(bool json, object result)
    {
        var serialized = JsonSerializer.Serialize(result, new JsonSerializerOptions
        {
            WriteIndented = !json, PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });
        Console.WriteLine(serialized);
    }

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr window);
}
