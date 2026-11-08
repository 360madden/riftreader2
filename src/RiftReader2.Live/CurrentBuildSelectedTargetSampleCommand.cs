using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal sealed record CurrentBuildSelectedTargetReport(SelectedTargetObservation Observation)
{
    public int SchemaVersion => 1;
    public string ContractVersion => "native-current-selected-target-candidate-sample/1";
    public string Status => "complete";
    public string Qualification => Observation.Qualification;
    public string[] Limitations => ["Executable SHA256 identifies on-disk bytes; loaded module bytes are not independently hashed.", "Sequential reads and byte anchors do not exclude ABA or prove atomicity.", "Target and vitals semantics, freshness and restart remain unverified.", "No game getter, memory write, or restart qualification is involved."];
}

internal static class CurrentBuildSelectedTargetSampleCommand
{
    internal static Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken) =>
        RunAsync(options, output, cancellationToken,
            static async (pid, ticks, token) => await NativeReadFileLease.AcquireAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, TimeSpan.FromSeconds(1), token),
            static async (pid, ticks, token) => await WindowsNativeMemorySession.OpenAsync(
                pid, ticks, CurrentBuildPlayerLookup.GameSha256, token),
            CurrentBuildSelectedTargetCandidateReader.Read);

    // Explicit offline-only seam; production entry supplies the real lease.
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options, TextWriter output,
        CancellationToken cancellationToken,
        Func<int, long, CancellationToken, Task<IAsyncDisposable>> acquireLease,
        Func<int, long, CancellationToken, Task<IReadOnlyNativeMemorySession>> open,
        Func<IReadOnlyNativeMemorySession, bool, bool, bool, SelectedTargetObservation> read)
    {
        ArgumentNullException.ThrowIfNull(acquireLease);
        ArgumentNullException.ThrowIfNull(open);
        ArgumentNullException.ThrowIfNull(read);
        if (!options.TryGetValue("--pid", out var rawPid) || !int.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out var pid) || pid <= 0 ||
            !options.TryGetValue("--start-ticks", out var rawTicks) || !long.TryParse(rawTicks, NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) || ticks <= 0 ||
            !options.TryGetValue("--output", out var path) || string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("--pid, --start-ticks and --output are required.");
        var includeName = options.TryGetValue("--include-name-seed", out var name) ? name == "true" ? true : throw new ArgumentException("--include-name-seed must be true.") : false;
        var includePosition = options.TryGetValue("--include-position", out var position) ? position == "true" ? true : throw new ArgumentException("--include-position must be true.") : false;
        var includeContext = options.TryGetValue("--include-context", out var context) ? context == "true" ? true : throw new ArgumentException("--include-context must be true.") : false;
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var lease = await acquireLease(pid, ticks, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await open(pid, ticks, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        var observation = read(session, includeName, includePosition, includeContext);
        if (await session.RevalidateAsync(cancellationToken) is not null) throw new InvalidDataException("Process identity invalidated; no report published.");
        cancellationToken.ThrowIfCancellationRequested();
        var report = new CurrentBuildSelectedTargetReport(observation);
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-selected-target-candidate-summary/1", report.Status, report.Qualification, output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }
}
