using System.Diagnostics;
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
        var samples = BoundedInt(options, "--samples", 1, 1, 30);
        var interval = BoundedInt(options, "--interval-ms", 500, 0, 2000);
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
        return samples == 1
            ? await CaptureAndPublishAsync(session, path, output, read, cancellationToken)
            : await CaptureBurstAndPublishAsync(session, path, output, read, samples, interval, cancellationToken);
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

    // A multi-sample physical read reuses the same lease and process session.
    // Preserve the single-sample report schema above for all existing callers.
    internal static async Task<int> CaptureBurstAndPublishAsync(
        IReadOnlyNativeMemorySession session, string path, TextWriter output,
        Func<IReadOnlyNativeMemorySession, CurrentBuildVitalsObservation> read,
        int samples, int intervalMilliseconds, CancellationToken cancellationToken)
    {
        if (samples is < 2 or > 30 || intervalMilliseconds is < 0 or > 2000)
            throw new ArgumentException("Vitals bursts require 2..30 samples and 0..2000ms intervals.");
        RequireNewOutput(path);
        var observations = new List<CurrentBuildVitalsObservation>(samples);
        ulong? playerKey = null;
        var elapsed = Stopwatch.StartNew();
        for (var index = 0; index < samples; ++index)
        {
            var observation = (await CaptureAsync(session, read, cancellationToken)).Observation;
            if (observation.UnitKey == 0 || (playerKey is ulong original && original != observation.UnitKey))
                throw new InvalidDataException("Native vitals player changed during sampling; no report was published.");
            playerKey = observation.UnitKey;
            observations.Add(observation);
            if (index + 1 < samples && intervalMilliseconds != 0)
                await Task.Delay(intervalMilliseconds, cancellationToken);
        }

        var last = observations[^1];
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-vitals-candidate-burst/1",
            status = "complete",
            sourceBuildSha256 = CurrentBuildPositionSampleCommand.GameSha256,
            session.Identity,
            source = last.Source,
            qualification = last.Qualification,
            requestedSamples = samples,
            completedSamples = observations.Count,
            captureElapsedMilliseconds = elapsed.Elapsed.TotalMilliseconds,
            observation = last, // Same compact projection as the original one-shot receipt.
            observations,
            limitations = new[]
            {
                "The exact process epoch/build and shared read lease are pinned for the entire burst.",
                "All observed player keys match; this does not prove continuous owner identity between samples.",
                "Each read revalidates the process and source inputs independently; sequential fields are not atomic.",
                "No changed-state semantics, passive freshness or game-restart qualification is implied."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-vitals-candidate-summary/2",
            report.status,
            report.qualification,
            report.completedSamples,
            healthStatus = last.Health.Status,
            manaStatus = last.Mana.Status,
            energyStatus = last.Energy.Status,
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
        var openedIdentity = session.Identity;
        var observation = read(session);
        var invalidated = await session.RevalidateAsync(cancellationToken);
        if (invalidated is not null)
            throw new InvalidDataException("Native vitals candidate process identity was invalidated; no report was published.");
        if (session.Identity != openedIdentity)
            throw new InvalidOperationException("Native vitals session identity changed during revalidation; no report was published.");
        if (observation.Identity != openedIdentity || observation.UnitKey == 0)
            throw new InvalidDataException("Native vitals player/process identity changed; no report was published.");
        cancellationToken.ThrowIfCancellationRequested();
        return new CurrentBuildVitalsReport(observation);
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
        int defaultValue, int minimum, int maximum)
    {
        if (!options.TryGetValue(name, out var raw))
            return defaultValue;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
            value < minimum || value > maximum)
            throw new ArgumentException($"{name} must be in {minimum}..{maximum}.");
        return value;
    }

    private static void RequireNewOutput(string path)
    {
        if (File.Exists(path))
            throw new IOException("Native vitals candidate output exists; never overwrite an earlier observation.");
    }
}
