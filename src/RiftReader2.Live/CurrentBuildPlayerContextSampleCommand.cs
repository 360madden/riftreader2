using System.Diagnostics;
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
        var samples = BoundedInt(options, "--samples", 1, 1, 30);
        var intervalMilliseconds = BoundedInt(options, "--interval-ms", 500, 0, 2000);
        if (File.Exists(path)) throw new IOException("Output exists; never overwrite an earlier observation.");
        await using var lease = await acquire(pid,ticks,cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = await open(pid,ticks,cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        if (samples == 1)
        {
            var observation = read(session);
            if (await session.RevalidateAsync(cancellationToken) is not null) throw new InvalidDataException("Process identity invalidated; no report published.");
            cancellationToken.ThrowIfCancellationRequested();
            var report = new CurrentBuildPlayerContextReport(observation);
            await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
            await output.WriteLineAsync(JsonSerializer.Serialize(new { recordType = "native-current-player-context-candidate-summary/1", report.Status, report.Qualification, output = Path.GetFullPath(path) }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
            return 0;
        }
        var observations = new List<CurrentBuildPlayerContextObservation>(samples);
        var watch = Stopwatch.StartNew();
        for (var i = 0; i < samples; ++i)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var observation = read(session);
            if (observation.Identity != session.Identity || observation.UnitKey == 0 ||
                (observations.Count != 0 &&
                    (observation.UnitKey != observations[0].UnitKey ||
                     observation.StartedAtUtc < observations[^1].CompletedAtUtc)) ||
                observation.CompletedAtUtc < observation.StartedAtUtc)
                throw new InvalidDataException("Player context burst owner or observation order changed; no report published.");
            if (await session.RevalidateAsync(cancellationToken) is not null)
                throw new InvalidDataException("Process identity invalidated during burst; no report published.");
            observations.Add(observation);
            if (i + 1 < samples && intervalMilliseconds != 0)
                await Task.Delay(intervalMilliseconds, cancellationToken);
        }
        cancellationToken.ThrowIfCancellationRequested();
        var last = observations[^1];
        var burst = new
        {
            schemaVersion = 1,
            contractVersion = "native-current-player-context-candidate-burst/1",
            status = "complete",
            qualification = last.Qualification,
            identity = session.Identity,
            requestedSamples = samples,
            completedSamples = observations.Count,
            captureElapsedMilliseconds = watch.Elapsed.TotalMilliseconds,
            observation = last,
            observations,
            limitations = new[] {
                "Exact process/build and read lease are bound through all observations.",
                "Stable self key is candidate evidence, not independent Lua player identity.",
                "Target reads are passive, sequential and may remain unavailable; no gameplay input is sent.",
                "Changed-state meaning, atomicity, passive freshness and restart qualification remain open."
            }
        };
        await JsonReportWriter.WriteNewAsync(path, burst, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new {
            recordType = "native-current-player-context-candidate-summary/1",
            burst.status, burst.qualification, burst.completedSamples,
            output = Path.GetFullPath(path)
        }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        return 0;
    }

    private static int BoundedInt(IReadOnlyDictionary<string, string> options, string name,
        int fallback, int min, int max)
    {
        if (!options.TryGetValue(name, out var raw)) return fallback;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
            value < min || value > max)
            throw new ArgumentException($"{name} must be {min}..{max}.");
        return value;
    }
}
