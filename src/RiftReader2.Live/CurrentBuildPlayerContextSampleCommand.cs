using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CurrentBuildPlayerContextReport(CurrentBuildPlayerContextObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-player-context-candidate-sample/1";
    public string Status => "complete";
    public string Qualification => Observation.Qualification;
    public string[] Limitations => ["Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.", "Sequential reads and byte anchors do not exclude ABA or prove atomicity.", "Target, level and combat semantics lack changed-state and API confirmation.", "No game getter, memory write, or restart qualification is involved."];
}

internal static class CurrentBuildPlayerContextSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken) =>
        RunAsync(options,output,cancellationToken,
            async (pid,ticks,ct)=>await NativeReadFileLease.AcquireAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,TimeSpan.FromSeconds(1),ct),
            async (pid,ticks,ct)=>await WindowsNativeMemorySession.OpenAsync(pid,ticks,CurrentBuildPlayerLookup.GameSha256,ct),
            CurrentBuildPlayerContextCandidateReader.Read);
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken,
        Func<int,long,CancellationToken,Task<IAsyncDisposable>> acquire,
        Func<int,long,CancellationToken,Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession,CurrentBuildPlayerContextObservation> read)
    {
        if (!options.TryGetValue("--pid", out var rawPid) || !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) || !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required.");
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var lease = await acquire(pid,ticks,cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await open(pid,ticks,cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        var observation = read(session);
        if (await session.RevalidateAsync(cancellationToken) is not null) throw new InvalidDataException("Process identity invalidated; no report published.");
        cancellationToken.ThrowIfCancellationRequested();
        var report = new CurrentBuildPlayerContextReport(observation);
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-player-context-candidate-summary/1", report.Status, report.Qualification, output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
