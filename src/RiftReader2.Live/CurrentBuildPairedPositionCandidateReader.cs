using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record PairedPositionCandidateSample(
    string Status, string UnitKey, string UnitIdCandidate, CurrentBuildXyz? Position,
    DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    double MonotonicStartMilliseconds, double MonotonicEndMilliseconds);

internal sealed record CurrentBuildPairedPositionObservation(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    string ClockDomain, PairedPositionCandidateSample Self, PairedPositionCandidateSample? Target,
    string TargetStatus, string BeforeGuardStatus, string AfterGuardStatus,
    double AcquisitionSpanMilliseconds, double? StartSkewMilliseconds,
    double? MaximumSampleSeparationMilliseconds)
{
    public string Status => Target?.Status == "candidate" ? "paired-candidate" : "target-unavailable";
    public string Qualification => "candidate-only; sequential acquisition, position semantics and passive freshness unverified";
    public string ZoneIdentityStatus => "unavailable";
    public string WorldIdentityStatus => "unavailable";
    public bool AtomicityQualified => false;
}

/// <summary>
/// One caller-owned read-only session, one local acquisition clock. This does not
/// open a process, call game methods, infer world/zone, or establish atomicity.
/// Present target health retains the existing REAL guarded vitals dependency.
/// </summary>
internal static class CurrentBuildPairedPositionCandidateReader
{
    internal static CurrentBuildPairedPositionObservation Read(
        IReadOnlyNativeMemorySession session, int maxPairSpanMilliseconds = 1000)
    {
        var timer = Stopwatch.StartNew();
        return Read(session, CurrentBuildPlayerContextCandidateReader.Read,
            (source, context) =>
            {
                var owner = CurrentBuildPlayerLookup.Resolve(source);
                if (owner.PlayerKey != context.UnitKey || owner.EntityAddress != context.Entity)
                    throw new InvalidDataException("Self position/context owner mismatch.");
                return new(owner.PlayerKey, owner.ResolveComponent(0x2F588A0), owner.VerifyUnchanged);
            }, maxPairSpanMilliseconds, () => (DateTimeOffset.UtcNow, timer.Elapsed.TotalMilliseconds));
    }

