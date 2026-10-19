using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record ReaderConfiguration(int SchemaVersion, AnalysisOptions Analysis, long MaxCaptureBytes)
{
    public static ReaderConfiguration Default { get; } = new(1, new(), 268435456);

    public void Validate()
    {
        if (SchemaVersion != 1)
            throw new InvalidDataException($"Unsupported configuration schema {SchemaVersion}; expected 1.");
        if (Analysis is null || !double.IsFinite(Analysis.MaxGapSeconds) || Analysis.MaxGapSeconds <= 0 || Analysis.MaxSamples < 2)
            throw new InvalidDataException("Analysis requires a positive finite maxGapSeconds and maxSamples >= 2.");
        if (MaxCaptureBytes <= 0 || MaxCaptureBytes > 8L * 1024 * 1024 * 1024)
            throw new InvalidDataException("maxCaptureBytes must be between 1 and 8589934592.");
    }

    public static async Task<ReaderConfiguration> LoadAsync(string path, CancellationToken cancellationToken = default)
    {
        var bytes = await BoundedJson.ReadAsync(path, cancellationToken);
        var document = JsonSerializer.Deserialize<ConfigurationDocument>(bytes, JsonFormat.Options)
            ?? throw new InvalidDataException("Configuration cannot be null.");
        var configuration = new ReaderConfiguration(document.SchemaVersion,
            new AnalysisOptions(document.Analysis.MaxGapSeconds, document.Analysis.MaxSamples), document.MaxCaptureBytes);
        configuration.Validate();
        return configuration;
    }

    // Wire contracts require every setting. Domain defaults are for code callers only.
    private sealed record ConfigurationDocument(int SchemaVersion, AnalysisDocument Analysis, long MaxCaptureBytes);
    private sealed record AnalysisDocument(double MaxGapSeconds, int MaxSamples);
}
