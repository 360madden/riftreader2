using System.Globalization;
using System.Diagnostics;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class CurrentBuildFacingSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) => RunAsync(options, output, ct,
        static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
            pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
        static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
            pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
        CurrentBuildFacingCandidateReader.Read);

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildFacingCandidate> read,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPairedPositionObservation>? readTarget = null)
    {
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("Facing requires --pid, --start-ticks and --output.");
        var count = BoundedInt(options, "--samples", 1, 1, 30);
        var interval = BoundedInt(options, "--interval-ms", 100, 0, 2000);
        var includeTarget = options.TryGetValue("--include-target", out var rawTarget) &&
            (rawTarget == "true" ? true : rawTarget == "false" ? false :
             throw new ArgumentException("--include-target must be true or false."));
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Facing output already exists.");
        await using var lease = await acquireLease(pid, ticks, ct);
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                           StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Facing session identity mismatch.");
        var observations = new List<CurrentBuildFacingCandidate>(count);
        for (var index = 0; index < count; index++)
        {
            ct.ThrowIfCancellationRequested();
            if (index > 0 && interval > 0) await Task.Delay(interval, ct);
            var timer = Stopwatch.StartNew();
            var sample = read(session);
            if (includeTarget)
            {
                var pair = readTarget is null ? CurrentBuildPairedPositionCandidateReader.Read(session) : readTarget(session);
                var after = read(session);
                if (pair.Identity != identity || after.Identity != identity ||
                    pair.Self.UnitKey != sample.PlayerKeyDecimal || after.PlayerKey != sample.PlayerKey ||
                    after.PlayerEntity != sample.PlayerEntity || after.PlayerSystem != sample.PlayerSystem ||
                    pair.Self.Position != (sample.EntityPositionCandidate ?? sample.PositionCandidate) ||
                    (after.EntityPositionCandidate ?? after.PositionCandidate) != (sample.EntityPositionCandidate ?? sample.PositionCandidate) ||
                    pair.StartedAtUtc < sample.CompletedAtUtc || pair.CompletedAtUtc > after.StartedAtUtc ||
                    timer.Elapsed.TotalMilliseconds > 2000)
                    throw new InvalidDataException("Facing/target identity, position or acquisition interval changed.");
                var firstCamera = sample.OpticalCameraCandidate;
                var lastCamera = after.OpticalCameraCandidate;
                var stable = CurrentBuildOpticalCameraCandidateReader.SameProjectionSnapshot(firstCamera, lastCamera);
                sample = sample with
                {
                    CompletedAtUtc = after.CompletedAtUtc,
                    TargetPositionPairCandidate = pair,
                    OpticalCameraAfterTargetCandidate = lastCamera,
                    TargetProjectionCameraStableCandidate = stable
                };
            }
            if (sample.Identity != identity || session.Identity != identity || sample.PlayerKey == 0 ||
                (index > 0 && (sample.PlayerKey != observations[0].PlayerKey ||
                               sample.PlayerEntity != observations[0].PlayerEntity ||
                               sample.PlayerSystem != observations[0].PlayerSystem)))
                throw new InvalidDataException("Facing owner or process epoch changed during burst.");
            observations.Add(sample);
        }
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Facing process revalidation failed; no completed report.");
        ct.ThrowIfCancellationRequested();
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-facing-candidate-samples/1",
            status = "complete",
            identity,
            requestedSamples = count,
            completedSamples = observations.Count,
            observation = observations[^1],
            observations,
            limitations = new[]
            {
                "Owner and consumed bytes are rechecked; sequential reads cannot exclude ABA.",
                "The player-system scalar can differ from the position orientation during and after input.",
                "Source-specific current-session evidence does not establish restart recovery or alternate view modes.",
                "Optional target projection uses sequential positions bracketed by camera reads; it is not atomic or an occlusion test.",
                "Executable SHA256 identifies on-disk bytes; loaded module bytes are not hashed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-facing-summary/1",
            status = "complete",
            completedSamples = observations.Count,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
        int fallback, int minimum, int maximum)
    {
        if (!options.TryGetValue(name, out var raw)) return fallback;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
            value < minimum || value > maximum)
            throw new ArgumentException($"{name} must be in {minimum}..{maximum}.");
        return value;
    }
}
