namespace RiftReader2.Domain;

public sealed record WallMotionSample(
    long Sequence,
    DateTimeOffset CapturedAtUtc,
    double MonotonicMilliseconds,
    double X,
    double Z,
    double ProjectionX,
    double ProjectionZ);

public sealed record WallMotionTrial(
    string Phase,
    string Role,
    DateTimeOffset KeyDownAtUtc,
    DateTimeOffset KeyUpAtUtc,
    double ObservedHoldMilliseconds,
    bool GameResponseVerified,
    string RunSha256);

public sealed record WallMotionReplayOptions(
    double MaxBoundaryGapMilliseconds = 100,
    double MaxProjectionGapMilliseconds = 100,
    double FreeTravelMaxDirectionErrorDegrees = 2,
    double FreeTravelMaxVectorErrorFraction = 0.05,
    double WallMinDirectionErrorDegrees = 45,
    double WallMinVectorErrorFraction = 1);

public sealed record WallMotionTrialResult(
    string Phase,
    string Role,
    DateTimeOffset KeyDownAtUtc,
    DateTimeOffset KeyUpAtUtc,
    double ObservedHoldMilliseconds,
    long StartSequence,
    long EndSequence,
    int ProjectionSampleCount,
    double StartBoundaryAgeMilliseconds,
    double EndBoundaryAgeMilliseconds,
    double MaximumProjectionGapMilliseconds,
    double KeyTimestampHoldMilliseconds,
    IReadOnlyList<double> ActualDeltaXz,
    double BracketDisplacementPerKeyHoldSecond,
    IReadOnlyList<double> ProjectionVectorXz,
    double ProjectionMagnitude,
    IReadOnlyList<double> ProjectedDeltaXz,
    double DirectionErrorDegrees,
    double ProjectedVectorErrorFractionOfActualDisplacement,
    string Classification,
    bool GameResponseVerified,
    string RunSha256);

public sealed record WallMotionReplaySummary(
    long SampleCount,
    long FirstSequence,
    long LastSequence,
    IReadOnlyList<WallMotionTrialResult> Trials,
    string ProjectionSemantic,
    string RealizedVelocity,
    bool ReproducedSavedConclusion);
