using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

/// <summary>
/// A bounded operational sampling convenience, not a field qualification workflow.
/// </summary>
internal static class PositionSampleCommand
{
    private static readonly JsonSerializerOptions JsonLineOptions = new(JsonFormat.Options) { WriteIndented = false };

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--profile", out var profilePath) ||
            !options.TryGetValue("--output", out var outputPath))
            throw new ArgumentException("--profile and --output are required.");
        if (File.Exists(outputPath))
            throw new IOException("Position sample output already exists and will not be overwritten.");
        var sampleCount = ParseBoundedInt(options, "--samples", 3, 1, 30);
        var intervalMilliseconds = ParseBoundedInt(options, "--interval-ms", 500, 0, 2000);
        if ((long)(sampleCount - 1) * intervalMilliseconds > 60_000)
            throw new ArgumentException("The requested sampling schedule exceeds 60 seconds.");
        var profile = await NativePositionProfileLoader.LoadAsync(profilePath, cancellationToken);
        var processes = Process.GetProcessesByName("rift_x64");
        try
        {
            if (processes.Length != 1)
                throw new InvalidDataException($"Expected exactly one rift_x64 process; found {processes.Length}.");
            await using var session = await WindowsNativeMemorySession.OpenAsync(
                processes[0].Id, null, profile.Profile.ExecutableSha256, cancellationToken);
            var samples = await PositionCandidateSampler.SampleAsync(
                profile.Profile, session, sampleCount, intervalMilliseconds, cancellationToken,
                observation => output.WriteLineAsync(JsonSerializer.Serialize(new
                {
                    RecordType = "native-position-sample/1",
                    Qualification = "candidate-only",
                    Observation = observation
                }, JsonLineOptions)));
            var report = new NativePositionSamplesReport(
                1,
                "native-position-samples/1",
                "candidate-only-not-motion-or-update-qualified",
                profile.SourceSha256,
                profile.EvidenceReference,
                profile.Profile,
                samples,
                [
                    "A complete read means only that the exact-build pointer and finite float32 bytes were read; it does not prove player-position semantics.",
                    "Every sample re-resolves the module-relative pointer and brackets reads with process identity validation; absolute owner addresses are session-local.",
                    "The current profile is not valid for a different game executable SHA-256; discovery fallback is separate, never automatic.",
                    "Sample intervals are delays after each completed read, not a guaranteed rate; use per-sample timestamps to measure cadence.",
                    "No Lua freshness, player movement, restart survival or patch survival was tested by this command.",
                    "Raw terminal bytes are not embedded in this compact operational report; retain follow-pointer originals for independent field-evidence review."
                ]);
            await JsonReportWriter.WriteNewAsync(outputPath, report, cancellationToken);
            await output.WriteLineAsync(JsonSerializer.Serialize(new
            {
                RecordType = "native-position-samples-summary/1",
                report.ContractVersion,
                report.Qualification,
                report.Samples.Status,
                report.Samples.Reason,
                report.Samples.CompletedSamples,
                report.Samples.RequestedSamples,
                Latest = report.Samples.Observations.LastOrDefault(),
                Output = Path.GetFullPath(outputPath)
            }, JsonLineOptions));
            return samples.Status == "complete" ? 0 : 3;
        }
        finally
        {
            foreach (var process in processes)
                process.Dispose();
        }
    }

    private static int ParseBoundedInt(
        IReadOnlyDictionary<string, string> options,
        string name,
        int defaultValue,
        int minimum,
        int maximum)
    {
        if (!options.TryGetValue(name, out var raw))
            return defaultValue;
        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var value) ||
            value < minimum || value > maximum)
            throw new ArgumentException($"{name} must be an integer between {minimum} and {maximum}.");
        return value;
    }
}

public sealed record NativePositionSamplesReport(
    int SchemaVersion,
    string ContractVersion,
    string Qualification,
    string ProfileSha256,
    string EvidenceReference,
    PositionCandidateProfile Profile,
    PositionCandidateSampleSummary Samples,
    IReadOnlyList<string> Limitations);
