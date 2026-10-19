using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record FieldQualificationReport(
    int SchemaVersion,
    string ContractVersion,
    string EvidenceKind,
    ToolIdentity Implementation,
    string CatalogSha256,
    string ArtifactVerification,
    string BuildSessionIdentityVerification,
    FieldQualificationEvaluation Evaluation);
