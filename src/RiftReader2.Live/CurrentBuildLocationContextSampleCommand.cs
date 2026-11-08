using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class CurrentBuildLocationContextSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct) =>
        RunAsync(options, output, ct,
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildLocationContextCandidateReader.ReadAsync,
            static async (pid, ticks, sha, timeout, token) =>
                await NativeReadFileLease.AcquireAsync(pid, ticks, sha, timeout, token));

    // Offline lifecycle/publication tests use this seam; runtime sources remain exact-build native readers.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken ct,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CancellationToken, Task<CurrentBuildLocationContextObservation>> read,
        Func<int, long, string, TimeSpan, CancellationToken, Task<IAsyncDisposable>> acquireLease)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(acquireLease);
        if (!options.TryGetValue("--pid", out var p) ||
            !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) ||
            !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output required.");
        ct.ThrowIfCancellationRequested();
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        // Reverse await-using disposal closes the session BEFORE releasing the shared lease.
        await using var lease = await acquireLease(pid, ticks, CurrentBuildPlayerLookup.GameSha256,
            TimeSpan.FromSeconds(5), ct) ?? throw new InvalidDataException("Native read lease acquisition returned no handle.");
        ct.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, ct);
        ct.ThrowIfCancellationRequested();
        var identity = session.Identity;
        if (identity.ProcessId != pid || identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Opened location process identity mismatch.");
        var observation = await read(session, ct);
        ct.ThrowIfCancellationRequested();
        if (observation.Identity != identity || session.Identity != identity ||
            !ulong.TryParse(observation.UnitKey, NumberStyles.None, CultureInfo.InvariantCulture, out var key) || key == 0 ||
            observation.UnitIdCandidate != $"u{key:X16}" ||
            observation.Zone.Identity is not NativeProcessIdentity zoneIdentity || zoneIdentity != identity ||
            observation.Zone.SelfKey != key)
            throw new InvalidDataException("Location observation identity mismatch.");
        if (await session.RevalidateAsync(ct) is not null || session.Identity != identity)
            throw new InvalidDataException("Process identity invalidated; no report published.");
        ct.ThrowIfCancellationRequested();
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-location-context-candidate/1",
            status = "complete",
            observation,
            limitations = new[]
            {
                "Position and zone retain separate source intervals; this is not an atomic world snapshot.",
                "Null zone ID or cache miss remains unavailable, not zero or proof that the zone is absent.",
                "Zone ID does not establish world-instance identity; cached XYZ and API correspondence remain unqualified.",
                "Sequential anchors cannot exclude ABA or prove uninterrupted same-player continuity.",
                "Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.",
                "No game getter, initialization, refcount operation, input or memory write is performed."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, ct);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-location-context-summary/1",
            status = "complete",
            observation.Qualification,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
