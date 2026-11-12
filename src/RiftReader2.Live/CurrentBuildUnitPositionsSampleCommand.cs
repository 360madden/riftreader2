using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class CurrentBuildUnitPositionsSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken ct) => RunAsync(options, output, ct,
        static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(pid, ticks,
            CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
        static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(pid, ticks,
            CurrentBuildPlayerLookup.GameSha256, token), CurrentBuildUnitPositionsCandidateReader.Read);

    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken ct, Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquire,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, int, ulong, CurrentBuildUnitPositionsObservation> read)
    {
        if (!options.TryGetValue("--pid", out var p) || !int.TryParse(p, NumberStyles.None,
                CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) || !long.TryParse(t, NumberStyles.None,
                CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("Unit positions require --pid, --start-ticks and --output.");
        var limit = 512;
        if (options.TryGetValue("--unit-limit", out var rawLimit) &&
            (!int.TryParse(rawLimit, NumberStyles.None, CultureInfo.InvariantCulture, out limit) || limit is < 1 or > 512))
            throw new ArgumentException("--unit-limit must be 1..512.");
        ulong start = 0;
        if (options.TryGetValue("--start-bucket", out var rawStart) &&
            !ulong.TryParse(rawStart, NumberStyles.None, CultureInfo.InvariantCulture, out start))
            throw new ArgumentException("--start-bucket must be an unsigned integer.");
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Unit-position output exists.");
        await using var lease = await acquire(pid, ticks, ct);
        await using var session = await open(pid, ticks, ct);
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Unit-position session identity mismatch.");
        var observation = read(session, limit, start);
        if (observation.Identity != identity || session.Identity != identity ||
            await session.RevalidateAsync(ct) is not null)
            throw new InvalidDataException("Unit-position process revalidation failed; no report published.");
        ct.ThrowIfCancellationRequested();
        var report = new { schemaVersion = 1, contractVersion = "native-current-unit-positions-candidate-sample/1",
            status = "complete", observation, limitations = new[]
            {
                "The bounded unit-manager subset is not a complete world inventory.",
                "Each row is owner/type checked, but acquisitions are sequential and cannot exclude ABA.",
                "Camera stability and projected screen bounds cannot establish occlusion or renderer freshness.",
                "No game method, memory write, input or foreground change is performed."
            } };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-unit-positions-summary/1",
            status = "complete", positions = observation.Rows.Count, output = Path.GetFullPath(path) },
            new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
