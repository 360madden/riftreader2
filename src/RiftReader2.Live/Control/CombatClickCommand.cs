using System.Diagnostics;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Control;

/// <summary>One reviewed secure-button click. It never discovers or repeats an action.</summary>
internal static class CombatClickCommand
{
    internal sealed record Options(string ExpectedHost, int Pid, long ExpectedStartTicks,
        string ExpectedSha256, long ExpectedHwnd, ulong ExpectedPlayerKey,
        ulong ExpectedTargetKey, int OwnerPid, long OwnerStartTicks,
        string ActionId, string Nonce, int ClientX, int ClientY, int ClientWidth,
        int ClientHeight, ClickTarget Rectangle, string StopFile, int HoldMilliseconds,
        bool Cleanup, bool Execute, bool Json);

    internal sealed record TargetPins(ulong PlayerKey, ulong TargetKey,
        DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc);

    internal static Options Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        var flags = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i++)
        {
            var name = args[i];
            if (name is "--cleanup" or "--execute" or "--json")
            {
                if (!flags.Add(name)) throw new InvalidDataException("Repeated option: " + name);
                continue;
            }
            if (!name.StartsWith("--", StringComparison.Ordinal) || i + 1 >= args.Length
                || !values.TryAdd(name, args[++i]))
                throw new InvalidDataException("Missing or repeated option: " + name);
        }
        var allowed = new HashSet<string>(StringComparer.Ordinal)
        {
            "--expected-host", "--pid", "--expect-start-ticks", "--expect-sha256", "--expect-hwnd",
            "--expect-player-key", "--expect-target-key", "--owner-pid", "--owner-start-ticks",
            "--action-id", "--nonce", "--client-x", "--client-y", "--client-width", "--client-height",
            "--rect-x", "--rect-y", "--rect-width", "--rect-height", "--stop-file", "--hold-ms"
        };
        var unknown = values.Keys.FirstOrDefault(key => !allowed.Contains(key));
        if (unknown is not null) throw new InvalidDataException("Unknown option: " + unknown);
        string Required(string name) => values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new InvalidDataException("Required option missing: " + name);
        static int Integer(string raw, string name, int minimum, int maximum) =>
            int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
            && value >= minimum && value <= maximum ? value
                : throw new InvalidDataException($"{name} must be in {minimum}..{maximum}.");
        static long PositiveLong(string raw, string name) =>
            long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) && value > 0
                ? value : throw new InvalidDataException(name + " must be positive.");
        static ulong PositiveUlong(string raw, string name) =>
            ulong.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) && value > 0
                ? value : throw new InvalidDataException(name + " must be a positive decimal key.");
        static string Token(string raw, string name)
        {
            if (raw.Length is < 1 or > 128 || raw.Any(c => !(char.IsLetterOrDigit(c) || c is '.' or '_' or ':' or '-')))
                throw new InvalidDataException(name + " contains unsupported characters.");
            return raw;
        }
        var sha = Required("--expect-sha256");
        if (sha.Length != 64 || !sha.All(Uri.IsHexDigit))
            throw new InvalidDataException("--expect-sha256 must contain 64 hex digits.");
        var cleanup = flags.Contains("--cleanup");
        var actionId = Token(Required("--action-id"), "--action-id");
        if (cleanup ? actionId != "controls.cancel" : !actionId.StartsWith("controls.actions.", StringComparison.Ordinal))
            throw new InvalidDataException(cleanup
                ? "--cleanup requires the exact controls.cancel action."
                : "New combat actions must use a controls.actions.* action ID.");
        var stop = Required("--stop-file");
        if (!Path.IsPathFullyQualified(stop)) throw new InvalidDataException("--stop-file must be absolute.");
        var clientX = Integer(Required("--client-x"), "--client-x", -32768, 32767);
        var clientY = Integer(Required("--client-y"), "--client-y", -32768, 32767);
        var clientWidth = Integer(Required("--client-width"), "--client-width", 64, 8192);
        var clientHeight = Integer(Required("--client-height"), "--client-height", 64, 8192);
        var rectangle = new ClickTarget(
            Integer(Required("--rect-x"), "--rect-x", 0, 8191),
            Integer(Required("--rect-y"), "--rect-y", 0, 8191),
            Integer(Required("--rect-width"), "--rect-width", 4, 128),
            Integer(Required("--rect-height"), "--rect-height", 4, 128));
        if ((long)rectangle.X + rectangle.Width > clientWidth
            || (long)rectangle.Y + rectangle.Height > clientHeight)
            throw new InvalidDataException("Reviewed rectangle is outside the pinned client geometry.");
        return new(Required("--expected-host"), Integer(Required("--pid"), "--pid", 1, int.MaxValue),
            PositiveLong(Required("--expect-start-ticks"), "--expect-start-ticks"), sha.ToUpperInvariant(),
            MoveKeyCommand.ParseWindowHandle(Required("--expect-hwnd")),
            PositiveUlong(Required("--expect-player-key"), "--expect-player-key"),
            PositiveUlong(Required("--expect-target-key"), "--expect-target-key"),
            Integer(Required("--owner-pid"), "--owner-pid", 1, int.MaxValue),
            PositiveLong(Required("--owner-start-ticks"), "--owner-start-ticks"), actionId,
            Token(Required("--nonce"), "--nonce"),
            clientX, clientY, clientWidth, clientHeight, rectangle,
            Path.GetFullPath(stop), values.TryGetValue("--hold-ms", out var hold)
                ? Integer(hold, "--hold-ms", 20, 100) : 40,
            cleanup, flags.Contains("--execute"), flags.Contains("--json"));
    }

    internal static async Task<ControlExecutionResult> ExecuteReviewedClickAsync(Options options,
        Func<CancellationToken, Task<TargetPins>> readPins, Func<string?> safetyReason,
        Func<CursorPreparation> prepare, IControlInput input,
        Func<TimeSpan, CancellationToken, Task>? delay = null, CancellationToken token = default)
    {
        async Task RequirePins()
        {
            var pins = await readPins(token);
            if (pins.PlayerKey != options.ExpectedPlayerKey || pins.TargetKey != options.ExpectedTargetKey
                || pins.CompletedAtUtc < pins.StartedAtUtc
                || DateTimeOffset.UtcNow - pins.CompletedAtUtc > TimeSpan.FromSeconds(1))
                throw new InvalidOperationException("Combat self/selected-target pin changed.");
        }
        if (safetyReason() is string before) throw new InvalidOperationException(before);
        await RequirePins();
        _ = prepare();
        await (delay ?? Task.Delay)(TimeSpan.FromMilliseconds(50), token);
        if (safetyReason() is string after) throw new InvalidOperationException(after);
        await RequirePins();
        return await new BoundedControlExecutor(input, delayAsync: delay)
            .ExecuteAsync(new([], options.HoldMilliseconds, "left", ClickTarget: options.Rectangle), token);
    }

    internal static async Task<int> RunAsync(string[] args, CancellationToken token)
    {
        var json = args.Contains("--json", StringComparer.Ordinal);
        Options? options = null;
        DesktopTarget? receiptTarget = null;
        var inputSent = false;
        var releaseSucceeded = true;
        try
        {
            options = Parse(args);
            if (!string.Equals(options.ExpectedHost, Environment.MachineName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Current machine does not match --expected-host.");
            ValidateStopPath(options);
            using var ownerProcess = ExactProcess(options.OwnerPid, options.OwnerStartTicks, null);
            using var game = ExactProcess(options.Pid, options.ExpectedStartTicks, "rift_x64");
            var executable = game.MainModule?.FileName
                ?? throw new InvalidOperationException("Cannot resolve game executable path.");
            var sha = WindowsControlDesktop.GetFreshExecutableSha256(executable);
            if (!string.Equals(sha, options.ExpectedSha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(sha, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("RIFT executable hash does not match the supported exact build.");
            DesktopTarget Inspect()
            {
                var value = WindowsControlDesktop.InspectPinned("rift_x64", executable, sha,
                    options.Pid, options.ExpectedStartTicks);
                MoveKeyCommand.ValidateExpectedWindow(options.ExpectedHwnd, value.WindowHandle);
                if (value.ClientX != options.ClientX || value.ClientY != options.ClientY
                    || value.ClientWidth != options.ClientWidth || value.ClientHeight != options.ClientHeight)
                    throw new InvalidOperationException("RIFT client geometry differs from reviewed producer geometry.");
                return value;
            }
            var target = Inspect();
            receiptTarget = target;
            TargetPins? latestPins = null;
            async Task<TargetPins> ReadPins(CancellationToken cancellation)
            {
                await using var lease = await NativeReadFileLease.AcquireAsync(options.Pid,
                    options.ExpectedStartTicks, options.ExpectedSha256, TimeSpan.FromSeconds(1), cancellation);
                await using var session = await WindowsNativeMemorySession.OpenAsync(options.Pid,
                    options.ExpectedStartTicks, options.ExpectedSha256, cancellation);
                var context = CurrentBuildPlayerContextCandidateReader.Read(session);
                if (await session.RevalidateAsync(cancellation) is not null || session.Identity != context.Identity
                    || context.TargetKeyCandidate is not ulong selected || selected == 0)
                    throw new InvalidDataException("Combat identity or selected target is unavailable.");
                return latestPins = new(context.UnitKey, selected, context.StartedAtUtc, context.CompletedAtUtc);
            }
            string? Safety()
            {
                if (!options.Cleanup && File.Exists(options.StopFile)) return "stop-file-requested";
                if (Directory.Exists(options.StopFile)
                    || !Directory.Exists(Path.GetDirectoryName(options.StopFile))) return "stop-path-unavailable";
                try { using var ignored = ExactProcess(options.OwnerPid, options.OwnerStartTicks, null); }
                catch { return "owner-process-lost"; }
                return null;
            }
            var preflightPins = await ReadPins(token);
            if (preflightPins.PlayerKey != options.ExpectedPlayerKey
                || preflightPins.TargetKey != options.ExpectedTargetKey)
                throw new InvalidOperationException("Combat self/selected-target pin changed.");
            if (!options.Execute)
            {
                MoveKeyCommand.Report(options.Json, Receipt("preview-only", null, target, options,
                    preflightPins, null, [], false, true, null));
                return 0;
            }
            using var controlOwner = new Semaphore(1, 1, MoveKeyCommand.ControlOwnerName);
            if (!controlOwner.WaitOne(0))
                throw new InvalidOperationException("Another RR2 control helper already owns game input.");
            try
            {
                if (Safety() is string admission) throw new InvalidOperationException(admission);
                _ = await MoveKeyCommand.FocusOnlyAsync(target, Inspect, WindowsControlDesktop.ReadPressedInputs,
                    () => MoveKeyCommand.RequestForegroundWithAttachedThreads(
                        new IntPtr(MoveKeyCommand.ParseWindowHandle(target.WindowHandle)), options.Pid),
                    cancellation => MoveKeyCommand.WaitForForegroundAsync(Inspect, 600, cancellation), token);
                var ready = Inspect();
                if (WindowsControlDesktop.ReadPressedInputs().Length != 0)
                    throw new InvalidOperationException("Desktop inputs are already held.");
                var events = new List<object>();
                using var clickInput = new ClickInput(WindowsControlDesktop.PinInputTarget(ready),
                    ready, options.Rectangle, events, () => inputSent = true);
                using var actionCancellation = CancellationTokenSource.CreateLinkedTokenSource(token);
                var monitor = MonitorSafetyAsync(Safety, actionCancellation);
                ControlExecutionResult result;
                CursorPreparation? preparation = null;
                try
                {
                    result = await ExecuteReviewedClickAsync(options, ReadPins, Safety,
                        () =>
                        {
                            var value = WindowsControlDesktop.PrepareTargetedClick(ready, options.Rectangle);
                            preparation = value;
                            return value;
                        },
                        clickInput, token: actionCancellation.Token);
                }
                finally
                {
                    actionCancellation.Cancel();
                    await monitor;
                }
                releaseSucceeded = result.ReleaseSucceeded;
                var status = result.DeliverySucceeded && result.ReleaseSucceeded ? "completed" : "halted";
                MoveKeyCommand.Report(options.Json, Receipt(status, result.Error, ready, options,
                    latestPins ?? preflightPins, preparation, events, inputSent, result.ReleaseSucceeded,
                    WindowsControlDesktop.ReadPressedInputs()));
                return status == "completed" ? 0 : 3;
            }
            finally { controlOwner.Release(); }
        }
        catch (Exception error)
        {
            IReadOnlyList<string> down;
            try { down = WindowsControlDesktop.ReadPressedInputs(); }
            catch { down = ["input-state-unavailable"]; }
            MoveKeyCommand.Report(json, new
            {
                status = inputSent ? "halted" : "blocked", reason = error.Message,
                errorType = error.GetType().Name, target = receiptTarget,
                actionId = options?.ActionId, nonce = options?.Nonce,
                cleanup = options?.Cleanup ?? false, inputSent, releaseSucceeded,
                desktopInputsDown = down, stopFile = options?.StopFile,
                owner = options is null ? null : new { processId = options.OwnerPid,
                    processStartUtcTicks = options.OwnerStartTicks }, responseVerified = false
            });
            return inputSent ? 3 : 2;
        }
    }

    private static object Receipt(string status, string? reason, DesktopTarget target, Options options,
        TargetPins pins, CursorPreparation? preparation, IReadOnlyList<object> events,
        bool inputSent, bool releaseSucceeded, IReadOnlyList<string>? desktopInputs) => new
    {
        status, reason, target, actionId = options.ActionId, nonce = options.Nonce,
        cleanup = options.Cleanup,
        cleanupSemantics = options.Cleanup
            ? "explicit controls.cancel secure button; producer asserts idempotence; native game response unverified"
            : null,
        playerKey = pins.PlayerKey.ToString(CultureInfo.InvariantCulture),
        targetKey = pins.TargetKey.ToString(CultureInfo.InvariantCulture),
        reviewedClientGeometry = new { x = options.ClientX, y = options.ClientY,
            width = options.ClientWidth, height = options.ClientHeight },
        rectangle = options.Rectangle, cursorPreparation = preparation,
        holdMilliseconds = options.HoldMilliseconds, inputEvents = events,
        inputSent, releaseSucceeded, desktopInputsDown = desktopInputs ?? [],
        stopFile = options.StopFile,
        owner = new { processId = options.OwnerPid, processStartUtcTicks = options.OwnerStartTicks },
        responseVerified = false
    };

    private static void ValidateStopPath(Options options)
    {
        if (Directory.Exists(options.StopFile) || !Directory.Exists(Path.GetDirectoryName(options.StopFile)))
            throw new InvalidOperationException("STOP path must name a file in an existing directory.");
        if (!options.Cleanup && File.Exists(options.StopFile))
            throw new InvalidOperationException("stop-file-requested");
    }

    private static async Task MonitorSafetyAsync(Func<string?> safety,
        CancellationTokenSource cancellation)
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                if (safety() is not null) { cancellation.Cancel(); return; }
                await Task.Delay(10, cancellation.Token);
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        catch { cancellation.Cancel(); }
    }

    private sealed class ClickInput(WindowsControlDesktop.PinnedInputTarget pinned,
        DesktopTarget target, ClickTarget rectangle, List<object> events, Action attempted)
        : IControlInput, IDisposable
    {
        public bool IsTargetCurrent() => pinned.IsCurrent();
        public void ButtonDown(string button)
        {
            if (button != "left" || !pinned.IsCurrent())
                throw new InvalidOperationException("Reviewed click target changed before button down.");
            var position = WindowsControlDesktop.GetCursorPosition();
            WindowsControlDesktop.ValidateTargetedClickPosition(target, rectangle, position);
            attempted();
            WindowsControlDesktop.SendMouseButton(MouseButton.Left, true);
            events.Add(new { phase = "button-down", inserted = true, atUtc = DateTimeOffset.UtcNow, position });
        }
        public void ButtonUp(string button)
        {
            WindowsControlDesktop.SendMouseButton(MouseButton.Left, false);
            events.Add(new { phase = "button-up", inserted = true, atUtc = DateTimeOffset.UtcNow });
        }
        public void Dispose() => pinned.Dispose();
        public void KeyDown(string _) => throw new NotSupportedException();
        public void KeyUp(string _) => throw new NotSupportedException();
        public void MoveRelative(int _, int __) => throw new NotSupportedException();
        public void Wheel(int _) => throw new NotSupportedException();
    }

    internal static Process ExactProcess(int pid, long ticks, string? name)
    {
        var process = Process.GetProcessById(pid);
        process.Refresh();
        if (process.HasExited || process.StartTime.ToUniversalTime().Ticks != ticks
            || name is not null && !string.Equals(process.ProcessName, name, StringComparison.OrdinalIgnoreCase))
        {
            process.Dispose();
            throw new InvalidOperationException("Expected process identity is unavailable.");
        }
        return process;
    }
}
