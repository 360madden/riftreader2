using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record LoadedFieldCatalog(
    FieldCatalog Catalog,
    string CatalogSha256,
    IReadOnlyList<FieldAssessment> Assessments);

public static class FieldCatalogFile
{
    private const int MaxDocumentBytes = 65_536;
    private const int MaxCatalogFields = 128;
    private const int MaxAssessments = 256;
    private const int MaxArtifacts = 16;
    private const long MaxArtifactBytes = 16 * 1024 * 1024;
    private const long MaxAggregateArtifactBytes = 64 * 1024 * 1024;

    public static async Task<LoadedFieldCatalog> LoadAsync(
        string path,
        CancellationToken cancellationToken = default)
    {
        var fullPath = Path.GetFullPath(path);
        var bytes = await ReadBoundedAsync(fullPath, "Field catalog", cancellationToken);
        var document = Deserialize<FieldCatalogDocument>(bytes, "Field catalog");
        ValidateHeader(document.SchemaVersion, document.ContractVersion, "field-catalog/1", "Field catalog");
        if (document.Fields is null || document.Assessments is null ||
            document.Fields.Any(static field => field is null) ||
            document.Assessments.Any(static assessment => assessment is null))
            throw new InvalidDataException("Field catalog contains a null collection or entry.");
        if (document.Fields.Count is < 1 or > MaxCatalogFields)
            throw new InvalidDataException($"Field catalog must contain 1 to {MaxCatalogFields} fields.");
        if (document.Assessments.Count > MaxAssessments)
            throw new InvalidDataException($"Field catalog cannot reference more than {MaxAssessments} assessments.");

        var fields = document.Fields.Select(ToDomain).ToArray();
        RequireUnique(fields.Select(static field => field.FieldId), "fieldId");
        var directory = Path.GetDirectoryName(fullPath)!;
        var assessments = new List<FieldAssessment>(document.Assessments.Count);
        long aggregateArtifactBytes = 0;
        var referencedNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var reference in document.Assessments)
        {
            ValidatePlainFile(reference.Path, "assessment path");
            if (!referencedNames.Add(reference.Path))
                throw new InvalidDataException($"Assessment path '{reference.Path}' is duplicated.");
            ValidateLengthAndHash(reference.ByteLength, reference.Sha256, MaxDocumentBytes, "Assessment reference");
            var assessmentPath = Path.Combine(directory, reference.Path);
            var assessmentBytes = await ReadVerifiedAsync(
                assessmentPath, reference.ByteLength, reference.Sha256, MaxDocumentBytes, "Assessment", cancellationToken);
            var parsed = await ParseAssessmentAsync(assessmentBytes, directory,
                MaxAggregateArtifactBytes - aggregateArtifactBytes, cancellationToken);
            aggregateArtifactBytes = checked(aggregateArtifactBytes + parsed.ArtifactBytes);
            if (aggregateArtifactBytes > MaxAggregateArtifactBytes)
                throw new InvalidDataException($"Catalog artifacts exceed the {MaxAggregateArtifactBytes}-byte aggregate limit.");
            assessments.Add(parsed.Assessment);
        }
        RequireUnique(assessments.Select(static assessment => assessment.AssessmentId), "assessmentId");
        return new(new(1, "field-catalog/1", fields), Convert.ToHexString(SHA256.HashData(bytes)), assessments);
    }

    private static FieldDefinition ToDomain(FieldDefinitionDocument field)
    {
        if (field.Locator is null || field.Applicability is null || field.InvalidationConditions is null ||
            field.RequiredClaims is null || field.Applicability.Any(static item => item is null) ||
            field.InvalidationConditions.Any(static item => item is null) || field.RequiredClaims.Any(static item => item is null))
            throw new InvalidDataException($"Field '{field.FieldId}' contains a null object or entry.");
        RequireText(field.FieldId, 128, "fieldId");
        RequireText(field.Meaning, 512, $"Field '{field.FieldId}' meaning");
        RequireText(field.Units, 128, $"Field '{field.FieldId}' units");
        if (field.SourceKind is not ("addon" or "native" or "derived" or "synthetic"))
            throw new InvalidDataException($"Field '{field.FieldId}' has an unsupported sourceKind.");
        if (field.Locator.Kind is not ("addon-api" or "module-relative-rva" or "signature-scan" or
            "derivation" or "absolute-session-address" or "synthetic-fixture"))
            throw new InvalidDataException($"Field '{field.FieldId}' has an unsupported locator kind.");
        RequireText(field.Locator.Method, 1024, $"Field '{field.FieldId}' locator method");
        if (!LocatorMatchesSource(field.SourceKind, field.Locator.Kind))
            throw new InvalidDataException($"Field '{field.FieldId}' locator kind is inconsistent with its sourceKind.");
        if (field.Applicability.Count is < 1 or > 64)
            throw new InvalidDataException($"Field '{field.FieldId}' must declare 1 to 64 applicability entries.");
        var applicability = field.Applicability.Select(item =>
        {
            ValidateSha256(item.BuildSha256, $"Field '{field.FieldId}' buildSha256");
            RequireText(item.SessionId, 256, $"Field '{field.FieldId}' sessionId");
            return new FieldApplicability(item.BuildSha256.ToUpperInvariant(), item.SessionId);
        }).ToArray();
        RequireUnique(applicability.Select(static item => $"{item.BuildSha256}\0{item.SessionId}"),
            $"Field '{field.FieldId}' applicability");
        if (field.InvalidationConditions.Count is < 1 or > 32)
            throw new InvalidDataException($"Field '{field.FieldId}' must declare 1 to 32 invalidation conditions.");
        foreach (var condition in field.InvalidationConditions)
            RequireText(condition, 512, $"Field '{field.FieldId}' invalidation condition");
        RequireUnique(field.InvalidationConditions, $"Field '{field.FieldId}' invalidation condition");
        if (field.RequiredClaims.Count is < 2 or > 4 ||
            !field.RequiredClaims.Contains("meaning", StringComparer.Ordinal) ||
            !field.RequiredClaims.Contains("locator", StringComparer.Ordinal))
            throw new InvalidDataException($"Field '{field.FieldId}' requiredClaims must include meaning and locator.");
        foreach (var claim in field.RequiredClaims)
            ValidateClaim(claim, $"Field '{field.FieldId}'");
        RequireUnique(field.RequiredClaims, $"Field '{field.FieldId}' required claim");
        return new(field.FieldId, field.Meaning, field.Units, field.SourceKind,
            new(field.Locator.Kind, field.Locator.Method), applicability,
            field.InvalidationConditions.ToArray(), field.RequiredClaims.ToArray());
    }

    private static async Task<(FieldAssessment Assessment, long ArtifactBytes)> ParseAssessmentAsync(
        byte[] bytes,
        string directory,
        long remainingArtifactBudget,
        CancellationToken cancellationToken)
    {
        var document = Deserialize<FieldAssessmentDocument>(bytes, "Field assessment");
        ValidateHeader(document.SchemaVersion, document.ContractVersion, "field-assessment/1", "Field assessment");
        if (document.Applicability is null || document.Declarations is null || document.Artifacts is null ||
            document.Declarations.Any(static item => item is null) || document.Artifacts.Any(static item => item is null))
            throw new InvalidDataException("Field assessment contains a null object or entry.");
        RequireText(document.AssessmentId, 128, "assessmentId");
        RequireText(document.FieldId, 128, $"Assessment '{document.AssessmentId}' fieldId");
        ValidateSha256(document.FieldDefinitionSha256, $"Assessment '{document.AssessmentId}' fieldDefinitionSha256");
        RequireText(document.Reviewer, 256, $"Assessment '{document.AssessmentId}' reviewer");
        RequireText(document.Method, 1024, $"Assessment '{document.AssessmentId}' method");
        if (document.EvidenceOrigin is not ("synthetic" or "rift-recording"))
            throw new InvalidDataException($"Assessment '{document.AssessmentId}' has an unsupported evidenceOrigin.");
        RequireUtc(document.AssessedAtUtc, $"Assessment '{document.AssessmentId}' assessedAtUtc");
        if (document.ExpiresAtUtc is { } expires)
        {
            RequireUtc(expires, $"Assessment '{document.AssessmentId}' expiresAtUtc");
            if (expires <= document.AssessedAtUtc)
                throw new InvalidDataException($"Assessment '{document.AssessmentId}' expiresAtUtc must follow assessedAtUtc.");
        }
        ValidateSha256(document.Applicability.BuildSha256, $"Assessment '{document.AssessmentId}' buildSha256");
        RequireText(document.Applicability.SessionId, 256, $"Assessment '{document.AssessmentId}' sessionId");
        if (document.Declarations.Count is < 1 or > 4)
            throw new InvalidDataException($"Assessment '{document.AssessmentId}' must contain 1 to 4 declarations.");
        foreach (var declaration in document.Declarations)
        {
            ValidateClaim(declaration.Claim, $"Assessment '{document.AssessmentId}'");
            if (declaration.Outcome is not ("supports" or "contradicts"))
                throw new InvalidDataException($"Assessment '{document.AssessmentId}' has an unsupported outcome.");
            RequireText(declaration.Rationale, 1024, $"Assessment '{document.AssessmentId}' rationale");
        }
        RequireUnique(document.Declarations.Select(static item => item.Claim),
            $"Assessment '{document.AssessmentId}' declaration claim");
        if (document.Artifacts.Count is < 1 or > MaxArtifacts)
            throw new InvalidDataException($"Assessment '{document.AssessmentId}' must reference 1 to {MaxArtifacts} artifacts.");
        long declaredArtifactBytes = 0;
        foreach (var artifact in document.Artifacts)
        {
            ValidateLengthAndHash(artifact.ByteLength, artifact.Sha256, MaxArtifactBytes, "Artifact");
            declaredArtifactBytes = checked(declaredArtifactBytes + artifact.ByteLength);
        }
        if (declaredArtifactBytes > remainingArtifactBudget)
            throw new InvalidDataException($"Catalog artifacts exceed the {MaxAggregateArtifactBytes}-byte aggregate limit.");
        var artifacts = new List<FieldEvidenceArtifact>(document.Artifacts.Count);
        long artifactBytes = 0;
        var artifactNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var artifact in document.Artifacts)
        {
            if (artifact.EvidenceRole != "observation")
                throw new InvalidDataException($"Assessment '{document.AssessmentId}' artifact evidenceRole must be observation.");
            ValidatePlainFile(artifact.Path, "artifact path");
            if (!artifactNames.Add(artifact.Path))
                throw new InvalidDataException($"Assessment '{document.AssessmentId}' duplicates artifact '{artifact.Path}'.");
            ValidateLengthAndHash(artifact.ByteLength, artifact.Sha256, MaxArtifactBytes, "Artifact");
            artifactBytes = checked(artifactBytes + artifact.ByteLength);
            RequireText(artifact.EvidenceKind, 128, $"Assessment '{document.AssessmentId}' artifact evidenceKind");
            ValidateSha256(artifact.BuildSha256, $"Assessment '{document.AssessmentId}' artifact buildSha256");
            RequireText(artifact.SessionId, 256, $"Assessment '{document.AssessmentId}' artifact sessionId");
            if (!artifact.BuildSha256.Equals(document.Applicability.BuildSha256, StringComparison.OrdinalIgnoreCase) ||
                artifact.SessionId != document.Applicability.SessionId)
                throw new InvalidDataException($"Assessment '{document.AssessmentId}' artifact identity differs from its applicability.");
            await VerifyFileAsync(Path.Combine(directory, artifact.Path), artifact.ByteLength, artifact.Sha256,
                MaxArtifactBytes, "Artifact", cancellationToken);
            artifacts.Add(new("observation", artifact.Path, artifact.ByteLength, artifact.Sha256.ToUpperInvariant(),
                artifact.EvidenceKind, artifact.BuildSha256.ToUpperInvariant(), artifact.SessionId));
        }
        return (new(document.AssessmentId, document.FieldId, document.FieldDefinitionSha256.ToUpperInvariant(),
            document.Reviewer, document.Method, document.EvidenceOrigin, document.AssessedAtUtc,
            document.ExpiresAtUtc, new(document.Applicability.BuildSha256.ToUpperInvariant(),
                document.Applicability.SessionId),
            document.Declarations.Select(static item => new FieldAssessmentDeclaration(
                item.Claim, item.Outcome, item.Rationale)).ToArray(), artifacts,
            Convert.ToHexString(SHA256.HashData(bytes))), artifactBytes);
    }

    private static async Task<byte[]> ReadBoundedAsync(string path, string label, CancellationToken cancellationToken)
    {
        await using var stream = OpenRegularFile(path, label);
        if (stream.Length > MaxDocumentBytes)
            throw new InvalidDataException($"{label} exceeds {MaxDocumentBytes} bytes.");
        var bytes = new byte[stream.Length];
        await stream.ReadExactlyAsync(bytes, cancellationToken);
        return bytes;
    }

    private static async Task<byte[]> ReadVerifiedAsync(
        string path, long expectedLength, string expectedSha256, long maximumLength,
        string label, CancellationToken cancellationToken)
    {
        await using var stream = OpenRegularFile(path, label);
        if (stream.Length != expectedLength || stream.Length > maximumLength)
            throw new InvalidDataException($"{label} byte length does not match its declaration.");
        var bytes = new byte[stream.Length];
        await stream.ReadExactlyAsync(bytes, cancellationToken);
        var hash = Convert.ToHexString(SHA256.HashData(bytes));
        if (!hash.Equals(expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"{label} SHA-256 does not match its declaration.");
        return bytes;
    }

    private static async Task VerifyFileAsync(
        string path, long expectedLength, string expectedSha256, long maximumLength,
        string label, CancellationToken cancellationToken)
    {
        await using var stream = OpenRegularFile(path, label);
        if (stream.Length != expectedLength || stream.Length > maximumLength)
            throw new InvalidDataException($"{label} byte length does not match its declaration.");
        var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken));
        if (!hash.Equals(expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"{label} SHA-256 does not match its declaration.");
    }

    private static FileStream OpenRegularFile(string path, string label)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException($"{label} must be a regular file.");
        return new(path, FileMode.Open, FileAccess.Read, FileShare.Read, 8192,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
    }

    private static T Deserialize<T>(byte[] bytes, string label) where T : class
    {
        try
        {
            return JsonSerializer.Deserialize<T>(bytes, JsonFormat.Options)
                ?? throw new InvalidDataException($"{label} cannot be null.");
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"Invalid {label.ToLowerInvariant()}: {ex.Message}", ex);
        }
    }

    private static void ValidateHeader(int schemaVersion, string contractVersion, string expected, string label)
    {
        if (schemaVersion != 1 || contractVersion != expected)
            throw new InvalidDataException($"{label} must use {expected} schema version 1.");
    }

    private static void ValidatePlainFile(string value, string label)
    {
        RequireText(value, 200, label);
        if (value is "." or ".." || Path.IsPathRooted(value) || value.IndexOfAny(['/', '\\', ':']) >= 0 ||
            value.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new InvalidDataException($"{label} must be a plain sibling filename.");
    }

    private static void ValidateLengthAndHash(long length, string hash, long maximum, string label)
    {
        if (length < 1 || length > maximum)
            throw new InvalidDataException($"{label} byteLength must be 1 to {maximum}.");
        ValidateSha256(hash, $"{label} sha256");
    }

    private static void ValidateSha256(string value, string label)
    {
        if (value is not { Length: 64 } || !value.All(char.IsAsciiHexDigit))
            throw new InvalidDataException($"{label} must be a SHA-256 hexadecimal string.");
    }

    private static void RequireText(string value, int maximum, string label)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maximum)
            throw new InvalidDataException($"{label} must contain 1 to {maximum} characters.");
    }

    private static void RequireUtc(DateTimeOffset value, string label)
    {
        if (value.Offset != TimeSpan.Zero)
            throw new InvalidDataException($"{label} must use UTC offset Z.");
    }

    private static void RequireUnique(IEnumerable<string> values, string label)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var value in values)
            if (!seen.Add(value))
                throw new InvalidDataException($"Duplicate {label} '{value}'.");
    }

    private static void ValidateClaim(string claim, string label)
    {
        if (claim is not ("meaning" or "locator" or "restart-survival" or "update-survival"))
            throw new InvalidDataException($"{label} has unsupported claim '{claim}'.");
    }

    private static bool LocatorMatchesSource(string source, string locator) => source switch
    {
        "addon" => locator == "addon-api",
        "native" => locator is "module-relative-rva" or "signature-scan" or "absolute-session-address",
        "derived" => locator == "derivation",
        "synthetic" => locator == "synthetic-fixture",
        _ => false
    };
}

