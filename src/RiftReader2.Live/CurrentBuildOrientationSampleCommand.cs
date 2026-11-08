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
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildOrientationCandidateReader.Read);

    // Injection seam is for offline lifecycle/publication tests, not alternate runtime sources.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildOrientationCandidate> read)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        if (!options.TryGetValue("--pid", out var p) ||
            !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) ||
            !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output required.");
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var session = await open(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Opened orientation process identity mismatch.");
        var observation = read(session);
        ct.ThrowIfCancellationRequested();
        if (observation.Identity != identity || observation.UnitKey == 0 || session.Identity != identity)
            throw new InvalidDataException("Orientation observation identity mismatch.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Process identity invalidated; no report published.");
        ct.ThrowIfCancellationRequested();
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
}
