using System.Security.Cryptography;
using System.Text;

namespace RiftReader2.Domain;

public static class FieldDefinitionFingerprint
{
    /// <summary>
    /// Hashes the definition using framing version 1: an ASCII version tag followed by every
    /// scalar in record declaration order. Each UTF-8 string is prefixed by its unsigned 32-bit
    /// little-endian byte length; each list is prefixed by its unsigned 32-bit little-endian count,
    /// and applicability entries frame build then session. No JSON representation participates.
    /// </summary>
    public static string Compute(FieldDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        using var bytes = new MemoryStream();
        using (var writer = new BinaryWriter(bytes, new UTF8Encoding(false, true), leaveOpen: true))
        {
            WriteString(writer, "RiftReader2.FieldDefinitionFingerprint/1");
            WriteString(writer, definition.FieldId);
            WriteString(writer, definition.Meaning);
            WriteString(writer, definition.Units);
            WriteString(writer, definition.SourceKind);
            WriteString(writer, definition.Locator.Kind);
            WriteString(writer, definition.Locator.Method);
            WriteCount(writer, definition.Applicability.Count);
            foreach (var item in definition.Applicability)
            {
                WriteString(writer, item.BuildSha256);
                WriteString(writer, item.SessionId);
            }
            WriteStrings(writer, definition.InvalidationConditions);
            WriteStrings(writer, definition.RequiredClaims);
        }
        return Convert.ToHexString(SHA256.HashData(bytes.GetBuffer().AsSpan(0, checked((int)bytes.Length))));
    }

    private static void WriteStrings(BinaryWriter writer, IReadOnlyList<string> values)
    {
        WriteCount(writer, values.Count);
        foreach (var value in values)
            WriteString(writer, value);
    }

    private static void WriteCount(BinaryWriter writer, int count) => writer.Write(checked((uint)count));

    private static void WriteString(BinaryWriter writer, string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        var bytes = Encoding.UTF8.GetBytes(value);
        writer.Write(checked((uint)bytes.Length));
        writer.Write(bytes);
    }
}

public sealed record FieldCatalog(
    int SchemaVersion,
    string ContractVersion,
    IReadOnlyList<FieldDefinition> Fields);

public sealed record FieldDefinition(
    string FieldId,
    string Meaning,
    string Units,
    string SourceKind,
    FieldLocator Locator,
    IReadOnlyList<FieldApplicability> Applicability,
    IReadOnlyList<string> InvalidationConditions,
    IReadOnlyList<string> RequiredClaims);

public sealed record FieldLocator(string Kind, string Method);

public sealed record FieldApplicability(string BuildSha256, string SessionId);

public sealed record FieldAssessment(
    string AssessmentId,
    string FieldId,
    string FieldDefinitionSha256,
    string Reviewer,
    string Method,
    string EvidenceOrigin,
    DateTimeOffset AssessedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    FieldApplicability Applicability,
    IReadOnlyList<FieldAssessmentDeclaration> Declarations,
    IReadOnlyList<FieldEvidenceArtifact> Artifacts,
    string AssessmentSha256);

public sealed record FieldAssessmentDeclaration(string Claim, string Outcome, string Rationale);

public sealed record FieldEvidenceArtifact(
    string EvidenceRole,
    string File,
    long ByteLength,
    string Sha256,
    string EvidenceKind,
    string BuildSha256,
    string SessionId);

public sealed record FieldQualificationContext(
    string BuildSha256,
    string SessionId,
    DateTimeOffset EvaluatedAtUtc);

public sealed record FieldQualificationEvaluation(
    string SemanticVerification,
    FieldQualificationContext Context,
    IReadOnlyList<FieldQualificationResult> Fields,
    IReadOnlyList<FieldAssessmentDisposition> AssessmentDispositions);

public sealed record FieldQualificationResult(
    string FieldId,
    string FieldDefinitionSha256,
    IReadOnlyList<string> RequiredClaims,
    string Status,
    IReadOnlyList<string> Reasons,
    IReadOnlyList<FieldClaimResult> Claims);

public sealed record FieldClaimResult(
    string Claim,
    string Status,
    IReadOnlyList<string> Reasons,
    IReadOnlyList<string> SupportingAssessmentIds,
    IReadOnlyList<string> ContradictingAssessmentIds);

public sealed record FieldAssessmentDisposition(
    string AssessmentId,
    string AssessmentSha256,
    string FieldId,
    string Claim,
    string Outcome,
    string Disposition,
    string Reason,
    string Reviewer,
    string Method,
    string EvidenceOrigin,
    string Rationale,
    string ArtifactVerification,
    IReadOnlyList<FieldEvidenceArtifact> Artifacts,
    string BuildSha256,
    string SessionId,
    DateTimeOffset AssessedAtUtc,
    DateTimeOffset? ExpiresAtUtc);
