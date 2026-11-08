using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record PerUnitZoneKeyCandidate(
    string Status, string? UnitKey, string? UnitIdCandidate, ulong? Entity,
    ulong? Health, ulong? Owner, uint? RawZoneKey, string? UnavailableReason);

internal sealed record CurrentBuildPairedZoneKeyObservation(
    NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc,
    CurrentBuildPairedPositionObservation Positions, PerUnitZoneKeyCandidate SelfZone,
    PerUnitZoneKeyCandidate TargetZone, double AcquisitionMilliseconds)
{
    public string Status => "candidate-only";
    public string ZoneKeyRelation => SelfZone.RawZoneKey.HasValue && TargetZone.RawZoneKey.HasValue
        ? SelfZone.RawZoneKey == TargetZone.RawZoneKey ? "matching-zone-key-candidate" : "different-zone-key-candidate"
        : "unavailable";
    public string SameWorldStatus => "unavailable";
    public string PublicZoneIdStatus => "not-derived";
    public bool AtomicityQualified => false;
    public string Qualification => "independent raw per-unit zone-key candidates; equal keys do not establish same zone instance/world; XYZ and freshness unverified";
}

/// <summary>
/// Brackets independent 0294 owner+150 raw keys around existing paired XYZ.
/// No global zone is assigned to a target, public ID constructed, or native
/// getter/resolver called. The caller retains final async process admission.
/// </summary>
internal static class CurrentBuildPairedZoneKeyCandidateReader
{
    internal static CurrentBuildPairedZoneKeyObservation Read(
        IReadOnlyNativeMemorySession session, int maxAcquisitionMilliseconds = 1000)
    {
        var timer = Stopwatch.StartNew();
        return Read(session, CurrentBuildPlayerContextCandidateReader.Read,
            (source, bound) => CurrentBuildPairedPositionCandidateReader.Read(source, bound),
            maxAcquisitionMilliseconds, () => timer.Elapsed.TotalMilliseconds);
    }

