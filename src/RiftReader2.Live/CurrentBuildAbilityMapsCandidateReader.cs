using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record AbilityMapEntry(ulong Address, uint Key, string RawHex, string ValueRawHex, float? Value, string SecondaryRawHex, float? Secondary);
internal sealed record AbilityMapCandidate(ulong Offset, ulong BucketBase, ulong Stride, ulong BucketCount, ulong EntryCount, IReadOnlyList<AbilityMapEntry> Entries);
internal sealed record CurrentBuildAbilityMapsObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, ulong NativeUnitKey, ulong Context, ulong ClockPointer, float ClockBefore, float ClockAfter, IReadOnlyList<AbilityMapCandidate> Maps)
{
    public string Source => "native-process-memory";
    public string Qualification => "candidate-only; learned-ability, API-cooldown, freshness and restart semantics unverified";
}

internal static class CurrentBuildAbilityMapsCandidateReader
{
    internal static CurrentBuildAbilityMapsObservation Read(IReadOnlyNativeMemorySession session)
    {
        var started = DateTimeOffset.UtcNow;
        var identity = session.Identity;
        var lookup = CurrentBuildPlayerLookup.Resolve(session);
        var context = lookup.ResolveComponent(0x2F57260);
        return ReadResolved(session, identity, started, lookup.PlayerKey, lookup.EntityAddress, context, lookup.VerifyUnchanged);
    }

    internal static CurrentBuildAbilityMapsObservation ReadResolved(IReadOnlyNativeMemorySession session, NativeProcessIdentity identity,
        DateTimeOffset started, ulong key, ulong entity, ulong context, Action verifyOwner)
    {
        if (identity != session.Identity || !string.Equals(identity.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            identity.ProcessId <= 0 || identity.ProcessStartUtcTicks <= 0 || identity.ModuleSize < 0x33DC2B8 || key == 0)
            throw new InvalidDataException("Ability map requires exact build and process epoch.");
        CurrentBuildPlayerLookup.Pointer(context, 0x260);
        var anchors = new Dictionary<(ulong, int), byte[]>();
        var budget = 0;
        byte[] Read(ulong address, int length, bool anchor = true)
        {
            budget = checked(budget + length);
            if (budget > 1024 * 1024) throw new InvalidDataException("Ability map read budget exceeded.");
            var bytes = CurrentBuildPlayerLookup.Exact(session, address, length);
            if (anchor)
            {
                if (anchors.TryGetValue((address, length), out var previous) && !previous.AsSpan().SequenceEqual(bytes))
                    throw new InvalidDataException("Ability map changed during capture.");
                anchors[(address, length)] = bytes.ToArray();
            }
            return bytes;
        }
        ulong Ptr(ulong value, int length = 8) => CurrentBuildPlayerLookup.Pointer(value, length);
        var system = Ptr(U64(Read(checked(identity.ModuleBaseAddress + 0x33623E0), 8)));
        if (U64(Read(checked(system + 0x3F8), 8)) != entity)
            throw new InvalidDataException("Cached player entity differs from lookup.");
        var clock = Ptr(U64(Read(checked(identity.ModuleBaseAddress + 0x33DC2B0), 8)), 0x1C);
        var before = F32(Read(checked(clock + 0x18), 4, false));
        if (!float.IsFinite(before)) throw new InvalidDataException("Invalid game clock.");
        var maps = new List<AbilityMapCandidate>();
        ulong total = 0;
        foreach (var (offset, expected) in new[] { (0x1C0UL, 0x28UL), (0x240UL, 0x18UL) })
        {
            var header = Read(checked(context + offset), 32);
            var baseAddress = U64(header); var stride = U64(header.AsSpan(8));
            var buckets = U64(header.AsSpan(16)); var count = U64(header.AsSpan(24));
            if (stride != expected || buckets > 4096 || count > 512 || (total += count) > 512 ||
                (buckets == 0 && (baseAddress != 0 || count != 0)))
                throw new InvalidDataException("Invalid ability map header or count budget.");
            if (buckets > 0) Ptr(baseAddress, checked((int)((buckets - 1) * stride + 24)));
            var seen = new HashSet<ulong>(); var pending = new Queue<ulong>(); var entries = new List<AbilityMapEntry>();
            void Add(ulong address, byte[] raw)
            {
                if (!seen.Add(address) || (ulong)seen.Count > count) throw new InvalidDataException("Duplicate, cyclic or excessive map node.");
                var v = F32(raw.AsSpan(16)); var s = F32(raw.AsSpan(20));
                entries.Add(new(address, BinaryPrimitives.ReadUInt32LittleEndian(raw.AsSpan(8)), Convert.ToHexString(raw).ToLowerInvariant(), Convert.ToHexString(raw.AsSpan(16, 4)).ToLowerInvariant(), float.IsFinite(v) ? v : null, Convert.ToHexString(raw.AsSpan(20, 4)).ToLowerInvariant(), float.IsFinite(s) ? s : null));
            }
            void Enqueue(ulong link)
            {
                var next = link & ~1UL;
                if (next != 0) pending.Enqueue(Ptr(next, 24));
            }
            for (ulong i = 0; i < buckets; i++)
            {
                var address = checked(baseAddress + i * stride); var raw = Read(address, 24); var link = U64(raw);
                if ((link & 1) == 0) Add(address, raw);
                Enqueue(link);
            }
            while (pending.Count > 0)
            {
                if ((ulong)pending.Count + (ulong)seen.Count > count) throw new InvalidDataException("Ability map chain count exceeded.");
                var address = pending.Dequeue(); var raw = Read(address, 24); Add(address, raw); Enqueue(U64(raw));
            }
            if ((ulong)entries.Count != count) throw new InvalidDataException("Ability map entry count mismatch.");
            maps.Add(new(offset, baseAddress, stride, buckets, count, entries));
        }
        foreach (var anchor in anchors)
            CurrentBuildPlayerLookup.RequireSame(Read(anchor.Key.Item1, anchor.Key.Item2, false), anchor.Value);
        var after = F32(Read(checked(clock + 0x18), 4, false));
        if (!float.IsFinite(after) || after < before) throw new InvalidDataException("Game clock invalid or moved backward.");
        verifyOwner();
        if (session.Identity != identity) throw new InvalidDataException("Process identity changed.");
        return new(identity, started, DateTimeOffset.UtcNow, key, context, clock, before, after, maps);
    }
    private static ulong U64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt64LittleEndian(bytes);
    private static float F32(ReadOnlySpan<byte> bytes) => BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(bytes));
}
