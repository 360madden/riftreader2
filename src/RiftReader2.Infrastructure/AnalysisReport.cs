using System.Reflection;
using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

// Explicit output DTOs prevent changes to input/configuration types leaking into schema 1.
public sealed record AnalysisReport(
    int SchemaVersion,
    string AnalyzerVersion,
    string EvidenceKind,
    ToolIdentity Implementation,
    ReportInput Input,
    ReportSettings Configuration,
    AnalysisSummary Summary)
{
    public static AnalysisReport Create(CaptureReader capture, ReaderConfiguration configuration,
        AnalysisSummary summary, ToolIdentity implementation) => new(
        1, "motion-derived/1", "derived-motion", implementation,
        new(capture.ManifestSha256, capture.Manifest.SamplesSha256, "verified",
            capture.Manifest.BuildSha256, "declared-only", capture.Manifest.SessionId,
            capture.Manifest.SourceKind, capture.Manifest.PositionUnits, capture.Manifest.CoordinateFrame,
            capture.Manifest.ClockBasis, capture.Manifest.TimingUncertaintySeconds),
        new(configuration.Analysis.MaxGapSeconds, configuration.Analysis.MaxSamples, configuration.MaxCaptureBytes),
        summary);
}

public sealed record ReportInput(
    string ManifestSha256,
    string SamplesSha256,
    string SamplesHashVerification,
    string DeclaredBuildSha256,
    string BuildIdentityVerification,
    string SessionId,
    string SourceKind,
    string PositionUnits,
    string CoordinateFrame,
    string ClockBasis,
    double? TimingUncertaintySeconds);

public sealed record ReportSettings(double MaxGapSeconds, int MaxSamples, long MaxCaptureBytes);

public sealed record ToolIdentity(string ToolVersion, IReadOnlyDictionary<string, string> AssemblySha256)
{
    public static ToolIdentity FromAssemblies(string toolVersion, params Assembly[] assemblies)
    {
        var hashes = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (var assembly in assemblies)
        {
            if (string.IsNullOrWhiteSpace(assembly.Location))
                throw new InvalidDataException("This deployment cannot identify its analysis binaries.");
            using var stream = File.OpenRead(assembly.Location);
            hashes.Add(assembly.GetName().Name!, Convert.ToHexString(SHA256.HashData(stream)));
        }
        return new(toolVersion, hashes);
    }
}
