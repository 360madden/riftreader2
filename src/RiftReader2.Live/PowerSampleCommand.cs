using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

internal static class PowerSampleCommand
{
    internal static async Task<int> RunAsync(IReadOnlyDictionary<string, string> options,
        TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--output", out var path) ||
            !options.TryGetValue("--pid", out var pidText) ||
            !options.TryGetValue("--start-ticks", out var ticksText))
            throw new ArgumentException("--output, --pid and --start-ticks are required.");
        if (File.Exists(path)) throw new IOException("Power output already exists.");
        var pid = checked((int)ParseNumber(pidText));
        var ticks = ParseNumber(ticksText);
        var count = options.TryGetValue("--samples", out var countText)
            ? checked((int)ParseNumber(countText)) : 1;
        var interval = options.TryGetValue("--interval-ms", out var intervalText)
            ? checked((int)ParseNumber(intervalText)) : 100;
        if (pid <= 0 || ticks <= 0 || count is < 1 or > 600 || interval is < 0 or > 2000 ||
            (long)(count - 1) * interval > 60_000)
            throw new ArgumentException("Invalid identity or sampling schedule (maximum 600 samples / 60 seconds).");
        await using var session = await WindowsNativeMemorySession.OpenAsync(
            pid, ticks, PowerCandidateReader.ExecutableSha256, cancellationToken);
        var samples = new List<PowerCandidateObservation>();
        var timer = Stopwatch.StartNew();
        for (var i = 0; i < count && timer.ElapsedMilliseconds < 60_000; i++)
        {
            samples.Add(await PowerCandidateReader.ReadAsync(session, cancellationToken));
            if (i + 1 < count && interval > 0) await Task.Delay(interval, cancellationToken);
        }
        var report = new
        {
            SchemaVersion = 1,
            ContractVersion = "native-power-samples/1",
            Qualification = "candidate-only",
            PowerCandidateReader.Recipe,
            session.Identity,
            Status = samples.Count == count && samples.All(s => s.Status == "complete") ? "complete" : "partial",
            RequestedSamples = count,
            Samples = samples,
            Limitations = new[] { "Exact-build Warrior Power only. No patch recovery or semantic/restart qualification is implied by this read.",
                "Every observation resolves fresh pointers and checks stable record inputs; reads are not atomic with Lua or the game.",
                "Sequence changes and unavailable reads produce null values, never cached Power. Raw record base is not current Power." }
        };
        await JsonReportWriter.WriteNewAsync(path, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { report.Status, Samples = samples.Count, Output = path }, JsonFormat.Options));
        return report.Status == "complete" ? 0 : 3;
    }
    private static long ParseNumber(string text) =>
        long.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var value)
            ? value : throw new ArgumentException("Identity and sampling options must be nonnegative integers.");
}
