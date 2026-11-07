using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record AbilityRecordChild(string Status, ulong Address, uint? LocalizationKey);
internal sealed record AbilityRecordCandidate(uint Key, string Status, ulong? RecordAddress = null, byte? ApiListFilterNonzeroRaw = null, AbilityRecordChild? Child = null, AbilityRecordChild? SecondaryChild = null, string? FullIdCandidate = null);
internal sealed record CurrentBuildAbilityRecordsObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, ushort Selector, uint TlsIndex, ulong Collection, IReadOnlyList<AbilityRecordCandidate> Records)
{
    public string Qualification => "candidate-only; membership, freshness and restart unverified";
    public string Source => "native-process-memory";
}
internal static class CurrentBuildAbilityRecordsCandidateReader
{
    internal static CurrentBuildAbilityRecordsObservation Read(IReadOnlyNativeMemorySession session, IReadOnlyList<uint> keys) =>
        Read(session, keys, () => WindowsThreadTlsSnapshot.Capture(session.Identity.ProcessId));
    internal static CurrentBuildAbilityRecordsObservation Read(IReadOnlyNativeMemorySession session, IReadOnlyList<uint> keys, Func<IReadOnlyList<NativeThreadEpoch>> threads)
    {
        var started = DateTimeOffset.UtcNow; var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 || id.ModuleSize < 0x344A6B8 ||
            !string.Equals(id.ExecutableSha256, CurrentBuildPlayerLookup.GameSha256, StringComparison.OrdinalIgnoreCase) ||
            keys.Count is < 1 or > 128 || keys.Distinct().Count() != keys.Count)
            throw new InvalidDataException("Invalid build, process identity or keys.");
        var anchors = new Dictionary<(ulong, int), byte[]>(); var budget = 0;
        byte[] ReadBytes(ulong a, int n, bool remember = true)
        {
            budget = checked(budget + n); if (budget > 2 * 1024 * 1024) throw new InvalidDataException("Read budget exceeded.");
            var b = CurrentBuildPlayerLookup.Exact(session, a, n);
            if (remember) { if (anchors.TryGetValue((a, n), out var old) && !old.AsSpan().SequenceEqual(b)) throw new InvalidDataException("Bytes changed during capture."); anchors[(a, n)] = b.ToArray(); }
            return b;
        }
        ulong Ptr(ulong value, int n = 8) => CurrentBuildPlayerLookup.Pointer(value, n);
        ulong Q(ulong a) => U64(ReadBytes(a, 8));
        var selectorOwner = Ptr(Q(checked(id.ModuleBaseAddress + 0x33624C8)), 0x42);
        var selector = BinaryPrimitives.ReadUInt16LittleEndian(ReadBytes(selectorOwner + 0x40, 2));
        var wrapper = Ptr(Q(checked(id.ModuleBaseAddress + 0x3372C18)));
        var owner = Ptr(Q(wrapper), 0x278);
        var index = BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(owner + 0x274, 4));
        if (index > 1087) throw new InvalidDataException("Invalid TLS index.");
        var epochs = threads();
        if (epochs.Count is < 1 or > 256 || epochs.Select(t => t.Id).Distinct().Count() != epochs.Count || epochs.Select(t => t.Teb).Distinct().Count() != epochs.Count) throw new InvalidDataException("Invalid thread set.");
        ulong? collection = null;
        foreach (var t in epochs)
        {
            Ptr(t.Teb, 0x1788); var tebIdentity = ReadBytes(t.Teb + 0x30, 32);
            if (t.Id <= 0 || t.Created <= 0 || U64(tebIdentity) != t.Teb || U64(tebIdentity.AsSpan(16)) != (ulong)id.ProcessId || U64(tebIdentity.AsSpan(24)) != (ulong)t.Id) throw new InvalidDataException("TEB identity mismatch.");
            ulong value;
            if (index < 64) value = Q(t.Teb + 0x1480 + index * 8UL);
            else { var expansion = Q(t.Teb + 0x1780); value = expansion == 0 ? 0 : Q(checked(Ptr(expansion) + (index - 64) * 8UL)); }
            var selected = value == 0 ? checked(owner + 0x200) : Ptr(value);
            if (collection.HasValue && collection != selected) throw new InvalidDataException("Thread collections disagree.");
            collection = selected;
        }
        var header = ReadBytes(checked(collection!.Value + 0x20), 32); var b = Ptr(U64(header)); var stride = U64(header.AsSpan(8)); var count = U64(header.AsSpan(16));
        if (stride != 24 || count is < 1 or > 4096) throw new InvalidDataException("Invalid registry header.");
        Ptr(b, checked((int)(count * 24)));
        bool Fingerprint(ulong address, ulong vt, ulong getter, ulong descriptor, ulong descVt, ulong descGetter)
        {
            var actual = Q(address);
            if (actual != id.ModuleBaseAddress + vt) return false;
            return Q(actual + 0x40) == id.ModuleBaseAddress + getter && Q(id.ModuleBaseAddress + descriptor) == id.ModuleBaseAddress + descVt && Q(id.ModuleBaseAddress + descVt + 8) == id.ModuleBaseAddress + descGetter;
        }
        AbilityRecordChild Child(ulong address)
        {
            if (address == 0) return new("null", 0, 0);
            Ptr(address, 0x28);
            if (!Fingerprint(address, 0x27F24F8, 0x170C5D0, 0x3417970, 0x2802E40, 0x17361E0)) return new("unverified-type", address, null);
            return new("type-verified-candidate", address, BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(address + 0x18, 4)));
        }
        var rows = new List<AbilityRecordCandidate>();
        foreach (var key in keys)
        {
            var address = checked(b + Hash(Hash(key)) % count * 24); var seen = new HashSet<ulong>(); var head = true; byte[]? node = null;
            for (var i = 0; i <= 128; i++)
            {
                if (!seen.Add(address)) throw new InvalidDataException("Cyclic registry chain.");
                node = ReadBytes(address, 24); var link = U64(node);
                if ((!head || (link & 1) == 0) && BinaryPrimitives.ReadUInt16LittleEndian(node.AsSpan(8)) == selector && BinaryPrimitives.ReadUInt32LittleEndian(node.AsSpan(12)) == key) break;
                var next = link & ~1UL; if (next == 0) { node = null; break; }
                if (i == 128) throw new InvalidDataException("Registry chain budget exceeded.");
                address = Ptr(next, 24); head = false;
            }
            if (node is null) { rows.Add(new(key, "cache-miss")); continue; }
            var holder = U64(node.AsSpan(16)); if (holder == 0) { rows.Add(new(key, "cache-null-holder")); continue; }
            var record = Q(checked(Ptr(holder, 0x20) + 0x18)); if (record == 0) { rows.Add(new(key, "cache-null-record")); continue; }
            Ptr(record, 0x960);
            if (!Fingerprint(record, 0x28A08C0, 0x1899BF0, 0x344A6B0, 0x28A9C38, 0x18C06C0)) { rows.Add(new(key, "unverified-type", record)); continue; }
            var flag = ReadBytes(record + 0xC9, 1)[0]; var child = Child(Q(record + 0x8E0)); var second = Child(Q(record + 0x958));
            string? full = child.LocalizationKey.HasValue && second.LocalizationKey.HasValue ? $"A{(((ulong)key << 32) | unchecked((uint)(Hash(child.LocalizationKey.Value) + Hash(second.LocalizationKey.Value)))):X16}" : null;
            rows.Add(new(key, "type-verified-candidate", record, flag, child, second, full));
        }
        foreach (var anchor in anchors) CurrentBuildPlayerLookup.RequireSame(ReadBytes(anchor.Key.Item1, anchor.Key.Item2, false), anchor.Value);
        var after = threads();
        if (!epochs.OrderBy(t => t.Id).SequenceEqual(after.OrderBy(t => t.Id)) || session.Identity != id) throw new InvalidDataException("Thread or process identity changed.");
        return new(id, started, DateTimeOffset.UtcNow, selector, index, collection.Value, rows);
    }
    internal static uint Hash(uint key)
    {
        var low = unchecked((int)key); var quotient = low / 127773; var remainder = low - quotient * 127773;
        var signed = unchecked((int)((long)remainder * 16807 - (long)quotient * 2836));
        return unchecked((uint)(signed >= 0 ? signed : (long)signed + 2147483647));
    }
    private static ulong U64(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt64LittleEndian(bytes);
}
