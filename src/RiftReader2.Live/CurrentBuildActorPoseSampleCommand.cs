using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>Read-only physical process actor/model pose candidate, never qualified body facing.</summary>
internal static class CurrentBuildActorPoseSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) =>
        RunAsync(options, output, ct,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildActorPoseCandidateReader.Read,
            CurrentBuildPositionCandidateReader.ReadOwned);

    // Offline injection seam preserves the exact production lease/session/publication path.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildActorPoseCandidate> read,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOwnedPosition> readPosition)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(acquireLease);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(readPosition);
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required for actor pose.");
        var samples = BoundedInt(options, "--samples", 1, 1, 30);
        var intervalMilliseconds = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        var includePosition = BoolOption(options, "--include-position");

        ct.ThrowIfCancellationRequested();
        if (File.Exists(path))
            throw new IOException("Actor pose candidate output exists; never overwrite evidence.");
        await using var lease = await acquireLease(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Opened actor pose process identity mismatch.");
        var elapsed = Stopwatch.StartNew();
        var observation = await CaptureAsync(session, read, ct,
            includePosition ? readPosition : null);
        if (samples > 1)
        {
            var observations = new List<CurrentBuildActorPoseCandidate>(samples) { observation };
            for (var index = 1; index < samples; index++)
            {
                if (intervalMilliseconds > 0)
                    await Task.Delay(intervalMilliseconds, ct);
                var next = await CaptureAsync(session, read, ct,
                    includePosition ? readPosition : null);
                if (next.PlayerKey != observation.PlayerKey || next.Identity != identity)
                    throw new InvalidDataException("Actor pose player or process changed during burst; no report published.");
                observations.Add(next);
            }
            var last = observations[^1];
            var burst = new
            {
                schemaVersion = 1,
                contractVersion = "native-current-actor-pose-candidate-burst/1",
                status = "complete",
                identity,
                requestedSamples = samples,
                completedSamples = observations.Count,
                captureElapsedMilliseconds = elapsed.Elapsed.TotalMilliseconds,
                observation = last,
                observations,
                limitations = new[]
                {
                    "All samples share one physical PID, start epoch, build SHA, read lease and session.",
                    "All observed player keys match; continuity between samples cannot be proved.",
                    "Matrices and planar angles remain candidates, not qualified body or camera facing.",
                    "Optional XYZ brackets share the actor owner, lease and session but are sequential candidates, not atomic movement proof.",
                    "Sequential reads cannot exclude ABA; no changed-state, freshness or restart qualification.",
                    "No game input, process write, getter invocation or foreground change is performed."
                }
            };
            await JsonReportWriter.WriteNewAsync(path, burst, ct);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                recordType = "native-current-actor-pose-summary/1",
                burst.status,
                last.Qualification,
                burst.completedSamples,
                output = Path.GetFullPath(path)
            }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
            return 0;
        }
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-actor-pose-candidate/1",
            status = "complete",
            identity,
            observation,
            limitations = new[]
            {
                "Actor/model/render matrices are candidates, not qualified body or camera facing.",
                "Structural planar angles do not prove axis, sign, source freshness or input response.",
                "Optional XYZ brackets share the actor owner and session but are sequential, not atomic position evidence.",
                "Owner and consumed bytes are bracketed but reads are sequential and cannot exclude ABA.",
                "The executable SHA256 covers on-disk bytes; loaded module bytes are not separately hashed.",
                "No game input, getter invocation, process write or foreground change is performed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-actor-pose-summary/1",
            report.status,
            observation.Qualification,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    internal static async Task<CurrentBuildActorPoseCandidate> CaptureAsync(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildActorPoseCandidate> read,
        CancellationToken ct,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOwnedPosition>? readPosition = null)
    {
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        var started = Stopwatch.GetTimestamp();
        var before = readPosition?.Invoke(session);
        var observation = read(session);
        var after = readPosition?.Invoke(session);
        // The XYZ bracket ends with the second position read, not with the later
        // process revalidation (which can take unrelated time).
        var positionBracketElapsedMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        if (observation.Identity != identity || observation.PlayerKey == 0 || session.Identity != identity)
            throw new InvalidDataException("Actor pose observation owner or process changed.");
        if (before is not null && (after is null || before.UnitKey != observation.PlayerKey ||
                                   after.UnitKey != observation.PlayerKey))
            throw new InvalidDataException("Actor pose and bracketed XYZ player owner differ; no report published.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Actor pose process identity invalidated; no report published.");
        ct.ThrowIfCancellationRequested();
        if (before is not null && after is not null)
            observation = observation with
            {
                PositionBracketCandidate = new(observation.PlayerKeyDecimal,
                    before.Position, after.Position,
                    positionBracketElapsedMilliseconds)
            };
        return observation;
    }

    private static bool BoolOption(IReadOnlyDictionary<string, string> options, string name)
    {
        if (!options.TryGetValue(name, out var raw)) return false;
        if (raw == "true") return true;
        if (raw == "false") return false;
        throw new ArgumentException($"{name} must be true or false.");
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
        int fallback, int minimum, int maximum)
    {
        if (!options.TryGetValue(name, out var raw))
            return fallback;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
            value < minimum || value > maximum)
            throw new ArgumentException($"{name} must be in {minimum}..{maximum}.");
        return value;
    }
}