    // Injection is restricted to source-owner and clock acquisition for offline tests.
    // Target lookup/position and any present-health vitals always use real readers.
    internal static CurrentBuildPairedPositionObservation Read(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation> context,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation, CurrentBuildPositionOwnerSnapshot> resolveSelf,
        int maxPairSpanMilliseconds,
        Func<(DateTimeOffset Utc, double Milliseconds)> clock)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(resolveSelf);
        ArgumentNullException.ThrowIfNull(clock);
        if (maxPairSpanMilliseconds is < 1 or > 5000)
            throw new ArgumentOutOfRangeException(nameof(maxPairSpanMilliseconds));
        var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 ||
            !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            id.ModuleBaseAddress < 0x10000 || id.ModuleBaseAddress % 8 != 0 ||
            id.ModuleSize < 0x34731B8 || id.ModuleBaseAddress > 0x7FFFFFFFFFFFUL ||
            id.ModuleSize > 0x7FFFFFFFFFFFUL - id.ModuleBaseAddress)
            throw new InvalidDataException("Invalid paired position build/process/module identity.");

        var clockDomain = Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture);
        var stamps = new List<(DateTimeOffset Utc, double Milliseconds)>();
        (DateTimeOffset Utc, double Milliseconds) Stamp()
        {
            var stamp = clock();
            if (stamp.Utc.Offset != TimeSpan.Zero || !double.IsFinite(stamp.Milliseconds) || stamp.Milliseconds < 0 ||
                (stamps.Count > 0 && (stamp.Utc < stamps[^1].Utc || stamp.Milliseconds < stamps[^1].Milliseconds)))
                throw new InvalidDataException("Paired acquisition clock changed or is invalid.");
            stamps.Add(stamp);
            if (stamp.Milliseconds - stamps[0].Milliseconds > maxPairSpanMilliseconds)
                throw new InvalidDataException("Paired acquisition exceeded its bounded time span.");
            return stamp;
        }
        var started = Stamp();
        var before = context(session);
        if (before.Identity != id || before.UnitKey == 0 || before.Entity == 0 || session.Identity != id)
            throw new InvalidDataException("Invalid initial self context.");
        var afterGuard = before.TargetStatus;
        CurrentBuildPlayerContextObservation GuardedContext(IReadOnlyNativeMemorySession source)
        {
            if (!ReferenceEquals(source, session) || source.Identity != id)
                throw new InvalidDataException("Paired session identity changed.");
            var current = context(source);
            if (current.Identity != id || current.UnitKey != before.UnitKey || current.Entity != before.Entity ||
                current.HealthComponent != before.HealthComponent || current.Owner != before.Owner ||
                current.CachedContext != before.CachedContext || current.RawFallbackKey != before.RawFallbackKey ||
                current.TargetKeyCandidate != before.TargetKeyCandidate || current.TargetStatus != before.TargetStatus ||
                source.Identity != id)
                throw new InvalidDataException("Self or guarded selection changed across paired acquisition.");
            afterGuard = current.TargetStatus;
            return current;
        }

        var selfStart = Stamp();
        var owner = resolveSelf(session, before);
        if (owner.UnitKey != before.UnitKey)
            throw new InvalidDataException("Self position key differs from guarded self.");
        var component = CurrentBuildPlayerLookup.Pointer(owner.ComponentAddress, 0x110);
        var backlink = CurrentBuildPlayerLookup.Exact(session, component + 0x10, 8);
        if (BinaryPrimitives.ReadUInt64LittleEndian(backlink) != before.Entity)
            throw new InvalidDataException("Self position entity backlink differs.");
        var self = CurrentBuildPositionCandidateReader.ReadOwned(session, _ => owner);
        var selfEnd = Stamp();
        var selfBits = new byte[12];
        BinaryPrimitives.WriteSingleLittleEndian(selfBits.AsSpan(0), self.Position.X);
        BinaryPrimitives.WriteSingleLittleEndian(selfBits.AsSpan(4), self.Position.Y);
        BinaryPrimitives.WriteSingleLittleEndian(selfBits.AsSpan(8), self.Position.Z);
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, component + 0x48, 12), selfBits);

        var targetStart = Stamp();
        var target = CurrentBuildSelectedTargetCandidateReader.Read(session, GuardedContext,
            (source, targetOwner) => CurrentBuildVitalsCandidateReader.Read(source, _ => targetOwner),
            includePosition: true);
        var targetEnd = Stamp();
        if (target.Identity != id || target.SelfKey != before.UnitKey)
            throw new InvalidDataException("Selected position returned a different process/self identity.");
        if (target.TargetPosition is { } targetPosition &&
            (target.TargetKey != targetPosition.UnitKey || targetPosition.UnitKey != before.TargetKeyCandidate))
            throw new InvalidDataException("Selected position key differs from guarded selection.");

        owner.VerifyUnchanged();
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, component + 0x10, 8), backlink);
        CurrentBuildPlayerLookup.RequireSame(CurrentBuildPlayerLookup.Exact(session, component + 0x48, 12), selfBits);
        GuardedContext(session);
        if (session.Identity != id)
            throw new InvalidDataException("Paired process identity changed.");
        var completed = Stamp();
        PairedPositionCandidateSample Sample(string status, ulong key, CurrentBuildXyz? xyz,
            (DateTimeOffset Utc, double Milliseconds) begin, (DateTimeOffset Utc, double Milliseconds) end) =>
            new(status, key.ToString(CultureInfo.InvariantCulture), $"u{key:X16}", xyz,
                begin.Utc, end.Utc, begin.Milliseconds, end.Milliseconds);
        var selfSample = Sample("candidate", self.UnitKey, self.Position, selfStart, selfEnd);
        var position = target.TargetPosition;
        var targetSample = position is null ? null :
            Sample(position.Status, position.UnitKey, position.Position, targetStart, targetEnd);
        return new(id, started.Utc, completed.Utc, clockDomain, selfSample, targetSample,
            position?.Status ?? target.Status, before.TargetStatus, afterGuard,
            completed.Milliseconds - started.Milliseconds,
            position is null ? null : targetStart.Milliseconds - selfStart.Milliseconds,
            position is null ? null : targetEnd.Milliseconds - selfStart.Milliseconds);
    }
}
