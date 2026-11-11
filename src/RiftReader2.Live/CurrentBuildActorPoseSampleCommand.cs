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
            CurrentBuildActorPoseCandidateReader.Read);

    // Offline injection seam preserves the exact production lease/session/publication path.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildActorPoseCandidate> read)
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
            throw new ArgumentException("--pid, --start-ticks and --output are required for actor pose.");

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
        ct.ThrowIfCancellationRequested();
        var observation = read(session);
        if (observation.Identity != identity || observation.PlayerKey == 0 || session.Identity != identity)
            throw new InvalidDataException("Actor pose observation owner or process changed.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Actor pose process identity invalidated; no report published.");
        ct.ThrowIfCancellationRequested();
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
}
