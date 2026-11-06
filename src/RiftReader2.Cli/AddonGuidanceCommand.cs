using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

public static class AddonGuidanceCommand
{
    public static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken = default)
    {
        var hasFrame = options.TryGetValue("--frame", out var framePath);
        var hasSnapshot = options.TryGetValue("--snapshot", out var snapshotPath);
        if (hasFrame == hasSnapshot)
            throw new ArgumentException("Exactly one of --frame or --snapshot is required.");
        var lab = Required(options, "--lab");
        var sessionId = Required(options, "--session-id");
        var resultSequence = ParseLong(Required(options, "--result-sequence"), "--result-sequence");
        var destinationX = ParseDouble(Required(options, "--destination-x"), "--destination-x");
        var destinationY = ParseDouble(Required(options, "--destination-y"), "--destination-y");
        var destinationZ = ParseDouble(Required(options, "--destination-z"), "--destination-z");
        var snapshot = hasSnapshot
            ? await GuidanceSnapshotFile.ReadAsync(snapshotPath!, sessionId, cancellationToken: cancellationToken)
            : null;
        var frame = snapshot?.Frame ??
            await GuidanceFrameFile.ReadAsync(framePath!, sessionId, cancellationToken);
        var sourcePath = snapshotPath ?? framePath!;
        var sourceOrigin = snapshot is null ? null : new AddonGuidanceOrigin(
            snapshot.Provenance.SourcePath,
            snapshot.Frame.EnvelopeSha256,
            snapshot.Frame.AddonFrameSha256,
            "live-reader-snapshot",
            "bound",
            "conditionally-fresh-at-load",
            "hashes-reported-by-live-reader; snapshot-file-hash-computed-from-source-bytes",
            snapshot.Provenance.SnapshotFileSha256,
            new(
                new(snapshot.Provenance.Target.ProcessId, snapshot.Provenance.Target.ProcessStartUtcTicks,
                    snapshot.Provenance.Target.ExecutablePath, snapshot.Provenance.Target.ExecutableSha256),
                new(snapshot.Provenance.Reader.InstanceId, snapshot.Provenance.Reader.SnapshotSequence,
                    snapshot.Provenance.Reader.Nonce),
                snapshot.Provenance.CapturedAtUtc,
                snapshot.Provenance.ScanStartedAtTimestamp,
                snapshot.Provenance.PublishedAtTimestamp,
                snapshot.Provenance.LastAdvanceAtTimestamp,
                snapshot.Provenance.SnapshotAgeMilliseconds,
                snapshot.Provenance.EffectiveLastAdvanceAgeMilliseconds,
                snapshot.Provenance.FreshnessTimeoutMilliseconds,
                GuidanceSnapshotFile.AssumedUtcSkewMilliseconds,
                "Snapshot age uses the host UTC clock and assumes source and host UTC differ by at most 250 ms; loading the file does not independently prove clock synchronization."));
        var report = AddonGuidanceCalculator.Calculate(
            frame, sourcePath, lab, sessionId, resultSequence,
            destinationX, destinationY, destinationZ, sourceOrigin);
        if (options.TryGetValue("--output", out var reportPath))
            await JsonReportWriter.WriteNewAsync(reportPath, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static string Required(IReadOnlyDictionary<string, string> options, string name) =>
        options.TryGetValue(name, out var value) ? value : throw new ArgumentException($"{name} is required.");

    private static long ParseLong(string text, string name) =>
        long.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var value)
            ? value : throw new ArgumentException($"{name} must be a positive integer.");

    private static double ParseDouble(string text, string name) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) && double.IsFinite(value)
            ? value : throw new ArgumentException($"{name} must be a finite invariant-culture number.");
}
