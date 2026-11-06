namespace RiftReader2.Domain;

/// <summary>
/// Bounds and continuity rules for offline motion analysis.
/// </summary>
public sealed record AnalysisOptions(
    double MaxGapSeconds = 0.25,
    int MaxSamples = 1_000_000);
