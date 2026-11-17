using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class CurrentBuildSelectedPositionSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken ct)
    {
        var expectedSha = ExpectedSha(options);
        return RunAsync(options, output, ct,
            async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(pid, ticks,
                expectedSha, TimeSpan.FromSeconds(2), token),
            async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(pid, ticks,
                expectedSha, token), CurrentBuildSelectedPositionCandidateReader.Read);
    }

    private static string ExpectedSha(IReadOnlyDictionary<string, string> options)
    {
        var sha = options.TryGetValue("--sha256", out var requested)
            ? requested : CurrentBuildPlayerLookup.GameSha256;
        if (!CurrentBuildPlayerLookup.IsCoreBuild(sha))
            throw new ArgumentException("Unqualified executable SHA256 for selected target position.");
        return sha;
    }

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquire,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildSelectedPositionObservation> read)
    {
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("Selected target position requires --pid, --start-ticks and --output.");
        static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
            int fallback, int minimum, int maximum)
        {
            if (!options.TryGetValue(name, out var raw)) return fallback;
            if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
                value < minimum || value > maximum)
                throw new ArgumentException(name + $" must be in {minimum}..{maximum}.");
            return value;
        }
        var count = BoundedInt(options, "--samples", 1, 1, 30);
        var interval = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        var expectedSha = ExpectedSha(options);
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Selected target position output already exists.");
        await using var lease = await acquire(pid, ticks, ct);
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, expectedSha, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Selected target position session identity mismatch.");
        var observations = new List<CurrentBuildSelectedPositionObservation>(count);
        for (var index = 0; index < count; index++)
        {
            ct.ThrowIfCancellationRequested();
            if (index > 0 && interval > 0) await Task.Delay(interval, ct);
            var next = read(session);
            if (next.Identity != identity || session.Identity != identity ||
                string.IsNullOrWhiteSpace(next.SelfKey) || next.SelfKey == "0" ||
                (index > 0 && (next.SelfKey != observations[0].SelfKey ||
                               next.StartedAtUtc < observations[^1].CompletedAtUtc)))
                throw new InvalidDataException("Selected target position player or process changed during burst.");
            observations.Add(next);
        }
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Selected target position process revalidation failed.");
        ct.ThrowIfCancellationRequested();
        var observation = observations[^1];
        var limitations = new[]
        {
            "Conditional fallback target key is a read-only candidate, not independently verified selection.",
            "A different active selection branch is withheld rather than guessed.",
            "Native position and projection are cached candidates; freshness, occlusion and restart are unverified.",
            "Changed target keys across sequential samples do not independently prove game selection or causality.",
            "No game method, memory write, input, or foreground change is performed."
        };
        if (count > 1)
        {
            var burst = new
            {
                schemaVersion = 1,
                contractVersion = "native-current-selected-position-candidate-burst/1",
                status = "complete",
                identity,
                requestedSamples = count,
                completedSamples = observations.Count,
                observation,
                observations,
                limitations
            };
            await JsonReportWriter.WriteNewAsync(path, burst, ct);
        }
        else
        {
            var report = new
            {
                schemaVersion = 1,
                contractVersion = "native-current-selected-position-candidate-sample/1",
                status = "complete",
                observation,
                limitations
            };
            await JsonReportWriter.WriteNewAsync(path, report, ct);
        }
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-selected-position-summary/1",
            status = "complete", selectionStatus = observation.Status,
            completedSamples = observations.Count,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