    // Only paired acquisition/context/clock are injectable for offline tests.
    // Raw self and target lookup, ownership, type and zone-byte checks remain real.
    internal static CurrentBuildPairedZoneKeyObservation Read(
        IReadOnlyNativeMemorySession session,
        Func<IReadOnlyNativeMemorySession, CurrentBuildPlayerContextObservation> context,
        Func<IReadOnlyNativeMemorySession, int, CurrentBuildPairedPositionObservation> acquirePair,
        int maxAcquisitionMilliseconds, Func<double> elapsedMilliseconds)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(acquirePair);
        ArgumentNullException.ThrowIfNull(elapsedMilliseconds);
        if (maxAcquisitionMilliseconds is < 1 or > 5000)
            throw new ArgumentOutOfRangeException(nameof(maxAcquisitionMilliseconds));
        var started = DateTimeOffset.UtcNow; var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 ||
            !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            id.ModuleBaseAddress < 0x10000 || id.ModuleBaseAddress % 8 != 0 ||
            id.ModuleBaseAddress > 0x7FFFFFFFFFFFUL || id.ModuleSize < 0x34731B8 ||
            id.ModuleSize > 0x7FFFFFFFFFFFUL - id.ModuleBaseAddress)
            throw new InvalidDataException("Invalid zone-pair build/process/module.");
        var initialElapsed = elapsedMilliseconds();
        if (!double.IsFinite(initialElapsed) || initialElapsed < 0)
            throw new InvalidDataException("Invalid acquisition clock.");
        var anchors = new Dictionary<(ulong, int), byte[]>(); var budget = 0;
        byte[] Take(ulong a, int n, bool save = true)
        {
            budget = checked(budget + n);
            if (budget > 2 * 1024 * 1024) throw new InvalidDataException("Zone-pair read budget exceeded.");
            var bytes = CurrentBuildPlayerLookup.Exact(session, a, n);
            if (save)
            {
                if (anchors.TryGetValue((a, n), out var old)) CurrentBuildPlayerLookup.RequireSame(bytes, old);
                anchors[(a, n)] = bytes.ToArray();
            }
            return bytes;
        }
        ulong Ptr(ulong a, int n = 8) => CurrentBuildPlayerLookup.Pointer(a, n);
        ulong Q(ulong a) => BinaryPrimitives.ReadUInt64LittleEndian(Take(a, 8));
        var before = context(session);
        if (before.Identity != id || before.UnitKey == 0 || session.Identity != id)
            throw new InvalidDataException("Invalid guarded self.");
        var selfEntity = Ptr(before.Entity, 128); var selfHealth = Ptr(before.HealthComponent, 0x48);
        var system = Ptr(Q(id.ModuleBaseAddress + 0x33623E0), 0x400);
        if (Q(system + 0x360) != before.UnitKey || Q(system + 0x3F8) != selfEntity ||
            Q(selfHealth + 0x40) != before.Owner)
            throw new InvalidDataException("Self cache/owner mismatch.");
        PerUnitZoneKeyCandidate Unavailable(ulong? key, ulong? entity, ulong? health, ulong? owner, string reason) =>
            new("unavailable", key?.ToString(CultureInfo.InvariantCulture),
                key.HasValue ? $"u{key:X16}" : null, entity, health, owner, null, reason);
        PerUnitZoneKeyCandidate Zone(ulong key, ulong entity, ulong health)
        {
            if (health == 0) return Unavailable(key, entity, null, null, "health-component-absent");
            Ptr(health, 0x48);
            if (Q(health + 0x10) != entity) throw new InvalidDataException("Zone health/entity backlink mismatch.");
            var owner = Q(health + 0x40);
            if (owner == 0) return Unavailable(key, entity, health, null, "owner-absent");
            Ptr(owner, 0x154);
            if (Q(owner) != id.ModuleBaseAddress + 0x2927448 ||
                Q(id.ModuleBaseAddress + 0x2927488) != id.ModuleBaseAddress + 0x19D21E0 ||
                Q(id.ModuleBaseAddress + 0x34731B0) != id.ModuleBaseAddress + 0x2929BD0 ||
                Q(id.ModuleBaseAddress + 0x2929BD8) != id.ModuleBaseAddress + 0x19F4D60)
                return Unavailable(key, entity, health, owner, "unverified-0294-owner");
            return new("raw-zone-key-candidate", key.ToString(CultureInfo.InvariantCulture), $"u{key:X16}",
                entity, health, owner, BinaryPrimitives.ReadUInt32LittleEndian(Take(owner + 0x150, 4)), null);
        }
        var selfZone = Zone(before.UnitKey, selfEntity, selfHealth);
        var targetZone = Unavailable(null, null, null, null, "guarded-target-unavailable");
        var selectedKey = before.TargetKeyCandidate;
        if (selectedKey is > 0)
        {
            var manager = Ptr(Q(id.ModuleBaseAddress + 0x33624A8));
            var table = Ptr(Q(manager + 0x50)); var header = Take(table, 24);
            var buckets = Ptr(BinaryPrimitives.ReadUInt64LittleEndian(header));
            var stride = BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(8));
            var count = BinaryPrimitives.ReadUInt64LittleEndian(header.AsSpan(16));
            if (stride is < 24 or > 4096 || stride % 8 != 0 || count is < 1 or > (1 << 24))
                throw new InvalidDataException("Invalid target unit table.");
            var a = Ptr(checked(buckets + CurrentBuildPlayerLookup.BucketIndex(selectedKey.Value, count) * stride), 24);
            var seen = new HashSet<ulong>(); var head = true; ulong targetEntity = 0;
            for (var i = 0; i < 128; i++)
            {
                if (!seen.Add(a)) throw new InvalidDataException("Cyclic target unit chain.");
                var node = Take(a, 24); var link = BinaryPrimitives.ReadUInt64LittleEndian(node);
                if ((!head || (link & 1) == 0) && BinaryPrimitives.ReadUInt64LittleEndian(node.AsSpan(8)) == selectedKey.Value)
                { targetEntity = Ptr(BinaryPrimitives.ReadUInt64LittleEndian(node.AsSpan(16)), 128); break; }
                var next = link & ~1UL; if (next == 0) break; a = Ptr(next, 24); head = false;
            }
            if (targetEntity == 0) throw new InvalidDataException("Guarded target absent or lookup bound exceeded.");
            var selector = BinaryPrimitives.ReadInt32LittleEndian(Take(id.ModuleBaseAddress + 0x2F57850, 4));
            if (selector is < 0 or >= 0x60) throw new InvalidDataException("Invalid target health selector.");
            var slot = Take(targetEntity + 0x18 + (ulong)selector, 1)[0];
            var health = slot == 0xFF ? 0 : Ptr(Q(checked(Ptr(Q(targetEntity + 0x78)) + slot * 8UL)), 0x48);
            targetZone = Zone(selectedKey.Value, targetEntity, health);
        }

        var pair = acquirePair(session, maxAcquisitionMilliseconds);
        if (pair.Identity != id || pair.Self.UnitKey != before.UnitKey.ToString(CultureInfo.InvariantCulture) ||
            (selectedKey is > 0 ? pair.Target?.UnitKey != selectedKey.Value.ToString(CultureInfo.InvariantCulture) : pair.Target is not null))
            throw new InvalidDataException("Paired XYZ does not match independently bound zone units.");
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(Take(anchor.Key.Item1, anchor.Key.Item2, false), anchor.Value);
        var after = context(session);
        if (after.Identity != id || after.UnitKey != before.UnitKey || after.Entity != before.Entity ||
            after.HealthComponent != before.HealthComponent || after.Owner != before.Owner ||
            after.CachedContext != before.CachedContext || after.RawFallbackKey != before.RawFallbackKey ||
            after.TargetKeyCandidate != selectedKey || after.TargetStatus != before.TargetStatus || session.Identity != id)
            throw new InvalidDataException("Self/selection/source epoch changed around zone-pair acquisition.");
        var finalElapsed = elapsedMilliseconds();
        var span = finalElapsed - initialElapsed;
        if (!double.IsFinite(finalElapsed) || !double.IsFinite(span) || span < 0 || span > maxAcquisitionMilliseconds)
            throw new InvalidDataException("Zone-pair acquisition clock/span invalid.");
        return new(id, started, DateTimeOffset.UtcNow, pair, selfZone, targetZone, span);
    }
}
