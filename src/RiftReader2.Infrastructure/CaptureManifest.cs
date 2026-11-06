namespace RiftReader2.Infrastructure;

public sealed record CaptureManifest(
    int SchemaVersion,
    string BuildSha256,
    string SessionId,
    string SamplesFile,
    string SamplesSha256,
    string SourceKind,
    string PositionUnits,
    string CoordinateFrame,
    string ClockBasis,
    double? TimingUncertaintySeconds)
{
    public void Validate()
    {
        if (SchemaVersion != 1)
            throw new InvalidDataException($"Unsupported capture schema {SchemaVersion}; expected 1.");
        if (!IsSha256(BuildSha256) || !IsSha256(SamplesSha256))
            throw new InvalidDataException("Build and samples identities must be SHA-256 hex strings.");
        if (string.IsNullOrWhiteSpace(SessionId) || SessionId.Length > 256)
            throw new InvalidDataException("sessionId must contain 1 to 256 characters.");
        if (SourceKind is not ("synthetic" or "rift-recording"))
            throw new InvalidDataException("sourceKind must be 'synthetic' or 'rift-recording'.");
        if (string.IsNullOrWhiteSpace(PositionUnits) || PositionUnits.Length > 64)
            throw new InvalidDataException("positionUnits must contain 1 to 64 characters.");
        if (CoordinateFrame != "xz-horizontal-y-up")
            throw new InvalidDataException("coordinateFrame must be 'xz-horizontal-y-up'.");
        if (ClockBasis != "session-monotonic-seconds")
            throw new InvalidDataException("clockBasis must be 'session-monotonic-seconds'.");
        if (TimingUncertaintySeconds is { } timingUncertainty &&
            (!double.IsFinite(timingUncertainty) || timingUncertainty < 0))
            throw new InvalidDataException("timingUncertaintySeconds must be null or a finite nonnegative number.");
        // Evidence bundles are deliberately flat. Avoid implicit arbitrary path access.
        if (string.IsNullOrWhiteSpace(SamplesFile) || SamplesFile.Length > 200 ||
            SamplesFile is "." or ".." || SamplesFile.IndexOfAny(['/', '\\', ':']) >= 0 ||
            SamplesFile.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new InvalidDataException("samplesFile must be a plain filename beside the manifest.");
    }

    private static bool IsSha256(string? value) =>
        value is { Length: 64 } && value.All(char.IsAsciiHexDigit);
}
