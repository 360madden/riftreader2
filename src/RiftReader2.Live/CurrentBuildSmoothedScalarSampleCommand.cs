using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>Physical read-only self-owned scalar candidate; never qualified heading.</summary>
internal static class CurrentBuildSmoothedScalarSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) =>
        RunAsync(options, output, ct,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildSmoothedScalarCandidateReader.Read);

    // Offline seam tests the exact production lease, owner, epoch and publication sequence.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildSmoothedScalarCandidate> read)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(acquireLease);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required for smoothed scalar.");
        var samples = BoundedInt(options, "--samples", 1, 1, 30);
        var intervalMilliseconds = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path))
            throw new IOException("Smoothed scalar output exists; never overwrite evidence.");
        await using var lease = await acquireLease(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256,
                StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Opened scalar process identity mismatch.");
        var observation = await CaptureAsync(session, read, ct);
        if (samples > 1)
        {
            var observations = new List<CurrentBuildSmoothedScalarCandidate>(samples) { observation };
            for (var index = 1; index < samples; index++)
            {
                if (intervalMilliseconds > 0)
                    await Task.Delay(intervalMilliseconds, ct);
                var next = await CaptureAsync(session, read, ct);
                if (next.PlayerKey != observation.PlayerKey || next.Identity != identity)
                    throw new InvalidDataException("Smoothed scalar player or epoch changed during burst.");
                observations.Add(next);
            }
            var last = observations[^1];
            var burst = new
            {
                schemaVersion = 1,
                contractVersion = "native-current-smoothed-scalar-candidate-burst/1",
                status = "complete",
                identity,
                requestedSamples = samples,
                completedSamples = observations.Count,
                observation = last,
                observations,
                limitations = new[]
                {
                    "All samples share one exact-build PID/start epoch, owner key, lease and session.",
                    "Four entity-owned scalars are unqualified for heading, camera yaw or movement response.",
                    "Sequential reads cannot exclude ABA or prove changes between observations.",
                    "No gameplay input, memory write, getter invocation or foreground change is performed."
                }
            };
            await JsonReportWriter.WriteNewAsync(path, burst, ct);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                recordType = "native-current-smoothed-scalar-summary/1",
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
            contractVersion = "native-current-smoothed-scalar-candidate/1",
            status = "complete",
            identity,
            observation,
            limitations = new[]
            {
                "Four entity-owned scalars are candidates, not qualified actor heading or camera yaw.",
                "Sequential owner/byte rechecks cannot exclude ABA or establish response to turning.",
                "On-disk executable SHA256 does not separately hash the loaded module.",
                "No gameplay input, getter invocation, process write or foreground change is performed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-smoothed-scalar-summary/1",
            report.status,
            observation.Qualification,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    private static async Task<CurrentBuildSmoothedScalarCandidate> CaptureAsync(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildSmoothedScalarCandidate> read,
        CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        var observation = read(session);
        if (observation.Identity != identity || observation.PlayerKey == 0 || session.Identity != identity)
            throw new InvalidDataException("Scalar observation owner or epoch mismatch.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Smoothed scalar process identity invalidated.");
        ct.ThrowIfCancellationRequested();
        return observation;
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