public sealed record FieldCatalogDocument(
    int SchemaVersion,
    string ContractVersion,
    IReadOnlyList<FieldDefinitionDocument> Fields,
    IReadOnlyList<FieldAssessmentReference> Assessments);

public sealed record FieldDefinitionDocument(
    string FieldId,
    string Meaning,
    string Units,
    string SourceKind,
    FieldLocatorDocument Locator,
    IReadOnlyList<FieldApplicabilityDocument> Applicability,
    IReadOnlyList<string> InvalidationConditions,
    IReadOnlyList<string> RequiredClaims);

public sealed record FieldLocatorDocument(string Kind, string Method);
public sealed record FieldApplicabilityDocument(string BuildSha256, string SessionId);
public sealed record FieldAssessmentReference(string Path, long ByteLength, string Sha256);

public sealed record FieldAssessmentDocument(
    int SchemaVersion,
    string ContractVersion,
    string AssessmentId,
    string FieldId,
    string FieldDefinitionSha256,
    string Reviewer,
    string Method,
    string EvidenceOrigin,
    DateTimeOffset AssessedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    FieldApplicabilityDocument Applicability,
    IReadOnlyList<FieldAssessmentDeclarationDocument> Declarations,
    IReadOnlyList<FieldEvidenceArtifactDocument> Artifacts);

public sealed record FieldAssessmentDeclarationDocument(string Claim, string Outcome, string Rationale);

public sealed record FieldEvidenceArtifactDocument(
    string EvidenceRole,
    string Path,
    long ByteLength,
    string Sha256,
    string EvidenceKind,
    string BuildSha256,
    string SessionId);
