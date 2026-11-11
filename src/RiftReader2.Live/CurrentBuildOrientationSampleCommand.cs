using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class CurrentBuildOrientationSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) =>
        RunAsync(options, output, ct,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildOrientationCandidateReader.Read);

    // Injection seam is for offline lifecycle/publication tests, not alternate runtime sources.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOrientationCandidate> read)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(acquireLease);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        if (!options.TryGetValue("--pid", out var p) ||
            !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) ||
            !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output required.");
        var samples = BoundedInt(options, "--samples", 1, 1, 30);
        var intervalMilliseconds = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var lease = await acquireLease(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Opened orientation process identity mismatch.");
        var elapsed = Stopwatch.StartNew();
        var observation = await CaptureAsync(session, read, ct);
        if (samples > 1)
        {
            var observations = new List<CurrentBuildOrientationCandidate>(samples) { observation };
            for (var i = 1; i < samples; i++)
            {
                if (intervalMilliseconds > 0)
                    await Task.Delay(intervalMilliseconds, ct);
                var next = await CaptureAsync(session, read, ct);
                if (next.Identity != identity || next.UnitKey != observation.UnitKey ||
                    next.ComponentAddress != observation.ComponentAddress)
                    throw new InvalidDataException("Orientation owner or component changed during burst.");
                observations.Add(next);
            }
            var last = observations[^1];
            var burst = new
            {
                schemaVersion = 1,
                contractVersion = "native-current-orientation-candidate-burst/1",
                status = "complete",
                identity,
                requestedSamples = samples,
                completedSamples = observations.Count,
                captureElapsedMilliseconds = elapsed.Elapsed.TotalMilliseconds,
                observation = last,
                observations,
                limitations = new[]
                {
                    "Each sample shares the exact game process/build epoch, unit key, component, read lease and session.",
                    "Position matrices can be cached; these are not qualified player body or camera headings.",
                    "Sequential samples cannot exclude ABA or prove state changes between reads.",
                    "No gameplay input, memory write, getter invocation or foreground change is performed."
                }
            };
            await JsonReportWriter.WriteNewAsync(path, burst, ct);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                recordType = "native-current-orientation-summary/1",
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
            contractVersion = "native-current-orientation-candidate/1",
            status = "complete",
            observation,
            limitations = new[]
            {
                "Angles are numeric matrix descriptors, not body yaw, public heading or camera orientation.",
                "Stable cached matrices do not establish passive freshness; axis/sign and restart remain unverified.",
                "Sequential ownership and input rereads are not atomic and cannot exclude ABA.",
                "Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.",
                "No game function, getter, initializer, refcount operation or memory write is performed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-orientation-summary/1",
            status = "complete",
            observation.Qualification,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    private static async Task<CurrentBuildOrientationCandidate> CaptureAsync(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOrientationCandidate> read,
        CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        var observation = read(session);
        if (observation.Identity != identity || observation.UnitKey == 0 || session.Identity != identity)
            throw new InvalidDataException("Orientation observation identity mismatch.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Process identity invalidated; no report published.");
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
