using System.Buffers.Binary;
using RiftReader2.Application;
using RiftReader2.Domain;

namespace RiftReader2.Live;

internal sealed record AbilityRecordChild(string Status, ulong Address, uint? LocalizationKey);
internal sealed record RawCostChild(string Status, ulong Address, ulong? Vtable = null, ulong? GetterRva = null, string? RawPayloadHex = null, int? Int18 = null, int? Int1C = null, float? Float18 = null, float? Float1C = null, byte? Flag1C = null, int? Int20 = null, float? Float20 = null, int? Int24 = null, byte? Flag28 = null);
internal sealed record RawCostVector(string Status, ulong Begin, ulong End, IReadOnlyList<RawCostChild> Children);
internal sealed record RawTimingVector(string Status, ulong Begin, ulong End, ulong Count, ulong? ChildAddress = null, ulong? Vtable = null, ulong? GetterRva = null, int? RawMilliseconds = null);
internal sealed record RawAbilityTiming(int RawGate88, int BaseCooldownMilliseconds, RawTimingVector Primary, RawTimingVector Secondary);
internal sealed record RawAbilityRangeInputs(string BaseMinRawHex, float? BaseMin, string BaseMaxRawHex, float? BaseMax, ulong ConditionsBegin, ulong ConditionsEnd, IReadOnlyList<uint> Conditions, bool StealthRequiredCandidate)
{
    public string Qualification => "raw definition inputs; adjusted range and usability unverified";
}
internal sealed record RawVariantChild(string Status, ulong Address, ulong? Vtable = null, ulong? GetterRva = null, uint? Key = null);
internal sealed record RawAbilityVariants(string Status, ulong? SourceAddress = null, IReadOnlyList<RawVariantChild>? Entries = null);
internal sealed record AbilityRecordCandidate(uint Key, string Status, ulong? RecordAddress = null, byte? ApiListFilterNonzeroRaw = null, AbilityRecordChild? Child = null, AbilityRecordChild? SecondaryChild = null, string? FullIdCandidate = null, RawCostVector? RawCosts = null, RawAbilityTiming? RawTiming = null, RawAbilityRangeInputs? RawRange = null, RawAbilityVariants? RawVariants = null);
internal sealed record CurrentBuildAbilityRecordsObservation(NativeProcessIdentity Identity, DateTimeOffset StartedAtUtc, DateTimeOffset CompletedAtUtc, ushort Selector, uint TlsIndex, ulong Collection, IReadOnlyList<AbilityRecordCandidate> Records)
{
    public string Qualification => "candidate-only; membership, freshness and restart unverified";
    public string Source => "native-process-memory";
}
internal static class CurrentBuildAbilityRecordsCandidateReader
{
    internal static CurrentBuildAbilityRecordsObservation Read(IReadOnlyNativeMemorySession session, IReadOnlyList<uint> keys, bool includeRawCosts = false, bool includeRawTiming = false, bool includeRawRange = false, bool includeRawVariants = false) =>
        Read(session, keys, () => WindowsThreadTlsSnapshot.Capture(session.Identity.ProcessId), includeRawCosts, includeRawTiming, includeRawRange, includeRawVariants);
    internal static CurrentBuildAbilityRecordsObservation Read(IReadOnlyNativeMemorySession session, IReadOnlyList<uint> keys, Func<IReadOnlyList<NativeThreadEpoch>> threads, bool includeRawCosts = false, bool includeRawTiming = false, bool includeRawRange = false, bool includeRawVariants = false)
    {
        var started = DateTimeOffset.UtcNow; var id = session.Identity;
        if (id.ProcessId <= 0 || id.ProcessStartUtcTicks <= 0 || id.ModuleSize < (includeRawCosts ? 0x35A8338UL : includeRawVariants ? 0x359F398UL : includeRawTiming ? 0x34E28B8UL : 0x344A6B8UL) ||
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
        RawCostVector Costs(ulong record)
        {
            var vector = ReadBytes(record + 0x6D0, 16); var begin = U64(vector); var end = U64(vector.AsSpan(8));
            if (begin == 0 && end == 0) return new("empty", 0, 0, []);
            if (begin == 0 || end < begin || (end - begin) % 8 != 0 || (end - begin) / 8 > 64) throw new InvalidDataException("Invalid raw cost vector.");
            Ptr(begin, end == begin ? 8 : checked((int)(end - begin)));
            var children = new List<RawCostChild>();
            for (var slot = begin; slot < end; slot += 8)
            {
                var address = Q(slot); if (address == 0) { children.Add(new("null", 0)); continue; }
                Ptr(address, 0x20); var vt = Q(address); ulong? getter = null;
                if (vt >= id.ModuleBaseAddress && vt <= id.ModuleBaseAddress + id.ModuleSize - 0x48)
                { var target = Q(vt + 0x40); if (target >= id.ModuleBaseAddress && target < id.ModuleBaseAddress + id.ModuleSize) getter = target - id.ModuleBaseAddress; }
                var profile = vt == id.ModuleBaseAddress + 0x29EE1F8 ? ("power", 0x29EE1F8UL, 0x1BB6C50UL, 0x34B5890UL, 0x2A05470UL, 0x1BED8F0UL) :
                    vt == id.ModuleBaseAddress + 0x29DFB00 ? ("mana", 0x29DFB00UL, 0x1B86480UL, 0x34AD5C0UL, 0x29E9220UL, 0x1BAD860UL) :
                    vt == id.ModuleBaseAddress + 0x2800660 ? ("energy", 0x2800660UL, 0x171A0B0UL, 0x3416390UL, 0x2801400UL, 0x1735BE0UL) :
                    vt == id.ModuleBaseAddress + 0x29F7628 ? ("mana-charge", 0x29F7628UL, 0x1BBF8B0UL, 0x34B4B20UL, 0x2A04450UL, 0x1BED910UL) :
                    vt == id.ModuleBaseAddress + 0x2CEF3D8 ? ("unhandled-1e2d", 0x2CEF3D8UL, 0x22CCCF0UL, 0x35A8330UL, 0x2D060C0UL, 0x2303720UL) : default;
                if (profile.Item1 is null) { children.Add(new("unknown-type", address, vt, getter)); continue; }
                if (!Fingerprint(address, profile.Item2, profile.Item3, profile.Item4, profile.Item5, profile.Item6)) { children.Add(new("unverified-type", address, vt, getter)); continue; }
                if (profile.Item1 == "unhandled-1e2d") { children.Add(new("typed-unhandled-1e2d", address, vt, getter)); continue; }
                var raw = ReadBytes(address + 0x18, profile.Item1 == "mana-charge" ? 17 : 8); var a = BinaryPrimitives.ReadInt32LittleEndian(raw); var b = BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(4));
                var fa = BitConverter.Int32BitsToSingle(a); var fb = BitConverter.Int32BitsToSingle(b);
                var c = raw.Length == 17 ? BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(8)) : (int?)null;
                var fc = c.HasValue ? BitConverter.Int32BitsToSingle(c.Value) : (float?)null;
                children.Add(new(profile.Item1 + "-raw-candidate", address, vt, getter, Convert.ToHexString(raw).ToLowerInvariant(), a, b, float.IsFinite(fa) ? fa : null, float.IsFinite(fb) ? fb : null, raw[4], c, fc.HasValue && float.IsFinite(fc.Value) ? fc : null, raw.Length == 17 ? BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(12)) : null, raw.Length == 17 ? raw[16] : null));
            }
            return new(children.Count == 0 ? "empty" : "raw-candidates", begin, end, children);
        }
        RawTimingVector TimingVector(ulong headerAddress)
        {
            var raw = ReadBytes(headerAddress, 16); var begin = U64(raw); var end = U64(raw.AsSpan(8));
            if (begin == 0 && end == 0) return new("empty", 0, 0, 0);
            if (begin == 0 || end < begin || (end - begin) % 8 != 0 || (end - begin) / 8 > 64) throw new InvalidDataException("Invalid timing vector.");
            Ptr(begin, end == begin ? 8 : checked((int)(end - begin))); var count = (end - begin) / 8;
            if (count == 0) return new("empty", begin, end, count);
            if (count != 1) return new("not-single", begin, end, count);
            var child = Q(begin); if (child == 0) return new("null-child", begin, end, count, 0);
            Ptr(child, 0x24); var vt = Q(child); ulong? getter = null;
            if (vt >= id.ModuleBaseAddress && vt <= id.ModuleBaseAddress + id.ModuleSize - 0x48) { var target = Q(vt + 0x40); if (target >= id.ModuleBaseAddress && target < id.ModuleBaseAddress + id.ModuleSize) getter = target - id.ModuleBaseAddress; }
            var profile = vt == id.ModuleBaseAddress + 0x28940E0 ? ("type-0650", 0x28940E0UL, 0x188FAC0UL, 0x3448E50UL, 0x28A7EF8UL, 0x18C0680UL) :
                vt == id.ModuleBaseAddress + 0x2A8C218 ? ("type-0678", 0x2A8C218UL, 0x1D0E500UL, 0x34E28B0UL, 0x2A9CD68UL, 0x1D44970UL) :
                vt == id.ModuleBaseAddress + 0x2A40918 ? ("typed-0759-fixed-input", 0x2A40918UL, 0x1C4C940UL, 0x34C8FE0UL, 0x2A4AF80UL, 0x1C83A10UL) :
                vt == id.ModuleBaseAddress + 0x294B498 ? ("typed-0648-zero-path", 0x294B498UL, 0x1A3DE20UL, 0x3485090UL, 0x2964410UL, 0x1A77380UL) : default;
            if (profile.Item1 is null) return new("unknown-type", begin, end, count, child, vt, getter);
            if (!Fingerprint(child, profile.Item2, profile.Item3, profile.Item4, profile.Item5, profile.Item6)) return new("unverified-type", begin, end, count, child, vt, getter);
            if (profile.Item1.StartsWith("typed-", StringComparison.Ordinal)) return new(profile.Item1, begin, end, count, child, vt, getter);
            return new(profile.Item1 + "-raw-candidate", begin, end, count, child, vt, getter, BinaryPrimitives.ReadInt32LittleEndian(ReadBytes(child + 0x20, 4)));
        }
        RawAbilityTiming Timing(ulong record) => new(BinaryPrimitives.ReadInt32LittleEndian(ReadBytes(record + 0x88, 4)), BinaryPrimitives.ReadInt32LittleEndian(ReadBytes(record + 0x94, 4)), TimingVector(record + 0x5F0), TimingVector(record + 0x8E8));
        RawAbilityRangeInputs Range(ulong record)
        {
            var minRaw = ReadBytes(record + 0xB4, 4); var maxRaw = ReadBytes(record + 0x9C, 4);
            var min = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(minRaw));
            var max = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(maxRaw));
            var vector = ReadBytes(record + 0x740, 16); var begin = U64(vector); var end = U64(vector.AsSpan(8));
            if ((begin == 0) != (end == 0) || end < begin || (end - begin) % 4 != 0 || (end - begin) / 4 > 64 || (begin != 0 && (begin < 0x10000 || begin % 4 != 0 || end > 0x7FFFFFFFFFFFUL))) throw new InvalidDataException("Invalid condition vector.");
            var values = new List<uint>();
            for (var address = begin; address < end; address += 4) values.Add(BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(address, 4)));
            return new(Convert.ToHexString(minRaw).ToLowerInvariant(), float.IsFinite(min) ? min : null, Convert.ToHexString(maxRaw).ToLowerInvariant(), float.IsFinite(max) ? max : null, begin, end, values, values.Contains(1U));
        }
        RawAbilityVariants Variants(ulong record)
        {
            var h=ReadBytes(record+0x5F0,16);var begin=U64(h);var end=U64(h.AsSpan(8));
            if(begin==0&&end==0)return new("primary-empty");
            if(begin==0||end<begin||(end-begin)%8!=0||(end-begin)/8>64)throw new InvalidDataException("Invalid primary vector.");
            Ptr(begin,end==begin?8:checked((int)(end-begin)));
            if(end==begin)return new("primary-empty");
            var source=Q(begin);if(source==0)return new("primary-null");Ptr(source,0x28);
            if(!Fingerprint(source,0x283E6C0,0x17BD530,0x342C310,0x2845BD0,0x17DBA60))return new("primary-unverified-type",source);
            var vh=ReadBytes(source+0x18,16);var vb=U64(vh);var ve=U64(vh.AsSpan(8));
            if(vb==0&&ve==0)return new("empty",source,[]);
            if(vb==0||ve<vb||(ve-vb)%8!=0||(ve-vb)/8>64)throw new InvalidDataException("Invalid variant vector.");
            Ptr(vb,ve==vb?8:checked((int)(ve-vb)));
            var entries=new List<RawVariantChild>();
            for(var slot=vb;slot<ve;slot+=8)
            {
                var child=Q(slot);if(child==0){entries.Add(new("null",0));continue;}Ptr(child,0x1C);var vt=Q(child);ulong? getter=null;
                if(vt>=id.ModuleBaseAddress&&vt<=id.ModuleBaseAddress+id.ModuleSize-0x48){var target=Q(vt+0x40);if(target>=id.ModuleBaseAddress&&target<id.ModuleBaseAddress+id.ModuleSize)getter=target-id.ModuleBaseAddress;}
                if(vt!=id.ModuleBaseAddress+0x2CDE8F0){entries.Add(new("unknown-type",child,vt,getter));continue;}
                if(!Fingerprint(child,0x2CDE8F0,0x229B4B0,0x359F390,0x2CE8820,0x22C1850)){entries.Add(new("unverified-type",child,vt,getter));continue;}
                entries.Add(new("type-0061-raw-candidate",child,vt,getter,BinaryPrimitives.ReadUInt32LittleEndian(ReadBytes(child+0x18,4))));
            }
            return new(entries.Count==0?"empty":"raw-candidates",source,entries);
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
            rows.Add(new(key, "type-verified-candidate", record, flag, child, second, full, includeRawCosts ? Costs(record) : null, includeRawTiming ? Timing(record) : null, includeRawRange ? Range(record) : null, includeRawVariants ? Variants(record) : null));
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
