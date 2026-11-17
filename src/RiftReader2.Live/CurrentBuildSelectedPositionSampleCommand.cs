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
        var expectedSha = ExpectedSha(options);
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Selected target position output already exists.");
        await using var lease = await acquire(pid, ticks, ct);
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, expectedSha, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Selected target position session identity mismatch.");
        var observation = read(session);
        if (observation.Identity != identity || session.Identity != identity ||
            await session.RevalidateAsync(ct) is not null)
            throw new InvalidDataException("Selected target position process revalidation failed.");
        ct.ThrowIfCancellationRequested();
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-selected-position-candidate-sample/1",
            status = "complete",
            observation,
            limitations = new[]
            {
                "Conditional fallback target key is a read-only candidate, not independently verified selection.",
                "A different active selection branch is withheld rather than guessed.",
                "Native position and projection are cached candidates; freshness, occlusion and restart are unverified.",
                "No game method, memory write, input, or foreground change is performed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-selected-position-summary/1",
            status = "complete", selectionStatus = observation.Status,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
