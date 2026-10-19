namespace RiftReader2.Domain;

public sealed record LiveAttachmentIdentity(
    int ProcessId,
    long ProcessStartUtcTicks,
    string ExecutableSha256,
    string ReaderSessionNonce);

public sealed record LiveAddonFrame(
    string Challenge,
    AddonObservation Observation,
    string EnvelopeSha256,
    string AddonFrameSha256);

public enum LiveAddonSelectionStatus
{
    Selected,
    NoMatchingCandidate,
    IncompleteScan,
    Conflict
}

public sealed record LiveAddonSelection(
    LiveAddonSelectionStatus Status,
    LiveAddonFrame? Frame,
    int MatchingCandidateCount,
    int IdenticalCopyCount,
    string? Reason);

public sealed record LiveFreshnessOptions
{
    public TimeSpan FreshnessTimeout { get; init; } = TimeSpan.FromSeconds(5);

    public TimeSpan MaxClockSkew { get; init; } = TimeSpan.FromSeconds(1);
}

public enum LiveFreshnessStatus
{
    Warming,
    Fresh,
    Unavailable,
    Invalidated,
    Expired
}

public sealed record LiveAddonFreshness(
    LiveFreshnessStatus Status,
    LiveAttachmentIdentity Identity,
    AddonObservation? Observation,
    string? EnvelopeSha256,
    long? ObservedAtTimestamp,
    TimeSpan? Age,
    string? Reason);
