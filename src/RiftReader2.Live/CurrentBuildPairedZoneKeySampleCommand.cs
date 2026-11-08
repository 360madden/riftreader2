using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CurrentBuildPairedZoneKeyReport(CurrentBuildPairedZoneKeyObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-paired-zone-key-candidate-sample/1";
    public string Status => "complete";
    public string Qualification => Observation.Qualification;
    public string ProcessRevalidationStatus => "passed-before-publication";
    public string[] Limitations =>
    [
        "Exact executable SHA256 pins on-disk bytes; loaded module bytes are not independently hashed.",
        "Raw per-unit zone keys and positions are sequential candidates, not an atomic snapshot.",
        "Matching raw zone keys do not prove the same zone instance/world; world identity remains unavailable.",
        "The clock domain is local to this one paired acquisition, not a cross-run producer clock.",
        "Final process revalidation precedes atomic file publication; it does not prove producer freshness.",
        "No getter, process-memory write, target selection or game/VM action is performed."
    ];
}

/// <summary>
/// Registered candidate command boundary. One read-only process session, one
/// guarded paired acquisition, final async process check, atomic no-overwrite
/// report publication. No game input or native getter is invoked.
/// </summary>
internal static class CurrentBuildPairedZoneKeySampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken cancellationToken) =>
        RunAsync(options, output, cancellationToken,
            async (pid, ticks, ct) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, ct),
            CurrentBuildPairedZoneKeyCandidateReader.Read);

    // Dependency injection is for offline lifecycle/publication tests only.
    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> openSession,
        Func<IReadOnlyNativeMemorySession, int, CurrentBuildPairedZoneKeyObservation> readPair)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(openSession);
        ArgumentNullException.ThrowIfNull(readPair);
        if (options.Keys.Any(key => key is not ("--pid" or "--start-ticks" or "--output" or "--max-acquisition-ms")))
            throw new ArgumentException("Unsupported paired-zone-key option.");
        if (!options.TryGetValue("--pid", out var p) ||
            !int.TryParse(p, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var t) ||
            !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var requestedPath) || string.IsNullOrWhiteSpace(requestedPath))
            throw new ArgumentException("--pid, --start-ticks and --output are required.");
        var maxSpan = 1000;
        if (options.TryGetValue("--max-acquisition-ms", out var span) &&
            (!int.TryParse(span, NumberStyles.None, CultureInfo.InvariantCulture, out maxSpan) ||
             maxSpan is < 1 or > 5000))
            throw new ArgumentException("--max-acquisition-ms must be 1..5000.");
        var path = Path.GetFullPath(requestedPath);
        if (File.Exists(path) || Directory.Exists(path))
            throw new IOException("Output already exists; never overwrite evidence.");
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await openSession(pid, ticks, cancellationToken);
        var admitted = session.Identity;
        if (admitted.ProcessId != pid || admitted.ProcessStartUtcTicks != ticks ||
            !string.Equals(admitted.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            admitted.ModuleBaseAddress < 0x10000 || admitted.ModuleBaseAddress % 8 != 0 ||
            admitted.ModuleBaseAddress > 0x7FFFFFFFFFFFUL || admitted.ModuleSize < 0x34731B8 ||
            admitted.ModuleSize > 0x7FFFFFFFFFFFUL - admitted.ModuleBaseAddress)
            throw new InvalidDataException("Opened process does not match the requested exact-build epoch/module.");
        cancellationToken.ThrowIfCancellationRequested();
        var observation = readPair(session, maxSpan);
        if (observation.Identity != admitted || observation.Positions.Identity != admitted || session.Identity != admitted)
            throw new InvalidDataException("Paired result process/module identity changed.");
        if (observation.SelfZone.UnitKey != observation.Positions.Self.UnitKey ||
            observation.TargetZone.UnitKey != observation.Positions.Target?.UnitKey)
            throw new InvalidDataException("Zone units do not match paired position ownership.");
        cancellationToken.ThrowIfCancellationRequested();
        if (await session.RevalidateAsync(cancellationToken) is not null || session.Identity != admitted)
            throw new InvalidDataException("Final process revalidation failed; no report published.");
        cancellationToken.ThrowIfCancellationRequested();
        var report = new CurrentBuildPairedZoneKeyReport(observation);
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new
        {
            recordType = "native-current-paired-zone-key-candidate-summary/1",
            report.Status, report.Qualification,
            observationStatus = observation.Status, observation.ZoneKeyRelation,
            targetZoneStatus = observation.TargetZone.Status, observation.SameWorldStatus,
            observation.AcquisitionMilliseconds, output = path
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
