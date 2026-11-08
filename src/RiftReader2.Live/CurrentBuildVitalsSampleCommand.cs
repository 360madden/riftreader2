using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CurrentBuildVitalsReport(CurrentBuildVitalsObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-vitals-candidate-sample/2";
    public string Status => "complete";
    public string SourceBuildSha256 => CurrentBuildPositionSampleCommand.GameSha256;
    public string Source => Observation.Source;
    public string Qualification => Observation.Qualification;
    public string[] Limitations =>
    [
        "The executable and process epoch are pinned; loaded module bytes are not independently hashed.",
        "Player/component ownership, type fingerprints and stable record inputs are bracketed; the process-sourced game clock may advance, reads are sequential, and ABA cannot be excluded.",
        "Health, Mana and Energy calculations are candidates; inspect each field status and unavailableReason before using its values.",
        "Mana is emitted only for type-fingerprinted kind three; Energy is emitted only for type-fingerprinted kind four.",
        "Independent same-player changed-state correspondence, passive freshness, continuity and full-game restart qualification remain unverified.",
        "No native game getter is invoked; no memory, revision, refcount or game state is written."
    ];
}

/// <summary>One exact-build passive vitals candidate capture; no game actions.</summary>
internal static class CurrentBuildVitalsSampleCommand
{
    internal static Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken) =>
        RunAsync(options, output, cancellationToken,
            async (pid, ticks, ct) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPositionSampleCommand.GameSha256, ct),
            CurrentBuildVitalsCandidateReader.Read,
            async (pid, ticks, sha, ct) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, sha, TimeSpan.FromSeconds(1), ct));

    // Explicit offline lifecycle seam; production always acquires the shared lease.
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsObservation> read,
        Func<int, long, string, CancellationToken, Task<IAsyncDisposable>> acquireLease)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(openSession);
        ArgumentNullException.ThrowIfNull(read);
        ArgumentNullException.ThrowIfNull(acquireLease);
        if (!options.TryGetValue("--pid", out var rawPid) ||
            !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) ||
            !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required for the current-build vitals candidate sampler.");
        RequireNewOutput(path);
        cancellationToken.ThrowIfCancellationRequested();
        await using var lease = await acquireLease(pid, ticks,
            CurrentBuildPositionSampleCommand.GameSha256, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        // Reverse disposal order keeps the lease through all session cleanup.
        await using var session = await openSession(pid, ticks, cancellationToken);
        if (session.Identity.ProcessId != pid || session.Identity.ProcessStartUtcTicks != ticks ||
            !string.Equals(session.Identity.ExecutableSha256,
                CurrentBuildPositionSampleCommand.GameSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Native vitals session does not match requested process epoch/build.");
        return await CaptureAndPublishAsync(session, path, output, read, cancellationToken);
    }

    // The delegate lets offline tests exercise the publication boundary without
    // opening a process; production always uses the exact-build vitals reader.
    internal static async Task<int> CaptureAndPublishAsync(
        IReadOnlyNativeMemorySession session, string path, TextWriter output,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsObservation> read,
        CancellationToken cancellationToken)
    {
        RequireNewOutput(path);
        var report = await CaptureAsync(session, read, cancellationToken);
        var observation = report.Observation;
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-vitals-candidate-summary/2",
            status = report.Status,
            report.Qualification,
            healthStatus = observation.Health.Status,
            manaStatus = observation.Mana.Status,
            energyStatus = observation.Energy.Status,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    // Shared no-file acquisition boundary for the CLI and authenticated channel.
    internal static async Task<CurrentBuildVitalsReport> CaptureAsync(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsObservation> read,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var observation = read(session);
        var invalidated = await session.RevalidateAsync(cancellationToken);
        if (invalidated is not null)
            throw new InvalidDataException("Native vitals candidate process identity was invalidated; no report was published.");
        cancellationToken.ThrowIfCancellationRequested();
        return new CurrentBuildVitalsReport(observation);
    }

    private static void RequireNewOutput(string path)
    {
        if (File.Exists(path))
            throw new IOException("Native vitals candidate output exists; never overwrite an earlier observation.");
    }
}
