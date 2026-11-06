using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record WallMotionEvidenceManifest(
    int SchemaVersion,
    string EvidenceKind,
    string SourcePath,
    long SourceByteLength,
    string SourceSha256,
    int ExpectedSampleCount,
    int MaxLineBytes,
    WallMotionExpectedIdentity Identity,
    double MaxBoundaryGapMilliseconds,
    double MaxProjectionGapMilliseconds,
    IReadOnlyList<WallMotionRunArtifact> Trials)
{
    public void Validate()
    {
        if (SchemaVersion != 1 || EvidenceKind != "v1-wall-motion")
            throw new InvalidDataException("Unsupported wall-motion evidence manifest.");
        if (!Path.IsPathFullyQualified(SourcePath))
            throw new InvalidDataException("Wall-motion sourcePath must be an exact absolute path.");
        if (SourceByteLength <= 0 || SourceByteLength > 2L * 1024 * 1024 * 1024)
            throw new InvalidDataException("Wall-motion source byte length is outside the supported range.");
        ValidateSha256(SourceSha256, "source");
        if (ExpectedSampleCount is < 1 or > 1_000_000)
            throw new InvalidDataException("Wall-motion sample count is outside the supported range.");
        if (MaxLineBytes is < 1024 or > 1024 * 1024)
            throw new InvalidDataException("Wall-motion line limit is outside the supported range.");
        if (!double.IsFinite(MaxBoundaryGapMilliseconds) || MaxBoundaryGapMilliseconds <= 0 || MaxBoundaryGapMilliseconds > 1000)
            throw new InvalidDataException("Wall-motion boundary-gap limit is invalid.");
        if (!double.IsFinite(MaxProjectionGapMilliseconds) || MaxProjectionGapMilliseconds <= 0 || MaxProjectionGapMilliseconds > 1000)
            throw new InvalidDataException("Wall-motion projection-gap limit is invalid.");
        Identity.Validate();
        if (Trials is null || Trials.Count is < 3 or > 32 || Trials.Any(static trial => trial is null)
            || Trials.Select(static trial => trial.Phase).Distinct(StringComparer.Ordinal).Count() != Trials.Count)
            throw new InvalidDataException("Wall-motion manifest requires unique bounded trials.");
        foreach (var trial in Trials)
            trial.Validate();
    }

    internal static void ValidateSha256(string value, string label)
    {
        if (value.Length != 64 || value.Any(static character => !char.IsAsciiHexDigit(character)))
            throw new InvalidDataException($"Wall-motion {label} SHA-256 is invalid.");
    }
}

public sealed record WallMotionExpectedIdentity(
    string ObserverInstanceId,
    int ProcessId,
    DateTimeOffset ProcessStartUtc,
    string ExecutableSha256,
    string RootRva)
{
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(ObserverInstanceId) || ObserverInstanceId.Length > 128 || ProcessId <= 0)
            throw new InvalidDataException("Wall-motion session identity is invalid.");
        WallMotionEvidenceManifest.ValidateSha256(ExecutableSha256, "executable");
        if (!RootRva.StartsWith("0x", StringComparison.Ordinal) || RootRva.Length is < 3 or > 18)
            throw new InvalidDataException("Wall-motion root RVA is invalid.");
    }
}

public sealed record WallMotionRunArtifact(
    string Phase,
    string Role,
    string File,
    long ByteLength,
    string Sha256)
{
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(Phase) || Phase.Length > 64 || Role is not ("free-travel" or "wall-contact"))
            throw new InvalidDataException("Wall-motion trial metadata is invalid.");
        if (Path.GetFileName(File) != File || string.IsNullOrWhiteSpace(File)
            || File.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new InvalidDataException($"Trial '{Phase}' must use a plain run filename.");
        if (ByteLength is < 1 or > 65536)
            throw new InvalidDataException($"Trial '{Phase}' run byte length is invalid.");
        WallMotionEvidenceManifest.ValidateSha256(Sha256, $"trial '{Phase}'");
    }
}

public sealed record WallMotionReplayReport(
    int SchemaVersion,
    string ReplayVersion,
    string EvidenceKind,
    ToolIdentity Implementation,
    WallMotionReplayInput Input,
    WallMotionReplayOptions Options,
    WallMotionReplaySummary Summary,
    IReadOnlyList<string> Limitations);

public sealed record WallMotionReplayInput(
    string ManifestSha256,
    string SourcePath,
    long SourceByteLength,
    string SourceSha256,
    string SourceHashVerification,
    int ExpectedSampleCount,
    WallMotionExpectedIdentity Identity,
    IReadOnlyList<WallMotionRunArtifact> RunArtifacts,
    string RunHashVerification);
