using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live.Control;

internal static class TargetCycleCommand
{
    internal sealed record Options(string Host, int Pid, long Start, string Sha, long Hwnd,
        ulong Player, ulong? OldTarget, int OwnerPid, long OwnerStart, string StopFile, bool Execute);

    internal static Options Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        var flags = new HashSet<string>();
        for (var i = 0; i < args.Length; i++)
        {
            var option = args[i];
            if (option is "--execute" or "--json")
            {
                if (!flags.Add(option)) throw new InvalidDataException("Repeated " + option);
            }
            else if (option is not ("--expected-host" or "--pid" or "--expect-start-ticks"
                or "--expect-sha256" or "--expect-hwnd" or "--expect-player-key" or "--expect-target-key"
                or "--owner-pid" or "--owner-start-ticks" or "--stop-file")
                || ++i >= args.Length || args[i].StartsWith("--", StringComparison.Ordinal)
                || !values.TryAdd(option, args[i]))
                throw new InvalidDataException("Unknown, repeated, or incomplete option: " + option);
        }
        string Need(string name) => values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new InvalidDataException("Missing " + name);
        ulong Number(string name, bool allowZero = false) =>
            ulong.TryParse(Need(name), NumberStyles.None, CultureInfo.InvariantCulture, out var n) && (allowZero || n > 0)
                ? n : throw new InvalidDataException("Invalid decimal value for " + name);
        var sha = Need("--expect-sha256");
        var stop = Need("--stop-file");
        if (sha.Length != 64 || !sha.All(Uri.IsHexDigit) || !Path.IsPathFullyQualified(stop))
            throw new InvalidDataException("Expected a 64-digit SHA-256 and absolute STOP file.");
        return new(Need("--expected-host"), checked((int)Number("--pid")), checked((long)Number("--expect-start-ticks")),
            sha.ToUpperInvariant(), MoveKeyCommand.ParseWindowHandle(Need("--expect-hwnd")), Number("--expect-player-key"),
            values.ContainsKey("--expect-target-key") ? Number("--expect-target-key", true) : null,
            checked((int)Number("--owner-pid")), checked((long)Number("--owner-start-ticks")), Path.GetFullPath(stop),
            flags.Contains("--execute"));
    }

    internal static void ValidatePins(Options options, CombatClickCommand.TargetPins pins, DateTimeOffset now)
    {
        if (pins.PlayerKey != options.Player || options.OldTarget.HasValue && options.OldTarget != pins.TargetKey
            || pins.StartedAtUtc > pins.CompletedAtUtc || pins.CompletedAtUtc > now
            || now - pins.StartedAtUtc > TimeSpan.FromSeconds(1))
            throw new InvalidDataException("Fresh player or previous-selection pin mismatch.");
    }

    // Responsibilities split at key-down: the selected unit is expected to change.
    // Foreground, owner, STOP and unrelated held input still guard the entire pulse.
    internal sealed class PulseInput(Func<string?> safety, Func<string[]> pressed,
        Action down, Action up, Action? validateBeforeDown = null) : IControlInput
    {
        public bool Attempted { get; private set; }
        public bool Inserted { get; private set; }
        public bool Released { get; private set; }
        public string? Refusal { get; private set; }
        public bool IsTargetCurrent()
        {
            Refusal = safety();
            if (Refusal is null && pressed().Any(key => !(key == "tab" && Inserted && !Released)))
                Refusal = "external-input-held";
            return Refusal is null;
        }
        public void KeyDown(string key)
        {
            if (key != "tab" || Attempted || !IsTargetCurrent())
                throw new InvalidOperationException(Refusal ?? "tab-admission-refused");
            validateBeforeDown?.Invoke();
            Attempted = true;
            down();
            Inserted = true;
        }
        public void KeyUp(string key)
        {
            if (key != "tab") throw new InvalidOperationException("Unexpected key.");
            if (!Attempted || Released) return;
            up();
            Released = true;
        }
        public void ButtonDown(string _) => throw new NotSupportedException();
        public void ButtonUp(string _) => throw new NotSupportedException();
        public void MoveRelative(int _, int __) => throw new NotSupportedException();
        public void Wheel(int _) => throw new NotSupportedException();
    }

    internal static async Task<int> RunAsync(string[] args, CancellationToken token, TextWriter? helpOutput = null)
    {
        if (args is ["--help"] or ["-h"])
        {
            await (helpOutput ?? Console.Out).WriteLineAsync("""
                RiftReader2.Live target-cycle --expected-host HOST --pid PID --expect-start-ticks TICKS
                  --expect-sha256 SHA256 --expect-hwnd HWND --expect-player-key DECIMAL
                  --owner-pid PID --owner-start-ticks TICKS --stop-file ABSOLUTE_PATH
                  [--expect-target-key DECIMAL] [--execute] [--json]

                Without --execute, check admission and report readiness. With --execute, send one 40 ms Tab
                press to the pinned foreground game window. STOP, lost foreground or held operator input
                refuse or interrupt the press. The command never requests focus or repeats a press.

                --expect-target-key pins the previous selection. Use 0 to require an observed empty selection.
                Omitting it admits any readable previous selection. The receipt includes selectedTargetKeyBefore,
                inputSent, keyDownInserted, releaseSucceeded and desktopInputsDown. Observe the new target
                independently after release before using it for another action.
                """);
            return 0;
        }

        Options? options = null;
        DesktopTarget? target = null;
        CombatClickCommand.TargetPins? pins = null;
        PulseInput? input = null;
        string? fallback = null;
        int Report(string status, string? reason, string[] pressed)
        {
            var release = input?.Attempted != true || input.Released && !pressed.Contains("tab")
                && !pressed.Contains("input-state-unavailable");
            MoveKeyCommand.Report(args.Contains("--json"), new { status, reason, target,
                playerKey = pins?.PlayerKey.ToString(CultureInfo.InvariantCulture),
                selectedTargetKeyBefore = pins?.TargetKey.ToString(CultureInfo.InvariantCulture),
                selectionReadAtUtc = pins?.CompletedAtUtc, stopFile = options?.StopFile,
                owner = options is null ? null : new { processId = options.OwnerPid, processStartUtcTicks = options.OwnerStart },
                inputSent = input?.Attempted == true, keyDownInserted = input?.Inserted == true,
                releaseSucceeded = release, desktopInputsDown = pressed, releaseFallback = fallback,
                holdMilliseconds = 40, responseVerified = false });
            return status is "ready" or "completed" ? 0 : status == "blocked" ? 2 : 3;
        }
        try
        {
            options = Parse(args);
            if (!string.Equals(options.Host, Environment.MachineName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("expected-host-mismatch");
            using var owner = CombatClickCommand.ExactProcess(options.OwnerPid, options.OwnerStart, null);
            using var game = CombatClickCommand.ExactProcess(options.Pid, options.Start, "rift_x64");
            var path = game.MainModule?.FileName ?? throw new InvalidDataException("Game executable unavailable.");
            var sha = WindowsControlDesktop.GetFreshExecutableSha256(path);
            if (sha != options.Sha || !string.Equals(sha, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Unsupported game build or executable mismatch.");
            target = WindowsControlDesktop.InspectPinned("rift_x64", path, sha, options.Pid, options.Start);
            MoveKeyCommand.ValidateExpectedWindow(options.Hwnd, target.WindowHandle);
            using var pinned = WindowsControlDesktop.PinInputTarget(target);
            using var semaphore = new Semaphore(1, 1, MoveKeyCommand.ControlOwnerName);
            if (!semaphore.WaitOne(0)) throw new InvalidOperationException("control-owner-busy");
            try
            {
                string? Safety()
                {
                    if (token.IsCancellationRequested) return "cancelled";
                    if (owner.HasExited) return "owner-process-lost";
                    if (!pinned.IsCurrent()) return "foreground-or-window-identity-changed";
                    if (!Directory.Exists(Path.GetDirectoryName(options.StopFile))) return "stop-path-unavailable";
                    try
                    {
                        _ = File.GetAttributes(options.StopFile);
                        return "stop-file-requested";
                    }
                    catch (FileNotFoundException) { return null; }
                }
                if (Safety() is string refused) throw new InvalidOperationException(refused);
                await using (var lease = await NativeReadFileLease.AcquireAsync(options.Pid, options.Start,
                    sha, TimeSpan.FromSeconds(1), token))
                await using (var session = await WindowsNativeMemorySession.OpenAsync(options.Pid, options.Start, sha, token))
                {
                    var context = CurrentBuildPlayerContextCandidateReader.Read(session);
                    if (await session.RevalidateAsync(token) is not null || context.Identity != session.Identity
                        || context.TargetKeyCandidate is not ulong old)
                        throw new InvalidDataException("Game identity or previous selection unreadable.");
                    pins = new(context.UnitKey, old, context.StartedAtUtc, context.CompletedAtUtc);
                }
                ValidatePins(options, pins, DateTimeOffset.UtcNow);
                var releaseWindow = pinned.CaptureKeyReleaseWindow();
                input = new(Safety, WindowsControlDesktop.ReadPressedInputs,
                    () => WindowsControlDesktop.SendKeys("\t", true),
                    () =>
                    {
                        try { WindowsControlDesktop.SendKeys("\t", false); }
                        finally { fallback = pinned.PostOwnedKeyUpIfBackground('\t', releaseWindow); }
                        if (fallback.StartsWith("unavailable", StringComparison.Ordinal))
                            throw new InvalidOperationException("tab-background-release-unverified");
                    }, () => ValidatePins(options, pins, DateTimeOffset.UtcNow));
                if (!input.IsTargetCurrent()) throw new InvalidOperationException(input.Refusal);
                if (!options.Execute) return Report("ready", null, []);
                var result = await new BoundedControlExecutor(input).TapTargetCycleAsync(token);
                var pressed = WindowsControlDesktop.ReadPressedInputs();
                var completed = result.DeliverySucceeded && result.ReleaseSucceeded && input.Inserted && input.Released
                    && pressed.Length == 0 && Safety() is null;
                return Report(completed ? "completed" : input.Attempted ? "halted" : "blocked",
                    completed ? null : input.Refusal ?? result.Error ?? "post-release-guard-refused", pressed);
            }
            finally { semaphore.Release(); }
        }
        catch (Exception error)
        {
            string[] pressed;
            try { pressed = WindowsControlDesktop.ReadPressedInputs(); }
            catch { pressed = ["input-state-unavailable"]; }
            return Report(input?.Attempted == true ? "halted" : "blocked", error.Message, pressed);
        }
    }
}
