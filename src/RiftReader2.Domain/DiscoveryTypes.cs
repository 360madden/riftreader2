namespace RiftReader2.Domain;

/// <summary>Normalized, evidence-attributed discovery. The row never upgrades source qualifications.</summary>
public sealed record DiscoveryRecord(
    string Id,
    string FieldId,
    string Category,
    string SourceKind,
    string Status,
    string Qualification,
    string Meaning,
    string Units,
    string? LocatorKind,
    string? Locator,
    string BuildSha256,
    string SessionId,
    DateTimeOffset? ObservedAtUtc,
    DiscoveryValue? Value,
    string EvidenceKind,
    string EvidenceSha256,
    string SourceId,
    string SourcePath,
    IReadOnlyList<string> Limitations);

/// <summary>Value text and optional named numeric components; never an inferred game type.</summary>
public sealed record DiscoveryValue(
    string Kind,
    string? Text,
    IReadOnlyDictionary<string, double>? Components);

public sealed record DiscoverySourceStamp(
    string SourceId,
    string Kind,
    string Path,
    long ByteLength,
    string Sha256);

public sealed record DiscoverySelection(
    string? Source,
    string? Category,
    string? Status,
    string? Search,
    string Sort);

public sealed record DiscoveryCompilation(
    int SchemaVersion,
    string ContractVersion,
    string ManifestSha256,
    string EvidenceVerification,
    string SemanticVerification,
    FieldQualificationContext CatalogContext,
    DiscoverySelection Selection,
    int TotalRecords,
    int SelectedRecords,
    IReadOnlyList<DiscoverySourceStamp> Sources,
    IReadOnlyList<DiscoveryRecord> Records);
