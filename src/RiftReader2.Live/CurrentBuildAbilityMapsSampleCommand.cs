using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CurrentBuildAbilityMapsReport(CurrentBuildAbilityMapsObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-ability-maps-candidate-sample/1";
    public string Status => "complete";
    public string Qualification => Observation.Qualification;
    public string[] Limitations => ["Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.", "Sequential reads and byte anchors do not exclude ABA or prove atomicity.", "Raw candidate fields do not establish learned abilities or API cooldown semantics.", "No game getter, memory write, or restart qualification is involved."];
}

internal static class CurrentBuildAbilityMapsSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken) =>
        RunAsync(options, output, cancellationToken,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildAbilityMapsCandidateReader.Read);

    // Explicit offline-only seam; production always supplies the real lease.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, CurrentBuildAbilityMapsObservation> read)
    {
        if (!options.TryGetValue("--pid", out var rawPid) || !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) || !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required.");
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var lease = await acquireLease(pid, ticks, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        var observation = read(session);
        if (await session.RevalidateAsync(cancellationToken) is not null) throw new InvalidDataException("Process identity invalidated; no report published.");
        cancellationToken.ThrowIfCancellationRequested();
        var report = new CurrentBuildAbilityMapsReport(observation);
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-ability-maps-candidate-summary/1", report.Status, report.Qualification, output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
