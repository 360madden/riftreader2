using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record CurrentBuildLocationContextObservation(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    string UnitKey, string UnitIdCandidate, DateTimeOffset PositionStartedAtUtc,
    DateTimeOffset PositionCompletedAtUtc, CurrentBuildXyz Position, ZoneSeedObservation Zone)
{
    public string Status => "candidate-only";
    public string WorldInstanceStatus => "unavailable";
    public string Qualification => "cached XYZ and zone candidates; sequential, not atomic; world instance, API correspondence, passive freshness and restart unverified";
}

/// <summary>One session and one anchored self lookup; retains each source's own capture interval.</summary>
internal static class CurrentBuildLocationContextCandidateReader
{
    internal static Task<CurrentBuildLocationContextObservation> ReadAsync(
        IReadOnlyNativeMemorySession session, CancellationToken cancellationToken) =>
        ReadAsync(session, () => WindowsThreadTlsSnapshot.Capture(session.Identity.ProcessId), cancellationToken);

    internal static async Task<CurrentBuildLocationContextObservation> ReadAsync(
        IReadOnlyNativeMemorySession session, Func<IReadOnlyList<NativeThreadEpoch>> threads,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(threads);
        cancellationToken.ThrowIfCancellationRequested();
        var started = DateTimeOffset.UtcNow;
        var identity = session.Identity;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var positionComponent = lookup.ResolveComponent(0x2F588A0);
        var health = lookup.ResolveComponent(0x2F57850);
        var positionStarted = DateTimeOffset.UtcNow;
        var position = CurrentBuildPositionCandidateReader.ReadOwned(session,
            _ => new(lookup.PlayerKey, positionComponent, lookup.VerifyUnchanged));
        var positionCompleted = DateTimeOffset.UtcNow;
        cancellationToken.ThrowIfCancellationRequested();

        var zone = CurrentBuildZoneSeedSampleCommand.Read(session,
            source => CurrentBuildPlayerContextCandidateReader.Read(source,
                _ => new(lookup.PlayerKey, lookup.EntityAddress, health, lookup.VerifyUnchanged)), threads);
        if (zone.Identity is not NativeProcessIdentity zoneIdentity || zoneIdentity != identity ||
            zone.SelfKey != position.UnitKey || zone.SelfEntity != lookup.EntityAddress || zone.Health != health)
            throw new InvalidDataException("Location source ownership or process mismatch.");

        cancellationToken.ThrowIfCancellationRequested();
        if (await session.RevalidateAsync(cancellationToken) is not null)
            throw new InvalidDataException("Location process identity invalidated.");
        lookup.VerifyUnchanged();
        if (session.Identity != identity)
            throw new InvalidDataException("Location process identity changed.");
        cancellationToken.ThrowIfCancellationRequested();
        return new(identity, started, DateTimeOffset.UtcNow, position.UnitKeyText, position.UnitIdCandidate,
            positionStarted, positionCompleted, position.Position, zone);
    }
}
