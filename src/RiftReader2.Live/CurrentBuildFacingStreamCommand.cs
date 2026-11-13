using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>A finite stream of individually revalidated, candidate-only facing samples.</summary>
internal static class CurrentBuildFacingStreamCommand
{
    private static readonly JsonSerializerOptions Compact = new(JsonFormat.Options) { WriteIndented = false };

    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken ct) => RunAsync(options, output, ct,
            static async (pid, ticks, remaining, token) => await NativeReadFileLease.AcquireAsync(pid, ticks,
                CurrentBuildPlayerLookup.GameSha256, remaining, token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(pid, ticks,
                CurrentBuildPlayerLookup.GameSha256, token),
            static (session, token) => CurrentBuildFacingCandidateReader.ReadStableObservation(session, token),
            createExecutablePin: static async (path, token) =>
                await VerifiedNativeExecutablePin.OpenAsync(path, CurrentBuildPlayerLookup.GameSha256, token),
            openPinned: static async (pid, ticks, pin, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, (VerifiedNativeExecutablePin)pin, token));

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken ct, Func<int, long, TimeSpan, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CancellationToken, CurrentBuildFacingCandidate> read,
        Func<TimeSpan>? elapsed = null,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPairedPositionObservation>? readTarget = null,
        Func<string, CancellationToken, Task<IAsyncDisposable>>? createExecutablePin = null,
        Func<int, long, IAsyncDisposable, CancellationToken, Task<IReadOnlyNativeMemorySession>>? openPinned = null)
    {
        if ((createExecutablePin is null) != (openPinned is null))
            throw new ArgumentException("Facing stream executable pin delegates must be supplied together.");
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0)
            throw new ArgumentException("Facing stream requires --pid and --start-ticks.");
        var durationMilliseconds = BoundedInt(options, "--duration-ms", 2_000, 1, 600_000);
        var explicitLongDuration = options.ContainsKey("--duration-ms") && durationMilliseconds > 2_000;
        var count = BoundedInt(options, "--samples", 20, 1, explicitLongDuration ? 30_000 : 30);
        var interval = BoundedInt(options, "--interval-ms", 50, 20, 200);
        var includeTarget = options.TryGetValue("--include-target", out var rawTarget) &&
            (rawTarget == "true" ? true : rawTarget == "false" ? false :
             throw new ArgumentException("--include-target must be true or false."));
        var stopwatch = Stopwatch.StartNew();
        elapsed ??= () => stopwatch.Elapsed;
        var deadline = TimeSpan.FromMilliseconds(durationMilliseconds);
        NativeProcessIdentity? identity = null;
        ulong? key = null, entity = null, system = null;
        var completed = 0;
        IAsyncDisposable? executablePin = null;
        try
        {
            for (var i = 0; i < count; i++)
            {
                ct.ThrowIfCancellationRequested();
                if (elapsed() >= deadline) break;
                if (i > 0)
                {
                    var remaining = deadline - elapsed();
                    if (remaining <= TimeSpan.Zero) break;
                    await Task.Delay(remaining < TimeSpan.FromMilliseconds(interval) ? remaining : TimeSpan.FromMilliseconds(interval), ct);
                    if (elapsed() >= deadline) break;
                }
                var captureTimer = Stopwatch.StartNew();
                var remainingLease = deadline - elapsed();
                if (remainingLease <= TimeSpan.Zero) break;
                var leaseWait = remainingLease < TimeSpan.FromSeconds(30)
                    ? remainingLease
                    : TimeSpan.FromSeconds(30);
                IAsyncDisposable lease;
                try { lease = await acquireLease(pid, ticks, leaseWait, ct); }
                catch (TimeoutException) when (elapsed() >= deadline) { break; }
                CurrentBuildFacingCandidate sample;
                NativeProcessIdentity currentIdentity;
                await using (lease)
                {
                    ct.ThrowIfCancellationRequested();
                    if (elapsed() >= deadline) break;
                    await using var session = executablePin is null
                        ? await open(pid, ticks, ct)
                        : await openPinned!(pid, ticks, executablePin, ct);
                    ct.ThrowIfCancellationRequested();
                    if (elapsed() >= deadline) break;
                    currentIdentity = session.Identity;
                    if (currentIdentity.ProcessId != pid || currentIdentity.ProcessStartUtcTicks != ticks ||
                        !string.Equals(currentIdentity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
                        (identity is not null && currentIdentity != identity))
                        throw new InvalidDataException("Facing stream session identity mismatch.");
                    if (executablePin is null && createExecutablePin is not null)
                        executablePin = await createExecutablePin(currentIdentity.ExecutablePath, ct);
                    var bracketTimer = Stopwatch.StartNew();
                    sample = read(session, ct);
                    if (includeTarget)
                    {
                        var pair = readTarget is null ? CurrentBuildPairedPositionCandidateReader.Read(session) : readTarget(session);
                        var after = read(session, ct);
                        sample = CurrentBuildFacingSampleCommand.AttachTargetBracket(sample, pair, after, currentIdentity, bracketTimer.Elapsed);
                    }
                    if (sample.Identity != currentIdentity || session.Identity != currentIdentity || sample.PlayerKey == 0 ||
                        (key is not null && (sample.PlayerKey != key || sample.PlayerEntity != entity || sample.PlayerSystem != system)))
                        throw new InvalidDataException("Facing stream owner or process epoch changed.");
                    if (elapsed() >= deadline) break;
                    if (await session.RevalidateAsync(ct) is not null || session.Identity != currentIdentity)
                        throw new InvalidDataException("Facing stream process revalidation failed.");
                    ct.ThrowIfCancellationRequested();
                    if (elapsed() >= deadline) break;
                    identity ??= currentIdentity;
                    key ??= sample.PlayerKey; entity ??= sample.PlayerEntity; system ??= sample.PlayerSystem;
                }
                // Output, serialization and potentially stalled pipes never hold the native lease.
                ct.ThrowIfCancellationRequested();
                if (elapsed() >= deadline) break;
                var observation = JsonSerializer.SerializeToElement(sample, Compact);
                var captureElapsedMilliseconds = captureTimer.Elapsed.TotalMilliseconds;
                await output.WriteLineAsync(JsonSerializer.Serialize(new {
                    recordType = "native-current-facing-stream-row/1", sequence = completed,
                    status = "candidate", identity = currentIdentity, observation, captureElapsedMilliseconds,
                    emittedAtUtc = DateTimeOffset.UtcNow
                }, Compact));
                await output.FlushAsync(ct);
                completed++;
            }
        }
        finally
        {
            if (executablePin is not null) await executablePin.DisposeAsync();
        }
        ct.ThrowIfCancellationRequested();
        await output.WriteLineAsync(JsonSerializer.Serialize(new {
            recordType = "native-current-facing-stream-end/1", status = completed == count ? "complete" : "duration-limit",
            requestedSamples = count, completedSamples = completed
        }, Compact));
        await output.FlushAsync(ct);
        return 0;
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
        int fallback, int min, int max)
    {
        if (!options.TryGetValue(name, out var raw)) return fallback;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) || value < min || value > max)
            throw new ArgumentException($"{name} must be in {min}..{max}.");
        return value;
    }
}
