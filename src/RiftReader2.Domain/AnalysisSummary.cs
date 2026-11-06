namespace RiftReader2.Domain;

/// <summary>
/// Describes an analyzed sample stream and derivatives calculated from continuous intervals.
/// Nullable maxima mean that the stream contained no interval eligible for derivation.
/// </summary>
public sealed record AnalysisSummary(
    string SessionId,
    int SampleCount,
    long FirstSequence,
    long LastSequence,
    double StartTimestampSeconds,
    double EndTimestampSeconds,
    double DurationSeconds,
    long MissingSequenceCount,
    int SequenceGapCount,
    int TimingGapCount,
    int DerivedIntervalCount,
    int SkippedDerivativeIntervalCount,
    double? MaxHorizontalDerivedSpeed,
    double? MaxAbsoluteDerivedYawRate);
