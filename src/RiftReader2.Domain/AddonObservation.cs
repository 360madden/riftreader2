namespace RiftReader2.Domain;

public enum AddonFieldStatus
{
    Ok,
    Unavailable,
    Invalid
}

public sealed record AddonNumberField(AddonFieldStatus Status, double? Value);

public sealed record AddonStringField(AddonFieldStatus Status, string? Value);

public sealed record AddonBooleanField(AddonFieldStatus Status, bool? Value);

public sealed record AddonObservationFields(
    AddonNumberField CoordX,
    AddonNumberField CoordY,
    AddonNumberField CoordZ,
    AddonNumberField Health,
    AddonNumberField HealthMax,
    AddonBooleanField Combat);

public sealed record AddonObservation(
    int SchemaVersion,
    string AddonVersion,
    long Sequence,
    long Epoch,
    AddonNumberField Clock,
    AddonStringField Player,
    AddonObservationFields Fields);
